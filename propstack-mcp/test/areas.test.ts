import { describe, expect, it } from "vitest";
import { areaNumber, computedTotal, totalDiffers } from "../src/propstack/areas";

describe("Gesamtfläche = Hallenfläche + Mezzaninefläche", () => {
	it("liest Flächen in allen Schreibweisen, die Propstack liefert", () => {
		expect(areaNumber(1050)).toBe(1050);
		expect(areaNumber("1050")).toBe(1050);
		expect(areaNumber("1.050 m²")).toBe(1050);
		expect(areaNumber("1.050,5 m²")).toBe(1050.5);
		expect(areaNumber("10.5")).toBe(10.5);
		expect(areaNumber("12.345.678")).toBe(12345678);
		expect(areaNumber({ pretty_value: "1.050 m²", value: 1050 })).toBe(1050);
		expect(areaNumber({ label: "Hallenfläche", value: "5863.0" })).toBe(5863);
		for (const empty of [null, undefined, "", "0 m² (vermietet)", "auf Anfrage", {}, [], { value: null }]) expect(areaNumber(empty)).toBeUndefined();
	});

	it("rechnet Halle + Mezzanine und weist abweichende Werte ab", () => {
		expect(computedTotal(5165, undefined)).toBe(5165);
		expect(computedTotal(2399, 1375)).toBe(3774);
		expect(computedTotal(1050.25, 99.5)).toBe(1149.75);
		// derselbe Wert ist in Ordnung (ältere Tool-Listen schicken ihn noch mit)
		expect(computedTotal(2399, 1375, 3774)).toBe(3774);
		expect(() => computedTotal(5165, 1050, 6585)).toThrow(
			/Hallenfläche 5\.165 m² \+ Mezzanine 1\.050 m² = 6\.215 m² \(ohne Büro\)\. Angegeben waren 6\.585 m²/,
		);
		// ohne Hallenfläche gilt die Regel nicht (z. B. reine Bürofläche)
		expect(computedTotal(undefined, 400, 900)).toBeUndefined();
		expect(computedTotal(0, 400)).toBeUndefined();
	});

	it("erkennt eine gespeicherte Gesamtfläche, die nicht zur Rechnung passt", () => {
		expect(totalDiffers(6585, 6215)).toBe(true);
		expect(totalDiffers(6215, 6215)).toBe(false);
		expect(totalDiffers(undefined, 6215)).toBe(false); // nicht lesbar → kein Alarm
	});
});
