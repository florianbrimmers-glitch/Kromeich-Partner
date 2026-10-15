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

/** Telefonnummer auf Ziffern in internationaler Form (+49 …) bringen. */
export function normalizePhone(phone: string | undefined | null): string {
	let digits = (phone ?? "").replace(/[^\d+]/g, "");
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

function fullName(input: ContactCandidate): string {
	return normalizeText([input.first_name, input.last_name].filter(Boolean).join(" "));
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
			if (normalizeText(contactName(row)) !== name) continue;
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
}

const GEO_TOLERANCE_M = 30;

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
		} else {
			warnings.push(`Weitere Einheit an derselben Adresse: ${label}.`);
		}
	}
	return { duplicates, warnings };
}
