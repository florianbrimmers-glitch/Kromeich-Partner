import { z } from "zod";
import { PropstackError, type PropstackClient } from "../propstack-client";
import { companyCandidates, companyDuplicates, isCompanyRow, strictCompanyName } from "../propstack/companies";
import { normalizeCompany } from "../propstack/dedupe";
import { scalar } from "../propstack/mappers";
import { beginWrite, finishWrite } from "../write-log";
import { id, optionalText } from "./params";
import type { ToolOutput } from "./read-tools";
import { asObjectOrThrow, checkOverride, createdId, ensureTestTag, groupIdsOf, notApplied, originNote, TEST_TAG, type WriteDeps } from "./write-tools";

// Firmen-Datensätze und die Verknüpfung Person ↔ Firma (Entscheidung Florian, 12.11.2026).
//
// Anlass: Der tägliche Kontakt-Import (GitHub-Job „Daily Contact Import“, src/propstack_client.py) legt zu jedem neuen
// Kontakt die Firma als eigenen Datensatz an und verknüpft beide. Kontakte, die über Claude entstehen, bekamen das nicht.
//
// Beides geht nur über die V2-Schnittstelle von Propstack (eigener Schlüssel PROPSTACK_API_KEY_V2):
//   - Firma: Kontakt mit commercial: true, Name im Feld company, ohne Nachnamen (sonst zeigt Propstack „X (X)“ an).
//   - Verknüpfung: POST /v2/relationships mit internal_name "associate", client_id = Person, related_client_id = Firma
//     und name "Firma".
//
// Zur Bezeichnung (live geprüft am 12.11.2026 an allen 5.149 Kontakt-Verknüpfungen des Kontos): Propstack führt jede
// Verknüpfung als zwei Zeilen – die angelegte und die Gegenrichtung, die es selbst ergänzt. name bezeichnet dabei den
// verknüpften Kontakt (related_client) aus Sicht von client_id. In der Oberfläche angelegte Verknüpfungen sehen so aus:
//     Person → Firma: „Firma“          Firma → Person: „Mitarbeiter“
// Genau das entsteht mit name "Firma" (so macht es auch personalkarussell_handler). Der tägliche Import schickt dagegen
// name "Mitarbeiter" – dann steht am Kontakt die Firma als „Mitarbeiter“ und an der Firma die Person als „Firma“
// (rund 220 Verknüpfungen). Das wird hier nicht nachgemacht; solche Verknüpfungen meldet das Tool als vertauscht.
//
// Gelesen und geprüft wird weiter über V1 (is_company, Suche), die Verknüpfungen über GET /v2/relationships
// (liefert zu client_id nur die Zeilen der eigenen Seite). Kein Löschen, kein Ändern bestehender Verknüpfungen.

type Raw = Record<string, unknown>;

type CompanyClient = Pick<
	PropstackClient,
	"searchContacts" | "getContact" | "listGroups" | "createGroup" | "createClientV2" | "updateClientV2" | "listRelationshipsV2" | "createRelationshipV2" | "hasV2Key"
>;

const MISSING_V2_KEY = "Für Firmen und Verknüpfungen zwischen Kontakten fehlt dem Server der zweite Propstack-Schlüssel (PROPSTACK_API_KEY_V2).";

/** Art und Bezeichnung der Verknüpfung aus Sicht der Person: Der verknüpfte Kontakt ist ihre „Firma“. */
export const COMPANY_RELATION = { internal_name: "associate", name: "Firma" } as const;
/** So bezeichnet Propstack die Gegenrichtung (Firma → Person). Steht das am Kontakt, ist die Verknüpfung vertauscht beschriftet. */
const REVERSE_LABEL = "mitarbeiter";

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

