import { scalar } from "./mappers";

// Dublettenprüfung (Spezifikation Phase 3, Entscheidungen Florian):
// Kontakte: normalisierte E-Mail → blockiert; generische Adressen (info@ …) nur Warnung.
//   Fallback ohne (persönliche) E-Mail: Mobilnummer → blockiert, Festnetz → Warnung,
//   Name + Firma → blockiert, gleicher Name ohne Firmenabgleich → Warnung.
// Objekte: Adresse (bzw. Geokoordinaten) + Vermarktungsart + Einheit → blockiert;
//   gleiche Adresse mit anderer Vermarktungsart oder anderer Einheit → nur Hinweis.

type Raw = Record<string, unknown>;

export interface Match {
	id: number;
	name: string;
	reason: string;
}

export interface DedupeResult {
	duplicates: Match[];
	warnings: string[];
}

// ---------- Normalisierung ----------

export function normalizeEmail(email: string | undefined | null): string {
	return (email ?? "").trim().toLowerCase();
}

const GENERIC_LOCAL_PARTS = new Set([
	"admin", "anfrage", "anfragen", "bewerbung", "buchhaltung", "buero", "büro", "contact", "empfang", "hallo", "hello",
	"hr", "info", "invoice", "jobs", "karriere", "kontakt", "mail", "marketing", "newsletter", "office", "personal",
	"post", "presse", "press", "rechnung", "rechnungen", "sales", "service", "support", "team", "verkauf", "vermietung",
	"vertrieb", "zentrale",
]);

/** Systemadressen (noreply, Benachrichtigungen) – fast sicher kein echter Kontakt. */
export function isSystemEmail(email: string): boolean {
	const local = normalizeEmail(email).split("@")[0] ?? "";
	return /(^|[-_.])(no-?reply|do-?not-?reply|donotreply|notifications?|mailer-daemon|bounce[s]?)([-_.]|$)/.test(local);
}

export function isGenericEmail(email: string): boolean {
	const local = normalizeEmail(email).split("@")[0] ?? "";
	return GENERIC_LOCAL_PARTS.has(local) || isSystemEmail(email);
}

// Länder, in denen nach der Ländervorwahl nie eine 0 folgt: Die 0 der Ortsvorwahl entfällt dort bei internationaler
// Schreibweise (DE, AT, CH, NL, BE, FR, GB …), oder Rufnummern beginnen ohnehin nie mit 0 (DK, NO, PL, ES, PT, CZ, GR).
const NO_ZERO_AFTER = ["49", "43", "41", "31", "32", "33", "44", "352", "45", "46", "47", "48", "34", "351", "353", "420", "421", "385", "386", "40", "359", "358", "30", "90", "423"];
// Länder, in denen die 0 zur Rufnummer gehört und mitgewählt wird (Italien, San Marino, Elfenbeinküste, Gabun, Kongo).
const ZERO_BELONGS = ["39", "378", "225", "241", "242"];

// Ländervorwahl zum Land des Kontakts – für Nummern, die ohne Ländervorwahl angegeben sind. Bewusst nur die Länder,
// mit denen Kromeich zu tun hat; ein Land, das hier fehlt, gilt als unbekannt (die Nummer bleibt dann, wie sie ist).
const COUNTRY_CODES: [RegExp, string][] = [
	[/^(de|deu|deutschland|germany|brd|bundesrepublik deutschland)$/, "49"],
	[/^(at|aut|österreich|oesterreich|austria)$/, "43"],
	[/^(ch|che|schweiz|switzerland|suisse)$/, "41"],
	[/^(nl|nld|niederlande|netherlands|nederland|holland)$/, "31"],
	[/^(be|bel|belgien|belgium|belgique|belgië)$/, "32"],
	[/^(fr|fra|frankreich|france)$/, "33"],
	[/^(lu|lux|luxemburg|luxembourg)$/, "352"],
	[/^(gb|gbr|uk|großbritannien|grossbritannien|vereinigtes königreich|united kingdom|england)$/, "44"],
	[/^(it|ita|italien|italy|italia)$/, "39"],
	[/^(pl|pol|polen|poland|polska)$/, "48"],
	[/^(cz|cze|tschechien|tschechische republik|czechia|czech republic)$/, "420"],
	[/^(dk|dnk|dänemark|daenemark|denmark)$/, "45"],
	[/^(es|esp|spanien|spain|españa)$/, "34"],
	[/^(se|swe|schweden|sweden)$/, "46"],
	[/^(li|lie|liechtenstein)$/, "423"],
];

/** Ländervorwahl zum Land: "49" usw.; undefined = kein Land angegeben, null = Land angegeben, aber nicht bekannt. */
export function countryCallingCode(country: unknown): string | null | undefined {
	const text = typeof country === "string" ? country.trim().toLocaleLowerCase("de") : "";
	if (text === "") return undefined;
	return COUNTRY_CODES.find(([pattern]) => pattern.test(text))?.[1] ?? null;
}

