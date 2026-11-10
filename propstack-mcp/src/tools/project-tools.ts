import { z } from "zod";
import { PropstackClient, PropstackError } from "../propstack-client";
import { type DedupeResult, sameAddress } from "../propstack/dedupe";
import { validateCustomFields } from "../propstack/field-rules";
import { coordinatesLine, coordsOf, ensureCoordinates } from "../propstack/geo";
import {
	checkExposeTexts,
	checkZipPrefix,
	commissionFields,
	commissionParam,
	imageTitleProblem,
	internalNoteLines,
	internalNoteShape,
	ownerNamesOf,
	PROJECT_UI_STEPS,
	projectNotProvided,
	TEXT_RULES,
	throwOnTextErrors,
} from "../propstack/howto";
import { scalar } from "../propstack/mappers";
import { linkContact, type RelationResult, type RelationRole, relationLine, ROLE_LABEL } from "../propstack/relations";
import { CRM_BASE, createReviewTask } from "../review-task";
import { beginWrite, finishWrite } from "../write-log";
import { flag, id, optionalText } from "./params";
import { loadAll, type ToolOutput } from "./read-tools";
import { same, TEST_TAG, type WriteDeps } from "./write-tools";

// Phase 3b (Entscheidung Florian, 15.10.2026): Projekte anlegen, Eigentümer verknüpfen,
// Bilder per URL hochladen. Regeln aus Notion-Feld-Mapping, API-Doku und dem Team-How-to „Projekte anlegen“:
// - Wrapper project. Die interne Notiz (note) nimmt Propstack an, liefert sie aber im GET nicht zurück →
//   beim Anlegen blind schreiben und in die Prüfaufgabe kopieren; nachträglich NICHT anhängen (würde überschreiben).
// - Eigentümer/Ansprechpartner separat per PUT relationships_attributes mit related_client_id,
//   Kontakt muss aus dem eigenen Shop stammen; Prüfung über die Gegenprobe (relations.ts).
// - Bilder: image[photo] als Multipart (image_upload_url) oder remote_photo_url (hier).
// - Keine Lösch-Funktionen.

type Raw = Record<string, unknown>;

const MIN_OVERRIDE_REASON = 15;
const EXPOSE_VISIBLE = "Steht im Exposé";
const publicPriceConfirmed = z
	.literal(true)
	.optional()
	.describe("Nur setzen, wenn der Nutzer ausdrücklich angesagt hat, dass ein Preis im Exposé-Text stehen soll. Sonst werden Preise in Texten abgewiesen");

function today(now: Date): string {
	return now.toISOString().slice(0, 10);
}

function createdId(response: unknown): number {
	const raw = (response ?? {}) as Raw;
	const value = raw.id ?? (raw.data as Raw | undefined)?.id;
	if (typeof value !== "number") {
		throw new PropstackError("Propstack hat keine ID zurückgegeben – Status unklar, bitte in Propstack prüfen.", 0);
	}
	return value;
}

function asObject(value: unknown): Raw {
	return value && typeof value === "object" && !Array.isArray(value) ? (value as Raw) : {};
}

function readValue(actual: Raw, key: string): unknown {
	if (key === "broker_id" && "broker" in actual) {
		const broker = actual.broker as Raw | null | undefined;
		return broker && typeof broker === "object" ? (broker.id ?? null) : null;
	}
	return key in actual ? scalar(actual[key]) : undefined;
}

function matches(requested: unknown, actual: unknown): boolean {
	if (typeof requested === "number") return actual !== null && actual !== "" && Number(actual) === requested;
	if (typeof requested === "boolean") return actual === requested || String(actual) === String(requested);
	const squash = (v: unknown) => String(v ?? "").replace(/\s+/g, " ").trim();
	return squash(actual) === squash(requested);
}

/** Vergleich nach dem Write: fehlende Keys = nicht prüfbar, abweichende = nicht übernommen. */
function compareProject(fields: Raw, actual: Raw, customExpect?: Raw): { missing: string[]; unverified: string[] } {
	const missing: string[] = [];
	const unverified: string[] = [];
	for (const [key, value] of Object.entries(fields)) {
		const got = readValue(actual, key);
		if (got === undefined) unverified.push(key);
		else if (!matches(value, got)) missing.push(key);
	}
	const actualCustom = actual.custom_fields && typeof actual.custom_fields === "object" ? (actual.custom_fields as Raw) : undefined;
	for (const [key, value] of Object.entries(customExpect ?? {})) {
		if (!actualCustom || !(key in actualCustom)) unverified.push(`custom_fields.${key}`);
		else if (!same(value, actualCustom[key])) missing.push(`custom_fields.${key}`);
	}
	return { missing, unverified };
}

function originNoteText(name: string, now: Date, verb: "Angelegt" | "Ergänzt"): string {
	return `${verb} über Claude (Propstack MCP) von ${name} am ${today(now)}.`;
}