export async function createCompany(deps: WriteDeps, input: z.infer<z.ZodObject<typeof createCompanyInput>>): Promise<ToolOutput> {
	const client: CompanyClient = deps.client;
	const { user } = deps;
	const now = deps.now?.() ?? new Date();
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
		overrideReason,
		request: payload,
		tool: "create_company",
		userEmail: user.email,
		warnings: dedupe.warnings,
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

	return {
		count: 1,
		result: {
			created: true,
			id: newId,
			name: scalar(actual.name) ?? input.name,
			is_company: actual.is_company === true,
			broker: user.name,
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

/**
 * Die Verknüpfung aus Sicht der Person (client_id = Person, related_client_id = Firma), falls es sie gibt.
 * Propstack liefert zu client_id nur die Zeilen der eigenen Seite; die Gegenrichtung steht bei der Firma.
 */
async function personSideLink(client: Pick<PropstackClient, "listRelationshipsV2">, contactId: number, companyId: number): Promise<Raw | undefined> {
	const { rows } = await client.listRelationshipsV2({ client_id: contactId, internal_name: COMPANY_RELATION.internal_name, per: 100 });
	return rows.find((row) => Number(row.client_id) === contactId && Number(row.related_client_id) === companyId);
}

/** Bezeichnung der Verknüpfung, wie sie am Kontakt steht. */
function labelOf(row: Raw | undefined): string | undefined {
	const label = typeof row?.name === "string" ? row.name.trim() : "";
	return label === "" ? undefined : label;
}

export async function linkContactCompany(deps: WriteDeps, input: z.infer<z.ZodObject<typeof linkContactCompanyInput>>): Promise<ToolOutput> {
	const client: CompanyClient = deps.client;
	const { user } = deps;
	if (!client.hasV2Key) throw new PropstackError(MISSING_V2_KEY, 0);
	if (input.contact_id === input.company_id) throw new PropstackError("contact_id und company_id sind derselbe Datensatz.", 400);

	const person = await asObjectOrThrow(client.getContact(input.contact_id));
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
	const warningsFor = (row: Raw | undefined) => {
		const swapped =
			labelOf(row)?.toLowerCase() === REVERSE_LABEL
				? `Die Verknüpfung ist vertauscht beschriftet: Am Kontakt steht die Firma als „${labelOf(row)}“ statt als „${COMPANY_RELATION.name}“. Korrigieren lässt sich das nur in Propstack.`
				: undefined;
		const list = [mismatch, swapped].filter((entry): entry is string => !!entry);
		return list.length ? list : undefined;
	};
	const linked = (row: Raw, count: number): ToolOutput => ({
		count,
		result: { linked: true, already_linked: count === 0 ? true : undefined, ...base, label: labelOf(row), relationship_id: row.id, warnings: warningsFor(row) },
	});

	const before = await personSideLink(client, input.contact_id, input.company_id);
	if (before) return linked(before, 0);

	const request = { ...COMPANY_RELATION, client_id: input.contact_id, related_client_id: input.company_id };
	const logId = await beginWrite(deps.db, {
		action: "update",
		before: null,
		brokerId: user.brokerId,
		entity: "contact",
		entityId: input.contact_id,
		overrideReason: null,
		request,
		tool: "link_contact_company",
		userEmail: user.email,
		warnings: mismatch ? [mismatch] : [],
	});

	try {
		await client.createRelationshipV2(request);
	} catch (error) {
		// 422 heißt bei Propstack oft „gibt es schon“ – aber nicht immer. Deshalb nachsehen statt annehmen.
		const exists = error instanceof PropstackError && error.status === 422 ? await personSideLink(client, input.contact_id, input.company_id).catch(() => undefined) : undefined;
		if (exists) {
			await finishWrite(deps.db, logId, { status: "done" });
			return linked(exists, 0);
		}
		await finishWrite(deps.db, logId, { error: (error as Error).message, status: "failed" });
		throw error;
	}

	// Gegenlesen: Die Verknüpfung muss jetzt in Propstack stehen.
	let after: Raw | undefined;
	let checkError: string | undefined;
	try {
		after = await personSideLink(client, input.contact_id, input.company_id);
	} catch (error) {
		checkError = (error as Error).message;
	}
	if (after) {
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
			warnings: warningsFor(undefined),
			note: "Propstack hat den Aufruf angenommen, die Verknüpfung ließ sich aber nicht bestätigen – bitte am Kontakt unter „Verknüpfte Kontakte“ prüfen.",
		},
	};
}
