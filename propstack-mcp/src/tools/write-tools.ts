import { z } from "zod";
import type { Props } from "../auth/session";
import { type GroupEntity, PropstackClient, PropstackError } from "../propstack-client";
import {
	type ContactSearchResults,
	contactDuplicates,
	type DedupeResult,
	isMobile,
	objectDuplicates,
} from "../propstack/dedupe";
import { ACTIVE_STATUSES } from "../config";
import { PUBLIC_PRICE_HINT, type CustomOption, loadFieldDefs, mirroredCustomFields, validateCustomFields } from "../propstack/field-rules";
import { scalar } from "../propstack/mappers";
import { readUnit, UNVERIFIABLE, type UnitState, unitCustomValue, unitValue } from "../propstack/unit-state";
import { CRM_BASE, createReviewTask } from "../review-task";
import { beginWrite, finishWrite } from "../write-log";
import { loadAll, type ToolOutput } from "./read-tools";

export { validateCustomFields };

// Schreib-Tools (Phase 3). Grundsätze:
// - Betreuer ist immer der angemeldete Nutzer (Spezifikation).
// - Dublettenprüfung vor jedem Anlegen; Override nur mit Begründung, nie bei gleicher E-Mail
//   (Propstack führt Kontakte über die E-Mail zusammen → würde den vorhandenen überschreiben).
// - Write-Log mit Snapshot VOR dem Write (fail-closed).
// - Nach dem Write zurücklesen: Propstack verwirft unbekannte Felder ohne Fehler.
// - Keine Lösch-Tools.

type Raw = Record<string, unknown>;

export const TEST_TAG = "MCP-TEST";
const MIN_OVERRIDE_REASON = 15;

export interface WriteDeps {
	client: PropstackClient;
	db: D1Database | undefined;
	user: Props;
	now?: () => Date;
	sleep?: (ms: number) => Promise<void>;
	kv?: KVNamespace;
}

const optionalText = (max: number) => z.string().trim().min(1).max(max).optional();
const id = z.number().int().positive();
const tagIds = z.array(id).min(1).max(20);

// ---------- Hilfen ----------

function today(now: Date): string {
	return now.toISOString().slice(0, 10);
}

function originNote(user: Props, now: Date, verb: "Angelegt" | "Ergänzt"): string {
	return `${verb} über Claude (Propstack MCP) von ${user.name} am ${today(now)}.`;
}

/** Test-Merkmal suchen, bei Bedarf anlegen (Entscheidung Florian). */
export async function ensureTestTag(client: PropstackClient, entity: GroupEntity): Promise<number> {
	const find = async () =>
		(await client.listGroups(entity)).rows.find((g) => String(scalar(g.name)).trim().toUpperCase() === TEST_TAG)?.id as
			| number
			| undefined;
	const existing = await find();
	if (existing) return existing;
	await client.createGroup(entity, TEST_TAG);
	const created = await find();
	if (!created) throw new PropstackError(`Merkmal ${TEST_TAG} konnte nicht angelegt werden – Testdatensatz wird nicht gespeichert.`, 0);
	return created;
}

function isOption(value: unknown): value is CustomOption {
	return !!value && typeof value === "object" && !Array.isArray(value) && typeof (value as Raw).id === "number" && "name" in (value as Raw);
}

function norm(value: unknown): string {
	return String(value ?? "").replace(/\s+/g, " ").trim().toLowerCase();
}

/** Alle Lesarten eines Propstack-Werts als Text (value, pretty_value, label, Listen, {id,name}). */
function readings(value: unknown): string[] {
	if (Array.isArray(value)) return value.flatMap(readings);
	if (value && typeof value === "object") {
		const obj = value as Raw;
		return [obj.value, obj.pretty_value, obj.id, obj.name].filter((v) => v !== undefined && v !== null).flatMap(readings);
	}
	if (value === null || value === undefined) return [];
	const text = norm(value);
	return text.includes(",") ? [text, ...text.split(/,\s*/)] : [text];
}

function isEmpty(value: unknown): boolean {
	if (value === null || value === undefined || value === "") return true;
	if (Array.isArray(value)) return value.length === 0;
	if (typeof value === "object") {
		const obj = value as Raw;
		if ("value" in obj) return isEmpty(obj.value);
	}
	return false;
}

function same(requested: unknown, actual: unknown): boolean {
	if (requested === null) return isEmpty(actual);
	if (isOption(requested)) {
		const have = readings(actual);
		return have.includes(String(requested.id)) || have.includes(norm(requested.name));
	}
	if (Array.isArray(requested)) {
		const have = readings(actual);
		return requested.every((r) => (isOption(r) ? have.includes(String(r.id)) || have.includes(norm(r.name)) : have.includes(norm(r))));
	}
	const candidates =
		actual && typeof actual === "object" && !Array.isArray(actual)
			? [(actual as Raw).value, (actual as Raw).pretty_value]
			: [actual];
	return candidates.some((candidate) => {
		if (typeof requested === "number") return candidate !== null && candidate !== "" && Number(candidate) === requested;
		if (typeof requested === "boolean") return candidate === requested || String(candidate) === String(requested);
		// Groß-/Kleinschreibung zählt (Korrektur „mueller“ → „Müller“ muss geschrieben werden)
		const squash = (v: unknown) => String(v ?? "").replace(/\s+/g, " ").trim();
		return squash(candidate) === squash(requested);
	});
}

