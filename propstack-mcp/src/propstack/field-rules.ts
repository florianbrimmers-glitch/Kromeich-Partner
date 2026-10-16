import { type CustomFieldEntity, PropstackClient, PropstackError } from "../propstack-client";
import { scalar } from "./mappers";

// Custom-Felder: Registry lesen und Eingaben streng prüfen.
// Quelle der Regeln: Notion „Propstack API – Feld-Mapping“ (Korrekturen) und Skill
// propstack-expose-workflow. Propstack bestätigt falsche Werte mit HTTP 200 und
// speichert Unsinn – deshalb wird hier vor dem Write abgewiesen statt geraten.

type Raw = Record<string, unknown>;

export interface CustomOption {
	id: number;
	name: string;
}

export interface FieldDef {
	key: string;
	label?: string;
	type: string;
	unit?: string;
	options: CustomOption[];
}

/**
 * Objektfelder, die über custom_fields NICHT gesetzt werden dürfen.
 * null (= leeren) bleibt erlaubt, außer wo anders vermerkt.
 */
export const BLOCKED_OBJECT_FIELDS: Record<string, string> = {
	provisionspflichtig: "nie setzen – jeder Wert bricht eine bestehende Automatisierung (nur null zum Leeren erlaubt)",
	mezzanineflache: "trägt die Einheit Euro – Fläche wird zum Geldbetrag. Stattdessen mezzanineflache_gesamt / mezzanineflache_verfugbar",
	bemerkung: "nicht direkt überschreiben – bemerkung_append verwenden (vorhandene Bemerkung bleibt erhalten)",
};

const BLOCK_EVEN_NULL = new Set(["bemerkung"]);

/**
 * Öffentliche Preisfelder (Exposé/Portale): nur auf Nachfrage oder ausdrückliche Ansage des Nutzers
 * (public_price_confirmed). Interne Preise (intern_*) sind immer erlaubt. Entscheidung Florian, 15.10.2026.
 */
export const PUBLIC_PRICE_FIELDS: Record<string, string> = {
	mietpreis_buroflache: "intern_mietpreis_buro",
	mietpreis_hallenflache: "intern_mietpreis_hallenflache",
	mietpreis_mezzanine: "intern_mietpreis_mezzanine",
};

export const PUBLIC_PRICE_HINT =
	"Öffentliche Preise nur auf ausdrückliche Ansage: erst den Nutzer fragen, dann mit public_price_confirmed: true erneut aufrufen. Interne Preise jederzeit in intern_mietpreis_hallenflache / intern_mietpreis_buro / intern_mietpreis_mezzanine.";

export async function loadFieldDefs(client: Pick<PropstackClient, "listCustomFieldGroups">, entity: CustomFieldEntity): Promise<Map<string, FieldDef>> {
	const defs = new Map<string, FieldDef>();
	for (const group of (await client.listCustomFieldGroups(entity)).rows) {
		for (const f of Array.isArray(group.custom_fields) ? (group.custom_fields as Raw[]) : []) {
			const options = (Array.isArray(f.custom_options) ? (f.custom_options as Raw[]) : [])
				.filter((o) => typeof o.id === "number")
				.map((o) => ({ id: o.id as number, name: String(scalar(o.name)) }));
			const unit = typeof f.unit === "string" && f.unit ? f.unit : undefined;
			const label = typeof f.pretty_name === "string" ? f.pretty_name : undefined;
			defs.set(String(f.name), { key: String(f.name), label, options, type: String(f.field_type), unit });
		}
	}
	return defs;
}

function findOption(def: FieldDef, value: unknown): CustomOption | undefined {
	if (typeof value === "number") return def.options.find((o) => o.id === value);
	if (typeof value === "string") {
		const wanted = value.trim().toLowerCase();
		return def.options.find((o) => o.name.trim().toLowerCase() === wanted || String(o.id) === wanted);
	}
	return undefined;
}

function optionList(def: FieldDef): string {
	return def.options.map((o) => `${o.name} (${o.id})`).join(", ");
}

/** m²-Wert mit genau drei Nachkommastellen = fast sicher ein deutscher Tausenderpunkt (6.417 statt 6417). */
function looksLikeThousandsDot(value: number): boolean {
	if (Number.isInteger(value)) return false;
	const decimals = String(value).split(".")[1] ?? "";
	return decimals.length === 3;
}

