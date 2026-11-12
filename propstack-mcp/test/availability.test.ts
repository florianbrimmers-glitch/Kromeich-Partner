import { describe, expect, it } from "vitest";
import { availabilityMirror, bezugDeviation, singleDate } from "../src/propstack/availability";
import type { FieldDef } from "../src/propstack/field-rules";

const def = (key: string, type: string): [string, FieldDef] => [key, { key, options: [], type }];
const DEFS = new Map<string, FieldDef>([def("bezug", "String"), def("bezug_datum", "Date")]);

describe("„Bezug“ folgt „Verfügbar ab“", () => {
	it("singleDate: genau ein Datum im Text, sonst keines", () => {
		expect(singleDate("01.04.2027")).toBe("2027-04-01");
		expect(singleDate("ab 01.07.2027")).toBe("2027-07-01");
		expect(singleDate("ab 1.4.2027")).toBe("2027-04-01");
		expect(singleDate("01.04.27")).toBe("2027-04-01");
		expect(singleDate("frühestens 2027-04-01")).toBe("2027-04-01");
		expect(singleDate("01.04.2027 (laut Mail 2027-04-01)")).toBe("2027-04-01");
		// kein Datum
		for (const text of ["sofort", "auf Anfrage", "Q3 2027", "Q2/Q3 2027", "ab 2027", "Mitte 2028", "vermietet", "kurzfristig"]) expect(singleDate(text)).toBeUndefined();
		// zwei verschiedene Daten oder ein unmögliches: lieber keines als ein geratenes
		expect(singleDate("01.04.2027 oder 01.07.2027")).toBeUndefined();
		expect(singleDate("31.02.2027")).toBeUndefined();
		expect(singleDate("Version 1.2.3")).toBeUndefined();
	});

	it("availabilityMirror: Text nach „Bezug“, Datum nach „Bezug (Datum)“ – veraltetes Datum wird geleert", () => {
		expect(availabilityMirror("ab 01.07.2027", DEFS, undefined, { clear: true })).toEqual({ bezug: "ab 01.07.2027", bezug_datum: "2027-07-01" });
		expect(availabilityMirror("Q3 2027", DEFS, undefined, { clear: true })).toEqual({ bezug: "Q3 2027", bezug_datum: null });
		expect(availabilityMirror("vermietet", DEFS, undefined, { clear: true })).toEqual({ bezug: "vermietet", bezug_datum: null });
		// geleert (z. B. Rückgängig auf einen leeren Stand)
		expect(availabilityMirror(null, DEFS, undefined, { clear: true })).toEqual({ bezug: null, bezug_datum: null });
		// beim Anlegen gibt es nichts zu leeren
		expect(availabilityMirror("sofort", DEFS, undefined, { clear: false })).toEqual({ bezug: "sofort" });
	});

	it("ausdrücklich übergebene Custom-Felder haben Vorrang; fehlende Felder werden nicht erfunden", () => {
		expect(availabilityMirror("01.04.2027", DEFS, { bezug: "April 2027" }, { clear: true })).toEqual({ bezug_datum: "2027-04-01" });
		expect(availabilityMirror("Q3 2027", DEFS, { bezug_datum: "2027-07-01" }, { clear: true })).toEqual({ bezug: "Q3 2027" });
		expect(availabilityMirror("01.04.2027", new Map(), undefined, { clear: true })).toEqual({});
		// „Bezug“ als Auswahlfeld (anderes Konto): nicht anfassen
		expect(availabilityMirror("sofort", new Map([def("bezug", "Dropdown")]), undefined, { clear: true })).toEqual({});
	});

	it("bezugDeviation meldet nur echte Abweichungen", () => {
		expect(bezugDeviation("sofort", undefined)).toBeUndefined();
		expect(bezugDeviation("sofort", " sofort ")).toBeUndefined();
		expect(bezugDeviation("Q3 2027", "sofort")).toMatch(/„Bezug“ \(„sofort“\) weicht von „Verfügbar ab“ \(„Q3 2027“\) ab.*free_from setzen/);
		expect(bezugDeviation(null, "sofort")).toMatch(/„Verfügbar ab“ \(leer\)/);
	});
});
