import { describe, expect, it } from "vitest";
import {
	abweichungen,
	bemerkungVoranstellen,
	type CfFeld,
	istNullflaeche,
	namenInTexten,
	pruefeCustomFields,
	pruefeStandardfelder,
	RegelVerstoss,
} from "../src/regeln";

const REG = new Map<string, CfFeld>([
	["lagerflache", { name: "lagerflache", field_type: "Number", unit: "sqm" }],
	["lagerflache_verfugbar", { name: "lagerflache_verfugbar", field_type: "String" }],
	["mezzanineflache", { name: "mezzanineflache", field_type: "Number", unit: "euro" }],
	["mezzanineflache_gesamt", { name: "mezzanineflache_gesamt", field_type: "Number", unit: "sqm" }],
	["provisionspflichtig", { name: "provisionspflichtig", field_type: "Dropdown" }],
	["aktiv", { name: "aktiv", field_type: "Multiselect", custom_options: [{ id: 182817, name: "Aktiv" }, { id: 182818, name: "Inaktiv" }] }],
	["alt_neubau", { name: "alt_neubau", field_type: "Dropdown", custom_options: [{ id: 180609, name: "Neubau" }] }],
]);

describe("Nullflaechen", () => {
	it("erkennt 0 in allen Schreibweisen", () => {
		for (const v of [0, "0", "0 m²", "0 m² (vermietet)", "ca. 0 m²", "0,0"]) expect(istNullflaeche(v)).toBe(true);
	});
	it("laesst echte Flaechen durch", () => {
		for (const v of [3475, "3.475 m²", "ca. 41.300 m²", "0,5 m²", "9.264 m² (Dublette stillgelegt)", null, ""]) expect(istNullflaeche(v)).toBe(false);
	});
	it("lehnt 0 m² im Verfuegbarkeitsfeld ab", () => {
		expect(() => pruefeCustomFields({ lagerflache_verfugbar: "0 m² (vermietet)" }, REG)).toThrow(RegelVerstoss);
	});
	it("lehnt industrial_area=0 ab", () => {
		expect(() => pruefeStandardfelder({ industrial_area: 0 })).toThrow(RegelVerstoss);
	});
});

describe("Gesperrte Felder", () => {
	it("provisionspflichtig nur leeren", () => {
		expect(() => pruefeCustomFields({ provisionspflichtig: "Ja" }, REG)).toThrow(/Automatisierung/);
		expect(pruefeCustomFields({ provisionspflichtig: null }, REG)).toEqual({ provisionspflichtig: null });
	});
	it("mezzanineflache (Euro-Feld) nie", () => {
		expect(() => pruefeCustomFields({ mezzanineflache: 500 }, REG)).toThrow(/Euro/);
		expect(pruefeCustomFields({ mezzanineflache_gesamt: 500 }, REG)).toEqual({ mezzanineflache_gesamt: 500 });
	});
	it("bemerkung nie direkt", () => {
		expect(() => pruefeCustomFields({ bemerkung: "x" }, REG)).toThrow(/bemerkung_ergaenzen/);
	});
	it("oeffentliche Preisfelder nie", () => {
		expect(() => pruefeStandardfelder({ base_rent: 5.5 })).toThrow(/intern_mietpreis/);
		expect(() => pruefeStandardfelder({ price: 1000 })).toThrow(RegelVerstoss);
	});
	it("note und name nie", () => {
		expect(() => pruefeStandardfelder({ note: "x" })).toThrow(/bemerkung/);
		expect(() => pruefeStandardfelder({ name: "x" })).toThrow(/title/);
	});
	it("unbekanntes Custom Field", () => {
		expect(() => pruefeCustomFields({ stuetzenraster: "12x24" }, REG)).toThrow(/existiert/);
	});
});

describe("Typen", () => {
	it("Zahlenfeld mit formatiertem Text abgelehnt", () => {
		expect(() => pruefeCustomFields({ lagerflache: "3.475 m²" }, REG)).toThrow(/Zahlenfeld/);
	});
	it("Dropdown per Name oder ID, Multiselect als Liste", () => {
		expect(pruefeCustomFields({ alt_neubau: "Neubau" }, REG)).toEqual({ alt_neubau: 180609 });
		expect(pruefeCustomFields({ aktiv: 182818 }, REG)).toEqual({ aktiv: [182818] });
		expect(() => pruefeCustomFields({ alt_neubau: "Bestand" }, REG)).toThrow(/Option/);
	});
	it("plot_area wird Ganzzahl (82600.0 -> HTTP 500)", () => {
		expect(pruefeStandardfelder({ plot_area: 82600.0 })).toEqual({ plot_area: 82600 });
	});
	it("Komma-Zahl als Text abgelehnt", () => {
		expect(() => pruefeStandardfelder({ hall_height: "7,25" })).toThrow(/Komma/);
	});
});

describe("Texte und Bemerkung", () => {
	it("findet Eigentuemernamen in exposé-sichtbaren Texten", () => {
		const t = namenInTexten({ description_note: "Halle von Scheren Logistik", bemerkung: "Scheren" }, ["Scheren"]);
		expect(t).toEqual(['description_note enthaelt "Scheren"']);
	});
	it("Bemerkung: neu vorne, alt als Historie", () => {
		expect(bemerkungVoranstellen("", "neu", "2026-09-29")).toBe("neu");
		expect(bemerkungVoranstellen("alt", "neu", "2026-09-29")).toContain("--- HISTORISCH (uebernommen 2026-09-29) ---\nalt");
		expect(bemerkungVoranstellen("x\n--- HISTORISCH ---\nalt", "neu", "d")).toBe("neu\n\nx\n--- HISTORISCH ---\nalt");
	});
	it("Nachkontrolle vergleicht Multiselect und Zahlen", () => {
		expect(abweichungen({ "cf.aktiv": 182818, "cf.lagerflache": 3475 }, { "cf.aktiv": ["182818"], "cf.lagerflache": 3475.0 })).toEqual([]);
		expect(abweichungen({ courtage: "Provisionsfrei" }, { courtage: "provisionspflichtig" })).toHaveLength(1);
	});
});