/** Kontakt laden und auf id + Name kürzen (404 → Fehler, bevor etwas angelegt wird). */
async function loadContact(client: PropstackClient, contactId: number): Promise<{ raw: Raw; ref: { id: number; name: string } }> {
	const raw = asObject(await client.getContact(contactId));
	return { raw, ref: { id: contactId, name: String(scalar(raw.name) ?? contactId) } };
}

// ---------- Projekt anlegen ----------

export const createProjectInput = {
	name: z
		.string()
		.trim()
		.min(1)
		.max(250)
		.describe("Projektname, Format: „Logistikhalle in (XX) Ort“ (XX = erste zwei PLZ-Ziffern; auch Logistikpark/Gewerbepark). Interner und externer Name gleich"),
	title: optionalText(250).describe("Überschrift für Exposé und Landing-Page. Standard: wie name – so will es das How-to"),
	marketing_type: z.enum(["RENT", "BUY"]).describe("RENT = Vermietung (Mietprojekt), BUY = Verkauf"),
	street: z.string().trim().min(1).max(200),
	house_number: optionalText(20),
	zip_code: z.string().trim().regex(/^\d{4,5}$/),
	city: z.string().trim().min(1).max(100),
	hide_address: z.boolean().optional().describe("Adresse im Exposé ausblenden"),
	commission: commissionParam,
	courtage: optionalText(200).describe("Außenprovision fürs Exposé, z. B. „Provisionsfrei“. Standardtexte über commission"),
	courtage_note: optionalText(2000).describe("Provisionshinweis. Standardtexte über commission"),
	description_note: optionalText(10000).describe(`${TEXT_RULES.description_project}. ${EXPOSE_VISIBLE}`),
	location_note: optionalText(10000).describe(`${TEXT_RULES.location}. ${EXPOSE_VISIBLE}`),
	furnishing_note: optionalText(10000).describe(`${TEXT_RULES.furnishing}. ${EXPOSE_VISIBLE}`),
	sub_headline: optionalText(250).describe("Unterzeile fürs Exposé: das stärkste Lageargument in wenigen Worten, z. B. „Direkt an der A40“"),
	show_units_on_landing_page: flag.optional().describe("Einheiten auf der Landing-Page des Projekts zeigen und verlinken. Standard: ja (How-to: muss aktiviert sein)"),
	public_price_confirmed: publicPriceConfirmed,
	...internalNoteShape,
	internal_rents: optionalText(1000).describe("Interne Notiz: Mietpreise, z. B. „Halle 6,80 €/m², Büro 12,80 €/m²“ – nie in Preisfelder oder Exposé-Texte"),
	internal_note: optionalText(4000).describe("Interne Notiz: weiterer Freitext (nicht im Exposé)"),
	custom_fields: z.record(z.string(), z.unknown()).optional().describe("Projekt-Custom-Felder {schlüssel: wert}, Schlüssel über list_fields entity=projects"),
	owner_contact_id: id.optional().describe("Eigentümer-Kontakt (eigener Shop) – wird als Eigentümer verknüpft. An den Einheiten ebenfalls angeben"),
	contact_person_id: id.optional().describe("Ansprechpartner-Kontakt, sofern vorhanden – wird als Kontakt verknüpft. An den Einheiten ebenfalls angeben"),
	lat: z.number().min(-90).max(90).optional().describe("Breitengrad – nur zusammen mit lng. Sonst übernimmt das Tool Propstacks Geokodierung oder ermittelt die Koordinaten aus der Adresse (OpenStreetMap)"),
	lng: z.number().min(-180).max(180).optional().describe("Längengrad"),
	review_notes: z
		.array(z.string().trim().min(1).max(500))
		.max(20)
		.optional()
		.describe("Offene Punkte, abgeleitete/unsichere Werte – landen in der Prüfaufgabe. Dieselben Punkte an der Einheit per bemerkung_append vermerken"),
	test: z.boolean().optional().describe(`Testdatensatz: Name beginnt mit ${TEST_TAG}, Prüfaufgabe geht an dich statt an Lena. Für alle Tests Pflicht.`),
	allow_duplicate_reason: optionalText(500).describe("Nur wenn ein Projekt an derselben Adresse existiert und es nachweislich ein anderes ist: Begründung"),
};

async function projectDuplicates(client: PropstackClient, input: { street: string; house_number?: string; zip_code: string }): Promise<DedupeResult> {
	const loaded = await loadAll((q) => client.searchProjects(q), { q: input.zip_code }, 100, 5);
	if (!loaded.complete) throw new PropstackError(`Zu viele Projekte in PLZ ${input.zip_code} für die Dublettenprüfung.`, 400);
	const duplicates = loaded.rows
		.filter((row) => sameAddress({ ...input, marketing_type: "" }, row))
		.map((row) => ({ id: row.id as number, name: String(scalar(row.name) ?? scalar(row.title) ?? "Projekt"), reason: "gleiche Adresse" }));
	return { duplicates, warnings: [] };
}