/**
 * Telefonnummer einheitlich und wählbar schreiben (Entscheidungen Florian, 13.11.2026):
 *
 * 1. Nach einer Ländervorwahl steht keine 0 der Ortsvorwahl. Aus Signaturen kommt oft „+49 (0) 151 …“ oder
 *    „+49 0151 …“ – so gespeichert lässt sich die Nummer nicht anwählen (12 der 600 neuesten Kontakte).
 *    - „(0)“ nach der Ländervorwahl: immer weg – außer in Ländern, in denen die 0 zur Nummer gehört (dort ohne Klammern).
 *    - eine 0 ohne Klammern bzw. „(0171)“: nur bei Ländern, in denen nach der Vorwahl nie eine 0 folgt.
 * 2. Einheitlich mit Ländervorwahl: „00“ wird zu „+“, und eine Nummer ohne Ländervorwahl („0171 …“) bekommt die des
 *    Landes. Ist kein Land angegeben, gilt die Nummer als deutsch (+49) – Kromeich arbeitet in Deutschland, und im
 *    Bestand tragen ausländische Nummern fast immer schon ihre Ländervorwahl. Ist ein Land angegeben, das hier nicht
 *    bekannt ist, bleibt die Nummer unverändert, statt eine falsche Vorwahl zu erfinden.
 *
 * Die übrige Schreibweise (Leerzeichen, Bindestriche) bleibt. Was nicht wie eine Nummer mit 0 oder + beginnt, bleibt ganz.
 */
