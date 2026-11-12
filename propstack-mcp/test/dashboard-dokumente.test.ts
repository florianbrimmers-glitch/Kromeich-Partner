import { describe, expect, it } from "vitest";
import {
	AUFGABEN_PRO_TEIL,
	type Aufgabe,
	aufgabenArt,
	baueDokumente,
	type Einheit,
	imFenster,
	kommazahl,
	MAX_DOKUMENT_BYTES,
	mitId,
	neuesteZuerst,
	ohneDoppelte,
	projektTitel,
	relevant,
	serialisiere,
	zuAufgabe,
	zuEinheit,
} from "../src/dashboard/dokumente";
import { toPage } from "../src/propstack-client";
import { berlinZeit, zeitMs } from "../src/dashboard/zeit";
import { GOLDEN } from "./dashboard-golden";

// Portierung der Python-Tests tests/weekly_report/test_dashboard_export.py und test_propstack_parsing.py –
// dieselben Fälle, dieselben Erwartungen. Das Dashboard-HTML bleibt unverändert, das Format muss exakt passen.

type Dok = Record<string, any>;

const SINCE = berlinZeit(zeitMs("2026-07-01T06:00:00+02:00"));
const UNTIL = berlinZeit(zeitMs("2026-10-01T06:00:00+02:00"));

const einheit = (felder: Partial<Einheit> & { id: number }): Einheit => ({
	address: null,
	city: null,
	created_at: null,
	marketing_type: null,
	name: null,
	project_id: null,
	property_space_value: null,
	title: null,
	...felder,
});

const aufgabe = (id: number, done: boolean | null, angelegt: string | null, geaendert: string | null, titel: string | null = "Pruefung Panattoni Welle 3: Park Rheine"): Aufgabe => ({
	done,
	id,
	original_created_at: angelegt,
	project_names: [],
	property_names: ["Unit 1.1"],
	title: titel,
	updated_at: geaendert,
});

function bauen(einheiten: Einheit[], titel: Record<number, string> = {}, beginn: Record<number, string | null> = {}, aufgaben: Aufgabe[] = []): Dok {
	return baueDokumente({
		aufgaben,
		brokerIds: [254958],
		einheiten,
		projektBeginn: new Map(Object.entries(beginn).map(([pid, wert]) => [Number(pid), wert])),
		projektTitel: new Map(Object.entries(titel).map(([pid, wert]) => [Number(pid), wert])),
		since: SINCE,
		tage: 92,
		until: UNTIL,
	}) as Dok;
}