export async function createProject(deps: WriteDeps, input: z.infer<z.ZodObject<typeof createProjectInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	const now = deps.now?.() ?? new Date();
	if ((input.lat === undefined) !== (input.lng === undefined)) throw new PropstackError("lat und lng nur zusammen angeben.", 400);

	const dedupe = await projectDuplicates(client, input);
	if (dedupe.duplicates.length && !input.allow_duplicate_reason) {
		return {
			count: 0,
			result: {
				created: false,
				blocked: "Dublette",
				duplicates: dedupe.duplicates,
				hint: "Nichts angelegt. Vorhandenes Projekt verwenden (Einheiten mit project_id anlegen) – oder, falls es nachweislich ein anderes ist, mit allow_duplicate_reason erneut aufrufen.",
			},
		};
	}
	const overrideReason = dedupe.duplicates.length ? input.allow_duplicate_reason!.trim() : null;
	if (overrideReason !== null && overrideReason.length < MIN_OVERRIDE_REASON) {
		throw new PropstackError(`allow_duplicate_reason braucht eine echte Begründung (mind. ${MIN_OVERRIDE_REASON} Zeichen).`, 400);
	}

	// Kontakte vorher prüfen (404 → nichts anlegen)
	const ownerLoaded = input.owner_contact_id ? await loadContact(client, input.owner_contact_id) : undefined;
	const owner = ownerLoaded?.ref;
	const sameContact = input.contact_person_id !== undefined && input.contact_person_id === input.owner_contact_id;
	const contactPerson = input.contact_person_id ? (sameContact ? owner : (await loadContact(client, input.contact_person_id)).ref) : undefined;

	const name = input.test ? `${TEST_TAG} ${input.name}` : input.name;
	const fields: Raw = {
		broker_id: user.brokerId,
		city: input.city,
		country: "DEU",
		name,
		street: input.street,
		// How-to „Webseite & Landing-Page“: Einheiten auf der Landing-Page verlinken – Feldname aus der Diagnose (10.11.)
		show_units_on_landing_page: input.show_units_on_landing_page ?? true,
		title: input.title ?? name,
		zip_code: input.zip_code,
		...(input.marketing_type === "RENT" ? { for_rent: true } : { for_sale: true }),
	};
	for (const key of ["house_number", "hide_address", "courtage", "courtage_note", "description_note", "location_note", "furnishing_note", "sub_headline"] as const) {
		if (input[key] !== undefined) fields[key] = input[key];
	}
	Object.assign(fields, commissionFields(input.commission, input.marketing_type, input));

	// Texte und Namensformat nach Team-Regeln – vor dem Anlegen abweisen statt hinterher korrigieren
	const findings = checkExposeTexts(fields, {
		city: input.city,
		ownerNames: ownerNamesOf(ownerLoaded?.raw),
		publicPriceConfirmed: input.public_price_confirmed === true,
		street: input.street,
	});
	throwOnTextErrors(findings);
	const textWarnings = [...findings.warnings];
	// How-to: Name „Logistikfläche in (PLZ) Ort“, Überschrift = Name inkl. der ersten beiden PLZ-Ziffern, intern und extern gleich
	const formatError = checkZipPrefix("Projektname", input.name, input.zip_code).error ?? checkZipPrefix("Überschrift", input.title ?? input.name, input.zip_code).error;
	if (formatError) throw new PropstackError(formatError, 400);
	if (input.title !== undefined && input.title !== input.name) {
		textWarnings.push("Überschrift weicht vom Projektnamen ab – laut How-to sollen interner und externer Name gleich sein.");
	}

	// Interne Notiz (How-to: Exposé-Link, Mandat, Mietpreise, Provisionsregelung, Projektname des Entwicklers)
	const noteLines = [...internalNoteLines(input), ...(input.internal_note ? [input.internal_note] : [])];
	fields.note = [originNoteText(user.name, now, "Angelegt"), ...noteLines].join("\n");
	const custom = await validateCustomFields(client, "for_projects", input.custom_fields);
	if (custom) fields.partial_custom_fields = custom.send;

	const logId = await beginWrite(deps.db, {
		action: "create",
		before: null,
		brokerId: user.brokerId,
		entity: "project",
		entityId: null,
		overrideReason,
		request: { ...fields, contact_person_id: input.contact_person_id, owner_contact_id: input.owner_contact_id },
		tool: "create_project",
		userEmail: user.email,
		warnings: [...dedupe.warnings, ...textWarnings],
	});
	let projectId: number;
	try {
		projectId = createdId(await client.createProject(fields));
	} catch (error) {
		await finishWrite(deps.db, logId, { error: (error as Error).message, status: "failed" });
		throw error;
	}

	// Zurücklesen; was im Sammel-Request verloren ging, einzeln nachsetzen (Feld-Mapping: Multi-Feld-Writes verlieren still)
	const { partial_custom_fields: _custom, ...plainFields } = fields;
	let actual = asObject(await client.getProject(projectId));
	let { missing, unverified } = compareProject(plainFields, actual, custom?.expect);
	const writeErrors: string[] = [];
	if (missing.length) {
		for (const key of missing) {
			try {
				await client.updateProject(projectId, key.startsWith("custom_fields.") ? { partial_custom_fields: { [key.slice(14)]: custom?.send[key.slice(14)] } } : { [key]: fields[key] });
			} catch (error) {
				writeErrors.push(`${key}: ${(error as Error).message}`);
			}
		}
		actual = asObject(await client.getProject(projectId));
		({ missing, unverified } = compareProject(plainFields, actual, custom?.expect));
	}
	// Die interne Notiz speichert Propstack (in der Oberfläche bestätigt, Projekt 613378, 10.11.2026), der GET
	// liefert sie aber nie zurück – das ist bekannt und kein Befund je Anlage.
	unverified = unverified.filter((key) => key !== "note");

	const coordinates = await ensureCoordinates({
		sleep: deps.sleep,
		address: input,
		current: coordsOf(actual),
		fetchFn: deps.fetchFn,
		provided: input.lat !== undefined && input.lng !== undefined ? { lat: input.lat, lng: input.lng } : undefined,
		put: (body) => client.updateProject(projectId, body),
		read: async () => coordsOf(asObject(await client.getProject(projectId))),
	});
	// Lücke nur, wenn geschrieben wurde und nicht haftet; „nichts gefunden“ steht in der Prüfaufgabe
	if (!coordinates.verified && coordinates.source !== "keine") missing.push("lat/lng");

	const target = { id: projectId, type: "project" as const };
	const ownerResult = owner ? await linkContact(client, target, owner.id, "owner", { fresh: true }) : undefined;
	if (ownerResult?.error) writeErrors.push(`Eigentümer: ${ownerResult.error}`);
	const gaps = ownerResult && ownerResult.linked !== true && !ownerResult.error ? [`owner ${ownerResult.linked === false ? "nicht gefunden" : "nicht prüfbar"}`] : [];
	let contactResult: RelationResult | undefined;
	if (contactPerson) {
		contactResult = sameContact
			? { already: true, linked: ownerResult?.linked ?? false, note: "Ansprechpartner ist der Eigentümer – als Eigentümer verknüpft." }
			: await linkContact(client, target, contactPerson.id, "contact_person", { fresh: true });
		if (contactResult.error) writeErrors.push(`Ansprechpartner: ${contactResult.error}`);
		else if (contactResult.linked !== true && !sameContact) gaps.push("contact_person nicht prüfbar");
	}
	await finishWrite(deps.db, logId, {
		entityId: projectId,
		error: writeErrors.length ? writeErrors.join(" | ") : undefined,
		notApplied: [...missing, ...gaps, ...unverified.map((f) => `${f} (nicht prüfbar)`)],
		status: missing.length || writeErrors.length || gaps.length ? "done_with_gaps" : "done",
	});

	const notProvided = projectNotProvided(input, fields);
	const review = await createReviewTask(client, deps.db, {
		lines: [
			`Projekt ${projectId}: ${name}`,
			`${CRM_BASE}/projects/${projectId}`,
			`Angelegt über Claude (Propstack MCP) von ${user.name} am ${today(now)}.`,
			relationLine("owner", owner, ownerResult),
			relationLine("contact_person", contactPerson, contactResult),
			coordinatesLine(coordinates),
			...(overrideReason ? [`Dublette bewusst angelegt: ${overrideReason}`] : []),
			...(missing.length ? [`Nicht übernommen: ${missing.join(", ")}`] : []),
			...(writeErrors.length ? [`Fehler: ${writeErrors.join("; ")}`] : []),
			...(notProvided.length ? [`Nicht angegeben (laut How-to wichtig): ${notProvided.join(", ")}`] : []),
			...textWarnings.map((w) => `Texthinweis: ${w}`),
			...(input.review_notes ?? []).map((n) => `Offen: ${n}`),
			"Prüfen: Adresse/Koordinaten, Texte (kein Eigentümer, keine Adresse, keine Preise), Provision, Einheiten.",
			...PROJECT_UI_STEPS,
		],
		now,
		projectIds: [projectId],
		test: input.test === true,
		title: `${name} - Projekt ${projectId}`,
		user,
	});

	return {
		count: 1,
		result: {
			created: true,
			id: projectId,
			name,
			link: `${CRM_BASE}/projects/${projectId}`,
			broker: user.name,
			test: input.test || undefined,
			owner: owner ? { ...owner, linked: ownerResult?.linked } : undefined,
			contact_person: contactPerson ? { ...contactPerson, linked: contactResult?.linked, note: contactResult?.note } : undefined,
			coordinates,
			override_reason: overrideReason ?? undefined,
			text_warnings: textWarnings.length ? textWarnings : undefined,
			howto_not_provided: notProvided.length ? notProvided : undefined,
			ui_steps: PROJECT_UI_STEPS,
			not_applied: missing.length || gaps.length ? [...missing, ...gaps] : undefined,
			not_verifiable: unverified.length ? unverified : undefined,
			write_errors: writeErrors.length ? writeErrors : undefined,
			review_task: review,
			next: "Einheiten mit create_object und project_id anlegen (unit_id, Flächen; Adresse, Überschrift, Texte und Provision kommen vom Projekt; Eigentümer/Ansprechpartner erneut angeben). Bilder mit image_upload_url bzw. add_images.",
		},
	};
}

