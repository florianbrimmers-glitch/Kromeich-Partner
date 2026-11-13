import { z } from "zod";
import { PropstackError, type PropstackClient } from "../propstack-client";
import { companyCandidates, companyDuplicates, isCompanyRow, strictCompanyName } from "../propstack/companies";
import { normalizeCompany } from "../propstack/dedupe";
import { scalar } from "../propstack/mappers";
import { beginWrite, finishWrite } from "../write-log";
import { id, optionalText } from "./params";
import type { ToolOutput } from "./read-tools";
import {
	asObjectOrThrow,
	checkOverride,
	createContact,
	type createContactInput,
	createdId,
	ensureTestTag,
	groupIdsOf,
	notApplied,
	originNote,
	TEST_TAG,
	type WriteDeps,
} from "./write-tools";

// Firmen-Datensätze und die Verknüpfung Person ↔ Firma (Entscheidung Florian, 12.11.2026).
//
// Anlass: Der tägliche Kontakt-Import (GitHub-Job „Daily Contact Import“, src/propstack_client.py) legt zu jedem neuen
// Kontakt die Firma als eigenen Datensatz an und verknüpft beide. Kontakte, die über Claude entstehen, bekamen das nicht.
//
// Beides geht nur über die V2-Schnittstelle von Propstack (eigener Schlüssel PROPSTACK_API_KEY_V2):
//   - Firma: Kontakt mit commercial: true, Name im Feld company, ohne Nachnamen (sonst zeigt Propstack „X (X)“ an).
//   - Verknüpfung: POST /v2/relationships mit internal_name "associate", client_id = Person, related_client_id = Firma
//     und name "Mitarbeiter".
//
// Zur Bezeichnung – berichtigt am 13.11.2026 nach einem Blick in die Propstack-Oberfläche (Bildschirmfoto Florian):
// Propstack führt jede Verknüpfung als zwei Zeilen – die angelegte und die Gegenrichtung, die es selbst ergänzt.
// name beschreibt client_id und wird am ANDEREN Kontakt angezeigt: Die Zeile {client_id: Person, related: Firma,
// name: "Mitarbeiter"} erscheint an der Firma als „Person · Mitarbeiter“; die Gegenzeile {client_id: Firma,
// related: Person, name: "Firma"} erscheint am Kontakt als „Firma · Firma“. Eine Kontaktseite zeigt also die Zeilen,
// in denen der Kontakt der verknüpfte (related_client) ist – dieselbe Sicht wie GET /v1/contacts/:id?include=relationships.
//
// Richtig ist deshalb name "Mitarbeiter" an der Zeile der Person – so macht es der tägliche Import seit jeher, und
// so sehen 83 von 87 von Hand angelegten Verknüpfungen aus. Die Fassungen 0.11.0–0.12.0 schickten "Firma": Dann
// steht am Kontakt die Firma als „Mitarbeiter“ und an der Firma die Person als „Firma“. Das war ein Fehlschluss aus
// den Rohdaten (Annahme: name beschreibe den verknüpften Kontakt), ohne die Oberfläche gesehen zu haben.
// Verknüpfungen in dieser Form meldet das Tool als vertauscht.
//
// Gelesen und geprüft wird weiter über V1 (is_company, Suche), die Verknüpfungen über GET /v2/relationships
// (liefert zu client_id nur die Zeilen der eigenen Seite). Kein Löschen, kein Ändern bestehender Verknüpfungen.

type Raw = Record<string, unknown>;

type CompanyClient = Pick<
	PropstackClient,
	"searchContacts" | "getContact" | "getContactRelationships" | "listGroups" | "createGroup" | "createClientV2" | "updateClientV2" | "listRelationshipsV2" | "createRelationshipV2" | "hasV2Key"
>;

const MISSING_V2_KEY = "Für Firmen und Verknüpfungen zwischen Kontakten fehlt dem Server der zweite Propstack-Schlüssel (PROPSTACK_API_KEY_V2).";

/** Die Zeile der Person: Sie ist „Mitarbeiter“ der Firma. Diese Bezeichnung zeigt Propstack an der Firma. */
export const EMPLOYEE_RELATION = { internal_name: "associate", name: "Mitarbeiter" } as const;
/** Die Gegenzeile ergänzt Propstack selbst: „Firma“ – das zeigt es am Kontakt. */
const COMPANY_LABEL = "Firma";

// ---------- create_company ----------