/** Nach dem Write: welche angefragten Felder hat Propstack NICHT übernommen? */
export function notApplied(requested: Raw, actual: Raw, custom?: Raw): string[] {
	const missing: string[] = [];
	for (const [key, value] of Object.entries(requested)) {
		if (!same(value, actual[key])) missing.push(key);
	}
	const actualCustom = (actual.custom_fields ?? {}) as Raw;
	for (const [key, value] of Object.entries(custom ?? {})) {
		if (!same(value, actualCustom[key])) missing.push(`custom_fields.${key}`);
	}
	return missing;
}

function groupIdsOf(raw: Raw): number[] {
	const groups = raw.groups ?? raw.property_groups ?? raw.group_ids;
	return (Array.isArray(groups) ? groups : [])
		.map((g) => (g && typeof g === "object" ? (g as Raw).id : g))
		.filter((g): g is number => typeof g === "number");
}

function blockedResult(dedupe: DedupeResult, hint: string): ToolOutput {
	return {
		count: 0,
		result: {
			created: false,
			blocked: "Dublette",
			duplicates: dedupe.duplicates,
			warnings: dedupe.warnings.length ? dedupe.warnings : undefined,
			hint,
		},
	};
}

function checkOverride(dedupe: DedupeResult, reason: string | undefined): string | null {
	if (!dedupe.duplicates.length) return null;
	if (!reason) return null;
	if (reason.trim().length < MIN_OVERRIDE_REASON) {
		throw new PropstackError(`allow_duplicate_reason braucht eine echte Begründung (mind. ${MIN_OVERRIDE_REASON} Zeichen).`, 400);
	}
	return reason.trim();
}

async function asObjectOrThrow(promise: Promise<unknown>): Promise<Raw> {
	const value = await promise;
	if (!value || typeof value !== "object" || Array.isArray(value)) throw new PropstackError("Unerwartete Antwort von Propstack", 0);
	return value as Raw;
}

function createdId(response: unknown): number {
	const raw = (response ?? {}) as Raw;
	const value = raw.id ?? (raw.data as Raw | undefined)?.id;
	if (typeof value !== "number") {
		throw new PropstackError("Propstack hat keine ID zurückgegeben – Status unklar, bitte in Propstack prüfen.", 0);
	}
	return value;
}

// ---------- Kontakte ----------

const contactFieldsShape = {
	salutation: z.enum(["mr", "ms"]).optional().describe("mr = Herr, ms = Frau"),
	academic_title: optionalText(30),
	first_name: optionalText(100),
	last_name: optionalText(100),
	company: optionalText(200).describe("Firmenname (als Text am Kontakt)"),
	position: optionalText(200),
	email: z.string().trim().toLowerCase().email().max(200).optional(),
	phone_office: optionalText(50).describe("Festnetz geschäftlich"),
	mobile: optionalText(50).describe("Mobilnummer"),
	street: optionalText(200),
	house_number: optionalText(20),
	zip_code: optionalText(10),
	city: optionalText(100),
	country: optionalText(60),
	source_id: id.optional().describe("Kontakt-Quelle (über list_reference kind=contact_sources)"),
	custom_fields: z.record(z.string(), z.unknown()).optional().describe("Custom-Felder {schlüssel: wert}, Schlüssel über list_fields"),
};

const CONTACT_KEYS: Record<string, string> = {
	academic_title: "academic_title",
	city: "office_city",
	company: "company",
	country: "office_country",
	email: "email",
	first_name: "first_name",
	house_number: "office_house_number",
	last_name: "last_name",
	mobile: "office_cell",
	phone_office: "office_phone",
	position: "position",
	salutation: "salutation",
	source_id: "client_source_id",
	street: "office_street",
	zip_code: "office_zip_code",
};

function contactPayload(input: Raw): Raw {
	const out: Raw = {};
	for (const [from, to] of Object.entries(CONTACT_KEYS)) if (input[from] !== undefined) out[to] = input[from];
	return out;
}

async function contactSearches(client: PropstackClient, input: Raw): Promise<ContactSearchResults> {
	const search = async (query: Record<string, string | number>) =>
		(await client.searchContacts({ ...query, archived: "-1", page: 1, per: 50 })).rows;
	const name = [input.first_name, input.last_name].filter(Boolean).join(" ");
	return {
		byEmail: input.email ? await search({ email: String(input.email) }) : [],
		byMobile: input.mobile ? await search({ phone_number: String(input.mobile) }) : [],
		byName: name ? await search({ q: name }) : [],
		byPhone: input.phone_office ? await search({ phone_number: String(input.phone_office) }) : [],
	};
}

export const createContactInput = {
	...contactFieldsShape,
	last_name: z.string().trim().min(1).max(100).describe("Nachname (Pflicht)"),
	description: optionalText(2000).describe("Notiz"),
	tag_ids: tagIds.optional().describe("Merkmal-IDs (über list_tags)"),
	test: z.boolean().optional().describe(`Testdatensatz: setzt das Merkmal ${TEST_TAG}. Für alle Tests Pflicht.`),
	allow_duplicate_reason: optionalText(500).describe(
		"Nur wenn die Dublettenprüfung blockiert und es nachweislich eine andere Person ist: Begründung (wird protokolliert). Wirkt nicht bei gleicher E-Mail.",
	),
};