// ---------- Projekt ändern ----------
// Entscheidung Florian, 16.10.: Provision, Texte und Koordinaten auch am Projekt nachträglich setzen.
// Wie update_object: nur echte Änderungen, Snapshot vorher, Gegenlesen, Verlorenes einzeln nachsetzen.

const PROJECT_TEXT_KEYS = ["name", "title", "sub_headline", "street", "house_number", "zip_code", "city", "courtage", "courtage_note", "description_note", "location_note", "furnishing_note"] as const;
/** Felder, die das How-to an den Einheiten vom Projekt erwartet – nach einer Änderung dort nachziehen. */
const UNIT_INHERITED_KEYS = ["courtage", "courtage_note", "description_note", "location_note", "furnishing_note"];

export const updateProjectInput = {
	id: id.describe("Propstack-Projekt-ID"),
	name: optionalText(250).describe("Projektname, Format: „Logistikhalle in (XX) Ort“"),
	title: optionalText(250).describe("Überschrift für Exposé und Landing-Page – wie name"),
	sub_headline: optionalText(250).describe("Unterzeile fürs Exposé, z. B. „Direkt an der A40“"),
	street: optionalText(200),
	house_number: optionalText(20),
	zip_code: z.string().trim().regex(/^\d{4,5}$/).optional(),
	city: optionalText(100),
	hide_address: z.boolean().optional().describe("Adresse im Exposé ausblenden"),
	show_units_on_landing_page: flag.optional().describe("Einheiten auf der Landing-Page des Projekts zeigen und verlinken (How-to: muss aktiviert sein)"),
	commission: commissionParam,
	courtage: optionalText(200).describe("Außenprovision fürs Exposé, z. B. „Provisionsfrei“"),
	courtage_note: optionalText(2000).describe("Provisionshinweis"),
	description_note: optionalText(10000).describe(`${TEXT_RULES.description_project}. ${EXPOSE_VISIBLE}`),
	location_note: optionalText(10000).describe(`${TEXT_RULES.location}. ${EXPOSE_VISIBLE}`),
	furnishing_note: optionalText(10000).describe(`${TEXT_RULES.furnishing}. ${EXPOSE_VISIBLE}`),
	public_price_confirmed: publicPriceConfirmed,
	note_append: optionalText(4000).describe(
		"Interne Notiz ergänzen – nur möglich, wenn Propstack die vorhandene Notiz zurückliefert. Sonst wird abgelehnt, damit nichts überschrieben wird; dann direkt in Propstack ergänzen",
	),
	custom_fields: z.record(z.string(), z.unknown()).optional().describe("Projekt-Custom-Felder {schlüssel: wert}, Schlüssel über list_fields entity=projects; null leert"),
	lat: z.number().min(-90).max(90).optional().describe("Breitengrad – nur zusammen mit lng; geschrieben mit dem Stufen-Trick und per Einzel-GET geprüft"),
	lng: z.number().min(-180).max(180).optional().describe("Längengrad"),
	allow_duplicate_reason: optionalText(500).describe("Nur falls die geänderte Adresse mit einem anderen Projekt kollidiert: Begründung"),
};

