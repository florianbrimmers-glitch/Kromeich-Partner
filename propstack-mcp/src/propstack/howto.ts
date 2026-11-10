import { z } from "zod";
import { PropstackError } from "../propstack-client";
import { count, flag, optionalText } from "../tools/params";
import { normalizeCompany, normalizeStreet, normalizeText } from "./dedupe";
import type { FieldDef, RentState } from "./field-rules";

// Regeln aus den Team-How-tos „Objekte in Propstack anlegen“ und „Projekte in Propstack anlegen“
// (Drive: K & P → Allgemein → Knowledge Sharing → Propstack, Stand 09.11.2026) und aus der Rückmeldung
// von Oguzhan (24.10.2026). Sie stehen hier im Server, damit jede Claude-Sitzung nach demselben Muster
// schreibt – unabhängig davon, welchen Skill oder Prompt sie gerade hat.
// Abgeglichen mit von Hand angelegten Datensätzen (Herford 6324578, Hillscheid 6282819).

type Raw = Record<string, unknown>;

// ---------- Provision ----------

export const COMMISSION_FREE = {
	courtage: "Provisionsfrei",
	courtage_note: "Die Anmietung erfolgt provisionsfrei für den Mieter.",
};

/** Standard-Staffel aus dem How-to (dort im letzten Satz „Nettokaltmiete“ – hier grammatisch richtig im Plural). */
export const COMMISSION_SCALE = [
	"Bei Mietverträgen mit einer Laufzeit von weniger als fünf (5) Jahren beträgt der Provisionsanspruch zwei (2) Nettokaltmieten zzgl. MwSt.",
	"Bei Mietverträgen mit einer Laufzeit von mehr als oder gleich fünf (5), jedoch weniger als sieben (7) Jahren beträgt der Provisionsanspruch drei (3) Nettokaltmieten zzgl. MwSt.",
	"Bei Mietverträgen mit einer Laufzeit von mehr als oder gleich sieben (7), jedoch weniger als zehn (10) Jahren beträgt der Provisionsanspruch dreieinhalb (3,5) Nettokaltmieten zzgl. MwSt.",
	"Bei Mietverträgen mit einer Laufzeit ab zehn (10) Jahren beträgt der Provisionsanspruch vier (4) Nettokaltmieten zzgl. MwSt.",
].join("\n");

export const commissionParam = z
	.enum(["provisionsfrei", "staffel"])
	.optional()
	.describe(
		"Provision nach Team-Standard (nur Miete). provisionsfrei: Außenprovision „Provisionsfrei“ + Hinweis „Die Anmietung erfolgt provisionsfrei für den Mieter.“ · staffel (provisionspflichtig): Provisionshinweis mit der Standard-Staffel (2 / 3 / 3,5 / 4 Nettokaltmieten je nach Laufzeit). Eigene Texte in courtage/courtage_note haben Vorrang. Feste Regeln je Eigentümer aus der Wissensdatenbank beachten",
	);

/** Felder, die aus der Provisions-Vorgabe folgen (ausdrücklich angegebene Texte haben Vorrang). */
export function commissionFields(
	commission: "provisionsfrei" | "staffel" | undefined,
	marketingType: unknown,
	explicit: { courtage?: unknown; courtage_note?: unknown },
): { courtage?: string; courtage_note?: string } {
	if (!commission) return {};
	if (marketingType === "BUY") {
		throw new PropstackError("commission gilt nur für Miete (die Standardtexte sprechen von Mietverträgen). Bei Kauf courtage und courtage_note selbst angeben.", 400);
	}
	const out: { courtage?: string; courtage_note?: string } = {};
	if (commission === "provisionsfrei") {
		if (explicit.courtage === undefined) out.courtage = COMMISSION_FREE.courtage;
		if (explicit.courtage_note === undefined) out.courtage_note = COMMISSION_FREE.courtage_note;
	} else if (explicit.courtage_note === undefined) {
		out.courtage_note = COMMISSION_SCALE;
	}
	return out;
}

