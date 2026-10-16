import type { PropstackClient } from "../propstack-client";

// Eigentümer verknüpfen – an Projekten und an Einheiten (Entscheidung Florian, 16.10.: auch an den Einheiten).
// PUT relationships_attributes mit related_client_id (nicht client_id). Prüfung über Propstack selbst:
// Ein zweiter, gleicher Aufruf wird mit „bereits mit dem Kontakt verbunden“ abgelehnt – das bestätigt die
// Verknüpfung, ohne dass etwas doppelt entsteht (Projekt-GET und Relationship-Liste sind dafür unbrauchbar).

export const ALREADY_LINKED = /existiert bereits|bereits mit dem Kontakt verbunden|bereits verbunden/i;

export type OwnerTarget = { type: "project" | "object"; id: number };

export interface OwnerResult {
	linked: boolean | "nicht prüfbar";
	already?: boolean;
	error?: string;
	note?: string;
}

export async function linkOwnerTo(
	client: Pick<PropstackClient, "updateProject" | "updateUnit">,
	target: OwnerTarget,
	contactId: number,
): Promise<OwnerResult> {
	const body = { relationships_attributes: [{ internal_name: "owner", related_client_id: contactId }] };
	const attach = () => (target.type === "project" ? client.updateProject(target.id, body) : client.updateUnit(target.id, body));
	try {
		await attach();
	} catch (error) {
		const message = (error as Error).message;
		if (ALREADY_LINKED.test(message)) return { already: true, linked: true };
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