export async function updateProject(deps: WriteDeps, input: z.infer<z.ZodObject<typeof updateProjectInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	if ((input.lat === undefined) !== (input.lng === undefined)) throw new PropstackError("lat und lng nur zusammen angeben.", 400);
	const current = asObject(await client.getProject(input.id));
	if (!Object.keys(current).length) throw new PropstackError("Projekt nicht gefunden.", 404);
	const currentText = (key: string) => String(scalar(current[key]) ?? "");

	const requested: Raw = {};
	for (const key of [...PROJECT_TEXT_KEYS, "hide_address", "show_units_on_landing_page"] as const) if (input[key] !== undefined) requested[key] = input[key];
	Object.assign(requested, commissionFields(input.commission, scalar(current.for_rent) === false ? "BUY" : "RENT", input));
	const fields: Raw = {};
	const before: Raw = {};
	for (const [key, value] of Object.entries(requested)) {
		const actual = readValue(current, key);
		if (actual !== undefined && matches(value, actual)) continue;
		fields[key] = value;
		before[key] = actual ?? null;
	}

	// Geänderte Texte und Namen gegen die Team-Regeln prüfen (unveränderte Alttexte bleiben unberührt)
	const zip = String(requested.zip_code ?? currentText("zip_code"));
	const findings = checkExposeTexts(fields, {
		city: String(requested.city ?? currentText("city")),
		publicPriceConfirmed: input.public_price_confirmed === true,
		street: String(requested.street ?? currentText("street")),
	});
	throwOnTextErrors(findings);
	const warnings = [...findings.warnings];
	const formatError = checkZipPrefix("Projektname", fields.name, zip).error ?? checkZipPrefix("Überschrift", fields.title, zip).error;
	if (formatError) throw new PropstackError(formatError, 400);

	// Adresse geändert → Kollision mit anderem Projekt prüfen
	let overrideReason: string | null = null;
	if (["street", "house_number", "zip_code"].some((k) => k in fields)) {
		const address = {
			house_number: String(fields.house_number ?? scalar(current.house_number) ?? ""),
			street: String(fields.street ?? scalar(current.street) ?? ""),
			zip_code: String(fields.zip_code ?? scalar(current.zip_code) ?? ""),
		};
		const dedupe = await projectDuplicates(client, address);
		const others = dedupe.duplicates.filter((d) => d.id !== input.id);
		if (others.length && !input.allow_duplicate_reason) {
			return { count: 0, result: { updated: false, blocked: "Dublette", duplicates: others, hint: "Nichts geändert – an dieser Adresse gibt es schon ein Projekt." } };
		}
		if (others.length) {
			overrideReason = input.allow_duplicate_reason!.trim();
			if (overrideReason.length < MIN_OVERRIDE_REASON) {
				throw new PropstackError(`allow_duplicate_reason braucht eine echte Begründung (mind. ${MIN_OVERRIDE_REASON} Zeichen).`, 400);
			}
		}
	}

	if (input.note_append) {
		// Der Projekt-GET liefert note nicht zurück (live 09.11.). Ohne den alten Text würde „anhängen“ ihn ersetzen.
		if (!("note" in current)) {
			throw new PropstackError(
				"Die vorhandene interne Notiz liefert Propstack über die API nicht zurück – anhängen würde sie überschreiben. Nichts geändert; bitte direkt in Propstack unter „Interne Notizen“ ergänzen.",
				400,
			);
		}
		const old = String(scalar(current.note) ?? "").trim();
		fields.note = [old, `${originNoteText(user.name, deps.now?.() ?? new Date(), "Ergänzt")}\n${input.note_append}`].filter(Boolean).join("\n\n");
		before.note = old;
	}
	const custom = await validateCustomFields(client, "for_projects", input.custom_fields);
	if (custom) {
		const currentCustom = (current.custom_fields ?? {}) as Raw;
		before.custom_fields = Object.fromEntries(Object.keys(custom.send).map((k) => [k, (currentCustom[k] as Raw | undefined)?.value ?? currentCustom[k] ?? null]));
	}

	const coordsRequested = input.lat !== undefined && input.lng !== undefined;
	if (!Object.keys(fields).length && !coordsRequested && !custom) {
		return { count: 0, result: { updated: false, id: input.id, note: "Keine Änderung – alle Werte sind bereits so gesetzt." } };
	}
	// Auch Koordinaten gehören in den Snapshot (Write-Log: Stand vorher)
	if (coordsRequested) Object.assign(before, { lat: coordsOf(current).lat ?? null, lng: coordsOf(current).lng ?? null });

	const logId = await beginWrite(deps.db, {
		action: "update",
		before,
		brokerId: user.brokerId,
		entity: "project",
		entityId: input.id,
		overrideReason,
		request: { ...fields, ...(custom ? { partial_custom_fields: custom.send } : {}), ...(coordsRequested ? { lat: input.lat, lng: input.lng } : {}) },
		tool: "update_project",
		userEmail: user.email,
		warnings,
	});
	if (Object.keys(fields).length || custom) {
		try {
			await client.updateProject(input.id, { ...fields, ...(custom ? { partial_custom_fields: custom.send } : {}) });
		} catch (error) {
			await finishWrite(deps.db, logId, { error: (error as Error).message, status: "failed" });
			throw error;
		}
	}

	// Gegenlesen; Verlorenes einzeln nachsetzen
	let actual = asObject(await client.getProject(input.id));
	let { missing, unverified } = compareProject(fields, actual, custom?.expect);
	const writeErrors: string[] = [];
	if (missing.length) {
		for (const key of missing) {
			try {
				await client.updateProject(
					input.id,
					key.startsWith("custom_fields.") ? { partial_custom_fields: { [key.slice(14)]: custom?.send[key.slice(14)] } } : { [key]: fields[key] },
				);
			} catch (error) {
				writeErrors.push(`${key}: ${(error as Error).message}`);
			}
		}
		actual = asObject(await client.getProject(input.id));
		({ missing, unverified } = compareProject(fields, actual, custom?.expect));
	}

	const coordinates = coordsRequested
		? await ensureCoordinates({
				sleep: deps.sleep,
				current: coordsOf(actual),
				provided: { lat: input.lat, lng: input.lng },
				put: (body) => client.updateProject(input.id, body),
				read: async () => coordsOf(asObject(await client.getProject(input.id))),
			})
		: undefined;
	if (coordinates && !coordinates.verified) missing.push("lat/lng");

	await finishWrite(deps.db, logId, {
		error: writeErrors.length ? writeErrors.join(" | ") : undefined,
		notApplied: [...missing, ...unverified.map((f) => `${f} (nicht prüfbar)`)],
		status: missing.length || writeErrors.length ? "done_with_gaps" : "done",
	});
	// How-to: Änderungen am Projekt kommen nicht von selbst an den Einheiten an („Daten auf Einheiten übertragen“)
	const toUnits = [...Object.keys(fields).filter((k) => UNIT_INHERITED_KEYS.includes(k)), ...(coordsRequested ? ["lat/lng"] : [])];
	return {
		count: 1,
		result: {
			updated: true,
			id: input.id,
			name: scalar(actual.name),
			changed: [...Object.keys(fields), ...Object.keys(custom?.send ?? {}).map((k) => `custom_fields.${k}`), ...(coordsRequested ? ["lat/lng"] : [])],
			coordinates,
			warnings: warnings.length ? warnings : undefined,
			not_applied: missing.length ? missing : undefined,
			not_verifiable: unverified.length ? unverified : undefined,
			write_errors: writeErrors.length ? writeErrors : undefined,
			units_hint: toUnits.length
				? `An den Einheiten des Projekts stehen weiter die alten Werte (${toUnits.join(", ")}). Übertragen: plan mit entity=objects, object_filter {project_id: ${input.id}} und denselben Werten (Koordinaten je Einheit mit update_object) – oder in Propstack „Daten auf Einheiten übertragen“.`
				: undefined,
		},
	};
}