// ---------- Interne Notiz ----------

export const internalNoteShape = {
	source_link: z
		.string()
		.trim()
		.regex(/^https?:\/\/\S+$/, "Link mit http(s)://")
		.max(500)
		.optional()
		.describe("Interne Notiz: Link zum Exposé oder zur Website"),
	mandate: optionalText(300).describe("Interne Notiz: Mandat, z. B. „Alleinmandat von <Makler>“ oder „kein Alleinmandat“"),
	internal_commission: optionalText(1000).describe("Interne Notiz: Provisionsregelung – Tischregel, Vereinbarungen, Höhe. Nur die Regelung, kein Bericht"),
	developer_project_name: optionalText(200).describe("Interne Notiz: Projektname des Entwicklers"),
};

export function internalNoteLines(input: Raw): string[] {
	const lines: string[] = [];
	if (input.source_link) lines.push(`Exposé/Website: ${input.source_link}`);
	if (input.mandate) lines.push(`Mandat: ${input.mandate}`);
	if (input.internal_rents) lines.push(`Mietpreise: ${input.internal_rents}`);
	if (input.internal_commission) lines.push(`Provision intern: ${input.internal_commission}`);
	if (input.developer_project_name) lines.push(`Projektname Entwickler: ${input.developer_project_name}`);
	return lines;
}

// ---------- Wichtige Felder am Objekt ----------
// Das How-to nennt die Felder mit ihrem Namen in der Oberfläche; die Schlüssel dahinter sind nicht zu
// erraten (Rampentore = ramepntore, Ebenerdige Tore = anzahl_rampentore_2). Deshalb eigene Parameter.

const area = z.number().positive().optional();
const euro = z.number().positive().max(10_000).optional();

export const howtoObjectShape = {
	hall_divisible_from: area.describe("Hallenfläche teilbar ab (m²)"),
	office_divisible_from: area.describe("Bürofläche teilbar ab (m²)"),
	mezzanine_area: area.describe("Mezzaninefläche (m²)"),
	mezzanine_divisible_from: area.describe("Mezzaninefläche teilbar ab (m²)"),
	car_parking: count.optional().describe("Stellplätze (PKW) verfügbar"),
	truck_parking: count.optional().describe("LKW-Stellplätze gesamt"),
	dock_doors: count.optional().describe("Rampentore (Anzahl)"),
	ground_level_doors: count.optional().describe("Ebenerdige Tore (Anzahl)"),
	wgk: optionalText(100).describe("WGK (Wassergefährdungsklasse), z. B. „WGK 1–3“ oder „nicht zugelassen“"),
	lighting: optionalText(200).describe("Beleuchtung, z. B. „LED“"),
	sprinkler: optionalText(200).describe("Sprinkleranlage, z. B. „vorhanden“ oder „ESFR“"),
	heating: optionalText(200).describe("Heizungsart Halle"),
	certification: optionalText(200).describe("Zertifizierung, z. B. „DGNB Gold“"),
	internal_rent_hall: euro.describe("Mietpreis Halle €/m² – INTERN (nie im Exposé). Öffentliche Preise nur auf ausdrückliche Ansage, siehe public_price_confirmed"),
	internal_rent_office: euro.describe("Mietpreis Büro €/m² – intern"),
	internal_rent_mezzanine: euro.describe("Mietpreis Mezzanine €/m² – intern"),
	active: flag
		.optional()
		.describe(
			"Aktiv ja/nein („Aktiv hinterlegen, wenn wir das Objekt anbieten können“). Ohne Angabe: Aktiv nur bei Status Vermarktung/Reserviert und nicht vermietet. Aktive Objekte können in Automatisierungen (Exposéversand) landen – true nur auf Ansage",
		),
};

interface HowtoField {
	param: string;
	label: string;
	/** Custom-Feld-Schlüssel; der erste muss existieren. */
	keys: string[];
	/** Zusätzlich nur, solange nicht vermietet. */
	availableOnly?: string[];
}