export async function createContact(deps: WriteDeps, input: z.infer<z.ZodObject<typeof createContactInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	const now = deps.now?.() ?? new Date();
	if (input.mobile && !isMobile(input.mobile)) {
		throw new PropstackError(`${input.mobile} ist keine deutsche Mobilnummer (015x/016x/017x) – bitte als phone_office angeben.`, 400);
	}

	const candidate = {
		company: input.company,
		email: input.email,
		first_name: input.first_name,
		last_name: input.last_name,
		mobile: input.mobile,
		phone: input.phone_office,
	};
	const dedupe = contactDuplicates(candidate, await contactSearches(client, input));
	const emailDuplicate = dedupe.duplicates.some((d) => d.reason.startsWith("gleiche E-Mail"));
	if (dedupe.duplicates.length && (emailDuplicate || !input.allow_duplicate_reason)) {
		return blockedResult(
			dedupe,
			emailDuplicate
				? "Propstack führt Kontakte über die E-Mail zusammen – ein zweiter Kontakt mit dieser E-Mail ist nicht möglich. Bitte den vorhandenen Kontakt mit update_contact ergänzen."
				: "Nichts angelegt. Vorhandenen Kontakt mit update_contact ergänzen – oder, falls es nachweislich eine andere Person ist, mit allow_duplicate_reason erneut aufrufen.",
		);
	}
	const overrideReason = checkOverride(dedupe, input.allow_duplicate_reason);

	const custom = await validateCustomFields(client, "for_clients", input.custom_fields);
	const tags = [...(input.tag_ids ?? [])];
	if (input.test) tags.push(await ensureTestTag(client, "for_clients"));

	const fields = contactPayload(input);
	const payload: Raw = {
		...fields,
		broker_id: user.brokerId,
		description: [input.description, originNote(user, now, "Angelegt")].filter(Boolean).join("\n\n"),
		...(tags.length ? { group_ids: tags } : {}),
		...(custom ? { partial_custom_fields: custom.send } : {}),
	};

	const logId = await beginWrite(deps.db, {
		action: "create",
		before: null,
		brokerId: user.brokerId,
		entity: "contact",
		entityId: null,
		overrideReason,
		request: payload,
		tool: "create_contact",
		userEmail: user.email,
		warnings: dedupe.warnings,
	});

	let newId: number;
	try {
		newId = createdId(await client.createContact(payload));
	} catch (error) {
		await finishWrite(deps.db, logId, { error: (error as Error).message, status: "failed" });
		throw error;
	}

	const actual = await asObjectOrThrow(client.getContact(newId));
	const missing = notApplied({ ...fields, broker_id: user.brokerId }, actual, custom?.expect);
	const groups = groupIdsOf(actual);
	for (const tag of tags) if (!groups.includes(tag)) missing.push(`tag ${tag}`);
	await finishWrite(deps.db, logId, { entityId: newId, notApplied: missing, status: missing.length ? "done_with_gaps" : "done" });

	return {
		count: 1,
		result: {
			created: true,
			id: newId,
			name: scalar(actual.name),
			broker: user.name,
			test: input.test || undefined,
			override_reason: overrideReason ?? undefined,
			warnings: dedupe.warnings.length ? dedupe.warnings : undefined,
			not_applied: missing.length ? missing : undefined,
			note: missing.length ? "Propstack hat einige Felder nicht übernommen – bitte prüfen." : undefined,
		},
	};
}

export const updateContactInput = {
	id: id.describe("Propstack-Kontakt-ID"),
	...contactFieldsShape,
	add_tag_ids: tagIds.optional().describe("Merkmale hinzufügen"),
	remove_tag_ids: tagIds.optional().describe("Merkmale entfernen"),
	note_append: optionalText(2000).describe("Text an die Notiz anhängen (mit Datum und Nutzer); vorhandene Notiz bleibt erhalten"),
	allow_duplicate_reason: optionalText(500).describe("Nur falls die neue E-Mail/Mobilnummer schon bei einem anderen Kontakt steht: Begründung"),
};

export async function updateContact(deps: WriteDeps, input: z.infer<z.ZodObject<typeof updateContactInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	const now = deps.now?.() ?? new Date();
	if (input.mobile && !isMobile(input.mobile)) {
		throw new PropstackError(`${input.mobile} ist keine deutsche Mobilnummer – bitte als phone_office angeben.`, 400);
	}
	const current = await asObjectOrThrow(client.getContact(input.id));

	// Nur echte Änderungen schreiben
	const requested = contactPayload(input);
	const fields: Raw = {};
	const before: Raw = {};
	for (const [key, value] of Object.entries(requested)) {
		if (same(value, current[key])) continue;
		fields[key] = value;
		before[key] = scalar(current[key]) ?? null;
	}

	// Neue E-Mail / Mobilnummer darf nicht einem anderen Kontakt gehören
	const identity: Raw = {};
	if (fields.email) identity.email = fields.email;
	if (fields.office_cell) identity.mobile = fields.office_cell;
	const dedupe = Object.keys(identity).length
		? contactDuplicates(identity, await contactSearches(client, identity), input.id)
		: { duplicates: [], warnings: [] };
	if (dedupe.duplicates.length && !input.allow_duplicate_reason) {
		return blockedResult(dedupe, "Nichts geändert. Die neue E-Mail bzw. Mobilnummer gehört bereits einem anderen Kontakt.");
	}
	const overrideReason = checkOverride(dedupe, input.allow_duplicate_reason);

	const currentTags = groupIdsOf(current);
	const addTags = (input.add_tag_ids ?? []).filter((t) => !currentTags.includes(t));
	const removeTags = (input.remove_tag_ids ?? []).filter((t) => currentTags.includes(t));
	const custom = await validateCustomFields(client, "for_clients", input.custom_fields);

	const payload: Raw = { ...fields };
	if (addTags.length) payload.add_group_ids = addTags;
	if (removeTags.length) payload.sub_group_ids = removeTags;
	if (custom) payload.partial_custom_fields = custom.send;
	if (input.note_append) {
		const old = String(scalar(current.description) ?? "");
		before.description = old;
		payload.description = [old, `${originNote(user, now, "Ergänzt")}\n${input.note_append}`].filter(Boolean).join("\n\n");
	}
	if (addTags.length || removeTags.length) before.tag_ids = currentTags;
	if (custom) before.custom_fields = Object.fromEntries(Object.keys(custom.send).map((k) => [k, scalar((current.custom_fields as Raw | undefined)?.[k]) ?? null]));

	if (!Object.keys(payload).length) {
		return { count: 0, result: { updated: false, id: input.id, note: "Keine Änderung – alle Werte sind bereits so gesetzt." } };
	}

	const logId = await beginWrite(deps.db, {
		action: "update",
		before,
		brokerId: user.brokerId,
		entity: "contact",
		entityId: input.id,
		overrideReason,
		request: payload,
		tool: "update_contact",
		userEmail: user.email,
		warnings: dedupe.warnings,
	});
	try {
		await client.updateContact(input.id, payload);
	} catch (error) {
		await finishWrite(deps.db, logId, { error: (error as Error).message, status: "failed" });
		throw error;
	}

	const actual = await asObjectOrThrow(client.getContact(input.id));
	const missing = notApplied(fields, actual, custom?.expect);
	const groups = groupIdsOf(actual);
	for (const t of addTags) if (!groups.includes(t)) missing.push(`add_tag ${t}`);
	for (const t of removeTags) if (groups.includes(t)) missing.push(`remove_tag ${t}`);
	await finishWrite(deps.db, logId, { notApplied: missing, status: missing.length ? "done_with_gaps" : "done" });

	return {
		count: 1,
		result: {
			updated: true,
			id: input.id,
			name: scalar(actual.name),
			changed: [...Object.keys(fields), ...(addTags.length ? ["add_tags"] : []), ...(removeTags.length ? ["remove_tags"] : []), ...(input.note_append ? ["note"] : []), ...Object.keys(custom?.send ?? {}).map((k) => `custom_fields.${k}`)],
			warnings: dedupe.warnings.length ? dedupe.warnings : undefined,
			not_applied: missing.length ? missing : undefined,
		},
	};
}