describe("Dokumente bauen (wie baue_dokumente)", () => {
	it("Einheiten landen in ihrer Woche", () => {
		const docs = bauen([
			einheit({ created_at: "2026-09-28T10:00:00+02:00", id: 1, project_id: 7, title: "A" }),
			einheit({ created_at: "2026-09-21T10:00:00+02:00", id: 2, title: "B" }),
		]);
		expect(docs["wochen/2026-KW40"].einheiten.map((e: Dok) => e.id)).toEqual([1]);
		expect(docs["wochen/2026-KW39"].einheiten.map((e: Dok) => e.id)).toEqual([2]);
		expect(docs["meta/stand"].wochen).toEqual(["2026-KW39", "2026-KW40"]);
	});

	it("Prüfung: offener Bestand plus Fenster – offen zählt immer, erledigt nur, wenn im Fenster angelegt oder erledigt", () => {
		const docs = bauen([], {}, {}, [
			aufgabe(1, null, "2026-03-29T09:00:00+02:00", "2026-03-29T09:00:00+02:00"), // offen, alt
			aufgabe(2, true, "2026-07-30T08:00:00+02:00", "2026-09-23T09:00:00+02:00"), // erledigt im Fenster
			aufgabe(3, true, "2026-03-01T08:00:00+01:00", "2026-03-30T10:00:00+02:00"), // erledigt, alt
			aufgabe(4, null, "2026-09-28T08:00:00+02:00", "2026-09-28T08:00:00+02:00"), // neu, offen
		]);
		const aufgaben = docs["pruefung/teil-01"].aufgaben;
		expect(aufgaben.map((a: Dok) => a.id)).toEqual([1, 2, 4]);
		expect(aufgaben.map((a: Dok) => a.erledigt)).toEqual([false, true, false]);
		expect(aufgaben[1].geaendert).toBe("2026-09-23T09:00:00+02:00");
		expect(aufgaben[0].bezug).toBe("Unit 1.1");
		const stand = docs["meta/stand"];
		expect([stand.anzahl_offen, stand.anzahl_aufgaben]).toEqual([2, 3]);
		expect(stand.pruefung_teile).toEqual(["teil-01"]);
	});

	it("Wochen enthalten keine Aufgaben – Prüfaufgaben stehen nur in pruefung/", () => {
		const docs = bauen([einheit({ created_at: "2026-09-28T10:00:00+02:00", id: 1 })], {}, {}, [aufgabe(2, true, "2026-09-28T08:00:00+02:00", "2026-09-29T09:00:00+02:00")]);
		expect(Object.keys(docs["wochen/2026-KW40"]).sort()).toEqual(["einheiten", "woche"]);
	});

	it("Art der Aufgabe aus dem Titel", () => {
		expect(aufgabenArt("Pruefung Panattoni Welle 3: Park Rheine")).toBe("Prüfung Panattoni Welle 3");
		expect(aufgabenArt("Prüfung: Logistikfläche in (85) Kirchheim")).toBe("Prüfung");
		expect(aufgabenArt("Pruefung: Logistikhalle in (45) Waltrop")).toBe("Prüfung");
		expect(aufgabenArt("Newsletter-Vermietung prüfen: Bauer Property")).toBe("Newsletter-Vermietung prüfen");
		expect(aufgabenArt('Gesuch "FIRMA" "Kontakt" | "Größe"')).toBe("Sonstige");
		expect(aufgabenArt(null)).toBe("Sonstige");
	});

	it("Art der Aufgabe: Wortgrenzen wie in Python (Unterstrich, Umlaut, Mehrzahl) – Abgleich mit dem echten Export", () => {
		expect(GOLDEN.zeit.aufgaben_art.length).toBeGreaterThanOrEqual(16);
		for (const [titel, erwartet] of GOLDEN.zeit.aufgaben_art) {
			const roh = zuAufgabe({ id: 1, title: titel }).title;
			expect([titel, aufgabenArt(roh)]).toEqual([titel, erwartet]);
		}
	});

	it("Prüfung wird in Teile zu je 400 aufgeteilt", () => {
		const n = AUFGABEN_PRO_TEIL + 5;
		const docs = bauen([], {}, {}, Array.from({ length: n }, (_, i) => aufgabe(i, null, "2026-09-01T08:00:00+02:00", "2026-09-01T08:00:00+02:00")));
		expect(docs["pruefung/teil-01"].aufgaben).toHaveLength(AUFGABEN_PRO_TEIL);
		expect(docs["pruefung/teil-02"].aufgaben).toHaveLength(5);
		expect(docs["pruefung/teil-02"].teil).toBe(2);
		expect(docs["meta/stand"].pruefung_teile).toEqual(["teil-01", "teil-02"]);
		// gleicher Zeitstempel → nach ID sortiert
		expect(docs["pruefung/teil-01"].aufgaben.slice(0, 3).map((a: Dok) => a.id)).toEqual([0, 1, 2]);
	});

	it("ein volles Prüfungs-Teil bleibt unter der Dokumentgrenze", () => {
		const lang = "Pruefung GARBE Welle 4 Nord: Logistikhalle in (21) Hamburg-Billbrook – Bauteil C – Halle 12";
		const docs = bauen(
			[],
			{},
			{},
			Array.from({ length: AUFGABEN_PRO_TEIL }, (_, i) => ({
				...aufgabe(440_000_000 + i, null, "2026-09-01T08:00:00+02:00", "2026-09-01T08:00:00+02:00", lang),
				property_names: ["Logistikhalle Hamburg-Billbrook Halle 12"],
			})),
		);
		const groesse = new TextEncoder().encode(JSON.stringify(docs["pruefung/teil-01"])).length;
		expect(groesse).toBeLessThan(MAX_DOKUMENT_BYTES);
	});

	it("Projekte mit Beginn und gelöschtem Projekt", () => {
		const docs = bauen(
			[einheit({ created_at: "2026-09-28T10:00:00+02:00", id: 1, project_id: 7 }), einheit({ created_at: "2026-09-28T11:00:00+02:00", id: 2, project_id: 8 })],
			{ 7: "Logistikhalle in (40) Düsseldorf" },
			{ 7: "2026-09-28T10:00:00+02:00", 8: null },
		);
		const projekte = docs["meta/projekte"].projekte;
		expect(projekte["7"]).toEqual({ erste_einheit: "2026-09-28T10:00:00+02:00", titel: "Logistikhalle in (40) Düsseldorf", vorhanden: true });
		// 404-Projekt: Die Einheit zeigt noch darauf, es hat aber keinen Titel mehr.
		expect(projekte["8"]).toEqual({ erste_einheit: null, titel: null, vorhanden: false });
		expect(docs["meta/stand"].anzahl_projekte).toBe(2);
	});

	it("Anlagedatum eines Projekts in der Schreibweise des bisherigen Exports (sechs Nachkommastellen)", () => {
		const docs = bauen([einheit({ created_at: "2026-09-28T10:00:00+02:00", id: 1, project_id: 7 })], { 7: "X" }, { 7: "2025-03-19T09:52:39.301+01:00" });
		expect(docs["meta/projekte"].projekte["7"].erste_einheit).toBe("2025-03-19T09:52:39.301000+01:00");
	});

	it("leeres Fenster erzeugt nur meta", () => {
		const docs = bauen([]);
		expect(Object.keys(docs).sort()).toEqual(["meta/projekte", "meta/stand"]);
		expect(docs["meta/stand"].wochen).toEqual([]);
		expect(docs["meta/stand"].pruefung_teile).toEqual([]);
		expect(docs["meta/projekte"]).toEqual({ projekte: {} });
	});

	it("eine realistische Spitzenwoche bleibt unter der Dokumentgrenze (KW31/32 2026: je ~255 Einheiten)", () => {
		const einheiten = Array.from({ length: 600 }, (_, i) =>
			einheit({
				city: "Kornwestheim",
				created_at: "2026-08-04T10:00:00+02:00",
				id: 6_000_000 + i,
				marketing_type: "RENT",
				project_id: 590_000 + (i % 40),
				property_space_value: 12345.5,
				title: "Logistikhalle in (71) Kornwestheim – Bauteil C – Halle 12 Süd",
			}),
		);
		const groesse = new TextEncoder().encode(JSON.stringify(bauen(einheiten)["wochen/2026-KW32"])).length;
		expect(groesse).toBeLessThan(MAX_DOKUMENT_BYTES);
	});

	it("meta/stand: Feldnamen, Reihenfolge und Zeitstempel wie im bisherigen Export", () => {
		const stand = bauen([einheit({ created_at: "2026-09-28T10:00:00+02:00", id: 1, project_id: 7 })])["meta/stand"];
		expect(Object.keys(stand)).toEqual([
			"aktualisiert",
			"fenster_von",
			"fenster_bis",
			"tage",
			"pruefer_broker_ids",
			"anzahl_einheiten",
			"anzahl_projekte",
			"anzahl_offen",
			"anzahl_aufgaben",
			"wochen",
			"pruefung_teile",
		]);
		expect(stand).toMatchObject({ aktualisiert: "2026-10-01T06:00:00+02:00", fenster_bis: "2026-10-01T06:00:00+02:00", fenster_von: "2026-07-01T06:00:00+02:00", pruefer_broker_ids: [254958], tage: 92 });
	});

	it("Einheit und Aufgabe: Feldnamen und Reihenfolge wie im bisherigen Export; Titel fällt auf Name, Adresse, ID zurück", () => {
		const docs = bauen(
			[
				einheit({ city: "Kaarst", created_at: "2026-09-28T10:00:00+02:00", id: 1, marketing_type: "RENT", project_id: 7, property_space_value: 4200.5, title: "Halle" }),
				einheit({ created_at: "2026-09-28T09:00:00+02:00", id: 2, name: "Unit B", title: "" }),
				einheit({ address: "Musterweg 1", created_at: "2026-09-28T08:00:00+02:00", id: 3 }),
				einheit({ created_at: "2026-09-28T07:00:00+02:00", id: 4 }),
			],
			{},
			{},
			[{ ...aufgabe(9, false, "2026-09-01T08:00:00+02:00", null, "  "), project_names: ["Park Rheine"], property_names: [] }],
		);
		const einheiten = docs["wochen/2026-KW40"].einheiten;
		expect(Object.keys(einheiten[0])).toEqual(["id", "titel", "flaeche", "vermarktung", "stadt", "projekt_id", "angelegt"]);
		expect(einheiten[0]).toEqual({ angelegt: "2026-09-28T10:00:00+02:00", flaeche: 4200.5, id: 1, projekt_id: 7, stadt: "Kaarst", titel: "Halle", vermarktung: "RENT" });
		expect(einheiten.map((e: Dok) => e.titel)).toEqual(["Halle", "Unit B", "Musterweg 1", "Einheit 4"]);
		const [a] = docs["pruefung/teil-01"].aufgaben;
		expect(Object.keys(a)).toEqual(["id", "titel", "art", "erledigt", "angelegt", "geaendert", "bezug"]);
		expect(a).toEqual({ angelegt: "2026-09-01T08:00:00+02:00", art: "Sonstige", bezug: "Park Rheine", erledigt: false, geaendert: null, id: 9, titel: "Aufgabe 9" });
	});

	it("relevant: Grenze genau am Fensterbeginn zählt mit", () => {
		expect(relevant(aufgabe(1, true, "2026-01-01T00:00:00+01:00", "2026-07-01T06:00:00.000+02:00"), SINCE)).toBe(true);
		expect(relevant(aufgabe(1, true, "2026-01-01T00:00:00+01:00", "2026-07-01T05:59:59.999+02:00"), SINCE)).toBe(false);
		expect(relevant(aufgabe(1, true, "2026-07-01T04:00:00.000+00:00", null), SINCE)).toBe(true);
		expect(relevant(aufgabe(1, true, null, null), SINCE)).toBe(false);
		expect(relevant(aufgabe(1, false, null, null), SINCE)).toBe(true);
	});

	it("serialisiere: kompakt, mit Größe; ein Dokument über 256 KiB bricht ab wie der bisherige Export", () => {
		const [zeile] = serialisiere({ "meta/stand": { a: "ä", b: [1, 2] } });
		expect(zeile).toEqual({ bytes: 20, inhalt: '{"a":"ä","b":[1,2]}', name: "meta/stand" });
		expect(() => serialisiere({ "wochen/2026-KW01": { text: "x".repeat(MAX_DOKUMENT_BYTES) } })).toThrow(/wochen\/2026-KW01: \d+ Bytes, Grenze 262144/);
	});
});