export const HOWTO_FIELDS: HowtoField[] = [
	{ keys: ["lagerflache_teilbar_ab"], label: "Hallenfläche teilbar ab", param: "hall_divisible_from" },
	{ keys: ["buroflache_teilbar_ab"], label: "Bürofläche teilbar ab", param: "office_divisible_from" },
	{ availableOnly: ["mezzanineflache_verfugbar"], keys: ["mezzanineflache_gesamt"], label: "Mezzaninefläche", param: "mezzanine_area" },
	{ keys: ["mezzanineflache_teilbar_ab"], label: "Mezzaninefläche teilbar ab", param: "mezzanine_divisible_from" },
	{ keys: ["stellplatze_verfugbar"], label: "Stellplätze (PKW) verfügbar", param: "car_parking" },
	{ keys: ["lkw_stellplatze_gesamt"], label: "LKW-Stellplätze gesamt", param: "truck_parking" },
	{ keys: ["ramepntore"], label: "Rampentore", param: "dock_doors" },
	{ keys: ["anzahl_rampentore_2"], label: "Ebenerdige Tore", param: "ground_level_doors" },
	{ keys: ["wgk"], label: "WGK", param: "wgk" },
	{ keys: ["beleuchtung", "beleuchtung_halle"], label: "Beleuchtung", param: "lighting" },
	{ keys: ["sprinkleranlage"], label: "Sprinkleranlage", param: "sprinkler" },
	{ keys: ["heizungsart_halle"], label: "Heizungsart Halle", param: "heating" },
	{ keys: ["zertifizierung"], label: "Zertifizierung", param: "certification" },
	{ keys: ["intern_mietpreis_hallenflache"], label: "Mietpreis Halle (intern)", param: "internal_rent_hall" },
	{ keys: ["intern_mietpreis_buro"], label: "Mietpreis Büro (intern)", param: "internal_rent_office" },
	{ keys: ["intern_mietpreis_mezzanine"], label: "Mietpreis Mezzanine (intern)", param: "internal_rent_mezzanine" },
];

/** How-to-Parameter → Custom-Felder. Text- oder Zahlform richtet sich nach dem Feldtyp in Propstack. */
export function howtoCustomFields(input: Raw, defs: Map<string, FieldDef>, explicit: Raw | undefined, rent: RentState): Raw {
	const out: Raw = {};
	for (const field of HOWTO_FIELDS) {
		const value = input[field.param];
		if (value === undefined) continue;
		const keys = [...field.keys, ...(rent === "available" ? (field.availableOnly ?? []) : [])];
		const clash = keys.find((key) => explicit && key in explicit);
		if (clash) throw new PropstackError(`${field.param} und custom_fields.${clash} gleichzeitig angegeben – bitte nur eines verwenden.`, 400);
		keys.forEach((key, index) => {
			const def = defs.get(key);
			if (!def) {
				if (index === 0) {
					throw new PropstackError(`Das Propstack-Feld „${key}“ (${field.label}) gibt es nicht (mehr) – ${field.param} kann nicht gespeichert werden. Bitte melden.`, 0);
				}
				return;
			}
			out[key] = value === null ? null : def.type === "Number" ? value : String(value);
		});
	}
	return out;
}

function provided(input: Raw, explicit: Raw | undefined, param: string): boolean {
	if (input[param] !== undefined) return true;
	const field = HOWTO_FIELDS.find((f) => f.param === param);
	return Boolean(field?.keys.some((key) => explicit && key in explicit));
}

// ---------- Was das How-to verlangt, aber nicht angegeben wurde ----------