// ---------- Objekte ----------
// Regeln aus dem Notion-Feld-Mapping (Korrekturen) und dem Skill propstack-expose-workflow:
// - Einige Felder verwirft Propstack im POST und in Multi-Feld-PUTs still → einzeln per PUT.
// - object_type leitet Propstack aus rs_type ab → nicht anbieten.
// - Öffentliche Preise (price, base_rent, mietpreis_*) nur mit public_price_confirmed (Nutzer hat es
//   ausdrücklich angesagt bzw. auf Nachfrage bestätigt); interne Preise (intern_*) immer. Sonst price_on_inquiry.
// - Interne Notizen in das Custom-Feld bemerkung; Beschreibungstexte sind exposé-sichtbar.
// - lat/lng haften unzuverlässig → nur für die Dublettenprüfung, nicht schreiben.

/** Werden im POST und in PUTs mit mehreren Feldern still verworfen → je Feld ein PUT. */
export const SOLO_OBJECT_FIELDS = [
	"rs_category",
	"total_floor_space",
	"industrial_area",
	"hall_height",
	"floor_load",
	"broker_id",
	"rented",
	"property_status_id",
] as const;

const num = z.number().nonnegative().optional();
/** Flächen nie 0 m² (Team-Regel). */
const area = z.number().positive().optional();
const EXPOSE_VISIBLE = "EXPOSÉ-SICHTBAR: keine Konditionen, Eigentümer, Kundennamen oder offenen Punkte – die gehören in bemerkung_append";

