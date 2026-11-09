import type { PropstackClient } from "../propstack-client";

// Kontakte mit Projekten und Einheiten verknüpfen (How-to „Ansprechpartner“: Eigentümer ausfüllen,
// sofern vorhanden Kontakt hinterlegen; Entscheidung Florian, 16.10.: auch an den Einheiten).
// API-Doku „Objekte“: PUT relationships_attributes mit related_client_id (nicht client_id) –
//   Eigentümer:      { internal_name: "owner", related_client_id }
//   verknüpfter Kontakt: { internal_name: "partner", name: "<Bezeichnung>", related_client_id }
// Prüfung über Propstack selbst: Ein zweiter, gleicher Aufruf wird mit „bereits mit dem Kontakt verbunden“
// abgelehnt – das bestätigt die Verknüpfung, ohne dass etwas doppelt entsteht (Projekt-GET und
// Relationship-Liste sind dafür unbrauchbar).

export const ALREADY_LINKED = /existiert bereits|bereits mit dem Kontakt verbunden|bereits verbunden/i;

export type RelationRole = "owner" | "contact_person";
export type RelationTarget = { type: "project" | "object"; id: number };

/** Bezeichnung, unter der ein verknüpfter Kontakt in Propstack erscheint. */
export const CONTACT_PERSON_LABEL = "Ansprechpartner";

export const ROLE_LABEL: Record<RelationRole, string> = { contact_person: "Ansprechpartner", owner: "Eigentümer" };

export interface RelationResult {
	linked: boolean | "nicht prüfbar";
	already?: boolean;
	error?: string;
	note?: string;
}

export function relationBody(contactId: number, role: RelationRole): Record<string, unknown> {
	return {
		relationships_attributes: [
			role === "owner"
				? { internal_name: "owner", related_client_id: contactId }
				: { internal_name: "partner", name: CONTACT_PERSON_LABEL, related_client_id: contactId },
		],
	};
}

export async function linkContact(
	client: Pick<PropstackClient, "updateProject" | "updateUnit">,
	target: RelationTarget,
	contactId: number,
	role: RelationRole = "owner",
): Promise<RelationResult> {
	const body = relationBody(contactId, role);
	const attach = () => (target.type === "project" ? client.updateProject(target.id, body) : client.updateUnit(target.id, body));
	try {
		await attach();
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
	client: Pick<PropstackClient, "updateProject" | "updateUnit">,
	target: RelationTarget,
	contactId: number,
): Promise<RelationResult> {
	return linkContact(client, target, contactId, "owner");
}

export type OwnerResult = RelationResult;
export type OwnerTarget = RelationTarget;