export const createCompanyInput = {
	name: z.string().trim().min(2).max(200).describe("Firmenname, so wie er in Propstack stehen soll, z. B. „Goodman Germany GmbH“"),
	street: optionalText(200),
	house_number: optionalText(20),
	zip_code: optionalText(10),
	city: optionalText(100),
	country: optionalText(60),
	phone_office: optionalText(50).describe("Telefon der Zentrale"),
	website: z
		.string()
		.trim()
		.max(300)
		.regex(/^https?:\/\/\S+$/)
		.optional()
		.describe("Website mit http:// oder https://"),
	tag_ids: z.array(id).min(1).max(20).optional().describe("Merkmal-IDs (über list_tags entity=contacts)"),
	description: optionalText(2000).describe("Notiz zur Firma"),
	test: z.boolean().optional().describe(`Testdatensatz: setzt das Merkmal ${TEST_TAG}. Für alle Tests Pflicht.`),
	allow_duplicate_reason: optionalText(500).describe("Nur wenn die Dublettenprüfung blockiert und es nachweislich eine andere Firma ist: Begründung (wird protokolliert)"),
};

const COMPANY_KEYS: Record<string, string> = {
	city: "office_city",
	country: "office_country",
	house_number: "office_house_number",
	phone_office: "office_phone",
	street: "office_street",
	website: "office_url",
	zip_code: "office_zip_code",
};

type CompanyInput = z.infer<z.ZodObject<typeof createCompanyInput>>;

/** Firmen-Datensatz anlegen und gegenlesen – ohne Dublettenprüfung, die macht der Aufrufer. */
async function insertCompany(
	deps: WriteDeps,
	input: CompanyInput,
	log: { overrideReason: string | null; tool: string; warnings: string[] },
): Promise<{ actual: Raw; id: number; missing: string[] }> {
	const client: CompanyClient = deps.client;
	const { user } = deps;
	const now = deps.now?.() ?? new Date();
	const tags = [...(input.tag_ids ?? [])];
	if (input.test) tags.push(await ensureTestTag(deps.client, "for_clients"));

	const fields: Raw = { company: input.name };
	for (const [from, to] of Object.entries(COMPANY_KEYS)) {
		const value = (input as Raw)[from];
		if (value !== undefined) fields[to] = value;
	}
	const payload: Raw = {
		...fields,
		broker_id: user.brokerId,
		commercial: true,
		description: [input.description, originNote(user, now, "Angelegt")].filter(Boolean).join("\n\n"),
		...(tags.length ? { group_ids: tags } : {}),
	};

	const logId = await beginWrite(deps.db, {
		action: "create",
		before: null,
		brokerId: user.brokerId,
		entity: "contact",
		entityId: null,
		overrideReason: log.overrideReason,
		request: payload,
		tool: log.tool,
		userEmail: user.email,
		warnings: log.warnings,
	});

	let newId: number;
	try {
		newId = createdId(await client.createClientV2(payload));
	} catch (error) {
		await finishWrite(deps.db, logId, { error: (error as Error).message, status: "failed" });
		throw error;
	}

	let actual = await asObjectOrThrow(client.getContact(newId));
	const missing = notApplied({ ...fields, broker_id: user.brokerId }, actual);
	// Kennzeichnung als Firma: Hat der erste Aufruf sie nicht gesetzt, einmal einzeln nachsetzen (so macht es der tägliche Import).
	if (actual.is_company !== true) {
		try {
			await client.updateClientV2(newId, { commercial: true, company: input.name, last_name: null });
			actual = await asObjectOrThrow(client.getContact(newId));
		} catch (error) {
			missing.push(`commercial (Nachsetzen fehlgeschlagen: ${(error as Error).message})`);
		}
		if (actual.is_company !== true && !missing.some((entry) => entry.startsWith("commercial"))) {
			missing.push("commercial (der Datensatz ist nicht als Firma gekennzeichnet – bitte in Propstack prüfen)");
		}
	}
	const groups = groupIdsOf(actual);
	for (const tag of tags) if (!groups.includes(tag)) missing.push(`tag ${tag}`);
	await finishWrite(deps.db, logId, { entityId: newId, notApplied: missing, status: missing.length ? "done_with_gaps" : "done" });
	return { actual, id: newId, missing };
}