// ---------- Eigentümer / Ansprechpartner verknüpfen ----------

export const setProjectOwnerInput = {
	project_id: id.optional().describe("Propstack-Projekt-ID"),
	object_id: id.optional().describe("Propstack-Objekt-ID (Einheit) – statt project_id"),
	contact_id: id.describe("Kontakt-ID (eigener Shop)"),
	role: z.enum(["owner", "contact_person"]).optional().describe("owner = Eigentümer (Standard) · contact_person = Ansprechpartner (verknüpfter Kontakt)"),
};

export async function setProjectOwner(deps: WriteDeps, input: z.infer<z.ZodObject<typeof setProjectOwnerInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	if ((input.project_id === undefined) === (input.object_id === undefined)) {
		throw new PropstackError("Genau eins von project_id oder object_id angeben.", 400);
	}
	const role: RelationRole = input.role ?? "owner";
	const target = input.project_id !== undefined ? { id: input.project_id, type: "project" as const } : { id: input.object_id!, type: "object" as const };
	const record = asObject(target.type === "project" ? await client.getProject(target.id) : await client.getUnit(target.id));
	const contact = asObject(await client.getContact(input.contact_id));
	const logId = await beginWrite(deps.db, {
		action: "update",
		before: null,
		brokerId: user.brokerId,
		entity: target.type,
		entityId: target.id,
		overrideReason: null,
		request: { contact_id: input.contact_id, role },
		tool: "set_project_owner",
		userEmail: user.email,
		warnings: [],
	});
	const result = await linkContact(client, target, input.contact_id, role);
	await finishWrite(deps.db, logId, {
		error: result.error,
		notApplied: result.linked === true ? [] : [`${role} ${result.linked === false ? "nicht gefunden" : "nicht prüfbar"}`],
		status: result.error ? "failed" : result.linked === true ? "done" : "done_with_gaps",
	});
	if (result.error) throw new PropstackError(result.error, 400);
	return {
		count: 1,
		result: {
			[target.type]: { id: target.id, name: scalar(record.name) ?? scalar(record.title) },
			contact: { id: input.contact_id, name: scalar(contact.name) },
			role: ROLE_LABEL[role],
			linked: result.linked,
			already_linked: result.already || undefined,
			note: result.linked === true ? result.note : (result.note ?? "Verknüpfung nicht bestätigt – bitte in der UI prüfen."),
		},
	};
}

