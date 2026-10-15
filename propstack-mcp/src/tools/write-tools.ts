import { z } from "zod";
import type { Props } from "../auth/session";
import { type CustomFieldEntity, type GroupEntity, PropstackClient, PropstackError } from "../propstack-client";
import {
	type ContactSearchResults,
	contactDuplicates,
	type DedupeResult,
	isMobile,
	objectDuplicates,
} from "../propstack/dedupe";
import { scalar } from "../propstack/mappers";
import { beginWrite, finishWrite } from "../write-log";
import { loadAll, type ToolOutput } from "./read-tools";

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

interface FieldDef {
	type: string;
	options: string[];
}

/** Custom-Felder gegen die Definition prüfen – sonst verwirft Propstack sie still. */
export async function validateCustomFields(
	client: PropstackClient,
	entity: CustomFieldEntity,
	fields: Record<string, unknown> | undefined,
): Promise<Record<string, unknown> | undefined> {
	if (!fields || !Object.keys(fields).length) return undefined;
	const defs = new Map<string, FieldDef>();
	for (const group of (await client.listCustomFieldGroups(entity)).rows) {
		for (const f of Array.isArray(group.custom_fields) ? (group.custom_fields as Raw[]) : []) {
			const options = Array.isArray(f.custom_options) ? (f.custom_options as Raw[]).map((o) => String(scalar(o.name))) : [];
			defs.set(String(f.name), { options, type: String(f.field_type) });
		}
	}
	const errors: string[] = [];
	const out: Record<string, unknown> = {};
	for (const [key, value] of Object.entries(fields)) {
		const def = defs.get(key);
		if (!def) {
			errors.push(`unbekanntes Feld "${key}"`);
			continue;
		}
		const fail = (expected: string) => errors.push(`"${key}" erwartet ${expected}`);
		switch (def.type) {
			case "Number": {
				const n = typeof value === "number" ? value : Number(String(value).replace(",", "."));
				if (!Number.isFinite(n)) fail("eine Zahl");
				else out[key] = n;
				break;
			}
			case "Boolean":
				if (typeof value !== "boolean") fail("true/false");
				else out[key] = value;
				break;
			case "Date":
				if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) fail("ein Datum JJJJ-MM-TT");
				else out[key] = value;
				break;
			case "Dropdown":
				if (!def.options.includes(String(value))) fail(`einen der Werte ${def.options.join(", ")}`);
				else out[key] = value;
				break;
			case "Multiselect": {
				const values = Array.isArray(value) ? value.map(String) : [String(value)];
				if (!values.every((v) => def.options.includes(v))) fail(`Werte aus ${def.options.join(", ")}`);
				else out[key] = values;
				break;
			}
			default:
				if (typeof value === "object") fail("einen Text");
				else out[key] = String(value);
		}
	}
	if (errors.length) {
		throw new PropstackError(`Custom-Felder ungültig: ${errors.join("; ")}. Gültige Felder über list_fields.`, 400);
	}
	return out;
}

function same(requested: unknown, actual: unknown): boolean {
	const candidates =
		actual && typeof actual === "object" && !Array.isArray(actual)
			? [(actual as Raw).value, (actual as Raw).pretty_value]
			: [actual];
	return candidates.some((candidate) => {
		if (typeof requested === "number") return Number(candidate) === requested;
		if (typeof requested === "boolean") return candidate === requested || String(candidate) === String(requested);
		if (Array.isArray(requested)) {
			const have = Array.isArray(candidate) ? candidate.map(String) : String(candidate ?? "").split(/,\s*/);
			return requested.every((r) => have.includes(String(r)));
		}
		return String(candidate ?? "").trim() === String(requested ?? "").trim();
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
		...(custom ? { partial_custom_fields: custom } : {}),
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
	const missing = notApplied({ ...fields, broker_id: user.brokerId }, actual, custom);
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
	if (custom) payload.partial_custom_fields = custom;
	if (input.note_append) {
		const old = String(scalar(current.description) ?? "");
		before.description = old;
		payload.description = [old, `${originNote(user, now, "Ergänzt")}\n${input.note_append}`].filter(Boolean).join("\n\n");
	}
	if (addTags.length || removeTags.length) before.tag_ids = currentTags;
	if (custom) before.custom_fields = Object.fromEntries(Object.keys(custom).map((k) => [k, scalar((current.custom_fields as Raw | undefined)?.[k]) ?? null]));

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
	const missing = notApplied(fields, actual, custom);
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
			changed: [...Object.keys(fields), ...(addTags.length ? ["add_tags"] : []), ...(removeTags.length ? ["remove_tags"] : []), ...(input.note_append ? ["note"] : []), ...Object.keys(custom ?? {}).map((k) => `custom_fields.${k}`)],
			warnings: dedupe.warnings.length ? dedupe.warnings : undefined,
			not_applied: missing.length ? missing : undefined,
		},
	};
}