export async function createCompany(deps: WriteDeps, input: CompanyInput): Promise<ToolOutput> {
	const client: CompanyClient = deps.client;
	if (!client.hasV2Key) throw new PropstackError(MISSING_V2_KEY, 0);

	const dedupe = companyDuplicates(input.name, await companyCandidates(client, input.name));
	if (dedupe.duplicates.length && !input.allow_duplicate_reason) {
		return {
			count: 0,
			result: {
				created: false,
				blocked: "Dublette",
				duplicates: dedupe.duplicates,
				warnings: dedupe.warnings.length ? dedupe.warnings : undefined,
				hint: "Nichts angelegt – die Firma gibt es schon. Diesen Datensatz verwenden (z. B. für link_contact_company). Nur falls es nachweislich eine andere Firma ist: mit allow_duplicate_reason erneut aufrufen.",
			},
		};
	}
	const overrideReason = checkOverride(dedupe, input.allow_duplicate_reason);
	const { actual, id: newId, missing } = await insertCompany(deps, input, { overrideReason, tool: "create_company", warnings: dedupe.warnings });

	return {
		count: 1,
		result: {
			created: true,
			id: newId,
			name: scalar(actual.name) ?? input.name,
			is_company: actual.is_company === true,
			broker: deps.user.name,
			test: input.test || undefined,
			override_reason: overrideReason ?? undefined,
			warnings: dedupe.warnings.length ? dedupe.warnings : undefined,
			not_applied: missing.length ? missing : undefined,
			note: missing.length ? "Propstack hat nicht alles übernommen – bitte prüfen." : undefined,
			next: "Personen dieser Firma mit link_contact_company verknüpfen.",
		},
	};
}

// ---------- link_contact_company ----------

export const linkContactCompanyInput = {
	contact_id: id.describe("Propstack-ID der Person"),
	company_id: id.describe("Propstack-ID des Firmen-Datensatzes (über search_contacts oder create_company)"),
};

/** Beide Zeilen einer Verknüpfung Person ↔ Firma, soweit vorhanden. */
type LinkState = {
	/** Zeile der Person (client_id = Person, related_client_id = Firma) – ihre Bezeichnung zeigt Propstack an der Firma. */
	own?: Raw;
	/** Zeile der Firma (client = Firma, related_client = Person) – ihre Bezeichnung zeigt Propstack am Kontakt. */
	shownAtContact?: Raw;
};

/**
 * Stand der Verknüpfung lesen. Die Zeile der Person kommt über GET /v2/relationships (liefert zu client_id nur die
 * eigenen Zeilen), die Gegenzeile über GET /v1/contacts/:id?include=relationships der Person (liefert die Zeilen, in
 * denen sie der verknüpfte Kontakt ist – das, was ihre Kontaktseite anzeigt).
 */
async function linkState(client: CompanyClient, contactId: number, companyId: number, personRaw?: Raw): Promise<LinkState> {
	const person = personRaw ?? (await asObjectOrThrow(client.getContactRelationships(contactId)));
	const shown = (Array.isArray(person.relationships) ? person.relationships : []).find((row) => {
		const raw = (row && typeof row === "object" ? row : {}) as Raw;
		return Number((raw.client as Raw | null | undefined)?.id) === companyId && !raw.property && !raw.project;
	}) as Raw | undefined;
	const { rows } = await client.listRelationshipsV2({ client_id: contactId, internal_name: EMPLOYEE_RELATION.internal_name, per: 100 });
	return { own: rows.find((row) => Number(row.client_id) === contactId && Number(row.related_client_id) === companyId), shownAtContact: shown };
}

function labelOf(row: Raw | undefined): string | undefined {
	const label = typeof row?.name === "string" ? row.name.trim() : "";
	return label === "" ? undefined : label;
}