const objectFieldsShape = {
	title: optionalText(250).describe("Überschrift, Format: Logistikhalle in (XX) Ort"),
	marketing_type: z.enum(["BUY", "RENT"]).optional().describe("BUY = Kauf, RENT = Miete"),
	rs_type: z.string().regex(/^[A-Z_]+$/).optional().describe("Objektart, z. B. INDUSTRY, OFFICE. Die Objektkategorie (object_type) leitet Propstack daraus ab"),
	rs_category: z.string().regex(/^[A-Z_]+$/).optional().describe("Unterart, z. B. HALL, WAREHOUSE"),
	unit_id: optionalText(50).describe("Einheitennummer – in ganz Propstack eindeutig. Bei Einzelobjekten ohne Projekt weglassen"),
	street: optionalText(200),
	house_number: optionalText(20),
	zip_code: optionalText(10),
	city: optionalText(100),
	project_id: id.optional(),
	status_id: id
		.optional()
		.describe("Objekt-Status (list_reference kind=object_statuses): 163672 Akquise, 163673 Vorbereitung, 163674 Vermarktung, 163675 Reserviert, 163676 Abgeschlossen. Einen Status „vermietet“ gibt es nicht – dafür rented"),
	price: num.describe("Öffentlicher Kaufpreis (nur BUY) – NUR mit public_price_confirmed. Ohne Ansage: weglassen, Objekt bekommt „Preis auf Anfrage“"),
	base_rent: num.describe("Öffentliche Kaltmiete (nur RENT) – NUR mit public_price_confirmed. Interne Mietpreise immer in custom_fields intern_mietpreis_*"),
	public_price_confirmed: z
		.literal(true)
		.optional()
		.describe("Nur setzen, wenn der Nutzer einen ÖFFENTLICHEN Preis ausdrücklich angesagt oder auf Nachfrage bestätigt hat. Sonst vorher fragen. Wird protokolliert"),
	price_on_inquiry: z.boolean().optional().describe("Preis auf Anfrage. Beim Anlegen automatisch true, außer ein öffentlicher Preis wird gesetzt"),
	industrial_area: area.describe("Hallenfläche m²"),
	total_floor_space: area.describe("Gesamtfläche m² = Halle + Mezzanine, OHNE Büro (Regel seit 13.08.2026)"),
	usable_floor_space: area.describe("Nutzfläche m² (bei Hallen: Bürofläche)"),
	plot_area: area.describe("Grundstücksfläche m²"),
	hall_height: num.describe("Hallenhöhe in m UKB"),
	floor_load: num.describe("Bodentragkraft in kg/m² – Propstack hängt kg/m² selbst an (5 t/m² = 5000)"),
	construction_year: z.number().int().min(1800).max(2100).optional(),
	free_from: optionalText(100).describe("Verfügbar ab (Text), z. B. „auf Anfrage“ oder „01.03.2027“"),
	hide_address: z.boolean().optional().describe("Adresse im Exposé ausblenden"),
	rented: z
		.boolean()
		.optional()
		.describe(
			"Vermietet ja/nein. true setzt automatisch free_from „vermietet“, status_logistik/aktiv Inaktiv und die verfügbaren Flächen auf „X m² (vermietet)“. Den Status (163676 Abgeschlossen) separat über status_id setzen",
		),
	courtage: optionalText(200).describe("Provisionstext fürs Exposé – nur der Provisionstext, keine Arbeitsvermerke"),
	courtage_note: optionalText(2000).describe("Provisionshinweis, z. B. die Staffel"),
	description_note: optionalText(10000).describe(`Objektbeschreibung. ${EXPOSE_VISIBLE}`),
	location_note: optionalText(10000).describe(`Lagebeschreibung. ${EXPOSE_VISIBLE}`),
	furnishing_note: optionalText(10000).describe(`Ausstattung. ${EXPOSE_VISIBLE}`),
	other_note: optionalText(10000).describe(`Sonstiges. ${EXPOSE_VISIBLE}`),
	bemerkung_append: optionalText(4000).describe("Interne Bemerkung (Custom-Feld bemerkung, nicht im Exposé) – wird mit Datum und Nutzer angehängt"),
	lat: z.number().min(-90).max(90).optional().describe("Nur für die Dublettenprüfung – wird nicht gespeichert"),
	lng: z.number().min(-180).max(180).optional().describe("Nur für die Dublettenprüfung – wird nicht gespeichert"),
	custom_fields: z
		.record(z.string(), z.unknown())
		.optional()
		.describe(
			"Custom-Felder {schlüssel: wert}, Schlüssel über list_fields entity=objects. Zahlen als nackte Zahl mit Dezimalpunkt (10.5, nie \"10,5\" oder \"6.417 m²\"), Auswahlfelder per Name oder Option-ID, null leert. Gesperrt: provisionspflichtig, mezzanineflache, bemerkung. mietpreis_* sind öffentlich → nur mit public_price_confirmed",
		),
};

const OBJECT_KEYS = [
	"title", "marketing_type", "rs_type", "rs_category", "unit_id", "street", "house_number", "zip_code", "city", "project_id",
	"price", "base_rent", "price_on_inquiry", "industrial_area", "total_floor_space", "usable_floor_space", "plot_area", "hall_height", "floor_load",
	"construction_year", "free_from", "hide_address", "rented", "courtage", "courtage_note",
	"description_note", "location_note", "furnishing_note", "other_note",
] as const;

function objectPayload(input: Raw): Raw {
	const out: Raw = {};
	for (const key of OBJECT_KEYS) if (input[key] !== undefined) out[key] = input[key];
	if (input.status_id !== undefined) out.property_status_id = input.status_id;
	return out;
}

const fieldLabel = (key: string) => (key === "property_status_id" ? "status_id" : key);

function splitSolo(fields: Raw): { bulk: Raw; solo: [string, unknown][] } {
	const bulk: Raw = {};
	const solo: [string, unknown][] = [];
	for (const [key, value] of Object.entries(fields)) {
		if ((SOLO_OBJECT_FIELDS as readonly string[]).includes(key)) solo.push([key, value]);
		else bulk[key] = value;
	}
	return { bulk, solo };
}

/** Einzel-PUTs; ein Fehler bricht die übrigen nicht ab (das Objekt existiert bereits). */
async function writeSolo(client: PropstackClient, unitId: number, solo: [string, unknown][]): Promise<string[]> {
	const errors: string[] = [];
	for (const [key, value] of solo) {
		try {
			await client.updateUnit(unitId, { [key]: value });
		} catch (error) {
			errors.push(`${fieldLabel(key)}: ${(error as Error).message}`);
		}
	}
	return errors;
}

function sameUnitValue(key: string, requested: unknown, actual: unknown): boolean {
	if (key === "property_status_id" || key === "broker_id") return actual !== null && actual !== undefined && Number(actual) === requested;
	return same(requested, actual);
}

function verifyObject(state: UnitState, fields: Raw, customExpect: Raw): { missing: string[]; unverified: string[] } {
	const missing: string[] = [];
	const unverified: string[] = [];
	for (const [key, value] of Object.entries(fields)) {
		const actual = unitValue(state, key);
		if (actual === UNVERIFIABLE) unverified.push(fieldLabel(key));
		else if (!sameUnitValue(key, value, actual)) missing.push(fieldLabel(key));
	}
	for (const [key, value] of Object.entries(customExpect)) {
		const actual = unitCustomValue(state, key);
		if (actual === UNVERIFIABLE) unverified.push(`custom_fields.${key}`);
		else if (!same(value, actual)) missing.push(`custom_fields.${key}`);
	}
	return { missing, unverified };
}

