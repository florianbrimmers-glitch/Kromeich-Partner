import { describe, expect, it } from "vitest";
import { formatPhone, isMobile, normalizePhone } from "../src/propstack/dedupe";

// Befund Florian, 13.11.2026: „Wenn die +49 oder andere Ländervorwahlen eingegeben werden, kommt trotzdem noch eine 0
// danach. So können wir die nicht anwählen.“ In Propstack standen bei 12 der 600 neuesten Kontakte Nummern wie
// „+49 (0) 151 …“, „+49 (0)162 …“, „+49(0)215 …“ – so, wie sie in E-Mail-Signaturen stehen.

describe("Telefonnummern: keine 0 nach der Ländervorwahl", () => {
	it("entfernt „(0)“ nach der Ländervorwahl – in allen Schreibweisen, die im Konto vorkommen", () => {
		expect(formatPhone("+49 (0) 151 12345678")).toBe("+49 151 12345678");
		expect(formatPhone("+49 (0)162 1234567")).toBe("+49 162 1234567");
		expect(formatPhone("+49(0)2151 1234 5678")).toBe("+49 2151 1234 5678");
		expect(formatPhone("+49 (0) 761-12345678")).toBe("+49 761-12345678");
		expect(formatPhone("0049 (0) 171 3920055")).toBe("0049 171 3920055");
		expect(formatPhone("  +49 ( 0 ) 171 3920055 ")).toBe("+49 171 3920055");
		// andere Länder genauso
		expect(formatPhone("+44 (0)20 7946 0958")).toBe("+44 20 7946 0958");
		expect(formatPhone("+31 (0)6 12345678")).toBe("+31 6 12345678");
		expect(formatPhone("+43 (0) 1 2345678")).toBe("+43 1 2345678");
		// auch bei einem Land, das nicht in der Liste steht: Die Klammer sagt selbst, dass die 0 entfällt
		expect(formatPhone("+61 (0)2 9876 5432")).toBe("+61 2 9876 5432");
	});

	it("entfernt eine 0 ohne Klammern, wo nach der Ländervorwahl nie eine 0 folgt – die übrige Schreibweise bleibt", () => {
		expect(formatPhone("+49 0171 3920055")).toBe("+49 171 3920055");
		expect(formatPhone("+4901713920055")).toBe("+491713920055");
		expect(formatPhone("+49-0221-4710199")).toBe("+49-221-4710199");
		expect(formatPhone("0049 0221 4710199")).toBe("0049 221 4710199");
		expect(formatPhone("+49 (0171) 3920055")).toBe("+49 (171) 3920055");
		expect(formatPhone("+41 044 123 45 67")).toBe("+41 44 123 45 67");
		expect(formatPhone("+420 0601 123 456")).toBe("+420 601 123 456");
	});

	it("lässt in Ruhe, was richtig ist oder was sich nicht sicher beurteilen lässt", () => {
		for (const nummer of [
			"+49 171 3920055",
			"+49 221 4710-198",
			"0171 3920055", // ohne Ländervorwahl: innerhalb Deutschlands wählbar
			"(0221) 4710199",
			"0221 / 47 10 199",
			"+1 212 555 0100",
			"+49 30 12345678", // 30 ist hier die Ortsvorwahl Berlin, keine 0 nach der Ländervorwahl
			"+7 0495 1234567", // Land nicht in der Liste, keine Klammer: nicht anfassen
			"+70495 1234567",
			"Zentrale",
			"",
		]) {
			expect(formatPhone(nummer), nummer).toBe(nummer);
		}
		expect(formatPhone(undefined)).toBeUndefined();
		expect(formatPhone(null)).toBeNull();
	});

	it("Italien und andere Länder, in denen die 0 zur Nummer gehört: Die 0 bleibt, nur die Klammer fällt weg", () => {
		expect(formatPhone("+39 06 1234567")).toBe("+39 06 1234567");
		expect(formatPhone("+39061234567")).toBe("+39061234567");
		expect(formatPhone("+39 (0)6 1234567")).toBe("+39 06 1234567");
		expect(formatPhone("+225 07 12 34 56 78")).toBe("+225 07 12 34 56 78");
	});

	it("Vergleich und Mobil-Erkennung sehen durch die 0 hindurch – dieselbe Nummer ist dieselbe Nummer", () => {
		const formen = ["+49 (0) 171 3920055", "+49 0171 3920055", "+49 171 3920055", "0171 3920055", "0049 (0)171 39200-55", "+491713920055"];
		expect(new Set(formen.map(normalizePhone))).toEqual(new Set(["491713920055"]));
		for (const form of formen) expect(isMobile(form), form).toBe(true);
		// Festnetz bleibt Festnetz
		expect(isMobile("+49 (0) 221 4710199")).toBe(false);
		expect(normalizePhone("+49 (0) 221 4710199")).toBe("492214710199");
	});
});