export interface ValidatedCustomFields {
	/** So wird an Propstack gesendet (Auswahlfelder als Option-IDs). */
	send: Raw;
	/** So wird zurückgelesen verglichen (Auswahlfelder als ID und Name). */
	expect: Raw;
}

/** Custom-Felder gegen die Registry prüfen – sonst verwirft oder verfälscht Propstack sie still. */
export async function validateCustomFields(
	client: Pick<PropstackClient, "listCustomFieldGroups">,
	entity: CustomFieldEntity,
	fields: Record<string, unknown> | undefined,
	preloaded?: Map<string, FieldDef>,
	options: { publicPriceConfirmed?: boolean } = {},
): Promise<ValidatedCustomFields | undefined> {
	if (!fields || !Object.keys(fields).length) return undefined;
	const defs = preloaded ?? (await loadFieldDefs(client, entity));
	const blocked = entity === "for_properties" ? BLOCKED_OBJECT_FIELDS : {};
	const errors: string[] = [];
	const send: Raw = {};
	const expect: Raw = {};
	for (const [key, value] of Object.entries(fields)) {
		const def = defs.get(key);
		if (!def) {
			errors.push(`unbekanntes Feld "${key}"`);
			continue;
		}
		if (blocked[key] && (value !== null || BLOCK_EVEN_NULL.has(key))) {
			errors.push(`"${key}" gesperrt: ${blocked[key]}`);
			continue;
		}
		if (entity === "for_properties" && PUBLIC_PRICE_FIELDS[key] && value !== null && !options.publicPriceConfirmed) {
			errors.push(`"${key}" ist ein öffentlicher Preis (intern: ${PUBLIC_PRICE_FIELDS[key]})`);
			continue;
		}
		if (value === null) {
			send[key] = null;
			expect[key] = null;
			continue;
		}
		const fail = (expected: string) => errors.push(`"${key}" erwartet ${expected}`);
		switch (def.type) {
			case "Number": {
				// Bewusst KEINE Umwandlung von Text: "7,25" kürzt Propstack auf 7, "6.417" ist mehrdeutig.
				if (typeof value !== "number" || !Number.isFinite(value)) {
					fail(`eine nackte Zahl ohne Einheit und Tausenderpunkt, Dezimalpunkt (z. B. 10.5)${def.unit ? ` – Einheit ${def.unit}` : ""}`);
				} else if (def.unit === "sqm" && value === 0) {
					fail("eine Fläche > 0 – 0 m² wird nie eingetragen (Feld leer lassen oder null)");
				} else if (def.unit === "sqm" && looksLikeThousandsDot(value)) {
					fail(`m² als ganze Zahl – ${value} sieht nach Tausenderpunkt aus (gemeint ${Math.round(value * 1000)}?)`);
				} else {
					send[key] = value;
					expect[key] = value;
				}
				break;
			}
			case "Boolean":
				if (typeof value !== "boolean") fail("true/false");
				else send[key] = expect[key] = value;
				break;
			case "Date":
				if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) fail("ein Datum JJJJ-MM-TT");
				else send[key] = expect[key] = value;
				break;
			case "Dropdown": {
				const option = findOption(def, value);
				if (!option) fail(`eine Option: ${optionList(def)}`);
				else {
					send[key] = option.id;
					expect[key] = option;
				}
				break;
			}
			case "Multiselect": {
				const values = Array.isArray(value) ? value : [value];
				const options = values.map((v) => findOption(def, v));
				if (!values.length || options.some((o) => !o)) fail(`Optionen aus: ${optionList(def)}`);
				else {
					send[key] = options.map((o) => o!.id);
					expect[key] = options;
				}
				break;
			}
			default:
				if (typeof value !== "string" && typeof value !== "number") fail("einen Text");
				else send[key] = expect[key] = String(value);
		}
	}
	if (errors.length) {
		const priceHint = errors.some((e) => e.includes("öffentlicher Preis")) ? ` ${PUBLIC_PRICE_HINT}` : "";
		throw new PropstackError(`Custom-Felder ungültig: ${errors.join("; ")}. Gültige Felder über list_fields.${priceHint}`, 400);
	}
	return { expect, send };
}