/** Öffentliche Preise nur mit ausdrücklicher Bestätigung; Kaufpreis nur BUY, Kaltmiete nur RENT. */
function checkPublicPrice(marketingType: unknown, fields: Raw, confirmed: boolean): boolean {
	const publishing = fields.price !== undefined || fields.base_rent !== undefined;
	if (!publishing) return false;
	if (!confirmed) throw new PropstackError(`price/base_rent sind öffentliche Preise. ${PUBLIC_PRICE_HINT}`, 400);
	if (fields.price !== undefined && marketingType !== "BUY") throw new PropstackError("price ist der Kaufpreis – nur bei BUY. Für Miete base_rent.", 400);
	if (fields.base_rent !== undefined && marketingType !== "RENT") throw new PropstackError("base_rent ist die Kaltmiete – nur bei RENT. Für Kauf price.", 400);
	return true;
}

function groupIdsOfUnit(state: UnitState): number[] {
	const fromDetail = groupIdsOf(state.detail);
	return fromDetail.length || !state.row ? fromDetail : groupIdsOf(state.row);
}

async function objectCandidates(client: PropstackClient, zip: string): Promise<Raw[]> {
	const loaded = await loadAll((q) => client.searchUnits(q), { archived: "-1", q: zip });
	if (!loaded.complete) throw new PropstackError(`Zu viele Objekte in PLZ ${zip} für die Dublettenprüfung.`, 400);
	return loaded.rows;
}

function gapNote(missing: string[], unverified: string[], writeErrors: string[]): string | undefined {
	const parts: string[] = [];
	if (writeErrors.length) parts.push("Einige Felder konnten nicht geschrieben werden (write_errors).");
	if (missing.length) parts.push("Propstack hat einige Felder nicht übernommen (not_applied) – bitte in Propstack prüfen.");
	if (unverified.length) parts.push("Einige Felder liefert Propstack nicht zurück und konnten deshalb nicht gegengeprüft werden (not_verifiable).");
	return parts.length ? parts.join(" ") : undefined;
}

export const createObjectInput = {
	...objectFieldsShape,
	title: z.string().trim().min(1).max(250).describe("Überschrift (Pflicht), Format: Logistikhalle in (XX) Ort"),
	marketing_type: z.enum(["BUY", "RENT"]).describe("BUY = Kauf, RENT = Miete (Pflicht)"),
	rs_type: z.string().regex(/^[A-Z_]+$/).describe("Objektart (Pflicht), z. B. INDUSTRY"),
	street: z.string().trim().min(1).max(200),
	zip_code: z.string().trim().regex(/^\d{4,5}$/),
	city: z.string().trim().min(1).max(100),
	test: z.boolean().optional().describe(`Testdatensatz: setzt das Merkmal ${TEST_TAG}. Für alle Tests Pflicht.`),
	allow_duplicate_reason: optionalText(500).describe("Nur wenn die Dublettenprüfung blockiert und es nachweislich ein anderes Objekt ist: Begründung (wird protokolliert)"),
};