/** Objekt: fields = endgültige Standardfelder (nach Übernahme vom Projekt und Provisions-Vorgabe). */
export function objectNotProvided(input: Raw, fields: Raw, options: { inProject: boolean; explicit?: Raw }): string[] {
	const missing: string[] = [];
	const need = (ok: boolean, label: string) => {
		if (!ok) missing.push(label);
	};
	const has = (param: string) => provided(input, options.explicit, param);
	const industrial = fields.rs_type === "INDUSTRY";
	need(fields.rs_category !== undefined, "Objektart-Unterart (rs_category, z. B. HALL)");
	if (!options.inProject) {
		need(input.source_link !== undefined, "Interne Notiz: Exposé-/Website-Link");
		need(input.mandate !== undefined, "Interne Notiz: Mandat");
		need(input.internal_commission !== undefined, "Interne Notiz: Provisionsregelung");
	}
	if (fields.marketing_type === "RENT") {
		need(has("internal_rent_hall") || has("internal_rent_office") || has("internal_rent_mezzanine"), "Mietpreise (intern)");
	}
	need(input.owner_contact_id !== undefined, "Eigentümer");
	need(fields.courtage !== undefined || fields.courtage_note !== undefined, "Provision");
	if (industrial) {
		need(fields.industrial_area !== undefined, "Hallenfläche");
		if (fields.industrial_area !== undefined) need(has("hall_divisible_from"), "Hallenfläche teilbar ab");
	}
	need(fields.usable_floor_space !== undefined, "Bürofläche");
	if (fields.usable_floor_space !== undefined) need(has("office_divisible_from"), "Bürofläche teilbar ab");
	if (industrial) {
		need(has("mezzanine_area"), "Mezzaninefläche");
		if (has("mezzanine_area")) need(has("mezzanine_divisible_from"), "Mezzaninefläche teilbar ab");
	}
	if (!options.inProject) need(fields.plot_area !== undefined, "Grundstücksfläche");
	need(has("car_parking"), "Stellplätze (PKW)");
	if (industrial) {
		need(has("truck_parking"), "LKW-Stellplätze");
		need(fields.hall_height !== undefined, "Hallenhöhe (m UKB)");
		need(has("dock_doors"), "Rampentore");
		need(has("ground_level_doors"), "Ebenerdige Tore");
		need(has("wgk"), "WGK");
		need(has("lighting"), "Beleuchtung");
		need(fields.floor_load !== undefined, "Bodentragkraft");
		need(has("sprinkler"), "Sprinkleranlage");
		need(has("heating"), "Heizungsart Halle");
	}
	need(has("certification"), "Zertifizierung");
	need(fields.construction_year !== undefined, "Baujahr");
	need(fields.free_from !== undefined, "Verfügbar ab");
	need(fields.description_note !== undefined, "Objektbeschreibung");
	need(fields.location_note !== undefined, "Lage");
	need(fields.furnishing_note !== undefined, "Ausstattung");
	return missing;
}

export function projectNotProvided(input: Raw, fields: Raw): string[] {
	const missing: string[] = [];
	const need = (ok: boolean, label: string) => {
		if (!ok) missing.push(label);
	};
	need(input.owner_contact_id !== undefined, "Eigentümer");
	need(input.source_link !== undefined, "Interne Notiz: Exposé-/Website-Link");
	need(input.mandate !== undefined, "Interne Notiz: Mandat");
	if (input.marketing_type === "RENT") need(input.internal_rents !== undefined, "Interne Notiz: Mietpreise");
	need(input.internal_commission !== undefined, "Interne Notiz: Provisionsregelung");
	need(fields.sub_headline !== undefined, "Unterzeile (z. B. „Direkt an der A40“)");
	need(fields.courtage !== undefined || fields.courtage_note !== undefined, "Provision");
	need(fields.description_note !== undefined, "Projektbeschreibung");
	need(fields.location_note !== undefined, "Lage");
	need(fields.furnishing_note !== undefined, "Ausstattung");
	return missing;
}

/** Schritte, die nur in der Propstack-Oberfläche gehen – stehen in der Prüfaufgabe. */
export const PROJECT_UI_STEPS = [
	"In Propstack prüfen, dass beide Schalter aktiv sind: „Einheitenliste im Exposé anzeigen“ und „Auf der Landing Page auf die jeweiligen Einheiten verlinken“. Der Connector setzt nur den Schalter für die Einheiten auf der Landing-Page.",
	"Bilder: benannt (z. B. „Außenansicht“), Grundrisse gekennzeichnet, keine Firmenschriftzüge; allgemeine Bilder am Projekt „Auf Einheiten vererben“.",
	"Landing-Page-Vorschau ansehen.",
];