export function formatPhone<T extends string | undefined | null>(phone: T, country?: unknown): T {
	if (typeof phone !== "string") return phone;
	const text = phone.trim();
	if (/^\(?\s*0(?!0)\s*\d/.test(text)) return national(text, phone, country) as T;
	const prefix = /^(\+|00)\s*/.exec(text);
	if (!prefix) return phone;
	const rest = text.slice(prefix[0].length);
	const lead = /^\d+/.exec(rest)?.[0] ?? "";
	// Ländervorwahl: die bekannte am Anfang (auch bei zusammengeschriebenen Nummern), sonst die Ziffern bis zum ersten Trenner
	const code = [...NO_ZERO_AFTER, ...ZERO_BELONGS].find((c) => lead.startsWith(c)) ?? (lead.length >= 1 && lead.length <= 3 ? lead : undefined);
	if (!code) return (prefix[1] === "00" && lead ? `+${rest}` : phone) as T;
	const tail = rest.slice(code.length);
	const separator = /^[\s\-/.]*/.exec(tail)?.[0] ?? "";
	const body = tail.slice(separator.length);
	const keepZero = ZERO_BELONGS.includes(code);
	const bracketed = /^\(\s*0\s*\)\s*/.exec(body);
	if (bracketed) return `+${code} ${keepZero ? "0" : ""}${body.slice(bracketed[0].length)}` as T;
	if (NO_ZERO_AFTER.includes(code)) {
		const inBracket = /^\(\s*0(?=\d)/.exec(body);
		if (inBracket) return `+${code}${separator}(${body.slice(inBracket[0].length)}` as T;
		if (/^0\d/.test(body)) return `+${code}${separator}${body.slice(1)}` as T;
	}
	return (prefix[1] === "00" ? `+${code}${tail}` : phone) as T;
}

/** Nummer ohne Ländervorwahl („0171 …“, „(0221) 47…“) mit der Vorwahl des Landes schreiben. */
function national(text: string, original: string, country: unknown): string {
	const known = countryCallingCode(country);
	if (known === null) return original;
	const code = known ?? "49";
	const keepZero = ZERO_BELONGS.includes(code);
	// „(0221) 4710199“: Klammer um die Ortsvorwahl auflösen
	const bracket = /^\(\s*0\s*(\d[\d\s]*?)\s*\)\s*/.exec(text);
	if (bracket) return `+${code} ${keepZero ? "0" : ""}${bracket[1]} ${text.slice(bracket[0].length)}`.trim();
	return `+${code} ${keepZero ? text : text.replace(/^0\s*/, "")}`;
}

/** Telefonnummer auf Ziffern in internationaler Form (+49 …) bringen. */
export function normalizePhone(phone: string | undefined | null): string {
	// formatPhone bringt jede Schreibweise auf „+Ländervorwahl …“ (ohne Land: +49) – übrig bleibt, die Ziffern zu nehmen
	let digits = (formatPhone(phone) ?? "").replace(/[^\d+]/g, "");
	if (digits.startsWith("+")) digits = digits.slice(1);
	else if (digits.startsWith("00")) digits = digits.slice(2);
	else if (digits.startsWith("0")) digits = `49${digits.slice(1)}`;
	return digits;
}

/** Deutsche Mobilfunknummern: 015x, 016x, 017x. */
export function isMobile(phone: string): boolean {
	return /^491[567]\d{7,}$/.test(normalizePhone(phone));
}

export function normalizeText(text: unknown): string {
	return String(text ?? "")
		.toLocaleLowerCase("de")
		.normalize("NFKD")
		.replace(/[̀-ͯ]/g, "")
		.replace(/ß/g, "ss")
		.replace(/[^a-z0-9]+/g, " ")
		.trim();
}

const LEGAL_FORMS = /\b(gmbh|co|kg|ag|se|mbh|ug|haftungsbeschrankt|ohg|gbr|e ?k|kgaa|inc|ltd|llc|bv|b v|nv|sa|sarl|plc)\b/g;

export function normalizeCompany(company: unknown): string {
	return normalizeText(company).replace(LEGAL_FORMS, " ").replace(/\s+/g, " ").trim();
}

export function normalizeStreet(street: unknown): string {
	return normalizeText(street)
		.replace(/\bstrasse\b|\bstr\b/g, "str")
		.replace(/strasse\b/g, "str")
		.replace(/\s+/g, "");
}

export function normalizeHouseNumber(value: unknown): string {
	return normalizeText(value).replace(/\s+/g, "");
}

export function normalizeUnit(value: unknown): string {
	return normalizeText(value).replace(/\b(unit|einheit|we|nr)\b/g, "").replace(/\s+/g, "");
}

export function distanceMeters(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
	const toRad = (d: number) => (d * Math.PI) / 180;
	const dLat = toRad(b.lat - a.lat);
	const dLng = toRad(b.lng - a.lng);
	const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
	return 6_371_000 * 2 * Math.asin(Math.sqrt(h));
}

// ---------- Kontakte ----------

export interface ContactCandidate {
	email?: string;
	phone?: string;
	mobile?: string;
	first_name?: string;
	last_name?: string;
	company?: string;
}

export interface ContactSearchResults {
	byEmail: Raw[];
	byMobile: Raw[];
	byPhone: Raw[];
	byName: Raw[];
}

function contactName(row: Raw): string {
	return String(scalar(row.name) ?? [scalar(row.first_name), scalar(row.last_name)].filter(Boolean).join(" "));
}

// Akademische Titel vor dem Namen. Propstack stellt sie dem Anzeigenamen voran ("Dr. Max Muster") – für den
// Namensvergleich zählen sie nicht (Live-Befund 12.11.2026: „Max Muster“ wurde neben „Dr. Max Muster“ angelegt).
const TITLE_TOKENS = new Set(["prof", "dr", "dres", "dipl", "ing", "med", "jur", "rer", "nat", "phil", "hc", "mag"]);

/** Vergleichsform eines Personennamens: normalisiert, ohne vorangestellte Titel. */
export function personName(name: unknown): string {
	const tokens = normalizeText(name).split(" ").filter(Boolean);
	let start = 0;
	while (start < tokens.length - 1 && TITLE_TOKENS.has(tokens[start])) start++;
	return tokens.slice(start).join(" ");
}

function fullName(input: ContactCandidate): string {
	return personName([input.first_name, input.last_name].filter(Boolean).join(" "));
}

/** Name eines vorhandenen Kontakts für den Vergleich: Vor- und Nachname, sonst der Anzeigename – jeweils ohne Titel. */
function rowPersonName(row: Raw): string {
	const parts = [scalar(row.first_name), scalar(row.last_name)].filter(Boolean);
	return personName(parts.length ? parts.join(" ") : contactName(row));
}

export function contactDuplicates(input: ContactCandidate, found: ContactSearchResults, excludeId?: number): DedupeResult {
	const duplicates: Match[] = [];
	const warnings: string[] = [];
	const add = (row: Raw, reason: string) => {
		if (row.id === excludeId || duplicates.some((d) => d.id === row.id)) return;
		duplicates.push({ id: row.id as number, name: contactName(row), reason });
	};
	const others = (rows: Raw[]) => rows.filter((r) => r.id !== excludeId);

	const email = normalizeEmail(input.email);
	const personalEmail = email && !isGenericEmail(email);
	if (email && isSystemEmail(email)) {
		warnings.push(`${email} ist eine Systemadresse (noreply o. ä.) – vermutlich kein echter Kontakt.`);
	} else if (email && !personalEmail) {
		warnings.push(`${email} ist eine allgemeine Firmenadresse – keine eindeutige Person.`);
	}

	// Nur echte Treffer zählen: Falls Propstack den E-Mail-Filter ignorieren würde, darf nicht jeder Kontakt als Dublette gelten.
	const emailHits = others(found.byEmail).filter((r) => {
		const all = [scalar(r.email), ...(Array.isArray(r.emails) ? r.emails : [])].map((e) => normalizeEmail(e as string));
		return all.includes(email);
	});
	if (personalEmail) {
		for (const row of emailHits) add(row, `gleiche E-Mail ${email}`);
	} else if (email && emailHits.length) {
		warnings.push(`Die Adresse ${email} nutzen bereits: ${emailHits.map((r) => `${contactName(r)} (${r.id})`).join(", ")}.`);
	}

	// Fallback-Kriterien blockieren nur, wenn keine persönliche E-Mail die Identität klärt.
	const block = !personalEmail;

	if (input.mobile) {
		for (const row of others(found.byMobile)) {
			if (block) add(row, `gleiche Mobilnummer ${input.mobile}`);
			else warnings.push(`Gleiche Mobilnummer wie ${contactName(row)} (${row.id}) – evtl. dieselbe Person mit neuer E-Mail.`);
		}
	}
	if (input.phone) {
		const hits = others(found.byPhone);
		if (hits.length) {
			warnings.push(
				`Gleiche Festnetznummer wie ${hits
					.slice(0, 5)
					.map((r) => `${contactName(r)} (${r.id})`)
					.join(", ")} – bei Zentralnummern normal.`,
			);
		}
	}

	const name = fullName(input);
	if (name) {
		const company = normalizeCompany(input.company);
		for (const row of others(found.byName)) {
			if (rowPersonName(row) !== name) continue;
			const rowCompany = normalizeCompany(scalar(row.company));
			if (company && rowCompany && company === rowCompany) {
				if (block) add(row, `gleicher Name und gleiche Firma (${scalar(row.company)})`);
				else warnings.push(`Gleicher Name und gleiche Firma wie ${contactName(row)} (${row.id}).`);
			} else if (!company || !rowCompany) {
				warnings.push(`Gleicher Name wie ${contactName(row)} (${row.id})${rowCompany ? `, Firma ${scalar(row.company)}` : ""}.`);
			}
		}
	}

	return { duplicates, warnings };
}

// ---------- Objekte ----------

export interface ObjectCandidate {
	street: string;
	house_number?: string;
	zip_code: string;
	marketing_type: string;
	unit_id?: string;
	lat?: number;
	lng?: number;
	/** Einheit eines Projekts: weitere Einheiten desselben Projekts sind erwartbar und werden nicht gemeldet. */
	project_id?: number;
}

const GEO_TOLERANCE_M = 30;
const MAX_UNIT_HINTS = 3;

export function sameAddress(input: ObjectCandidate, row: Raw): boolean {
	const zipMatch = String(scalar(row.zip_code) ?? "").trim() === input.zip_code.trim();
	const streetMatch = normalizeStreet(scalar(row.street)) === normalizeStreet(input.street);
	const numberMatch = normalizeHouseNumber(scalar(row.house_number)) === normalizeHouseNumber(input.house_number);
	if (zipMatch && streetMatch && numberMatch) return true;
	const lat = scalar(row.lat);
	const lng = scalar(row.lng);
	if (input.lat !== undefined && input.lng !== undefined && typeof lat === "number" && typeof lng === "number") {
		return distanceMeters({ lat: input.lat, lng: input.lng }, { lat, lng }) <= GEO_TOLERANCE_M;
	}
	return false;
}

export function objectDuplicates(input: ObjectCandidate, rows: Raw[], excludeId?: number): DedupeResult {
	const duplicates: Match[] = [];
	const warnings: string[] = [];
	const otherUnits: string[] = [];
	const unit = normalizeUnit(input.unit_id);
	for (const row of rows) {
		if (row.id === excludeId || !sameAddress(input, row)) continue;
		const label = `${scalar(row.title) ?? scalar(row.name) ?? "Objekt"} (${row.id}, ${scalar(row.unit_id) ?? "ohne Einheit"}, ${scalar(row.marketing_type)})`;
		const sameUnit = normalizeUnit(scalar(row.unit_id)) === unit;
		const sameMarketing = scalar(row.marketing_type) === input.marketing_type;
		if (sameUnit && sameMarketing) {
			duplicates.push({ id: row.id as number, name: label, reason: "gleiche Adresse, Vermarktungsart und Einheit" });
		} else if (sameUnit) {
			warnings.push(`Gleiche Adresse und Einheit mit anderer Vermarktungsart: ${label}.`);
		} else if (input.project_id === undefined || Number(scalar(row.project_id)) !== input.project_id) {
			otherUnits.push(label);
		}
	}
	for (const label of otherUnits.slice(0, MAX_UNIT_HINTS)) warnings.push(`Weitere Einheit an derselben Adresse: ${label}.`);
	if (otherUnits.length > MAX_UNIT_HINTS) warnings.push(`… und ${otherUnits.length - MAX_UNIT_HINTS} weitere Objekte an derselben Adresse.`);
	return { duplicates, warnings };
}
