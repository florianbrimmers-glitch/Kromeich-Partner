import { describe, expect, it } from "vitest";
import { countryCallingCode, formatPhone, isMobile, normalizePhone } from "../src/propstack/dedupe";

// Befund Florian, 13.11.2026: „Wenn die +49 oder andere Ländervorwahlen eingegeben werden, kommt trotzdem noch eine 0
// danach. So können wir die nicht anwählen.“ In Propstack standen bei 94 von 4.922 Kontakten Nummern wie
// „+49 (0) 151 …“, „+49 (0)162 …“, „+49(0)215 …“ – so, wie sie in E-Mail-Signaturen stehen.
// Zweite Entscheidung am selben Tag: alles einheitlich mit Ländervorwahl („0171 …“ → „+49 171 …“).

describe("Telefonnummern: keine 0 nach der Ländervorwahl", () => {
	it("entfernt „(0)“ nach der Ländervorwahl – in allen Schreibweisen, die im Konto vorkommen", () => {
		expect(formatPhone("+49 (0) 151 12345678")).toBe("+49 151 12345678");
		expect(formatPhone("+49 (0)162 1234567")).toBe("+49 162 1234567");
		expect(formatPhone("+49(0)2151 1234 5678")).toBe("+49 2151 1234 5678");
		expect(formatPhone("+49 (0) 761-12345678")).toBe("+49 761-12345678");
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
		expect(formatPhone("+49 (0171) 3920055")).toBe("+49 (171) 3920055");
		expect(formatPhone("+41 044 123 45 67")).toBe("+41 44 123 45 67");
		expect(formatPhone("+420 0601 123 456")).toBe("+420 601 123 456");
	});

	it("Italien und andere Länder, in denen die 0 zur Nummer gehört: Die 0 bleibt, nur die Klammer fällt weg", () => {
		expect(formatPhone("+39 06 1234567")).toBe("+39 06 1234567");
		expect(formatPhone("+39061234567")).toBe("+39061234567");
		expect(formatPhone("+39 (0)6 1234567")).toBe("+39 06 1234567");
		expect(formatPhone("+225 07 12 34 56 78")).toBe("+225 07 12 34 56 78");
	});

	it("richtig geschriebene internationale Nummern bleiben, wie sie sind", () => {
		for (const nummer of ["+49 171 3920055", "+49 221 4710-198", "+1 212 555 0100", "+49 30 12345678", "+7 0495 1234567", "+70495 1234567"]) {
			expect(formatPhone(nummer), nummer).toBe(nummer);
		}
	});
});

describe("Telefonnummern: einheitlich mit Ländervorwahl", () => {
	it("„00“ wird zu „+“", () => {
		expect(formatPhone("0049 171 3920055")).toBe("+49 171 3920055");
		expect(formatPhone("0049 (0) 171 3920055")).toBe("+49 171 3920055");
		expect(formatPhone("0049 0221 4710199")).toBe("+49 221 4710199");
		expect(formatPhone("0031 6 12345678")).toBe("+31 6 12345678");
		expect(formatPhone("00 7 495 1234567")).toBe("+7 495 1234567");
	});

	it("eine Nummer ohne Ländervorwahl gilt ohne Landesangabe als deutsch und bekommt +49", () => {
		expect(formatPhone("0171 3920055")).toBe("+49 171 3920055");
		expect(formatPhone("0221 4710199")).toBe("+49 221 4710199");
		expect(formatPhone("0221/4710-199")).toBe("+49 221/4710-199");
		expect(formatPhone("02214710199")).toBe("+49 2214710199");
		expect(formatPhone("(0221) 4710199")).toBe("+49 221 4710199");
		expect(formatPhone("(0 22 1) 47 10 199")).toBe("+49 22 1 47 10 199");
		expect(formatPhone(" 0171 3920055 ")).toBe("+49 171 3920055");
		for (const land of ["Deutschland", "deutschland", "DE", "Germany", " DEU "]) expect(formatPhone("0171 3920055", land), land).toBe("+49 171 3920055");
	});

	it("ist das Land angegeben, bekommt die Nummer dessen Vorwahl – in Italien bleibt die 0", () => {
		expect(formatPhone("0664 1234567", "Österreich")).toBe("+43 664 1234567");
		expect(formatPhone("044 123 45 67", "Schweiz")).toBe("+41 44 123 45 67");
		expect(formatPhone("06 12345678", "Niederlande")).toBe("+31 6 12345678");
		expect(formatPhone("020 7946 0958", "UK")).toBe("+44 20 7946 0958");
		expect(formatPhone("06 1234567", "Italien")).toBe("+39 06 1234567");
		expect(formatPhone("(06) 1234567", "Italien")).toBe("+39 06 1234567");
	});

	it("ist ein Land angegeben, das der Connector nicht kennt, bleibt die Nummer unverändert – lieber so als eine falsche Vorwahl", () => {
		expect(formatPhone("0495 1234567", "Russland")).toBe("0495 1234567");
		expect(formatPhone("021 1234567", "Südafrika")).toBe("021 1234567");
		expect(countryCallingCode("Russland")).toBeNull();
		expect(countryCallingCode("")).toBeUndefined();
		expect(countryCallingCode(undefined)).toBeUndefined();
		expect(countryCallingCode("Österreich")).toBe("43");
	});

	it("was nicht wie eine Nummer mit 0 oder + beginnt, bleibt ganz", () => {
		for (const text of ["171 3920055", "Zentrale", "-22", "", "0", "00"]) expect(formatPhone(text), text).toBe(text);
		expect(formatPhone(undefined)).toBeUndefined();
		expect(formatPhone(null)).toBeNull();
	});

	it("Vergleich und Mobil-Erkennung sehen durch alle Schreibweisen hindurch – dieselbe Nummer ist dieselbe Nummer", () => {
		const formen = ["+49 (0) 171 3920055", "+49 0171 3920055", "+49 171 3920055", "0171 3920055", "0049 (0)171 39200-55", "+491713920055", "(0171) 3920055"];
		expect(new Set(formen.map(normalizePhone))).toEqual(new Set(["491713920055"]));
		for (const form of formen) expect(isMobile(form), form).toBe(true);
		// Festnetz bleibt Festnetz
		expect(isMobile("+49 (0) 221 4710199")).toBe(false);
		expect(normalizePhone("+49 (0) 221 4710199")).toBe("492214710199");
		expect(normalizePhone("0221 4710199")).toBe("492214710199");
	});
});
