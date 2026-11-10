import type { PropstackClient } from "../propstack-client";

// Kontakte mit Projekten und Einheiten verknüpfen (How-to „Ansprechpartner“: Eigentümer ausfüllen,
// sofern vorhanden Kontakt hinterlegen; Entscheidung Florian, 16.10.: auch an den Einheiten).
// API-Doku „Objekte“: PUT relationships_attributes mit related_client_id (nicht client_id) –
//   Eigentümer:          { internal_name: "owner", related_client_id }
//   verknüpfter Kontakt: { internal_name: "partner", related_client_id }
// Von Hand hinterlegte Kontakte haben keine Bezeichnung (name leer, live 09.11. an Herford 6324578) –
// deshalb ohne name; nur wenn Propstack einen verlangt, mit „Ansprechpartner“.
//
// Prüfung:
// - Einheiten: Der Einzel-GET liefert relationships [{internal_name, client_id}] → direkt gegenlesen.
// - Projekte (und falls die Liste fehlt): Gegenprobe. Ein zweiter, gleicher Aufruf wird mit „bereits mit dem
//   Kontakt verbunden“ abgelehnt – das bestätigt die Verknüpfung, ohne dass etwas doppelt entsteht.

type Raw = Record<string, unknown>;

export const ALREADY_LINKED = /existiert bereits|bereits mit dem Kontakt verbunden|bereits verbunden/i;

export type RelationRole = "owner" | "contact_person";
export type RelationTarget = { type: "project" | "object"; id: number };

/** Bezeichnung, falls Propstack für einen verknüpften Kontakt eine verlangt. */
export const CONTACT_PERSON_LABEL = "Ansprechpartner";

export const ROLE_LABEL: Record<RelationRole, string> = { contact_person: "Ansprechpartner", owner: "Eigentümer" };
const INTERNAL_NAME: Record<RelationRole, string> = { contact_person: "partner", owner: "owner" };

export interface RelationResult {
	linked: boolean | "nicht prüfbar";
	already?: boolean;
	error?: string;
	note?: string;
}

export function relationBody(contactId: number, role: RelationRole, withLabel = false): Record<string, unknown> {
	return {
		relationships_attributes: [
			{ internal_name: INTERNAL_NAME[role], ...(role === "contact_person" && withLabel ? { name: CONTACT_PERSON_LABEL } : {}), related_client_id: contactId },
		],
	};
}

type LinkClient = Pick<PropstackClient, "updateProject" | "updateUnit"> & Partial<Pick<PropstackClient, "getUnit">>;

/** Ist der Kontakt in dieser Rolle an der Einheit verknüpft? undefined = Propstack liefert die Liste nicht. */
async function unitHasLink(client: LinkClient, unitId: number, contactId: number, role: RelationRole): Promise<boolean | undefined> {
	if (!client.getUnit) return undefined;
	try {
		const list = ((await client.getUnit(unitId)) as Raw | null)?.relationships;
		if (!Array.isArray(list)) return undefined;
		return list.some((entry) => (entry as Raw)?.internal_name === INTERNAL_NAME[role] && Number((entry as Raw)?.client_id) === contactId);
	} catch {
		return undefined;
	}
}

export async function linkContact(
	client: LinkClient,
	target: RelationTarget,
	contactId: number,
	role: RelationRole = "owner",
	options: { /** frisch angelegt: es kann noch keine Verknüpfung geben */ fresh?: boolean } = {},
): Promise<RelationResult> {
	const attach = (withLabel = false) => {
		const body = relationBody(contactId, role, withLabel);
		return target.type === "project" ? client.updateProject(target.id, body) : client.updateUnit(target.id, body);
	};
	const readable = target.type === "object";
	if (readable && !options.fresh && (await unitHasLink(client, target.id, contactId, role)) === true) return { already: true, linked: true };

	try {
		try {
			await attach();
		} catch (error) {
			// Verlangt Propstack eine Bezeichnung, einmal mit „Ansprechpartner“ wiederholen
			if (role !== "contact_person" || ALREADY_LINKED.test((error as Error).message) || !/\bname\b/i.test((error as Error).message)) throw error;
			await attach(true);
		}
	} catch (error) {
		const message = (error as Error).message;
		if (ALREADY_LINKED.test(message)) {
			return {
				already: true,
				linked: true,
				note: role === "contact_person" ? "Der Kontakt war bereits verknüpft – ggf. in anderer Rolle (z. B. als Eigentümer)." : undefined,
			};
		}
		if (/Shop/i.test(message)) {
			return { error: `${message} – der Kontakt gehört zu einem fremden Shop. Bitte den Kontakt aus dem eigenen Shop (Kromeich GmbH) verwenden.`, linked: false };
		}
		return { error: message, linked: false };
	}

	if (readable && (await unitHasLink(client, target.id, contactId, role)) === true) return { linked: true };
	try {
		await attach();
		// Zweiter Aufruf angenommen → Propstack hat die erste Verknüpfung nicht gespeichert oder lässt Doppelte zu
		return { linked: "nicht prüfbar", note: "Propstack hat die Verknüpfung zweimal angenommen – bitte in der UI prüfen, ob sie (ggf. doppelt) vorhanden ist." };
	} catch (error) {
		if (ALREADY_LINKED.test((error as Error).message)) return { linked: true };
		return { linked: "nicht prüfbar", note: `Gegenprobe nicht eindeutig: ${(error as Error).message}` };
	}
}

/** Zeile für die Prüfaufgabe. */
export function relationLine(role: RelationRole, contact: { id: number; name: string } | undefined, result: RelationResult | undefined): string {
	if (!contact) return `${ROLE_LABEL[role]}: nicht verknüpft`;
	return `${ROLE_LABEL[role]}: ${contact.name} (${contact.id})${result?.linked === true ? "" : " – Verknüpfung prüfen"}`;
}

/** Kompatibel zu früher: Eigentümer verknüpfen. */
export function linkOwnerTo(
	client: LinkClient,
	target: RelationTarget,
	contactId: number,
): Promise<RelationResult> {
	return linkContact(client, target, contactId, "owner");
}

export type OwnerResult = RelationResult;
export type OwnerTarget = RelationTarget;