export async function createObject(deps: WriteDeps, input: z.infer<z.ZodObject<typeof createObjectInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	const now = deps.now?.() ?? new Date();

	const fields = objectPayload(input);
	const publishing = checkPublicPrice(input.marketing_type, fields, input.public_price_confirmed === true);
	if (fields.price_on_inquiry === undefined) fields.price_on_inquiry = !publishing;
	fields.broker_id = user.brokerId;

	const dedupe = objectDuplicates(input, await objectCandidates(client, input.zip_code));
	if (dedupe.duplicates.length && !input.allow_duplicate_reason) {
		return blockedResult(
			dedupe,
			"Nichts angelegt. Vorhandenes Objekt mit update_object ändern – oder, falls es nachweislich ein anderes Objekt ist, mit allow_duplicate_reason erneut aufrufen.",
		);
	}
	const overrideReason = checkOverride(dedupe, input.allow_duplicate_reason);

	const defs = await loadFieldDefs(client, "for_properties");
	if (fields.rented === true && fields.free_from === undefined) fields.free_from = "vermietet";
	const mirrored = mirroredCustomFields(fields, defs, input.custom_fields, {
		flags: true,
		marketable: ACTIVE_STATUSES.includes(Number(fields.property_status_id)),
		priceOnInquiry: fields.price_on_inquiry === true,
		rent: fields.rented === true ? "rented" : "available",
	});
	// Testobjekte nie automatisch an Interessenten verschicken
	if (input.test && defs.get("kein_automatischer_exposeversand")?.type === "Boolean" && !(input.custom_fields && "kein_automatischer_exposeversand" in input.custom_fields)) {
		mirrored.kein_automatischer_exposeversand = true;
	}
	const custom = await validateCustomFields(client, "for_properties", { ...mirrored, ...input.custom_fields }, defs, {
		publicPriceConfirmed: input.public_price_confirmed === true,
	});
	const bemerkung = [originNote(user, now, "Angelegt"), input.bemerkung_append].filter(Boolean).join("\n");
	const customSend: Raw = { ...(custom?.send ?? {}), bemerkung };
	const customExpect: Raw = { ...(custom?.expect ?? {}), bemerkung };
	const tags = input.test ? [await ensureTestTag(client, "for_properties")] : [];

	const { bulk, solo } = splitSolo(fields);
	const payload: Raw = { ...bulk, ...(tags.length ? { group_ids: tags } : {}), partial_custom_fields: customSend };

	const logId = await beginWrite(deps.db, {
		action: "create",
		before: null,
		brokerId: user.brokerId,
		entity: "object",
		entityId: null,
		overrideReason,
		request: { ...payload, einzeln_nachgesetzt: Object.fromEntries(solo.map(([k, v]) => [fieldLabel(k), v])) },
		tool: "create_object",
		userEmail: user.email,
		warnings: dedupe.warnings,
	});
	let newId: number;
	try {
		newId = createdId(await client.createUnit(payload));
	} catch (error) {
		await finishWrite(deps.db, logId, { error: (error as Error).message, status: "failed" });
		throw error;
	}

	const writeErrors = await writeSolo(client, newId, solo);
	const state = await readUnit(client, newId, { fresh: true, sleep: deps.sleep });
	const { missing, unverified } = verifyObject(state, fields, customExpect);
	const groups = groupIdsOfUnit(state);
	for (const tag of tags) if (!groups.includes(tag)) missing.push(`tag ${TEST_TAG}`);
	const gaps = missing.length || writeErrors.length;
	await finishWrite(deps.db, logId, {
		entityId: newId,
		error: writeErrors.length ? writeErrors.join(" | ") : undefined,
		notApplied: [...missing, ...unverified.map((f) => `${f} (nicht prüfbar)`)],
		status: gaps ? "done_with_gaps" : "done",
	});

	const review = await createReviewTask(client, deps.db, {
		lines: [
			`Objekt ${newId}: ${input.title}`,
			`${CRM_BASE}/properties/${newId}`,
			...(input.project_id ? [`Projekt: ${CRM_BASE}/projects/${input.project_id}`] : []),
			`Angelegt ueber Claude (Propstack MCP) von ${user.name} am ${today(now)}.`,
			...(overrideReason ? [`Dublette bewusst angelegt: ${overrideReason}`] : []),
			...dedupe.warnings.map((w) => `Hinweis: ${w}`),
			...(missing.length ? [`Nicht uebernommen: ${missing.join(", ")}`] : []),
			...(unverified.length ? [`Nicht pruefbar: ${unverified.join(", ")}`] : []),
			...(writeErrors.length ? [`Fehler: ${writeErrors.join("; ")}`] : []),
			"Pruefen: Stammdaten, Flaechen (inkl. Custom-Felder), Texte (keine Konditionen/Eigentuemer), Provision, Custom Fields, Bilder.",
		],
		now,
		projectIds: input.project_id ? [input.project_id] : undefined,
		propertyIds: [newId],
		test: input.test === true,
		title: `${input.title} - Objekt ${newId}`,
		user,
	});

	return {
		count: 1,
		result: {
			created: true,
			id: newId,
			title: scalar(state.row?.title ?? state.detail.title),
			link: `${CRM_BASE}/properties/${newId}`,
			review_task: review,
			broker: user.name,
			test: input.test || undefined,
			override_reason: overrideReason ?? undefined,
			mirrored_custom_fields: Object.keys(mirrored).length ? Object.keys(mirrored) : undefined,
			warnings: dedupe.warnings.length ? dedupe.warnings : undefined,
			not_applied: missing.length ? missing : undefined,
			not_verifiable: unverified.length ? unverified : undefined,
			write_errors: writeErrors.length ? writeErrors : undefined,
			note: gapNote(missing, unverified, writeErrors),
		},
	};
}

export const updateObjectInput = {
	id: id.describe("Propstack-Objekt-ID"),
	...objectFieldsShape,
	allow_duplicate_reason: optionalText(500).describe("Nur falls die geänderte Adresse/Einheit/Vermarktungsart mit einem anderen Objekt kollidiert: Begründung"),
};

