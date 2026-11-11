// Notizen anhängen, ohne zu doppeln (Ansage Florian, 11.11.2026).
// Anlass: Beim Hillwood-Lauf am 10.11. gingen Aufrufe durch einen Neustart verloren und mussten wiederholt werden –
// interne Notiz und Änderungsvermerk werden angehängt, ein zweiter gleicher Aufruf hätte sie doppelt eingetragen.
//
// Zwei Maßstäbe:
// - Notizen (interne Notiz am Objekt und Projekt, Notiz am Kontakt) halten Sachverhalte fest. Steht derselbe Text
//   schon da – egal von wann und von wem –, wird er nicht noch einmal angehängt.
// - Die „Bemerkung“ ist ein Änderungsprotokoll: Derselbe Vermerk an einem späteren Tag ist ein neuer Eintrag.
//   Doppelt ist er nur unter dem Stempel desselben Tages und Nutzers (genau der Fall „Aufruf wiederholt“).
//
// Verglichen wird zeilenweise: Der neue Text muss als ganze, aufeinanderfolgende Zeilen vorhanden sein.
// Ein kurzer Text, der nur als Teil einer längeren Zeile vorkommt, gilt nicht als vorhanden.

const lines = (text: string) =>
	text
		.split(/\r?\n/)
		.map((line) => line.replace(/\s+/g, " ").trim())
		.filter(Boolean);

/** Steht block – als ganze, aufeinanderfolgende Zeilen – schon in text? Leerer Block gilt als vorhanden. */
export function containsBlock(text: string, block: string): boolean {
	const needle = lines(block);
	if (!needle.length) return true;
	const hay = lines(text);
	for (let start = 0; start + needle.length <= hay.length; start++) {
		if (needle.every((line, offset) => hay[start + offset] === line)) return true;
	}
	return false;
}

/** Teilt die anzuhängenden Teile in neue und schon vorhandene. */
export function splitNewParts(existing: string, parts: string[]): { fresh: string[]; present: string[] } {
	const fresh: string[] = [];
	const present: string[] = [];
	for (const part of parts) {
		// auch untereinander nicht doppeln (z. B. derselbe Satz in internal_note und mandate)
		if (containsBlock(existing, part) || fresh.some((earlier) => containsBlock(earlier, part))) present.push(part);
		else fresh.push(part);
	}
	return { fresh, present };
}

/**
 * Notiz mit Stempel anhängen. Liefert den neuen Gesamttext und die Ergänzung – oder undefined, wenn alles schon dasteht.
 * sameStampOnly: nur als doppelt werten, was unter genau diesem Stempel (Tag und Nutzer) schon steht (Änderungsprotokoll).
 */
export function appendNote(
	existing: string,
	stamp: string,
	parts: string[],
	options: { sameStampOnly?: boolean } = {},
): { text: string; addition: string; present: string[] } | { text: undefined; addition: undefined; present: string[] } {
	const old = existing.trim();
	const wanted = parts.map((part) => part.trim()).filter(Boolean);
	const { fresh, present } = options.sameStampOnly
		? wanted.reduce(
				(acc, part) => {
					(containsBlock(old, `${stamp}\n${part}`) || acc.fresh.includes(part) ? acc.present : acc.fresh).push(part);
					return acc;
				},
				{ fresh: [] as string[], present: [] as string[] },
			)
		: splitNewParts(old, wanted);
	if (!fresh.length) return { addition: undefined, present, text: undefined };
	const addition = `${stamp}\n${fresh.join("\n")}`;
	return { addition, present, text: [old, addition].filter(Boolean).join("\n\n") };
}
