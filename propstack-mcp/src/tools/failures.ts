// Maschinenlesbare Liste der Teilschritte, die beim Anlegen nicht geklappt haben (Auftrag 26.11.2026, Objekte
// Handler: „Bisher verlasse ich mich darauf, dass die KI es meldet“). Steht in create_object und create_project
// immer im Ergebnis unter `fehlgeschlagen` – leer, wenn alles geklappt hat. Die bisherigen Felder (not_applied,
// not_verifiable, write_errors, review_task.error) bleiben daneben bestehen.

export interface Failure {
	schritt: string;
	grund: string;
}

/** Schritt-Namen für die Kürzel aus not_applied bzw. write_errors. */
function stepOf(key: string): string {
	if (key === "lat/lng") return "Koordinaten";
	if (key === "owner" || key === "Eigentümer") return "Eigentümer verknüpfen";
	if (key === "contact_person" || key === "Ansprechpartner") return "Ansprechpartner verknüpfen";
	if (key.startsWith("tag ")) return `Merkmal ${key.slice(4)}`;
	return `Feld ${key}`;
}

/**
 * Teilschritte aus den Lücken eines Anlegevorgangs.
 * - writeErrors: „<Schritt>: <Meldung>“ (Schreibfehler, z. B. „Ansprechpartner: Propstack-Serverfehler (502)“)
 * - missing: nicht übernommene Felder bzw. Verknüpfungen – „owner (nicht prüfbar)“ (Objekt) oder
 *   „owner nicht gefunden“ (Projekt). Eine Verknüpfung, die sich nicht bestätigen lässt, zählt als fehlgeschlagen.
 * Einzelfelder, die sich nur nicht gegenlesen ließen (not_verifiable), zählen bewusst NICHT: Die gibt es fast
 * immer – die Liste wäre sonst nie leer und für den Workflow wertlos.
 * Je Schritt ein Eintrag; steht er schon mit einem Schreibfehler drin, gilt dessen genauerer Grund.
 */
export function failuresOf(parts: {
	writeErrors?: string[];
	missing?: string[];
	reviewTask?: { error?: string } | Record<string, unknown>;
	coordinatesNote?: string;
}): Failure[] {
	const out: Failure[] = [];
	const add = (failure: Failure) => {
		if (!out.some((f) => f.schritt === failure.schritt)) out.push(failure);
	};
	for (const entry of parts.writeErrors ?? []) {
		const at = entry.indexOf(": ");
		if (at > 0) add({ grund: entry.slice(at + 2), schritt: stepOf(entry.slice(0, at)) });
		else add({ grund: entry, schritt: "Schreiben" });
	}
	for (const entry of parts.missing ?? []) {
		const match = /^(owner|contact_person) \(?(nicht prüfbar|nicht gefunden)\)?$/.exec(entry);
		if (match) add({ grund: match[2], schritt: stepOf(match[1]) });
		else if (entry === "lat/lng") add({ grund: parts.coordinatesNote ?? "nicht übernommen", schritt: stepOf(entry) });
		else add({ grund: "nicht übernommen", schritt: stepOf(entry) });
	}
	const reviewError = (parts.reviewTask as { error?: unknown } | undefined)?.error;
	if (typeof reviewError === "string") add({ grund: reviewError, schritt: "Prüfaufgabe" });
	return out;
}