export async function updateObject(deps: WriteDeps, input: z.infer<z.ZodObject<typeof updateObjectInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	const now = deps.now?.() ?? new Date();
	const current = await readUnit(client, input.id);
	const currentValue = (key: string) => {
		const value = unitValue(current, key);
		return value === UNVERIFIABLE ? undefined : value;
	};

	const requested = objectPayload(input);
	if (checkPublicPrice(requested.marketing_type ?? scalar(currentValue("marketing_type")), requested, input.public_price_confirmed === true) && requested.price_on_inquiry === undefined) {
		requested.price_on_inquiry = false;
	}

	// Nur echte Änderungen schreiben; nicht lesbare Felder werden vorsichtshalber geschrieben
	const fields: Raw = {};
	const before: Raw = {};
	for (const [key, value] of Object.entries(requested)) {
		const actual = unitValue(current, key);
		if (actual !== UNVERIFIABLE && sameUnitValue(key, value, actual)) continue;
		fields[key] = value;
		before[fieldLabel(key)] = actual === UNVERIFIABLE ? "nicht lesbar" : (scalar(actual) ?? null);
	}

	// Adresse, Einheit oder Vermarktungsart geändert → Kollision mit anderem Objekt prüfen
	let dedupe: DedupeResult = { duplicates: [], warnings: [] };
	if (["street", "house_number", "zip_code", "unit_id", "marketing_type"].some((k) => k in fields)) {
		const merged = (key: string) => String(fields[key] ?? scalar(currentValue(key)) ?? "");
		const candidate = {
			house_number: merged("house_number"),
			lat: input.lat,
			lng: input.lng,
			marketing_type: merged("marketing_type"),
			street: merged("street"),
			unit_id: merged("unit_id"),
			zip_code: merged("zip_code"),
		};
		if (candidate.zip_code) dedupe = objectDuplicates(candidate, await objectCandidates(client, candidate.zip_code), input.id);
	}
	if (dedupe.duplicates.length && !input.allow_duplicate_reason) {
		return blockedResult(dedupe, "Nichts geändert – das Objekt würde mit einem vorhandenen kollidieren.");
	}
	const overrideReason = checkOverride(dedupe, input.allow_duplicate_reason);

	// Flächen spiegeln; *_verfugbar nur, solange das Objekt nicht vermietet ist
	const defs = await loadFieldDefs(client, "for_properties");
	const rentedNow = requested.rented ?? scalar(currentValue("rented"));
	const rentChanged = "rented" in fields;
	if (rentChanged && fields.rented === true && requested.free_from === undefined) {
		const actual = unitValue(current, "free_from");
		if (actual === UNVERIFIABLE || !same("vermietet", actual)) {
			fields.free_from = "vermietet";
			before.free_from = actual === UNVERIFIABLE ? "nicht lesbar" : (scalar(actual) ?? null);
		}
	}
	// Aus den angefragten (nicht nur geänderten) Flächen – so werden auch Altobjekte nachgezogen,
	// deren Custom-Varianten fehlen. Bei Vermietungswechsel auch die vorhandenen Flächen für
	// „X m² (vermietet)“ heranziehen. Bereits richtige Werte nicht erneut schreiben.
	const areaSource: Raw = { ...requested };
	if (rentChanged) {
		for (const key of ["industrial_area", "usable_floor_space", "total_floor_space"]) {
			const actual = scalar(currentValue(key));
			if (areaSource[key] === undefined && typeof actual === "number" && actual > 0) areaSource[key] = actual;
		}
	}
	const mirrored = Object.fromEntries(
		Object.entries(
			mirroredCustomFields(areaSource, defs, input.custom_fields, {
				flags: rentChanged || "property_status_id" in fields,
				marketable: ACTIVE_STATUSES.includes(Number(requested.property_status_id ?? currentValue("property_status_id"))),
				priceOnInquiry: requested.price_on_inquiry === true,
				rent: rentedNow === true ? "rented" : rentedNow === false ? "available" : "unknown",
			}),
		).filter(([key, value]) => {
			const actual = unitCustomValue(current, key);
			return actual === UNVERIFIABLE || !same(value, actual);
		}),
	);
	const custom = await validateCustomFields(client, "for_properties", { ...mirrored, ...input.custom_fields }, defs, {
		publicPriceConfirmed: input.public_price_confirmed === true,
	});
	const customSend: Raw = { ...(custom?.send ?? {}) };
	const customExpect: Raw = { ...(custom?.expect ?? {}) };
	const customBefore: Raw = {};
	for (const key of Object.keys(customSend)) {
		const actual = unitCustomValue(current, key);
		customBefore[key] = actual === UNVERIFIABLE ? "nicht lesbar" : (scalar(actual) ?? null);
	}
	if (input.bemerkung_append) {
		const old = unitCustomValue(current, "bemerkung");
		if (old === UNVERIFIABLE) {
			throw new PropstackError("Die vorhandene Bemerkung konnte nicht gelesen werden – nichts geändert, damit sie nicht überschrieben wird.", 0);
		}
		const oldText = String(scalar(old) ?? "").trim();
		const text = [oldText, `${originNote(user, now, "Ergänzt")}\n${input.bemerkung_append}`].filter(Boolean).join("\n\n");
		customSend.bemerkung = text;
		customExpect.bemerkung = text;
		customBefore.bemerkung = oldText;
	}
	if (Object.keys(customBefore).length) before.custom_fields = customBefore;

	if (!Object.keys(fields).length && !Object.keys(customSend).length) {
		return { count: 0, result: { updated: false, id: input.id, note: "Keine Änderung – alle Werte sind bereits so gesetzt." } };
	}

	const { bulk, solo } = splitSolo(fields);
	const payload: Raw = { ...bulk, ...(Object.keys(customSend).length ? { partial_custom_fields: customSend } : {}) };

	const logId = await beginWrite(deps.db, {
		action: "update",
		before,
		brokerId: user.brokerId,
		entity: "object",
		entityId: input.id,
		overrideReason,
		request: { ...payload, einzeln_nachgesetzt: Object.fromEntries(solo.map(([k, v]) => [fieldLabel(k), v])) },
		tool: "update_object",
		userEmail: user.email,
		warnings: dedupe.warnings,
	});
	if (Object.keys(payload).length) {
		try {
			await client.updateUnit(input.id, payload);
		} catch (error) {
			await finishWrite(deps.db, logId, { error: (error as Error).message, status: "failed" });
			throw error;
		}
	}
	const writeErrors = await writeSolo(client, input.id, solo);
	if (!Object.keys(payload).length && writeErrors.length === solo.length) {
		await finishWrite(deps.db, logId, { error: writeErrors.join(" | "), status: "failed" });
		throw new PropstackError(`Nichts geändert: ${writeErrors.join("; ")}`, 0);
	}

	const state = await readUnit(client, input.id);
	const { missing, unverified } = verifyObject(state, fields, customExpect);
	await finishWrite(deps.db, logId, {
		error: writeErrors.length ? writeErrors.join(" | ") : undefined,
		notApplied: [...missing, ...unverified.map((f) => `${f} (nicht prüfbar)`)],
		status: missing.length || writeErrors.length ? "done_with_gaps" : "done",
	});

	return {
		count: 1,
		result: {
			updated: true,
			id: input.id,
			title: scalar(state.row?.title ?? state.detail.title),
			changed: [
				...Object.keys(fields).map(fieldLabel),
				...Object.keys(customSend).map((k) => (k === "bemerkung" && input.bemerkung_append ? "bemerkung (angehängt)" : `custom_fields.${k}`)),
			],
			warnings: dedupe.warnings.length ? dedupe.warnings : undefined,
			not_applied: missing.length ? missing : undefined,
			not_verifiable: unverified.length ? unverified : undefined,
			write_errors: writeErrors.length ? writeErrors : undefined,
			note: gapNote(missing, unverified, writeErrors),
		},
	};
}