export const OBJECT_UI_STEPS = [
	"In Propstack eintragen: Wesentlicher Energieträger (über den Connector noch nicht möglich).",
	"Bilder: benannt (z. B. „Außenansicht“), Grundrisse gekennzeichnet, keine Firmenschriftzüge.",
	"Landing-Page-Vorschau ansehen.",
];

// ---------- Texte, die im Exposé stehen ----------

export const TEXT_RULES = {
	description_object:
		"Objektbeschreibung als kurzer Fließtext: Hallenfläche, Grundstücksgröße und die wichtigsten Ausstattungsmerkmale. Kein Eigentümername, keine Adresse, keine Preise. Bei Einheiten im Projekt weglassen – wird vom Projekt übernommen",
	description_project:
		"Projektbeschreibung als Fließtext mit sämtlichen Informationen: Gesamtfläche, teilbar in wie viele Abschnitte, Lager, Büro, Rampen usw. Kein Eigentümername, keine Adresse, keine Preise",
	furnishing:
		"Ausstattung als Aufzählung, eine Zeile je Punkt mit „- “ (keine Komma-Kette): alles Bekannte, das in kein Feld passt, z. B. Regalierung, Gleisanschluss. Bei Einheiten im Projekt nur angeben, wenn die Einheit vom Projekt abweicht",
	location:
		"Lage: ein bis zwei Sätze zur Einordnung, dann die Entfernungen in km ab der Adresse als Liste, gruppiert mit Überschriften „Autobahnen:“, „Bundesstraßen:“, „ÖPNV:“, „Häfen:“, „Flughäfen:“ – je Zeile z. B. „A2 (Anschlussstelle Ostwestfalen-Lippe): ca. 0,2 km“. Die Adresse selbst nicht nennen. Bei Einheiten im Projekt weglassen",
};

const TEXT_LABELS: Record<string, string> = {
	description_note: "Beschreibung",
	furnishing_note: "Ausstattung",
	location_note: "Lage",
	other_note: "Sonstiges",
	sub_headline: "Unterzeile",
	title: "Überschrift",
};

export const EXPOSE_TEXT_KEYS = Object.keys(TEXT_LABELS);

const PRICE = /\d[\d.,]*\s*(?:€|eur\b|euro\b)|(?:€|\beur\b|\beuro\b)\s*\d[\d.,]*/i;
/** Komma oder Semikolon als Aufzählungstrenner (nicht das Dezimalkomma in „10,5“). */
const LIST_SEPARATOR = /(?<!\d)[,;]|[,;](?!\d)/g;

/** Wörter, die in vielen Firmennamen stehen und deshalb nichts über den Eigentümer verraten. */
const GENERIC_NAME_TOKENS = new Set([
	"asset", "bau", "capital", "das", "der", "deutschland", "development", "developments", "die", "estate", "europe", "germany", "gesellschaft",
	"gewerbepark", "group", "grundbesitz", "gruppe", "holding", "immobilien", "industrial", "invest", "investment", "logistics", "logistik",
	"logistikpark", "management", "objekt", "objektgesellschaft", "park", "projekt", "projektgesellschaft", "properties", "property", "real", "the",
	"und", "verwaltung",
]);

export interface TextContext {
	/** Name und ggf. Firma des Eigentümer-Kontakts. */
	ownerNames?: string[];
	street?: string;
	city?: string;
	publicPriceConfirmed?: boolean;
}

export interface TextFindings {
	errors: string[];
	warnings: string[];
}

/**
 * Prüft exposé-sichtbare Texte. Fehler = eindeutig gegen die Team-Regeln (wird vor dem Schreiben abgewiesen),
 * Hinweise = bitte prüfen (stehen im Ergebnis und in der Prüfaufgabe).
 */
