import { describe, expect, it } from "vitest";
import { berlinTag, berlinVersatzMinuten, berlinZeit, minusTage, pythonIsoformat, wochenSchluessel, zeitMs } from "../src/dashboard/zeit";
import { GOLDEN } from "./dashboard-golden";

// Zeitrechnung des Dashboards. Die Erwartungswerte in GOLDEN.zeit hat Python selbst berechnet
// (datetime mit ZoneInfo("Europe/Berlin"), isocalendar(), isoformat()) – siehe dashboard-golden.erzeugen.py.

const berlin = (iso: string) => zeitMs(iso);

describe("Wochenschlüssel (portiert aus tests/weekly_report/test_dashboard_export.py)", () => {
	it("ISO-Woche als Dokument-ID", () => {
		expect(wochenSchluessel(berlin("2026-09-28T00:00:00+02:00"))).toBe("2026-KW40");
		expect(wochenSchluessel(berlin("2026-09-27T23:59:00+02:00"))).toBe("2026-KW39");
		// Jahreswechsel: 1.1.2027 ist ein Freitag und gehört noch zu 2026-KW53.
		expect(wochenSchluessel(berlin("2027-01-01T00:00:00+01:00"))).toBe("2026-KW53");
	});

	it("Woche wird in Berliner Zeit bestimmt: Sonntag 22:30 UTC ist Montag 00:30 Berlin", () => {
		expect(wochenSchluessel(Date.UTC(2026, 8, 27, 22, 30))).toBe("2026-KW40");
		expect(wochenSchluessel(Date.UTC(2026, 8, 27, 21, 59, 59, 999))).toBe("2026-KW39");
	});

	it("stimmt für alle Grenzfälle mit Python überein (Jahreswechsel, Zeitumstellung, KW53)", () => {
		expect(GOLDEN.zeit.wochen.length).toBeGreaterThanOrEqual(20);
		for (const [text, erwartet] of GOLDEN.zeit.wochen) expect([text, wochenSchluessel(zeitMs(text))]).toEqual([text, erwartet]);
	});
});

describe("Berliner Zeit wie datetime mit ZoneInfo", () => {
	it("Versatz: Winter +60, Sommer +120 – auch direkt an den Umstellungen", () => {
		expect(berlinVersatzMinuten(Date.UTC(2026, 0, 15, 12))).toBe(60);
		expect(berlinVersatzMinuten(Date.UTC(2026, 6, 15, 12))).toBe(120);
		// Beginn der Sommerzeit 2026: 29.03. 01:00 UTC
		expect(berlinVersatzMinuten(Date.UTC(2026, 2, 29, 0, 59, 59, 999))).toBe(60);
		expect(berlinVersatzMinuten(Date.UTC(2026, 2, 29, 1, 0))).toBe(120);
		// Ende der Sommerzeit 2026: 25.10. 01:00 UTC
		expect(berlinVersatzMinuten(Date.UTC(2026, 9, 25, 0, 59, 59, 999))).toBe(120);
		expect(berlinVersatzMinuten(Date.UTC(2026, 9, 25, 1, 0))).toBe(60);
	});

	it("Fenster: „aktualisiert“, Fensterbeginn und die Tagesgrenzen für den Serverfilter wie im Python-Export", () => {
		expect(GOLDEN.zeit.fenster.length).toBeGreaterThanOrEqual(10);
		for (const fall of GOLDEN.zeit.fenster) {
			const until = berlinZeit(fall.until_ms);
			const since = minusTage(until, fall.tage);
			expect(
				{ created_at_from: berlinTag(since, -1), created_at_to: berlinTag(until, 1), since_iso: since.iso, since_ms: since.ms, until_iso: until.iso },
				`until ${fall.until_iso}, ${fall.tage} Tage`,
			).toEqual({ created_at_from: fall.created_at_from, created_at_to: fall.created_at_to, since_iso: fall.since_iso, since_ms: fall.since_ms, until_iso: fall.until_iso });
		}
	});

	it("Fensterbeginn in der Lücke am Beginn der Sommerzeit: Versatz von vorher (wie Python, fold=0)", () => {
		// 28.06.2026 02:30 minus 91 Tage = 29.03.2026 02:30 – diese Uhrzeit gibt es in Berlin nicht.
		const since = minusTage(berlinZeit(zeitMs("2026-06-28T02:30:00+02:00")), 91);
		expect(since.iso).toBe("2026-03-29T02:30:00+01:00");
		expect(since.ms).toBe(Date.UTC(2026, 2, 29, 1, 30));
	});

	it("Fensterbeginn in der doppelten Stunde am Ende der Sommerzeit: das erste Mal (Sommerzeit)", () => {
		const since = minusTage(berlinZeit(zeitMs("2027-01-24T02:30:00+01:00")), 91);
		expect(since.iso).toBe("2026-10-25T02:30:00+02:00");
		expect(since.ms).toBe(Date.UTC(2026, 9, 25, 0, 30));
	});

	it("über einen Umstellungstag hinweg sind 91 Tage nicht 91 × 24 Stunden", () => {
		const until = berlinZeit(zeitMs("2026-11-12T09:47:42.960+01:00"));
		const since = minusTage(until, 91);
		expect(since.iso).toBe("2026-08-13T09:47:42.960000+02:00");
		expect(until.ms - since.ms).toBe(91 * 86_400_000 + 3_600_000);
	});
});

describe("Schreibweise von datetime.isoformat()", () => {
	it("Propstack-Zeitstempel: drei Nachkommastellen werden sechs, Nullen fallen weg", () => {
		expect(pythonIsoformat("2025-03-19T09:52:39.301+01:00")).toBe("2025-03-19T09:52:39.301000+01:00");
		expect(pythonIsoformat("2026-08-19T11:29:56.000+02:00")).toBe("2026-08-19T11:29:56+02:00");
	});

	it("stimmt für alle Schreibweisen mit Python überein", () => {
		expect(GOLDEN.zeit.isoformat.length).toBeGreaterThanOrEqual(12);
		for (const [text, erwartet] of GOLDEN.zeit.isoformat) expect([text, pythonIsoformat(text)]).toEqual([text, erwartet]);
	});

	it("nicht lesbare Texte bleiben unverändert", () => {
		expect(pythonIsoformat("gestern")).toBe("gestern");
	});

	it("berlinZeit: Sekundenbruchteile nur, wenn sie nicht null sind", () => {
		expect(berlinZeit(zeitMs("2026-11-12T09:47:42.960+01:00")).iso).toBe("2026-11-12T09:47:42.960000+01:00");
		expect(berlinZeit(zeitMs("2026-11-12T08:47:42Z")).iso).toBe("2026-11-12T09:47:42+01:00");
		expect(berlinZeit(zeitMs("2026-07-01T00:00:00.007Z")).iso).toBe("2026-07-01T02:00:00.007000+02:00");
	});
});