// ---------- Flächen spiegeln ----------
// Exposé und Teamansicht lesen die Flächen-Custom-Felder (lagerflache, buroflache …),
// nicht die Standardfelder. Skill: „Flächen-Custom-Fields doppelt setzen … immer alle Varianten.“
// Referenz: Einheit 4465616 (Baumstraße Unit 1).

const AREA_MIRRORS: Record<string, { always: string[]; available: string[] }> = {
	hall_height: { always: ["hallenhohe"], available: [] },
	industrial_area: { always: ["lagerflache", "lagerflache_gesamt"], available: ["lagerflache_verfugbar"] },
	total_floor_space: { always: ["gebaudeflache_gesamt"], available: ["gebaudeflache_verfugbar"] },
	usable_floor_space: { always: ["buroflache", "buroflache_gesamt"], available: ["buroflache_verfugbar"] },
};

function formatSqm(value: number): string {
	return `${value.toLocaleString("de-DE", { maximumFractionDigits: 2 })} m²`;
}

/** Custom-Felder mit gleicher Bedeutung, die getrennt gelesen werden – jeweils beide setzen. */
const CUSTOM_FIELD_PAIRS: [string, string][] = [["beleuchtung_halle", "beleuchtung"]];

export type RentState = "available" | "rented" | "unknown";

/**
 * Custom-Feld-Werte, die aus Standardfeldern folgen. Explizit übergebene Custom-Felder haben Vorrang.
 * rent = available: *_verfugbar = Fläche. rent = rented: *_verfugbar (Text) = „X m² (vermietet)“.
 * flags: zusätzlich status_logistik und aktiv setzen (beim Anlegen bzw. wenn rented oder Status geändert wird).
 * „Aktiv“ NUR bei Status Vermarktung und nicht vermietet (marketable) – sonst „Inaktiv“, damit Objekte in
 * Akquise/Vorbereitung nicht in Automatisierungen (Exposéversand, Webseite) landen.
 * Ablauf laut Team-Prozess: vermietete Einheit → status_logistik Inaktiv, aktiv Inaktiv, Fläche „(vermietet)“.
 */
export function mirroredCustomFields(
	fields: Raw,
	defs: Map<string, FieldDef>,
	explicit: Raw | undefined,
	options: { rent: RentState; flags: boolean; marketable: boolean; priceOnInquiry: boolean },
): Raw {
	const out: Raw = {};
	const free = (key: string) => defs.has(key) && !(explicit && key in explicit) && !BLOCKED_OBJECT_FIELDS[key];
	const put = (key: string, value: number, suffix = "") => {
		if (!free(key)) return;
		const def = defs.get(key)!;
		if (def.type === "Number") {
			if (!suffix) out[key] = value;
		} else out[key] = `${formatSqm(value)}${suffix}`;
	};
	for (const [field, targets] of Object.entries(AREA_MIRRORS)) {
		const value = fields[field];
		if (typeof value !== "number") continue;
		for (const key of targets.always) put(key, value);
		if (options.rent === "available") for (const key of targets.available) put(key, value);
		if (options.rent === "rented") for (const key of targets.available) put(key, value, " (vermietet)");
	}
	if (options.flags) {
		const active = options.rent === "available" && options.marketable;
		if (free("status_logistik")) out.status_logistik = active ? "Aktiv" : "Inaktiv";
		if (free("aktiv")) out.aktiv = [active ? "Aktiv" : "Inaktiv"];
	}
	// Feldpaare, die Exposé/Teamansicht getrennt lesen (live 16.10.: beleuchtung_halle gesetzt, beleuchtung leer)
	for (const [one, other] of CUSTOM_FIELD_PAIRS) {
		for (const [from, to] of [[one, other], [other, one]]) {
			const value = explicit?.[from];
			if (value === undefined || value === null || !free(to) || defs.get(from)?.type !== defs.get(to)?.type) continue;
			out[to] = value;
		}
	}
	if (options.priceOnInquiry && defs.get("preisangabe")?.type === "String" && !(explicit && "preisangabe" in explicit)) {
		out.preisangabe = "auf Anfrage";
	}
	return out;
}
