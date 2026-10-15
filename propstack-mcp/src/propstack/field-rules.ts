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
	mietpreis_hallenflache: "Mietpreise nie in öffentliche Felder – intern_mietpreis_hallenflache verwenden",
	mietpreis_buroflache: "Mietpreise nie in öffentliche Felder – intern_mietpreis_buro verwenden",
	mietpreis_mezzanine: "Mietpreise nie in öffentliche Felder – intern_mietpreis_mezzanine verwenden",
	bemerkung: "nicht direkt überschreiben – bemerkung_append verwenden (vorhandene Bemerkung bleibt erhalten)",
};

const BLOCK_EVEN_NULL = new Set(["bemerkung"]);

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
): Promise<ValidatedCustomFields | undefined> {
	if (!fields || !Object.keys(fields).length) return undefined;
	const defs = await loadFieldDefs(client, entity);
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
		throw new PropstackError(`Custom-Felder ungültig: ${errors.join("; ")}. Gültige Felder über list_fields.`, 400);
	}
	return { expect, send };
}