describe("Propstack-Antworten lesen (portiert aus tests/weekly_report/test_propstack_parsing.py)", () => {
	// Gekürzte, aber echte Propstack-Antworten – abgerufen am 20.08.2026 (tests/weekly_report/fixtures.py)
	const UNITS = {
		data: [
			{
				address: "Frostelstraße , 89537 Giengen an der Brenz, Deutschland",
				city: { label: "Stadt", value: "Giengen an der Brenz" },
				created_at: "2026-08-14T09:12:00.000+02:00",
				id: 5802066,
				marketing_type: "BUY",
				project_id: null,
				property_space_value: 10197.0,
				title: { label: "Überschrift", value: "Lagerhalle in (89) Giengen an der Benz" },
			},
			{
				address: "An der Gümpgesbrücke 24, 41564 Kaarst, Deutschland",
				created_at: "2026-08-17T15:39:39.244+02:00",
				id: 5813977,
				marketing_type: "RENT",
				project_id: 570215,
				property_space_value: 4200.0,
				title: { label: "Überschrift", value: "Logistikflächen in (41) Kaarst" },
			},
			{ created_at: "2026-08-17T15:48:46.262+02:00", id: 5814044, project_id: 570215, property_space_value: 8200.5, title: "Logistikflächen in (41) Kaarst – Halle B" },
			// Außerhalb des Fensters – der Serverfilter ist nur tagesgenau, der exakte Schnitt muss hier fallen.
			{ created_at: "2026-08-12T23:59:00.000+02:00", id: 5700001, project_id: 554679, title: "Zu alt" },
		],
		meta: { total_count: 4 },
	};
	const PROJECTS = [
		{ address: "An der Gümpgesbrücke 24", id: 570215, title: "Logistikflächen in (41) Kaarst" },
		{ address: "Wittener Straße 1", id: 554679, title: "Halle in (44) Bochum" },
	];

	it("Custom-Field-Objekte werden auf den Wert reduziert", () => {
		const unit = zuEinheit(UNITS.data[0]);
		expect(unit.title).toBe("Lagerhalle in (89) Giengen an der Benz");
		expect(unit.city).toBe("Giengen an der Brenz");
		expect(unit.property_space_value).toBe(10197);
		expect(unit.project_id).toBeNull();
	});

	it("immer value, nie pretty_value – der bisherige Export schreibt „RENT“, nicht „Miete“", () => {
		expect(zuEinheit({ id: 1, marketing_type: { label: "Vermarktungsart", pretty_value: "Miete", value: "RENT" } }).marketing_type).toBe("RENT");
	});

	it("einfache Werte bleiben, wie sie sind; Projekt-ID auch als Ziffern-Text", () => {
		const unit = zuEinheit(UNITS.data[2]);
		expect(unit.title).toBe("Logistikflächen in (41) Kaarst – Halle B");
		expect(unit.project_id).toBe(570215);
		expect(zuEinheit({ id: 1, project_id: "570215" }).project_id).toBe(570215);
	});

	it("beide Antwortformen: {data: […]} und nackte Liste", () => {
		expect(mitId(toPage(UNITS).rows)).toHaveLength(4);
		expect(mitId(toPage(PROJECTS).rows)).toHaveLength(2);
	});

	it("Einträge ohne ID zählen nicht", () => {
		expect(mitId(toPage({ data: [{ title: "kaputt" }, "nicht mal ein Objekt", { id: 0 }, { id: null }] }).rows)).toEqual([]);
	});

	it("Fläche: Komma und leer führen nicht zum Absturz", () => {
		expect(kommazahl(null)).toBeNull();
		expect(kommazahl("")).toBeNull();
		expect(kommazahl({ label: "Fläche", value: "4200.5" })).toBe(4200.5);
		// Propstack schneidet Komma-Dezimalzahlen selbst ab; hier darf nichts abstürzen.
		expect(kommazahl("7,25")).toBeNull();
		expect(kommazahl(4200)).toBe(4200);
	});

	it("Fensterschnitt fällt hier: die Einheit vom 12.08. 23:59 fällt heraus, neueste zuerst", () => {
		const since = berlinZeit(zeitMs("2026-08-13T19:00:00+02:00"));
		const until = berlinZeit(zeitMs("2026-08-20T19:00:00+02:00"));
		const units = neuesteZuerst(UNITS.data.map(zuEinheit).filter((unit) => imFenster(unit, since, until)));
		expect(units.map((unit) => unit.id)).toEqual([5814044, 5813977, 5802066]);
	});

	it("Fensterschnitt auf die Millisekunde: since ≤ angelegt < until; ohne Anlagedatum nie", () => {
		const im = (created_at: string | null) => imFenster(einheit({ created_at, id: 1 }), SINCE, UNTIL);
		expect(im("2026-07-01T06:00:00.000+02:00")).toBe(true);
		expect(im("2026-07-01T05:59:59.999+02:00")).toBe(false);
		expect(im("2026-10-01T05:59:59.999+02:00")).toBe(true);
		expect(im("2026-10-01T06:00:00.000+02:00")).toBe(false);
		expect(im("2026-10-01T03:59:59.999+00:00")).toBe(true);
		expect(im(null)).toBe(false);
	});

	it("neueste zuerst: bei gleichem Zeitstempel bleibt die Reihenfolge des Servers", () => {
		const gleich = "2026-08-17T15:39:39.244+02:00";
		const sortiert = neuesteZuerst([einheit({ created_at: gleich, id: 3 }), einheit({ created_at: "2026-08-18T00:00:00.000+02:00", id: 9 }), einheit({ created_at: gleich, id: 1 }), einheit({ created_at: gleich, id: 2 })]);
		expect(sortiert.map((unit) => unit.id)).toEqual([9, 3, 1, 2]);
	});

	it("Aufgaben: Namenslisten ohne leere Einträge, kein Array → leer; erledigt wie in Python gelesen", () => {
		expect(zuAufgabe({ done: true, id: 447177220, project_names: [], property_names: ["Panattoni Park Friedewald"], title: "Flächenupdate abgleichen: Panattoni" })).toMatchObject({
			done: true,
			property_names: ["Panattoni Park Friedewald"],
		});
		expect(zuAufgabe({ id: 1, property_names: ["", null, "Echt"] }).property_names).toEqual(["Echt"]);
		expect(zuAufgabe({ id: 1, property_names: "kein Array" }).property_names).toEqual([]);
		expect(zuAufgabe({ id: 1 })).toEqual({ done: null, id: 1, original_created_at: null, project_names: [], property_names: [], title: null, updated_at: null });
		expect([1, 0, "true", null].map((done) => zuAufgabe({ done, id: 1 }).done)).toEqual([true, false, true, null]);
	});

	it("Projekttitel: Überschrift, sonst Name, sonst Adresse, sonst „Projekt <ID>“", () => {
		expect(projektTitel(PROJECTS[0])).toBe("Logistikflächen in (41) Kaarst");
		expect(projektTitel({ id: 5, name: "Park", title: null })).toBe("Park");
		expect(projektTitel({ address: "Weg 1", id: 5, name: "", title: "" })).toBe("Weg 1");
		expect(projektTitel({ id: 99 })).toBe("Projekt 99");
		expect(projektTitel({ id: 5, title: { label: "Überschrift", value: "Gewerbepark" } })).toBe("Gewerbepark");
	});

	it("ohne Doppelte: erstes Vorkommen je ID bleibt", () => {
		expect(ohneDoppelte([{ id: 1, n: "a" }, { id: 2, n: "b" }, { id: 1, n: "c" }])).toEqual([
			{ id: 1, n: "a" },
			{ id: 2, n: "b" },
		]);
	});
});