// ---------- Bilder ----------

export const addImagesInput = {
	object_id: id.optional().describe("Objekt (Einheit), an das die Bilder kommen"),
	project_id: id.optional().describe("Projekt, an das die Bilder kommen (statt object_id) – allgemeine Bilder wie die Außenansicht gehören ans Projekt"),
	urls: z
		.array(z.string().trim().url().regex(/^https:\/\//, "nur https-URLs"))
		.min(1)
		.max(10)
		.describe("Öffentliche Bild-URLs (https). Reihenfolge = Reihenfolge in Propstack; das erste Bild eines Objekts wird Titelbild – bestes Außenfoto zuerst"),
	titles: z
		.array(z.string().trim().min(1).max(100))
		.min(1)
		.max(10)
		.describe("Pflicht: je Bild ein Titel in derselben Reihenfolge wie urls, z. B. „Außenansicht“ (How-to: Bilder müssen in Propstack benannt sein). Kein Dateiname, kein Firmen- oder Eigentümername"),
};

// Neutraler Client-Name – keine Firmen- oder Personendaten an fremde Server.
const USER_AGENT = "propstack-mcp/1.0 (CRM-Connector; Bildprüfung)";

/** Vorab prüfen, ob die URL ein erreichbares Bild ist – Propstack legt sonst ggf. leere Bildobjekte an, die nur in der UI löschbar sind. */
export async function checkImageUrl(url: string, fetchFn: typeof fetch = fetch): Promise<string | null> {
	try {
		// Ohne User-Agent blocken manche Hoster (z. B. Wikimedia) mit 403
		let response = await fetchFn(url, { headers: { "User-Agent": USER_AGENT }, method: "HEAD", redirect: "follow", signal: AbortSignal.timeout(8000) });
		if (response.status === 405 || response.status === 403) {
			response = await fetchFn(url, {
				headers: { Range: "bytes=0-0", "User-Agent": USER_AGENT },
				method: "GET",
				redirect: "follow",
				signal: AbortSignal.timeout(8000),
			});
		}
		if (!response.ok && response.status !== 206) return `nicht erreichbar (HTTP ${response.status})`;
		const type = response.headers.get("content-type") ?? "";
		if (!type.startsWith("image/")) return `kein Bild (Content-Type ${type || "unbekannt"})`;
		return null;
	} catch (error) {
		return `nicht erreichbar (${(error as Error).message})`;
	}
}

export async function addImages(
	deps: WriteDeps & { fetchFn?: typeof fetch },
	input: z.infer<z.ZodObject<typeof addImagesInput>>,
): Promise<ToolOutput> {
	const { client, user } = deps;
	if ((input.object_id === undefined) === (input.project_id === undefined)) {
		throw new PropstackError("Genau eins von object_id oder project_id angeben.", 400);
	}
	if (input.titles.length !== input.urls.length) {
		throw new PropstackError(`titles braucht genau so viele Einträge wie urls (${input.urls.length}).`, 400);
	}
	const titleProblems = input.titles.map(imageTitleProblem).filter(Boolean);
	if (titleProblems.length) throw new PropstackError(`Bildtitel ungültig: ${titleProblems.join("; ")}.`, 400);
	const target = input.object_id !== undefined ? { id: input.object_id, type: "Property" } : { id: input.project_id!, type: "Project" };

	// Ziel muss existieren (404 statt verwaister Bilder)
	if (target.type === "Property") await client.getUnit(target.id);
	else await client.getProject(target.id);

	const rejected: { url: string; reason: string }[] = [];
	const valid: { url: string; title?: string }[] = [];
	for (const [index, url] of input.urls.entries()) {
		const problem = await checkImageUrl(url, deps.fetchFn);
		if (problem) rejected.push({ reason: problem, url });
		else valid.push({ title: input.titles[index], url });
	}
	if (!valid.length) {
		return { count: 0, result: { uploaded: 0, rejected, note: "Kein Bild hochgeladen – keine der URLs ist ein erreichbares Bild." } };
	}

	const logId = await beginWrite(deps.db, {
		action: "create",
		before: null,
		brokerId: user.brokerId,
		entity: "image",
		entityId: target.id,
		overrideReason: null,
		request: { imageable_id: target.id, imageable_type: target.type, images: valid },
		tool: "add_images",
		userEmail: user.email,
		warnings: rejected.map((r) => `${r.url}: ${r.reason}`),
	});
	const uploaded: number[] = [];
	const errors: string[] = [];
	for (const { url, title } of valid) {
		try {
			const response = asObject(
				await client.createImage({ imageable_id: target.id, imageable_type: target.type, remote_photo_url: url, ...(title ? { title } : {}) }),
			);
			if (typeof response.id === "number") uploaded.push(response.id);
			else errors.push(`${url}: keine Bild-ID zurückbekommen – bitte in der UI prüfen`);
		} catch (error) {
			errors.push(`${url}: ${(error as Error).message}`);
		}
	}
	await finishWrite(deps.db, logId, {
		error: errors.length ? errors.join(" | ") : undefined,
		status: errors.length ? (uploaded.length ? "done_with_gaps" : "failed") : "done",
	});

	return {
		count: uploaded.length,
		result: {
			target: { id: target.id, type: target.type === "Property" ? "object" : "project" },
			uploaded: uploaded.length,
			image_ids: uploaded.length ? uploaded : undefined,
			rejected: rejected.length ? rejected : undefined,
			errors: errors.length ? errors : undefined,
			note: "Grundrisse in Propstack als Grundriss kennzeichnen. Bildrechte liegen beim Eigentümer/Entwickler – Portalfreigabe separat klären. Keine Firmenschriftzüge.",
		},
	};
}
