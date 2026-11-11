import { describe, expect, it } from "vitest";
import { appendNote, containsBlock, splitNewParts } from "../src/propstack/notes";

const STAMP = "Ergänzt über Claude (Propstack MCP) von Florian Brimmers am 2026-11-11.";
const OLD_STAMP = "Ergänzt über Claude (Propstack MCP) von Florian Brimmers am 2026-11-10.";
const PARKING = "Stellplatzmieten laut Hillwood (Mail vom 10.11.2026): Pkw 50 €, Lkw 100 € je Stellplatz und Monat, netto.";

describe("Notizen nicht doppelt anhängen", () => {
	it("containsBlock vergleicht ganze, aufeinanderfolgende Zeilen (Leerraum egal)", () => {
		const text = `Angelegt am 2026-11-09.\nMandat: kein Alleinmandat\n\n${OLD_STAMP}\n${PARKING}`;
		expect(containsBlock(text, PARKING)).toBe(true);
		expect(containsBlock(text, `  ${PARKING.replace(": Pkw", ":  Pkw")}  `)).toBe(true);
		expect(containsBlock(text.replace(/\n/g, "\r\n"), PARKING)).toBe(true);
		// ein kurzer Text, der nur Teil einer längeren Zeile ist, gilt nicht als vorhanden
		expect(containsBlock(text, "Stellplatzmieten laut Hillwood")).toBe(false);
		expect(containsBlock(text, "Mandat")).toBe(false);
		// mehrzeilig: nur als zusammenhängender Block
		expect(containsBlock(text, `${OLD_STAMP}\n${PARKING}`)).toBe(true);
		expect(containsBlock(text, `Mandat: kein Alleinmandat\n${PARKING}`)).toBe(false);
		expect(containsBlock(text, "")).toBe(true);
	});

	it("splitNewParts trennt Neues von Vorhandenem – auch untereinander", () => {
		expect(splitNewParts(`${OLD_STAMP}\n${PARKING}`, [PARKING, "Mandat: Alleinmandat", "Mandat: Alleinmandat"])).toEqual({
			fresh: ["Mandat: Alleinmandat"],
			present: [PARKING, "Mandat: Alleinmandat"],
		});
	});

	it("appendNote: Sachnotiz – derselbe Text wird nie noch einmal angehängt, egal von wann", () => {
		const first = appendNote("", STAMP, [PARKING]);
		expect(first.text).toBe(`${STAMP}\n${PARKING}`);
		const again = appendNote(`${OLD_STAMP}\n${PARKING}`, STAMP, [PARKING]);
		expect(again).toEqual({ addition: undefined, present: [PARKING], text: undefined });
		// nur der neue Teil kommt dazu
		const partly = appendNote(`${OLD_STAMP}\n${PARKING}`, STAMP, [PARKING, "Mandat: Alleinmandat"]);
		expect(partly.text).toBe(`${OLD_STAMP}\n${PARKING}\n\n${STAMP}\nMandat: Alleinmandat`);
		expect(partly.addition).toBe(`${STAMP}\nMandat: Alleinmandat`);
		expect(partly.present).toEqual([PARKING]);
	});

	it("appendNote mit sameStampOnly: Änderungsvermerk – doppelt nur am selben Tag vom selben Nutzer", () => {
		const note = "Verfügbarkeit laut Eigentümer aktualisiert.";
		const sameDay = appendNote(`${STAMP}\n${note}`, STAMP, [note], { sameStampOnly: true });
		expect(sameDay.text).toBeUndefined();
		expect(sameDay.present).toEqual([note]);
		// derselbe Vermerk an einem späteren Tag ist ein neuer Protokolleintrag
		const laterDay = appendNote(`${OLD_STAMP}\n${note}`, STAMP, [note], { sameStampOnly: true });
		expect(laterDay.text).toBe(`${OLD_STAMP}\n${note}\n\n${STAMP}\n${note}`);
		// anderer Vermerk am selben Tag wird angehängt
		expect(appendNote(`${STAMP}\n${note}`, STAMP, ["Status auf Abgeschlossen."], { sameStampOnly: true }).addition).toBe(`${STAMP}\nStatus auf Abgeschlossen.`);
	});

	it("appendNote mit always: Vermerke, die der Connector bei einer echten Änderung erzeugt, gelten nie als doppelt", () => {
		const event = "Gebäudefläche gesamt an die Gesamtfläche angeglichen (Halle + Mezzanine, ohne Büro): 2.500 m² statt 3.000 m².";
		const given = "Verfügbarkeit laut Eigentümer aktualisiert.";
		// derselbe Wortlaut steht heute schon da (angleichen → rückgängig → erneut angleichen) → kommt trotzdem dazu
		const again = appendNote(`${STAMP}\n${event}`, STAMP, [], { always: [event], sameStampOnly: true });
		expect(again.text).toBe(`${STAMP}\n${event}\n\n${STAMP}\n${event}`);
		// der mitgegebene Vermerk daneben bleibt geschützt: nur das Ereignis kommt dazu, und present meldet den Rest
		const mixed = appendNote(`${STAMP}\n${given}`, STAMP, [given], { always: [event], sameStampOnly: true });
		expect(mixed.addition).toBe(`${STAMP}\n${event}`);
		expect(mixed.present).toEqual([given]);
		// weder Ereignis noch Neues: nichts anzuhängen
		expect(appendNote(`${STAMP}\n${given}`, STAMP, [given], { always: [], sameStampOnly: true }).text).toBeUndefined();
	});
});