// ---------- Objekte ----------

const num = z.number().nonnegative().optional();

const objectFieldsShape = {
	title: optionalText(250).describe("Überschrift"),
	marketing_type: z.enum(["BUY", "RENT"]).optional().describe("BUY = Kauf, RENT = Miete"),
	object_type: z.enum(["LIVING", "COMMERCIAL", "INVESTMENT"]).optional(),
	rs_type: z.string().regex(/^[A-Z_]+$/).optional().describe("Objektart, z. B. INDUSTRY, OFFICE, HOUSE, APARTMENT"),
	rs_category: z.string().regex(/^[A-Z_]+$/).optional().describe("Unterart, z. B. HALL, WAREHOUSE"),
	unit_id: optionalText(50).describe("Einheit, z. B. Unit 1"),
	street: optionalText(200),
	house_number: optionalText(20),
	zip_code: optionalText(10),
	city: optionalText(100),
	project_id: id.optional(),
	status_id: id.optional().describe("Objekt-Status (über list_reference kind=object_statuses)"),
	price: num.describe("Kaufpreis"),
	base_rent: num.describe("Kaltmiete"),
	total_rent: num.describe("Warmmiete"),
	property_space_value: num.describe("Fläche m²"),
	plot_area: num.describe("Grundstücksfläche m²"),
	number_of_rooms: num,
	construction_year: z.number().int().min(1800).max(2100).optional(),
	courtage: optionalText(200).describe("Provision (Text)"),
	description_note: optionalText(10000).describe("Objektbeschreibung"),
	location_note: optionalText(10000).describe("Lagebeschreibung"),
	furnishing_note: optionalText(10000).describe("Ausstattung"),
	other_note: optionalText(10000).describe("Sonstiges"),
	lat: z.number().min(-90).max(90).optional(),
	lng: z.number().min(-180).max(180).optional(),
	custom_fields: z.record(z.string(), z.unknown()).optional().describe("Custom-Felder {schlüssel: wert}, Schlüssel über list_fields entity=objects"),
};

const OBJECT_KEYS = [
	"title", "marketing_type", "object_type", "rs_type", "rs_category", "unit_id", "street", "house_number", "zip_code", "city",
	"project_id", "price", "base_rent", "total_rent", "property_space_value", "plot_area", "number_of_rooms", "construction_year",
	"courtage", "description_note", "location_note", "furnishing_note", "other_note", "lat", "lng",
] as const;

function objectPayload(input: Raw): Raw {
	const out: Raw = {};
	for (const key of OBJECT_KEYS) if (input[key] !== undefined) out[key] = input[key];
	if (input.status_id !== undefined) out.property_status_id = input.status_id;
	return out;
}

function statusIdOf(raw: Raw): unknown {
	const status = (raw.property_status ?? raw.status) as Raw | undefined;
	return raw.property_status_id ?? (status && typeof status === "object" ? status.id : undefined);
}

async function objectCandidates(client: PropstackClient, zip: string): Promise<Raw[]> {
	const loaded = await loadAll((q) => client.searchUnits(q), { archived: "-1", q: zip });
	if (!loaded.complete) throw new PropstackError(`Zu viele Objekte in PLZ ${zip} für die Dublettenprüfung.`, 400);
	return loaded.rows;
}

function verifyObject(fields: Raw, actual: Raw, custom?: Raw): string[] {
	const { property_status_id: statusId, ...rest } = fields;
	const missing = notApplied(rest, actual, custom);
	if (statusId !== undefined && statusIdOf(actual) !== statusId) missing.push("status_id");
	return missing;
}

