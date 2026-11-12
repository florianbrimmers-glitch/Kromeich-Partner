import type { PropstackClient } from "../propstack-client";
import { type DedupeResult, type Match, normalizeCompany, normalizeText } from "./dedupe";
import { scalar } from "./mappers";

// Firmen-Datensätze erkennen und wiederfinden – nach dem Vorbild des täglichen Kontakt-Imports
// (src/propstack_client.py: find_company, _norm_name, _company_display_names), mit einer Erweiterung: Gesucht wird
// mit mehreren Begriffen (companySearchTerms), weil die Propstack-Suche bei abweichender Rechtsform nichts findet.

type Raw = Record<string, unknown>;

/** Vergleichsform wie im täglichen Import: nur Buchstaben und Ziffern zählen ("L.I.T. AG" = "LIT AG"). */
export function strictCompanyName(name: unknown): string {
	return normalizeText(name).replace(/\s+/g, "");
}

/** Alle Namensformen, unter denen ein Firmen-Datensatz auftauchen kann. Altlasten mit Nachname = Firma zeigt Propstack als „X (X)“. */
function companyNames(row: Raw): string[] {
	const names = [scalar(row.company), scalar(row.name)].filter((value): value is string => typeof value === "string" && value.trim() !== "");
	const doubled = /^(.+) \((.+)\)$/.exec(String(scalar(row.name) ?? "").trim());
	if (doubled && strictCompanyName(doubled[1]) === strictCompanyName(doubled[2])) names.push(doubled[1]);
	return names;
}

const displayName = (row: Raw) => String(scalar(row.name) ?? scalar(row.company) ?? `Kontakt ${row.id}`);

/** Echter Firmen-Datensatz? Personen, die fälschlich als Firma markiert sind, haben einen Vornamen. */
export function isCompanyRow(row: Raw): boolean {
	return row.is_company === true && !scalar(row.first_name);
}

/**
 * Gibt es die Firma schon? Gleicher Name blockiert – Schreibweise (Punkte, Groß-/Kleinschreibung) und Rechtsform
 * (GmbH, AG …) zählen nicht. Ein Name, der nur länger oder kürzer ist („Goodman“ / „Goodman Germany GmbH“), ist ein Hinweis.
 */
export function companyDuplicates(name: string, rows: Raw[]): DedupeResult {
	const duplicates: Match[] = [];
	const warnings: string[] = [];
	const strict = strictCompanyName(name);
	const loose = normalizeCompany(name);
	for (const row of rows) {
		if (!isCompanyRow(row) || typeof row.id !== "number" || duplicates.some((d) => d.id === row.id)) continue;
		const names = companyNames(row);
		if (names.some((n) => strictCompanyName(n) === strict || (loose !== "" && normalizeCompany(n) === loose))) {
			duplicates.push({ id: row.id, name: displayName(row), reason: "gleicher Firmenname" });
		} else if (
			loose !== "" &&
			names.some((n) => {
				const other = normalizeCompany(n);
				return other !== "" && (other.startsWith(`${loose} `) || loose.startsWith(`${other} `));
			})
		) {
			warnings.push(`Ähnlicher Firmen-Datensatz: ${displayName(row)} (${row.id}) – bitte prüfen, ob es dieselbe Firma ist.`);
		}
	}
	return { duplicates, warnings: warnings.slice(0, 5) };
}

/** Firmenname ohne Rechtsform, in der Schreibweise der Eingabe ("Goodman Germany GmbH & Co. KG" → "Goodman Germany"). */
export function companyCore(name: string): string {
	return name
		.trim()
		.split(/\s+/)
		.filter((word) => normalizeCompany(word) !== "")
		.join(" ");
}

/**
 * Suchbegriffe für die Dublettenprüfung. Die Propstack-Suche verlangt jedes Wort der Eingabe (live 12.11.2026:
 * „Goodman Germany AG“ und „Goodman Germany GmbH & Co. KG“ finden „Goodman Germany GmbH“ nicht). Deshalb wird
 * zusätzlich ohne Rechtsform gesucht – und mit dem ersten Wort allein, damit auch ein kürzer benannter Datensatz
 * („Goodman“) als Hinweis auftaucht.
 */
export function companySearchTerms(name: string): string[] {
	const full = name.trim().replace(/\s+/g, " ");
	const core = companyCore(full);
	const first = core.split(" ")[0] ?? "";
	const terms = [full, core, core.includes(" ") && normalizeText(first).length >= 4 ? first : ""];
	return terms.filter((term, index) => term !== "" && terms.findIndex((other) => other.toLowerCase() === term.toLowerCase()) === index);
}

export async function companyCandidates(client: Pick<PropstackClient, "searchContacts">, name: string): Promise<Raw[]> {
	const found = new Map<unknown, Raw>();
	for (const q of companySearchTerms(name)) {
		for (const row of (await client.searchContacts({ archived: "-1", page: 1, per: 50, q })).rows) {
			if (!found.has(row.id)) found.set(row.id, row);
		}
	}
	return [...found.values()];
}

/**
 * Firmen-Datensatz zu einem Firmennamen suchen (für den Hinweis nach create_contact).
 * Liefert den Datensatz nur, wenn genau einer passt.
 */
export async function findCompanyRecord(client: Pick<PropstackClient, "searchContacts">, name: string): Promise<{ id: number; name: string } | null> {
	const { duplicates } = companyDuplicates(name, await companyCandidates(client, name));
	return duplicates.length === 1 ? { id: duplicates[0].id, name: duplicates[0].name } : null;
}