export async function linkContactCompany(deps: WriteDeps, input: z.infer<z.ZodObject<typeof linkContactCompanyInput>>, tool = "link_contact_company"): Promise<ToolOutput> {
	const client: CompanyClient = deps.client;
	const { user } = deps;
	if (!client.hasV2Key) throw new PropstackError(MISSING_V2_KEY, 0);
	if (input.contact_id === input.company_id) throw new PropstackError("contact_id und company_id sind derselbe Datensatz.", 400);

	const person = await asObjectOrThrow(client.getContactRelationships(input.contact_id));
	const company = await asObjectOrThrow(client.getContact(input.company_id));
	const personName = String(scalar(person.name) ?? `Kontakt ${input.contact_id}`);
	const companyName = String(scalar(company.name) ?? scalar(company.company) ?? `Kontakt ${input.company_id}`);
	if (isCompanyRow(person)) {
		throw new PropstackError(`${personName} (${input.contact_id}) ist selbst ein Firmen-Datensatz. Als contact_id gehört die Person hierher, als company_id die Firma.`, 400);
	}
	if (!isCompanyRow(company)) {
		throw new PropstackError(
			`${companyName} (${input.company_id}) ist kein Firmen-Datensatz, sondern eine Person. Den Firmen-Datensatz mit search_contacts suchen (is_company: true) oder mit create_company anlegen.`,
			400,
		);
	}

	// Steht am Kontakt als Firma etwas anderes als der Name des Firmen-Datensatzes? Nur ein Hinweis – verknüpft wird trotzdem.
	const companyText = String(scalar(person.company) ?? "").trim();
	const mismatch =
		companyText && normalizeCompany(companyText) !== normalizeCompany(scalar(company.company) ?? companyName) && strictCompanyName(companyText) !== strictCompanyName(companyName)
			? `Am Kontakt steht als Firma „${companyText}“, der Firmen-Datensatz heißt „${companyName}“ – bitte prüfen, ob es dieselbe Firma ist.`
			: undefined;
	const base = { company: { id: input.company_id, name: companyName }, contact: { id: input.contact_id, name: personName } };
	const lower = (row: Raw | undefined) => labelOf(row)?.toLowerCase();
	const warningsFor = (state: LinkState) => {
		// vertauscht: Am Kontakt erscheint die Firma als „Mitarbeiter“ bzw. an der Firma die Person als „Firma“
		const swapped =
			lower(state.shownAtContact) === EMPLOYEE_RELATION.name.toLowerCase() || lower(state.own) === COMPANY_LABEL.toLowerCase()
				? `Die Verknüpfung ist vertauscht beschriftet: Am Kontakt steht die Firma als „${labelOf(state.shownAtContact) ?? "?"}“, an der Firma die Person als „${labelOf(state.own) ?? "?"}“ – üblich ist es umgekehrt. Korrigieren lässt sich das nur in Propstack.`
				: undefined;
		const list = [mismatch, swapped].filter((entry): entry is string => !!entry);
		return list.length ? list : undefined;
	};
	const linked = (state: LinkState, count: number): ToolOutput => ({
		count,
		result: {
			linked: true,
			already_linked: count === 0 ? true : undefined,
			...base,
			label: labelOf(state.shownAtContact),
			label_at_company: labelOf(state.own),
			relationship_id: (state.own ?? state.shownAtContact)?.id,
			warnings: warningsFor(state),
		},
	});
	const exists = (state: LinkState) => !!state.own || !!state.shownAtContact;

	const before = await linkState(client, input.contact_id, input.company_id, person);
	if (exists(before)) return linked(before, 0);

	const request = { ...EMPLOYEE_RELATION, client_id: input.contact_id, related_client_id: input.company_id };
	const logId = await beginWrite(deps.db, {
		action: "update",
		before: null,
		brokerId: user.brokerId,
		entity: "contact",
		entityId: input.contact_id,
		overrideReason: null,
		request,
		tool,
		userEmail: user.email,
		warnings: mismatch ? [mismatch] : [],
	});

	try {
		await client.createRelationshipV2(request);
	} catch (error) {
		// 422 heißt bei Propstack oft „gibt es schon“ – aber nicht immer. Deshalb nachsehen statt annehmen.
		const now = error instanceof PropstackError && error.status === 422 ? await linkState(client, input.contact_id, input.company_id).catch(() => undefined) : undefined;
		if (now && exists(now)) {
			await finishWrite(deps.db, logId, { status: "done" });
			return linked(now, 0);
		}
		await finishWrite(deps.db, logId, { error: (error as Error).message, status: "failed" });
		throw error;
	}

	// Gegenlesen: Die angelegte Zeile muss jetzt in Propstack stehen.
	let after: LinkState | undefined;
	let checkError: string | undefined;
	try {
		after = await linkState(client, input.contact_id, input.company_id);
	} catch (error) {
		checkError = (error as Error).message;
	}
	if (after?.own) {
		await finishWrite(deps.db, logId, { status: "done" });
		return linked(after, 1);
	}
	await finishWrite(deps.db, logId, {
		notApplied: [checkError ? `Verknüpfung nicht prüfbar (${checkError})` : "Verknüpfung steht beim Gegenlesen nicht in Propstack"],
		status: "done_with_gaps",
	});
	return {
		count: 0,
		result: {
			linked: checkError ? "nicht prüfbar" : false,
			...base,
			warnings: mismatch ? [mismatch] : undefined,
			note: "Propstack hat den Aufruf angenommen, die Verknüpfung ließ sich aber nicht bestätigen – bitte am Kontakt unter „Verknüpfte Kontakte“ prüfen.",
		},
	};
}