export function checkExposeTexts(texts: Raw, context: TextContext = {}): TextFindings {
	const errors: string[] = [];
	const warnings: string[] = [];
	const cityTokens = new Set(normalizeText(context.city).split(" "));
	const street = normalizeStreet(context.street);
	for (const [key, label] of Object.entries(TEXT_LABELS)) {
		const text = texts[key];
		if (typeof text !== "string" || !text.trim()) continue;
		const normalized = ` ${normalizeText(text)} `;

		for (const name of context.ownerNames ?? []) {
			const full = normalizeCompany(name);
			if (full.length >= 4 && normalized.includes(` ${full} `)) {
				errors.push(`${label}: nennt den Eigentümer „${name}“ – der Eigentümername darf in Exposé-Texten nicht vorkommen.`);
				continue;
			}
			const token = full.split(" ").find((t) => t.length >= 3 && !/^\d+$/.test(t) && !GENERIC_NAME_TOKENS.has(t) && !cityTokens.has(t));
			if (token && normalized.includes(` ${token} `)) {
				warnings.push(`${label}: enthält „${token}“ – Teil des Eigentümernamens „${name}“? Bitte prüfen.`);
			}
		}

		const price = PRICE.exec(text);
		if (price && !context.publicPriceConfirmed) {
			errors.push(
				`${label}: enthält einen Preis („${price[0].trim()}“). Preise gehören nicht in Exposé-Texte – intern in internal_rent_* bzw. die interne Notiz; öffentlich nur auf ausdrückliche Ansage mit public_price_confirmed.`,
			);
		}

		if (key === "furnishing_note" && !text.includes("\n") && (text.match(LIST_SEPARATOR) ?? []).length >= 2) {
			errors.push("Ausstattung: bitte als Aufzählung schreiben – eine Zeile je Punkt, beginnend mit „- “, nicht als Komma-Kette.");
		}
		if (key === "location_note" && !/\bkm\b/i.test(text)) {
			warnings.push("Lage: keine Entfernungen in km – laut How-to Liste der Entfernungen zu Autobahnen, Bundesstraßen, ÖPNV, Häfen und Flughäfen.");
		}
		if (street.length >= 6 && normalizeStreet(text).includes(street)) {
			warnings.push(`${label}: nennt die Straße „${context.street}“ – die Adresse gehört nicht in Exposé-Texte.`);
		}
	}
	return { errors, warnings };
}

export function throwOnTextErrors(findings: TextFindings): void {
	if (findings.errors.length) throw new PropstackError(`Texte entsprechen nicht den Team-Regeln: ${findings.errors.join(" ")}`, 400);
}

/**
 * „(XX)“ in Überschrift bzw. Name = erste zwei Ziffern der PLZ (How-to: „Logistikhalle in (2-stellige PLZ) Ort“).
 * Falsche Ziffern → Fehler; fehlt die Angabe ganz → Hinweis.
 */
export function checkZipPrefix(label: string, text: unknown, zip: unknown, warnIfAbsent = true): { error?: string; warning?: string } {
	if (typeof text !== "string" || typeof zip !== "string" || zip.trim().length < 2) return {};
	const expected = zip.trim().slice(0, 2);
	const found = /\((\d{2})\)/.exec(text);
	if (found && found[1] !== expected) {
		return { error: `${label} „${text}“: (${found[1]}) passt nicht zur PLZ ${zip.trim()} – richtig wäre (${expected}).` };
	}
	if (!found && warnIfAbsent) return { warning: `${label} ohne „(${expected})“ – Format laut How-to: „Logistikhalle in (${expected}) Ort“.` };
	return {};
}

/** Name und Firma eines Kontakts für die Eigentümer-Prüfung. */
export function ownerNamesOf(contact: Raw | null | undefined): string[] {
	const text = (v: unknown) => {
		const value = v && typeof v === "object" && "value" in (v as Raw) ? (v as Raw).value : v;
		return typeof value === "string" ? value.trim() : "";
	};
	return [...new Set([text(contact?.name), text(contact?.company)].filter(Boolean))];
}