export const createObjectInput = {
	...objectFieldsShape,
	title: z.string().trim().min(1).max(250).describe("Überschrift (Pflicht)"),
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

	const dedupe = objectDuplicates(input, await objectCandidates(client, input.zip_code));
	if (dedupe.duplicates.length && !input.allow_duplicate_reason) {
		return blockedResult(
			dedupe,
			"Nichts angelegt. Vorhandenes Objekt mit update_object ändern – oder, falls es nachweislich ein anderes Objekt ist, mit allow_duplicate_reason erneut aufrufen.",
		);
	}
	const overrideReason = checkOverride(dedupe, input.allow_duplicate_reason);

	const custom = await validateCustomFields(client, "for_properties", input.custom_fields);
	const tags = input.test ? [await ensureTestTag(client, "for_properties")] : [];
	const fields = objectPayload(input);
	const payload: Raw = {
		...fields,
		broker_id: user.brokerId,
		other_note: [input.other_note, originNote(user, now, "Angelegt")].filter(Boolean).join("\n\n"),
		...(tags.length ? { group_ids: tags } : {}),
		...(custom ? { partial_custom_fields: custom } : {}),
	};

	const logId = await beginWrite(deps.db, {
		action: "create",
		before: null,
		brokerId: user.brokerId,
		entity: "object",
		entityId: null,
		overrideReason,
		request: payload,
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

	const actual = await asObjectOrThrow(client.getUnit(newId));
	const { other_note: _ignored, ...checkFields } = fields;
	const missing = verifyObject({ ...checkFields, broker_id: user.brokerId }, actual, custom);
	const groups = groupIdsOf(actual);
	for (const tag of tags) if (!groups.includes(tag)) missing.push(`tag ${TEST_TAG}`);
	await finishWrite(deps.db, logId, { entityId: newId, notApplied: missing, status: missing.length ? "done_with_gaps" : "done" });

	return {
		count: 1,
		result: {
			created: true,
			id: newId,
			title: scalar(actual.title),
			broker: user.name,
			test: input.test || undefined,
			override_reason: overrideReason ?? undefined,
			warnings: dedupe.warnings.length ? dedupe.warnings : undefined,
			not_applied: missing.length ? missing : undefined,
			note: missing.length ? "Propstack hat einige Felder nicht übernommen – bitte prüfen." : undefined,
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
	const current = await asObjectOrThrow(client.getUnit(input.id));

	const requested = objectPayload(input);
	const fields: Raw = {};
	const before: Raw = {};
	for (const [key, value] of Object.entries(requested)) {
		const currentValue = key === "property_status_id" ? statusIdOf(current) : current[key];
		if (key === "property_status_id" ? currentValue === value : same(value, currentValue)) continue;
		fields[key] = value;
		before[key] = (key === "property_status_id" ? currentValue : scalar(currentValue)) ?? null;
	}

	// Adresse, Einheit oder Vermarktungsart geändert → Kollision mit anderem Objekt prüfen
	let dedupe: DedupeResult = { duplicates: [], warnings: [] };
	if (["street", "house_number", "zip_code", "unit_id", "marketing_type"].some((k) => k in fields)) {
		const merged = {
			house_number: String(fields.house_number ?? scalar(current.house_number) ?? ""),
			marketing_type: String(fields.marketing_type ?? scalar(current.marketing_type) ?? ""),
			street: String(fields.street ?? scalar(current.street) ?? ""),
			unit_id: String(fields.unit_id ?? scalar(current.unit_id) ?? ""),
			zip_code: String(fields.zip_code ?? scalar(current.zip_code) ?? ""),
		};
		if (merged.zip_code) dedupe = objectDuplicates(merged, await objectCandidates(client, merged.zip_code), input.id);
	}
	if (dedupe.duplicates.length && !input.allow_duplicate_reason) {
		return blockedResult(dedupe, "Nichts geändert – das Objekt würde mit einem vorhandenen kollidieren.");
	}
	const overrideReason = checkOverride(dedupe, input.allow_duplicate_reason);

	const custom = await validateCustomFields(client, "for_properties", input.custom_fields);
	const payload: Raw = { ...fields };
	if (custom) {
		payload.partial_custom_fields = custom;
		before.custom_fields = Object.fromEntries(Object.keys(custom).map((k) => [k, scalar((current.custom_fields as Raw | undefined)?.[k]) ?? null]));
	}
	if (!Object.keys(payload).length) {
		return { count: 0, result: { updated: false, id: input.id, note: "Keine Änderung – alle Werte sind bereits so gesetzt." } };
	}

	const logId = await beginWrite(deps.db, {
		action: "update",
		before,
		brokerId: user.brokerId,
		entity: "object",
		entityId: input.id,
		overrideReason,
		request: payload,
		tool: "update_object",
		userEmail: user.email,
		warnings: dedupe.warnings,
	});
	try {
		await client.updateUnit(input.id, payload);
	} catch (error) {
		await finishWrite(deps.db, logId, { error: (error as Error).message, status: "failed" });
		throw error;
	}

	const actual = await asObjectOrThrow(client.getUnit(input.id));
	const missing = verifyObject(fields, actual, custom);
	await finishWrite(deps.db, logId, { notApplied: missing, status: missing.length ? "done_with_gaps" : "done" });

	return {
		count: 1,
		result: {
			updated: true,
			id: input.id,
			title: scalar(actual.title),
			changed: [...Object.keys(fields).map((k) => (k === "property_status_id" ? "status_id" : k)), ...Object.keys(custom ?? {}).map((k) => `custom_fields.${k}`)],
			warnings: dedupe.warnings.length ? dedupe.warnings : undefined,
			not_applied: missing.length ? missing : undefined,
		},
	};
}