// ---------- create_contact: Firma automatisch verknüpfen ----------
// Entscheidung Florian, 12.11.2026: „Die Firmenverknüpfung soll bitte immer gesetzt werden“ – wie in den Import-Jobs,
// ohne dass jemand etwas tun muss. Nach dem Anlegen der Person wird deshalb der Firmen-Datensatz gesucht, bei Bedarf
// angelegt (mit der Geschäftsadresse des Kontakts, wie im Import) und verknüpft.
//
// Eine Ausnahme, damit dabei keine Firmen-Dubletten entstehen: Gibt es keinen gleichnamigen, aber einen ähnlich
// benannten Firmen-Datensatz („Goodman“ neben „Goodman Germany GmbH“ – so steht es seit dem Import vom 02.09.2026 im
// Konto), oder passen mehrere, wird nichts geraten. Das Ergebnis nennt die Kandidaten, entschieden wird mit
// link_contact_company. Der Kontakt selbst ist in jedem Fall angelegt; ein Fehler bei der Firma macht daraus keinen
// Fehler des Tools.

type ContactInput = z.infer<z.ZodObject<typeof createContactInput>>;

export async function createContactLinked(deps: WriteDeps, input: ContactInput): Promise<ToolOutput> {
	const out = await createContact(deps, input);
	const result = out.result as Raw;
	const company = input.company?.trim();
	if (result.created !== true || typeof result.id !== "number" || !company) return out;
	return { ...out, result: { ...result, company_link: await linkToCompany(deps, result.id, company, input) } };
}

async function linkToCompany(deps: WriteDeps, contactId: number, company: string, input: ContactInput): Promise<Raw> {
	const client: CompanyClient = deps.client;
	const later = `Nachholen mit link_contact_company (contact_id ${contactId}).`;
	if (!client.hasV2Key) return { linked: false, hint: `Nicht verknüpft: ${MISSING_V2_KEY}` };
	if (company.length < 2) return { linked: false, hint: `Nicht verknüpft: „${company}“ ist als Firmenname zu kurz. ${later}` };
	let found: { id: number; name: string } | undefined;
	let created = false;
	let gaps: string[] = [];
	try {
		const dedupe = companyDuplicates(company, await companyCandidates(client, company));
		const exact = dedupe.duplicates.filter((d) => strictCompanyName(d.name) === strictCompanyName(company));
		const match = dedupe.duplicates.length === 1 ? dedupe.duplicates[0] : exact.length === 1 ? exact[0] : undefined;
		found = match && { id: match.id, name: match.name };
		if (!found && dedupe.duplicates.length) {
			return {
				linked: false,
				candidates: dedupe.duplicates.map((d) => ({ id: d.id, name: d.name })),
				hint: `Mehrere Firmen-Datensätze passen zu „${company}“ – nicht automatisch verknüpft. Den richtigen mit link_contact_company wählen (contact_id ${contactId}).`,
			};
		}
		if (!found && dedupe.warnings.length) {
			return {
				linked: false,
				similar: dedupe.warnings,
				hint: `Für „${company}“ gibt es keinen gleichnamigen, aber einen ähnlich benannten Firmen-Datensatz – deshalb keine neue Firma angelegt. Ist es dieselbe Firma: link_contact_company (contact_id ${contactId}) mit deren ID. Ist es eine andere: create_company, dann link_contact_company.`,
			};
		}
		if (!found) {
			const { street, house_number, zip_code, city, country, test } = input;
			const inserted = await insertCompany(deps, { city, country, house_number, name: company, street, test, zip_code }, { overrideReason: null, tool: "create_contact", warnings: [] });
			found = { id: inserted.id, name: String(scalar(inserted.actual.name) ?? company) };
			created = true;
			gaps = inserted.missing;
		}
		const link = (await linkContactCompany(deps, { company_id: found.id, contact_id: contactId }, "create_contact")).result as Raw;
		return {
			linked: link.linked,
			company: found,
			company_created: created || undefined,
			company_not_applied: gaps.length ? gaps : undefined,
			label: link.label,
			warnings: link.warnings,
			note: link.note,
		};
	} catch (error) {
		return {
			linked: false,
			company: found,
			company_created: created || undefined,
			hint: `Der Kontakt ist angelegt, die Verknüpfung mit der Firma nicht: ${(error as Error).message} ${later}`,
		};
	}
}
