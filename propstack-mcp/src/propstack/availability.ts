import type { FieldDef } from "./field-rules";

// „Verfügbar ab“ (free_from) hat im Bestand zwei Begleiter in den Custom-Feldern:
// - „Bezug“ (bezug, Text): derselbe Wortlaut,
// - „Bezug (Datum)“ (bezug_datum, Datum): das Datum, wenn der Text genau eines nennt.
// Bestandsmuster (Mileway-Lauf 09.11.2026, 26 Einheiten): „ab 01.07.2027“ → Bezug „ab 01.07.2027“,
// Bezug (Datum) 01.07.2027; „sofort“, „auf Anfrage“, „ab 2027“ → Bezug gleich, Datum leer.
// Ansage Florian, 11.11.2026: „Bezug“ zieht automatisch mit, sobald „Verfügbar ab“ geändert wird.
// Anlass: Hillwood-Update vom 10.11. – „Verfügbar ab“ war neu, „Bezug“ stand noch auf dem alten Wert.

type Raw = Record<string, unknown>;

export const BEZUG_KEY = "bezug";
export const BEZUG_DATE_KEY = "bezug_datum";

function isoDate(year: number, month: number, day: number): string | undefined {
	const probe = new Date(Date.UTC(year, month - 1, day));
	if (probe.getUTCFullYear() !== year || probe.getUTCMonth() !== month - 1 || probe.getUTCDate() !== day) return undefined;
	return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/**
 * Genau ein Kalenderdatum im Text (TT.MM.JJJJ, TT.MM.JJ oder JJJJ-MM-TT) → JJJJ-MM-TT.
 * Kein Datum („sofort“, „Q3 2027“), mehrere verschiedene oder ein unmögliches (31.02.) → undefined:
 * lieber kein Datum als ein geratenes.
 */
export function singleDate(text: string): string | undefined {
	const found = new Set<string>();
	for (const match of text.matchAll(/(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})(?![\d.]*\d)/g)) {
		const year = match[3].length === 2 ? 2000 + Number(match[3]) : Number(match[3]);
		const iso = isoDate(year, Number(match[2]), Number(match[1]));
		if (!iso) return undefined;
		found.add(iso);
	}
	for (const match of text.matchAll(/(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-]*\d)/g)) {
		const iso = isoDate(Number(match[1]), Number(match[2]), Number(match[3]));
		if (!iso) return undefined;
		found.add(iso);
	}
	return found.size === 1 ? [...found][0] : undefined;
}

const isText = (def: FieldDef | undefined) => def?.type === "String" || def?.type === "Text";

/**
 * Was aus „Verfügbar ab“ für „Bezug“ und „Bezug (Datum)“ folgt. Ausdrücklich übergebene Custom-Felder haben Vorrang.
 * clear: veraltete Werte leeren (beim Ändern) – beim Anlegen gibt es nichts zu leeren.
 */
export function availabilityMirror(freeFrom: string | null, defs: Map<string, FieldDef>, explicit: Raw | undefined, options: { clear: boolean }): Raw {
	const out: Raw = {};
	const given = (key: string) => Boolean(explicit && key in explicit);
	const text = typeof freeFrom === "string" ? freeFrom.trim() : "";
	if (isText(defs.get(BEZUG_KEY)) && !given(BEZUG_KEY)) {
		if (text) out[BEZUG_KEY] = text;
		else if (options.clear) out[BEZUG_KEY] = null;
	}
	if (defs.get(BEZUG_DATE_KEY)?.type === "Date" && !given(BEZUG_DATE_KEY)) {
		const date = text ? singleDate(text) : undefined;
		if (date) out[BEZUG_DATE_KEY] = date;
		else if (options.clear) out[BEZUG_DATE_KEY] = null;
	}
	return out;
}

const squash = (value: unknown) => String(value ?? "").replace(/\s+/g, " ").trim();

/** Hinweis, wenn ein ausdrücklich gesetztes „Bezug“ von „Verfügbar ab“ abweicht (sonst leer). */
export function bezugDeviation(freeFrom: unknown, bezug: unknown): string | undefined {
	if (bezug === undefined) return undefined;
	const a = squash(freeFrom);
	const b = squash(bezug);
	if (a === b) return undefined;
	return `„Bezug“ (${b ? `„${b}“` : "leer"}) weicht von „Verfügbar ab“ (${a ? `„${a}“` : "leer"}) ab. Der Connector zieht „Bezug“ und „Bezug (Datum)“ selbst nach, sobald free_from angegeben wird – bitte free_from setzen statt custom_fields.bezug.`;
}
