import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { describe, expect, it } from "vitest";
import { dashboardDaten, type DashboardDeps, type Grenzen, STANDARD_GRENZEN } from "../src/dashboard/aufbau";
import { MAX_DOKUMENT_BYTES } from "../src/dashboard/dokumente";
import { MemoryDashboardStore } from "../src/dashboard/store";
import { PropstackError } from "../src/propstack-client";
import { registerReadTools } from "../src/tools/register";
import { grosseWelt, JETZT, neueWelt, propstackZeit, type Welt } from "./dashboard-welt";

// Ablauf von dashboard_daten: Aufbau in Etappen, Zwischenspeicher, Sperre, Fehler, Grenzen.
// Der Inhalt der Dokumente ist in dashboard-dokumente.test.ts und dashboard-golden.test.ts abgesichert.

type Dok = Record<string, any>;
const USER = { email: "routine@kromeichpartner.de" };
const MINUTE = 60_000;
const TAG = 86_400_000;

function aufbau(welt: Welt, grenzen: Partial<Grenzen> = {}) {
	const store = new MemoryDashboardStore();
	const uhr = { ms: JETZT };
	const anfragenJeAufruf: number[] = [];
	const aufruf = async (eingabe: { dokument: string; tage?: number; broker_ids?: number[]; stand?: string }, extra: Partial<DashboardDeps> = {}) => {
		const client = welt.client();
		try {
			return (await dashboardDaten({ client, grenzen, now: () => uhr.ms, sleep: async () => {}, store, user: USER, ...extra }, eingabe)).result as Dok;
		} finally {
			anfragenJeAufruf.push(client.requestsUsed);
		}
	};
	/** Wiederholt den Aufruf, bis das Dokument kommt – wie die Routine. */
	const bisFertig = async (eingabe: { dokument: string; tage?: number; broker_ids?: number[] }) => {
		for (let i = 0; i < 100; i++) {
			const ergebnis = await aufruf(eingabe);
			if (ergebnis.fortsetzen !== true) return ergebnis;
		}
		throw new Error("Aufbau endet nicht");
	};
	return { anfragenJeAufruf, aufruf, bisFertig, store, uhr };
}

/** Kleine Welt: 3 Einheiten in 2 Projekten, 2 Aufgaben. */
function kleineWelt(): Welt {
	return neueWelt({
		aufgaben: {
			254958: [
				{ done: null, id: 11, original_created_at: propstackZeit(JETZT - 300 * TAG), property_names: ["Unit 1"], title: "Pruefung: Halle A", updated_at: propstackZeit(JETZT - 300 * TAG) },
				{ done: true, id: 12, original_created_at: propstackZeit(JETZT - 10 * TAG), project_names: ["Park B"], title: "Newsletter-Vermietung prüfen: B", updated_at: propstackZeit(JETZT - 2 * TAG) },
			],
		},
		einheiten: [
			{ created_at: propstackZeit(JETZT - 2 * TAG), id: 101, project_id: 7, title: "Halle A" },
			{ created_at: propstackZeit(JETZT - 9 * TAG), id: 102, project_id: 8, title: "Halle B" },
			{ created_at: propstackZeit(JETZT - 16 * TAG), id: 103, project_id: null, title: "Halle C" },
			{ created_at: propstackZeit(JETZT - 400 * TAG), id: 90, project_id: 7, title: "Halle A alt" },
		],
		projekte: [
			{ id: 7, title: "Park A" },
			{ id: 8, title: "Park B" },
			{ id: 9, title: "Unbeteiligt" },
		],
	});
}

describe("dashboard_daten: Aufbau in Etappen", () => {
	it("Bestand in echter Größe: 119 Anfragen verteilen sich auf drei Aufrufe mit je höchstens 40 – danach stimmen alle Zahlen", async () => {
		const welt = grosseWelt();
		const lauf = aufbau(welt);

		const erste = await lauf.aufruf({ dokument: "meta/stand" });
		expect(erste).toEqual({
			anfragen_bisher: 40,
			fortschritt: "Anlagedatum: 34 von 110 Projekten",
			fortsetzen: true,
			hinweis: "Der Stand wird aufgebaut. Denselben Aufruf wiederholen, bis das Dokument kommt – nacheinander, nicht parallel.",
			phase: "Anlagedatum je Projekt",
			stand_von: "2026-11-12T09:47:42.960000+01:00",
		});
		const stand = await lauf.bisFertig({ dokument: "meta/stand" });

		// 3 Seiten Einheiten + 3 Seiten Projekte + 110 Anlagedaten + 3 Seiten Aufgaben
		expect(lauf.anfragenJeAufruf).toEqual([40, 40, 39]);
		expect(welt.log).toHaveLength(119);
		expect(new Set(welt.log).size).toBe(119); // keine Anfrage doppelt
		expect(Math.max(...lauf.anfragenJeAufruf)).toBeLessThanOrEqual(45);

		expect(stand).toEqual({
			aktualisiert: "2026-11-12T09:47:42.960000+01:00",
			anzahl_aufgaben: 520,
			anzahl_einheiten: 250,
			anzahl_offen: 493,
			anzahl_projekte: 110,
			fenster_bis: "2026-11-12T09:47:42.960000+01:00",
			fenster_von: "2026-08-13T09:47:42.960000+02:00",
			pruefer_broker_ids: [254958],
			pruefung_teile: ["teil-01", "teil-02"],
			tage: 91,
			wochen: ["2026-KW33", "2026-KW34", "2026-KW35", "2026-KW36", "2026-KW37", "2026-KW38", "2026-KW39", "2026-KW40", "2026-KW41", "2026-KW42", "2026-KW43", "2026-KW44", "2026-KW45", "2026-KW46"],
		});

		// Die Einzeldokumente kommen aus dem Zwischenspeicher – ohne eine einzige weitere Propstack-Anfrage
		const vorher = welt.log.length;
		const teil1 = await lauf.aufruf({ dokument: "pruefung/teil-01", stand: stand.aktualisiert });
		const teil2 = await lauf.aufruf({ dokument: "pruefung/teil-02", stand: stand.aktualisiert });
		expect([teil1.teil, teil1.aufgaben.length, teil2.teil, teil2.aufgaben.length]).toEqual([1, 400, 2, 120]);
		let einheiten = 0;
		for (const woche of stand.wochen) {
			const dokument = await lauf.aufruf({ dokument: `wochen/${woche}`, stand: stand.aktualisiert });
			expect(dokument.woche).toBe(woche);
			einheiten += dokument.einheiten.length;
		}
		expect(einheiten).toBe(250);
		const { projekte } = await lauf.aufruf({ dokument: "meta/projekte", stand: stand.aktualisiert });
		expect(Object.keys(projekte)).toHaveLength(110);
		expect(projekte["590007"]).toMatchObject({ titel: null, vorhanden: false });
		expect(projekte["590008"]).toMatchObject({ titel: "Logistikpark 590008", vorhanden: true });
		// gerades Projekt: eine ältere Einheit datiert es vor das Fenster; ungerades: seine erste Einheit liegt im Fenster
		expect(projekte["590008"].erste_einheit < stand.fenster_von).toBe(true);
		expect(projekte["590009"].erste_einheit > stand.fenster_von).toBe(true);
		expect(welt.log.length).toBe(vorher);

		// jedes Dokument bleibt unter der Grenze der Dashboard-Datenbank
		const dokumente = await lauf.store.dokumente(lauf.store.staende[0].id);
		expect(dokumente).toHaveLength(2 + 14 + 2);
		expect(Math.max(...dokumente.map((d) => d.bytes))).toBeLessThan(MAX_DOKUMENT_BYTES);
		for (const d of dokumente) expect(d.inhalt).not.toMatch(/\n| {2}/); // kompakt, kein Pretty-Print
	});

	it("die Abfragen selbst: Serverfenster um je einen Tag geweitet, expand=1, Aufgaben nach updated_at absteigend", async () => {
		const welt = kleineWelt();
		await aufbau(welt).bisFertig({ dokument: "meta/stand" });
		expect(welt.log).toEqual([
			"/units?created_at_from=2026-08-12&created_at_to=2026-11-13&expand=1&page=1&per=100",
			"/projects?page=1&per=200",
			"/units?expand=1&order=asc&per=1&project_id=7&sort_by=created_at",
			"/units?expand=1&order=asc&per=1&project_id=8&sort_by=created_at",
			"/activities?broker_id=254958&item_type=reminder&order=desc&page=1&per=200&sort_by=updated_at",
		]);
	});

	it("Standardwerte: 91 Tage, Prüfer 254958; andere Parameter bauen einen eigenen Stand", async () => {
		const welt = kleineWelt();
		const lauf = aufbau(welt);
		const standard = await lauf.bisFertig({ dokument: "meta/stand" });
		expect([standard.tage, standard.pruefer_broker_ids, standard.anzahl_einheiten]).toEqual([91, [254958], 3]);

		const kurz = await lauf.bisFertig({ broker_ids: [387451, 254958, 387451], dokument: "meta/stand", tage: 7 });
		expect([kurz.tage, kurz.pruefer_broker_ids, kurz.anzahl_einheiten, kurz.fenster_von]).toEqual([7, [387451, 254958], 1, "2026-11-05T09:47:42.960000+01:00"]);
		expect(lauf.store.staende.map((s) => s.params)).toEqual(["91|254958", "7|387451,254958"]);
		// der Standard-Stand ist davon unberührt
		expect(await lauf.aufruf({ dokument: "meta/stand" })).toEqual(standard);
	});

	it("ohne Projekte im Fenster: weder Projektliste noch Anlagedaten werden abgefragt", async () => {
		const welt = neueWelt({ einheiten: [{ created_at: propstackZeit(JETZT - TAG), id: 1, title: "Einzelobjekt" }], projekte: [{ id: 7, title: "Unbeteiligt" }] });
		const lauf = aufbau(welt);
		const stand = await lauf.bisFertig({ dokument: "meta/stand" });
		expect([stand.anzahl_einheiten, stand.anzahl_projekte]).toEqual([1, 0]);
		expect(welt.log.map((eintrag) => eintrag.split("?")[0])).toEqual(["/units", "/activities"]);
		expect(await lauf.aufruf({ dokument: "meta/projekte" })).toEqual({ projekte: {} });
	});

	it("leeres Fenster: nur meta/stand und meta/projekte", async () => {
		const lauf = aufbau(neueWelt());
		const stand = await lauf.bisFertig({ dokument: "meta/stand" });
		expect(stand).toMatchObject({ anzahl_aufgaben: 0, anzahl_einheiten: 0, anzahl_offen: 0, anzahl_projekte: 0, pruefung_teile: [], wochen: [] });
		expect((await lauf.store.dokumente(lauf.store.staende[0].id)).map((d) => d.name)).toEqual(["meta/projekte", "meta/stand"]);
	});

	it("Zeitbudget: Nach 20 Sekunden beginnt ein Aufruf keine neue Anfrage mehr", async () => {
		const welt = grosseWelt();
		const lauf = aufbau(welt);
		welt.vorAntwort = () => {
			lauf.uhr.ms += 6_000; // jede Anfrage dauert 6 Sekunden
		};
		const ergebnis = await lauf.aufruf({ dokument: "meta/stand" });
		expect(ergebnis.fortsetzen).toBe(true);
		expect(lauf.anfragenJeAufruf).toEqual([4]); // 0 s, 6 s, 12 s, 18 s – bei 24 s ist Schluss
	});

	it("Doppler beim Blättern: verschiebt sich die Liste zwischen zwei Seiten, zählt jede Einheit und jede Aufgabe nur einmal", async () => {
		const welt = kleineWelt();
		for (let i = 0; i < 5; i++) welt.einheiten.push({ created_at: propstackZeit(JETZT - 3 * TAG - i * 1000), id: 200 + i, title: `Zusatz ${i}` });
		for (let i = 0; i < 4; i++) welt.aufgaben.get(254958)!.push({ done: null, id: 20 + i, original_created_at: propstackZeit(JETZT - 5 * TAG), title: `Pruefung: Zusatz ${i}`, updated_at: propstackZeit(JETZT - 5 * TAG - i * 1000) });
		welt.vorAntwort = (schluessel) => {
			// Nach Seite 1 kommt vorn ein neuer Datensatz dazu – der letzte der Seite 1 rutscht auf Seite 2 und käme doppelt.
			if (schluessel.startsWith("/units?created_at_from") && schluessel.includes("page=2")) welt.einheiten.push({ created_at: propstackZeit(JETZT - 1000), id: 999, title: "Gerade angelegt" });
			if (schluessel.startsWith("/activities") && schluessel.includes("page=2")) {
				welt.aufgaben.get(254958)!.push({ done: null, id: 99, original_created_at: propstackZeit(JETZT - 1000), title: "Pruefung: gerade angelegt", updated_at: propstackZeit(JETZT - 500) });
			}
		};
		const lauf = aufbau(welt, { seiteAufgaben: 3, seiteEinheiten: 4 });
		const stand = await lauf.bisFertig({ dokument: "meta/stand" });
		// 8 Einheiten im Fenster beim Start; die neue (999) wurde nach „aktualisiert“ angelegt und zählt nicht
		expect(stand.anzahl_einheiten).toBe(8);
		// 6 Aufgaben beim Start. Die neue steht ganz vorn auf Seite 1, die schon gelesen ist – sie fehlt in diesem Stand
		// (wie im bisherigen Export). Wichtig ist: Die Aufgabe, die dadurch von Seite 1 auf Seite 2 gerutscht ist, zählt nicht doppelt.
		expect(stand.anzahl_aufgaben).toBe(6);
		expect(welt.log.filter((eintrag) => eintrag.startsWith("/activities"))).toHaveLength(3);
		const ids: number[] = [];
		for (const woche of stand.wochen) ids.push(...(await lauf.aufruf({ dokument: `wochen/${woche}` })).einheiten.map((e: Dok) => e.id));
		expect(ids.sort((a, b) => a - b)).toEqual([101, 102, 103, 200, 201, 202, 203, 204]);
		const aufgaben = (await lauf.aufruf({ dokument: "pruefung/teil-01" })).aufgaben.map((a: Dok) => a.id);
		expect([...aufgaben].sort((a, b) => a - b)).toEqual([11, 12, 20, 21, 22, 23]);
	});
});

describe("dashboard_daten: Zwischenspeicher", () => {
	it("fertiger Stand gilt 30 Minuten: in dieser Zeit keine Propstack-Anfrage; danach wird neu aufgebaut", async () => {
		const welt = kleineWelt();
		const lauf = aufbau(welt);
		const stand = await lauf.bisFertig({ dokument: "meta/stand" });
		const anfragen = welt.log.length;

		lauf.uhr.ms = JETZT + 30 * MINUTE;
		expect(await lauf.aufruf({ dokument: "meta/stand" })).toEqual(stand);
		expect((await lauf.aufruf({ dokument: "pruefung/teil-01" })).aufgaben).toHaveLength(2);
		expect(welt.log.length).toBe(anfragen);

		lauf.uhr.ms = JETZT + 30 * MINUTE + 1;
		const neu = await lauf.bisFertig({ dokument: "meta/stand" });
		expect(neu.aktualisiert).toBe("2026-11-12T10:17:42.961000+01:00");
		expect(welt.log.length).toBe(2 * anfragen);
		expect(lauf.store.staende.map((s) => s.status)).toEqual(["fertig", "fertig"]);
	});

	it("stand = „aktualisiert“ aus meta/stand: Dokumente kommen genau aus diesem Stand – auch wenn inzwischen ein neuerer gebaut wurde", async () => {
		const welt = kleineWelt();
		const lauf = aufbau(welt);
		const alt = await lauf.bisFertig({ dokument: "meta/stand" });

		// 40 Minuten später: eine neue Einheit, ein anderer Aufrufer baut einen neuen Stand
		lauf.uhr.ms = JETZT + 40 * MINUTE;
		welt.einheiten.push({ created_at: propstackZeit(JETZT + 10 * MINUTE), id: 104, project_id: 8, title: "Halle D" });
		const neu = await lauf.bisFertig({ dokument: "meta/stand" });
		expect([alt.anzahl_einheiten, neu.anzahl_einheiten]).toEqual([3, 4]);

		const woche = "wochen/2026-KW46";
		const anfragen = welt.log.length;
		expect((await lauf.aufruf({ dokument: woche, stand: alt.aktualisiert })).einheiten.map((e: Dok) => e.id)).toEqual([101]);
		expect((await lauf.aufruf({ dokument: woche, stand: neu.aktualisiert })).einheiten.map((e: Dok) => e.id)).toEqual([104, 101]);
		expect((await lauf.aufruf({ dokument: woche })).einheiten.map((e: Dok) => e.id)).toEqual([104, 101]); // ohne stand: der jüngste
		expect(await lauf.aufruf({ dokument: "meta/stand", stand: alt.aktualisiert })).toEqual(alt);
		expect(await lauf.aufruf({ dokument: "meta/stand", stand: ` ${alt.aktualisiert} ` })).toEqual(alt); // Leerzeichen am Rand stören nicht
		expect(await lauf.aufruf({ dokument: "meta/stand", stand: "" })).toEqual(neu); // leer zählt wie nicht angegeben
		expect(welt.log.length).toBe(anfragen); // festes Lesen baut nie neu auf
	});

	it("stand unbekannt oder gelöscht: klarer Fehler statt eines falschen Dokuments, und kein neuer Aufbau", async () => {
		const welt = kleineWelt();
		const lauf = aufbau(welt);
		await expect(lauf.aufruf({ dokument: "meta/stand", stand: "2026-11-12T09:00:00+01:00" })).rejects.toThrow(
			"Den Stand 2026-11-12T09:00:00+01:00 gibt es für diese Parameter nicht (mehr). Neu beginnen: ohne den Parameter stand abrufen (meta/stand bzw. alles) und danach alle Dokumente neu holen.",
		);
		expect(welt.log).toEqual([]);
		expect(lauf.store.staende).toEqual([]);

		const stand = await lauf.bisFertig({ dokument: "meta/stand" });
		// andere Parameter → anderer Stand
		await expect(lauf.aufruf({ dokument: "meta/stand", stand: stand.aktualisiert, tage: 30 })).rejects.toThrow(/gibt es für diese Parameter nicht/);

		// nach 24 Stunden räumt der nächste Aufbau den alten Stand weg
		lauf.uhr.ms = JETZT + 24 * 3_600_000 + MINUTE;
		await lauf.bisFertig({ dokument: "meta/stand" });
		expect(lauf.store.staende).toHaveLength(1);
		await expect(lauf.aufruf({ dokument: "meta/stand", stand: stand.aktualisiert })).rejects.toBeInstanceOf(PropstackError);
		expect(lauf.store.dokumentZeilen.every((d) => d.standId === lauf.store.staende[0].id)).toBe(true);
	});

	it("Dokument, das es im Stand nicht gibt (Woche ohne Einheiten, Teil 3): Fehler nennt die vorhandenen", async () => {
		const lauf = aufbau(kleineWelt());
		await lauf.bisFertig({ dokument: "meta/stand" });
		await expect(lauf.aufruf({ dokument: "wochen/2026-KW30" })).rejects.toThrow(
			"Das Dokument wochen/2026-KW30 gibt es im Stand 2026-11-12T09:47:42.960000+01:00 nicht. Vorhanden: meta/stand, meta/projekte, wochen/2026-KW44, wochen/2026-KW45, wochen/2026-KW46, pruefung/teil-01.",
		);
		await expect(lauf.aufruf({ dokument: "pruefung/teil-03" })).rejects.toMatchObject({ status: 404 });
	});

	it("jedes Dokument darf den Aufbau anstoßen und fortsetzen – nicht nur meta/stand", async () => {
		const lauf = aufbau(grosseWelt());
		expect((await lauf.aufruf({ dokument: "pruefung/teil-02" })).fortsetzen).toBe(true);
		const teil = await lauf.bisFertig({ dokument: "pruefung/teil-02" });
		expect(teil.aufgaben).toHaveLength(120);
		expect(lauf.anfragenJeAufruf).toEqual([40, 40, 39]);
	});

	it("ohne Zwischenspeicher (D1 fehlt): verständlicher Fehler, keine Propstack-Anfrage", async () => {
		const welt = kleineWelt();
		await expect(dashboardDaten({ client: welt.client(), store: undefined, user: USER }, { dokument: "meta/stand" })).rejects.toThrow("Der Zwischenspeicher für das Dashboard ist nicht verfügbar.");
		expect(welt.log).toEqual([]);
	});
});

describe('dashboard_daten: dokument = "alles" – alle Dokumente eines Stands in einer Antwort', () => {
	it("dieselben Dokumente wie die Einzelabrufe desselben Stands; die Schlüssel sind genau die, die meta/stand nennt", async () => {
		const welt = grosseWelt();
		const lauf = aufbau(welt);
		const stand = await lauf.bisFertig({ dokument: "meta/stand" });
		const anfragen = welt.log.length;

		const alles = await lauf.aufruf({ dokument: "alles" });
		expect(Object.keys(alles)).toEqual(["stand", "dokumente"]);
		expect(alles.stand).toBe(stand.aktualisiert);
		// Schlüssel: meta/stand, meta/projekte, dann genau die Wochen und Teile aus meta/stand – in dieser Reihenfolge
		expect(Object.keys(alles.dokumente)).toEqual([
			"meta/stand",
			"meta/projekte",
			...stand.wochen.map((woche: string) => `wochen/${woche}`),
			...stand.pruefung_teile.map((teil: string) => `pruefung/${teil}`),
		]);
		expect(Object.keys(alles.dokumente)).toHaveLength(2 + 14 + 2);
		// Werte: Zeichen für Zeichen die Einzelabrufe desselben Stands (also auch dieselbe Reihenfolge der Felder)
		for (const [name, dokument] of Object.entries(alles.dokumente)) {
			const einzeln = await lauf.aufruf({ dokument: name, stand: stand.aktualisiert });
			expect(JSON.stringify(dokument), name).toBe(JSON.stringify(einzeln));
		}
		expect(alles.dokumente["meta/stand"]).toEqual(stand);
		// alles aus dem Zwischenspeicher: keine weitere Propstack-Abfrage
		expect(welt.log.length).toBe(anfragen);
	});

	it("baut den Stand wie meta/stand in Etappen auf: erst die kleine Antwort mit fortsetzen: true, dann die eine große", async () => {
		const welt = grosseWelt();
		const lauf = aufbau(welt);
		const erste = await lauf.aufruf({ dokument: "alles" });
		expect(erste).toMatchObject({ fortschritt: "Anlagedatum: 34 von 110 Projekten", fortsetzen: true, stand_von: "2026-11-12T09:47:42.960000+01:00" });
		expect(erste.dokumente).toBeUndefined();
		const alles = await lauf.bisFertig({ dokument: "alles" });
		expect(lauf.anfragenJeAufruf).toEqual([40, 40, 39]);
		expect(alles.stand).toBe("2026-11-12T09:47:42.960000+01:00");
		expect(alles.dokumente["meta/stand"]).toMatchObject({ anzahl_aufgaben: 520, anzahl_einheiten: 250, anzahl_offen: 493, anzahl_projekte: 110 });
		expect(alles.dokumente["pruefung/teil-01"].aufgaben).toHaveLength(400);
		expect(alles.dokumente["pruefung/teil-02"].aufgaben).toHaveLength(120);
		// eine Zeile, kompakt – in dieser Größe legt eine Claude-Sitzung die Antwort als Datei ab
		const text = JSON.stringify(alles);
		expect(text.length).toBeGreaterThan(150_000);
		expect(text).not.toMatch(/\n/);
	});

	it("mit stand: genau dieser Stand, auch wenn inzwischen ein neuerer gebaut wurde; unbekannter Stand ist ein Fehler", async () => {
		const welt = kleineWelt();
		const lauf = aufbau(welt);
		const alt = await lauf.bisFertig({ dokument: "alles" });
		lauf.uhr.ms = JETZT + 40 * MINUTE;
		welt.einheiten.push({ created_at: propstackZeit(JETZT + 10 * MINUTE), id: 104, project_id: 8, title: "Halle D" });
		const neu = await lauf.bisFertig({ dokument: "alles" });
		expect([alt.dokumente["meta/stand"].anzahl_einheiten, neu.dokumente["meta/stand"].anzahl_einheiten]).toEqual([3, 4]);
		expect([alt.stand, neu.stand]).toEqual(["2026-11-12T09:47:42.960000+01:00", "2026-11-12T10:27:42.960000+01:00"]);

		const anfragen = welt.log.length;
		expect(await lauf.aufruf({ dokument: "alles", stand: alt.stand })).toEqual(alt);
		expect(await lauf.aufruf({ dokument: "alles", stand: neu.stand })).toEqual(neu);
		expect(await lauf.aufruf({ dokument: "alles" })).toEqual(neu); // ohne stand: der jüngste
		// der Wert "stand" aus der Antwort gilt auch für Einzelabrufe
		expect(await lauf.aufruf({ dokument: "meta/stand", stand: alt.stand })).toEqual(alt.dokumente["meta/stand"]);
		await expect(lauf.aufruf({ dokument: "alles", stand: "2026-11-12T09:00:00+01:00" })).rejects.toThrow(/Den Stand 2026-11-12T09:00:00\+01:00 gibt es für diese Parameter nicht \(mehr\)/);
		expect(welt.log.length).toBe(anfragen); // festes Lesen baut nie neu auf
	});

	it("tage und broker_ids wie bei den Einzelabrufen", async () => {
		const lauf = aufbau(kleineWelt());
		const alles = await lauf.bisFertig({ broker_ids: [387451], dokument: "alles", tage: 7 });
		expect(alles.dokumente["meta/stand"]).toMatchObject({ anzahl_aufgaben: 0, anzahl_einheiten: 1, pruefer_broker_ids: [387451], tage: 7 });
		expect(Object.keys(alles.dokumente)).toEqual(["meta/stand", "meta/projekte", "wochen/2026-KW46"]);
	});

	it("leeres Fenster: nur meta/stand und meta/projekte", async () => {
		const alles = await aufbau(neueWelt()).bisFertig({ dokument: "alles" });
		expect(Object.keys(alles.dokumente)).toEqual(["meta/stand", "meta/projekte"]);
		expect(alles.dokumente["meta/projekte"]).toEqual({ projekte: {} });
	});

	it("passt der Speicher nicht zu meta/stand, kommt ein Fehler statt eines unbemerkt unvollständigen Stands", async () => {
		const lauf = aufbau(kleineWelt());
		await lauf.bisFertig({ dokument: "alles" });
		const standId = lauf.store.staende[0].id;
		lauf.store.dokumentZeilen = lauf.store.dokumentZeilen.filter((d) => d.name !== "wochen/2026-KW45");
		await expect(lauf.aufruf({ dokument: "alles" })).rejects.toThrow(/ist nicht vollständig gespeichert \(es fehlt: wochen\/2026-KW45; nicht in meta\/stand genannt: nichts\)/);
		lauf.store.dokumentZeilen.push({ bytes: 2, inhalt: "{}", name: "wochen/2026-KW45", standId }, { bytes: 2, inhalt: "{}", name: "wochen/2020-KW01", standId });
		await expect(lauf.aufruf({ dokument: "alles" })).rejects.toThrow(/es fehlt: nichts; nicht in meta\/stand genannt: wochen\/2020-KW01/);
	});
});

describe("dashboard_daten: gleichzeitige Aufrufe", () => {
	it("zwei Aufrufe gleichzeitig: nur einer baut, der andere bekommt „erneut aufrufen“ und stellt keine Anfrage", async () => {
		const welt = grosseWelt();
		const lauf = aufbau(welt);
		const [a, b] = await Promise.all([lauf.aufruf({ dokument: "meta/stand" }), lauf.aufruf({ dokument: "meta/projekte" })]);
		const wartend = [a, b].filter((ergebnis) => /Ein anderer Aufruf baut diesen Stand gerade auf/.test(ergebnis.hinweis));
		expect(wartend).toHaveLength(1);
		expect(wartend[0].fortsetzen).toBe(true);
		expect([...lauf.anfragenJeAufruf].sort((x, y) => x - y)).toEqual([0, 40]);
		expect(new Set(welt.log).size).toBe(40);
		// beide haben denselben Stand gewählt; ein zweiter, verwaister Stand hat nie eine Anfrage gestellt
		expect(lauf.store.staende.filter((s) => s.anfragen > 0)).toHaveLength(1);

		// danach geht es normal weiter – die Sperre ist gelöst
		const stand = await lauf.bisFertig({ dokument: "meta/stand" });
		expect(stand.anzahl_projekte).toBe(110);
		expect(new Set(welt.log).size).toBe(119);
		expect(welt.log).toHaveLength(119);
	});

	it("bekommt ein Aufruf die Sperre erst, nachdem ein anderer weitergebaut hat, macht er an dessen Stelle weiter – nicht an seiner veralteten", async () => {
		const welt = grosseWelt();
		const lauf = aufbau(welt);
		// Aufruf B liest den Stand (noch ganz am Anfang) und wird dann aufgehalten, bis Aufruf A seine Etappe beendet hat.
		let aErledigt!: () => void;
		const aFertig = new Promise<void>((resolve) => {
			aErledigt = resolve;
		});
		const sperren = lauf.store.sperren.bind(lauf.store);
		let aufhalten = true;
		lauf.store.sperren = async (...args) => {
			if (aufhalten) {
				aufhalten = false;
				await aFertig;
			}
			return sperren(...args);
		};
		const b = lauf.aufruf({ dokument: "meta/stand" });
		while (!lauf.store.staende.length) await new Promise((resolve) => setTimeout(resolve, 1));
		const a = await lauf.aufruf({ dokument: "meta/stand" });
		expect(a.fortschritt).toBe("Anlagedatum: 34 von 110 Projekten");
		aErledigt();
		expect((await b).fortschritt).toBe("Anlagedatum: 74 von 110 Projekten");
		expect(welt.log).toHaveLength(80);
		expect(new Set(welt.log).size).toBe(80); // nichts doppelt gelesen
	});

	it("bricht ein Aufruf ab, ohne die Sperre zu lösen, übernimmt der nächste nach zwei Minuten", async () => {
		const welt = grosseWelt();
		const lauf = aufbau(welt);
		await lauf.aufruf({ dokument: "meta/stand" });
		const stand = lauf.store.staende[0];
		stand.sperre_bis = new Date(JETZT + STANDARD_GRENZEN.sperreMs).toISOString(); // als wäre der Aufruf mittendrin gestorben

		lauf.uhr.ms = JETZT + STANDARD_GRENZEN.sperreMs - 1;
		expect((await lauf.aufruf({ dokument: "meta/stand" })).hinweis).toMatch(/Ein anderer Aufruf/);
		expect(lauf.anfragenJeAufruf).toEqual([40, 0]);

		lauf.uhr.ms = JETZT + STANDARD_GRENZEN.sperreMs + 1;
		expect((await lauf.aufruf({ dokument: "meta/stand" })).fortschritt).toBe("Anlagedatum: 74 von 110 Projekten");
		expect(lauf.anfragenJeAufruf).toEqual([40, 0, 40]);
	});

	it("hängt ein Aufruf länger als die Sperre und ein zweiter übernimmt: beide liefern das richtige Dokument, der Nachzügler überschreibt nichts", async () => {
		const erwartet = await aufbau(kleineWelt()).bisFertig({ dokument: "meta/projekte" });
		const erwarteterStand = await aufbau(kleineWelt()).bisFertig({ dokument: "meta/stand" });
		const welt = kleineWelt();
		const lauf = aufbau(welt);
		let freigeben!: () => void;
		const haengt = new Promise<void>((resolve) => {
			freigeben = resolve;
		});
		let einmal = true;
		welt.vorAntwort = async (schluessel) => {
			if (einmal && schluessel.startsWith("/activities")) {
				einmal = false;
				await haengt; // die letzte Anfrage des ersten Aufrufs bleibt hängen
			}
		};
		const erster = lauf.aufruf({ dokument: "meta/projekte" });
		while (!welt.log.some((eintrag) => eintrag.startsWith("/activities"))) await new Promise((resolve) => setTimeout(resolve, 1));

		// Die Sperre läuft ab, ein zweiter Aufruf übernimmt und stellt den Stand fertig
		lauf.uhr.ms = JETZT + STANDARD_GRENZEN.sperreMs + 1;
		expect(await lauf.aufruf({ dokument: "meta/projekte" })).toEqual(erwartet);
		const dokumenteVorher = structuredClone(lauf.store.dokumentZeilen);
		expect(lauf.store.staende.map((s) => s.status)).toEqual(["fertig"]);

		// Jetzt kommt der erste zurück: Seine Rohdaten sind inzwischen gelöscht – er darf mit dem Rest nichts überschreiben
		freigeben();
		expect(await erster).toEqual(erwartet);
		expect(lauf.store.dokumentZeilen).toEqual(dokumenteVorher);
		expect(lauf.store.teilZeilen).toEqual([]);
		expect(await lauf.aufruf({ dokument: "meta/stand" })).toEqual(erwarteterStand);
		expect(erwarteterStand.anzahl_einheiten).toBe(3);
	});

	it("unfertiger Stand, älter als 30 Minuten: wird verworfen, der Aufbau beginnt neu mit neuem Zeitpunkt", async () => {
		const welt = grosseWelt();
		const lauf = aufbau(welt);
		await lauf.aufruf({ dokument: "meta/stand" });
		lauf.uhr.ms = JETZT + 30 * MINUTE + 1;
		const ergebnis = await lauf.aufruf({ dokument: "meta/stand" });
		expect(ergebnis).toMatchObject({ anfragen_bisher: 40, fortsetzen: true, stand_von: "2026-11-12T10:17:42.961000+01:00" });
		expect(lauf.store.staende.map((s) => [s.status, s.fehler])).toEqual([
			["fehler", "Aufbau nicht abgeschlossen – verworfen und neu begonnen"],
			["aufbau", null],
		]);
	});
});

describe("dashboard_daten: Fehler von Propstack", () => {
	const fehler = (status: number) => new Response("{}", { status });

	it("einzelner Serverfehler: ein zweiter Versuch, der Aufrufer merkt nichts", async () => {
		const welt = kleineWelt();
		let einmal = true;
		welt.stoerung = (schluessel) => (schluessel.startsWith("/projects") && einmal ? ((einmal = false), fehler(502)) : undefined);
		const lauf = aufbau(welt);
		expect((await lauf.bisFertig({ dokument: "meta/stand" })).anzahl_projekte).toBe(2);
		expect(welt.log.filter((eintrag) => eintrag.startsWith("/projects"))).toHaveLength(2);
	});

	it("anhaltender Serverfehler: Fehlermeldung, Fortschritt gesichert, Sperre gelöst – der nächste Aufruf macht dort weiter", async () => {
		const welt = grosseWelt();
		const lauf = aufbau(welt);
		let kaputt = true;
		welt.stoerung = (schluessel) => (kaputt && schluessel.includes("project_id=590020") ? fehler(503) : undefined);

		await expect(lauf.aufruf({ dokument: "meta/stand" })).rejects.toThrow(
			"Propstack-Serverfehler (503) – Der Aufbau des Stands ist bis hierher gespeichert (Anlagedatum je Projekt); ein erneuter Aufruf macht dort weiter.",
		);
		const stand = lauf.store.staende[0];
		expect([stand.status, stand.sperre_bis, stand.cursor.naechstesProjekt, stand.anfragen]).toEqual(["aufbau", null, 20, 28]);

		kaputt = false;
		const fertig = await lauf.bisFertig({ dokument: "meta/stand" });
		expect(fertig.anzahl_projekte).toBe(110);
		// nichts doppelt gelesen außer der gescheiterten Anfrage (2 Fehlversuche + 1 Erfolg)
		const zaehler = new Map<string, number>();
		for (const eintrag of welt.log) zaehler.set(eintrag, (zaehler.get(eintrag) ?? 0) + 1);
		expect([...zaehler].filter(([, n]) => n > 1)).toEqual([["/units?expand=1&order=asc&per=1&project_id=590020&sort_by=created_at", 3]]);
		expect((await lauf.aufruf({ dokument: "meta/projekte" })).projekte["590020"].erste_einheit).toBeTruthy();
	});

	it("Zugriff verweigert (Key darf Aufgaben nicht lesen): Meldung von Propstack kommt durch, kein zweiter Versuch im selben Aufruf", async () => {
		const welt = kleineWelt();
		welt.stoerung = (schluessel) => (schluessel.startsWith("/activities") ? fehler(403) : undefined);
		const lauf = aufbau(welt);
		const erwartet = /Propstack hat den Zugriff verweigert \(403\)\. Fehlt dem API-Key das Leserecht für diesen Bereich\? – Der Aufbau des Stands ist bis hierher gespeichert \(Aufgaben der Prüfer\)/;
		await expect(lauf.aufruf({ dokument: "meta/stand" })).rejects.toThrow(erwartet);
		expect(welt.log.filter((eintrag) => eintrag.startsWith("/activities"))).toHaveLength(1);
		// erneuter Aufruf: nur die Aufgaben werden noch einmal versucht, Einheiten und Projekte nicht
		await expect(lauf.aufruf({ dokument: "meta/stand" })).rejects.toThrow(erwartet);
		expect(lauf.anfragenJeAufruf).toEqual([5, 1]);
	});

	it("Rate-Limit (429): der Client wartet und wiederholt; die Wiederholungen zählen ins Budget", async () => {
		const welt = kleineWelt();
		let dreimal = 3;
		welt.stoerung = (schluessel) => (schluessel.startsWith("/activities") && dreimal-- > 0 ? new Response("{}", { headers: { "retry-after": "0" }, status: 429 }) : undefined);
		const lauf = aufbau(welt);
		expect((await lauf.bisFertig({ dokument: "meta/stand" })).anzahl_aufgaben).toBe(2);
		expect(lauf.anfragenJeAufruf).toEqual([8]);
		expect(lauf.store.staende[0].anfragen).toBe(8);
	});

	it("Dokument größer als 256 KiB: Fehler wie im bisherigen Export; der Stand gilt als fehlgeschlagen und blockiert nichts", async () => {
		const welt = kleineWelt();
		const riesig = "Pruefung: ".padEnd(700, "x");
		welt.aufgaben.set(
			254958,
			Array.from({ length: 400 }, (_, i) => ({ done: null, id: 1000 + i, original_created_at: propstackZeit(JETZT - TAG), title: riesig, updated_at: propstackZeit(JETZT - TAG) })),
		);
		const lauf = aufbau(welt);
		await expect(lauf.aufruf({ dokument: "meta/stand" })).rejects.toThrow(/^Ein Dokument ist größer als die Grenze der Dashboard-Datenbank \(pruefung\/teil-01: \d+ Bytes, Grenze 262144\)\.$/);
		expect(lauf.store.staende.map((s) => [s.status, s.sperre_bis])).toEqual([["fehler", null]]);
		expect(lauf.store.dokumentZeilen).toEqual([]);
		// nach der Korrektur in Propstack baut der nächste Aufruf neu auf
		welt.aufgaben.set(254958, []);
		expect((await lauf.bisFertig({ dokument: "meta/stand" })).anzahl_aufgaben).toBe(0);
	});

	it("Reißleine: Liefert der Server endlos volle Seiten, bricht der Aufbau ab statt Unvollständiges zu speichern", async () => {
		const welt = kleineWelt();
		for (let i = 0; i < 30; i++) welt.projekte.push({ id: 5000 + i, title: `Füllprojekt ${i}` });
		const lauf = aufbau(welt, { maxSeitenProjekte: 3, seiteProjekte: 5 });
		await expect(lauf.aufruf({ dokument: "meta/stand" })).rejects.toThrow(/Projektliste: mehr als 3 Seiten zu 5\. Der Abruf wurde abgebrochen, weil das Ergebnis unvollständig wäre\./);
	});
});

describe("dashboard_daten über das MCP-Protokoll", () => {
	async function verbinden(welt: Welt) {
		const server = new McpServer({ name: "test", version: "0" });
		const audits: unknown[][] = [];
		const db = { prepare: () => ({ bind: (...args: unknown[]) => ({ run: async () => audits.push(args) }) }) } as unknown as D1Database;
		const store = new MemoryDashboardStore();
		registerReadTools(server, {
			createClient: () => welt.client(),
			dashboardStore: () => store,
			env: { AUDIT_DB: db } as Env,
			now: () => JETZT,
			props: () => ({ brokerId: 347158, email: "routine@kromeichpartner.de", name: "Routine" }),
		});
		const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
		await server.connect(serverTransport);
		const client = new Client({ name: "claude-test", version: "0" });
		await client.connect(clientTransport);
		const aufruf = async (args: Record<string, unknown>) => {
			const ergebnis = await client.callTool({ arguments: args, name: "dashboard_daten" });
			return { fehler: ergebnis.isError === true, text: (ergebnis.content as { text: string }[])[0].text };
		};
		return { audits, aufruf, client, store };
	}

	it("ist ein reines Lese-Tool mit festem Parametersatz", async () => {
		const { client } = await verbinden(kleineWelt());
		const tool = (await client.listTools()).tools.find((t) => t.name === "dashboard_daten")!;
		expect(tool.annotations).toMatchObject({ openWorldHint: false, readOnlyHint: true });
		expect(Object.keys(tool.inputSchema.properties ?? {}).sort()).toEqual(["broker_ids", "dokument", "stand", "tage"]);
		expect(tool.inputSchema.required).toEqual(["dokument"]);
		expect(tool.inputSchema.additionalProperties).toBe(false);
		const eigenschaften = tool.inputSchema.properties as Record<string, Record<string, unknown>>;
		expect(eigenschaften.tage).toMatchObject({ maximum: 91, minimum: 1, type: "integer" });
		expect(eigenschaften.dokument.pattern).toBe("^(alles|meta\\/stand|meta\\/projekte|wochen\\/\\d{4}-KW\\d{2}|pruefung\\/teil-\\d{2})$");
	});

	it("weist falsche Eingaben ab, bevor Propstack gefragt wird", async () => {
		const welt = kleineWelt();
		const { aufruf, store } = await verbinden(welt);
		for (const args of [
			{},
			{ dokument: "alle" },
			{ dokument: "Alles" },
			{ dokument: "alles " },
			{ dokument: "alles/meta" },
			{ dokument: "meta/stand/../x" },
			{ dokument: "wochen/2026-KW5" },
			{ dokument: "pruefung/teil-1" },
			{ dokument: "meta/stand", tage: 92 },
			{ dokument: "meta/stand", tage: 0 },
			{ dokument: "meta/stand", tage: 7.5 },
			{ broker_ids: [], dokument: "meta/stand" },
			{ broker_ids: [1, 2, 3, 4, 5, 6], dokument: "meta/stand" },
			{ broker_ids: [-1], dokument: "meta/stand" },
			{ dokument: "meta/stand", sql: "DROP TABLE" },
		]) {
			expect((await aufruf(args)).fehler, JSON.stringify(args)).toBe(true);
		}
		expect(welt.log).toEqual([]);
		expect(store.staende).toEqual([]);
	});

	it("liefert genau das Dokument als kompakten JSON-Text und schreibt das Audit-Log", async () => {
		const { aufruf, audits } = await verbinden(kleineWelt());
		const { fehler, text } = await aufruf({ dokument: "meta/stand" });
		expect(fehler).toBe(false);
		expect(text).toBe(
			'{"aktualisiert":"2026-11-12T09:47:42.960000+01:00","fenster_von":"2026-08-13T09:47:42.960000+02:00","fenster_bis":"2026-11-12T09:47:42.960000+01:00","tage":91,"pruefer_broker_ids":[254958],"anzahl_einheiten":3,"anzahl_projekte":2,"anzahl_offen":1,"anzahl_aufgaben":2,"wochen":["2026-KW44","2026-KW45","2026-KW46"],"pruefung_teile":["teil-01"]}',
		);
		const woche = await aufruf({ dokument: "wochen/2026-KW46", stand: "2026-11-12T09:47:42.960000+01:00" });
		expect(woche.text).toBe(`{"woche":"2026-KW46","einheiten":[{"id":101,"titel":"Halle A","flaeche":null,"vermarktung":null,"stadt":null,"projekt_id":7,"angelegt":"${propstackZeit(JETZT - 2 * TAG)}"}]}`);
		const fehlt = await aufruf({ dokument: "wochen/2020-KW01" });
		expect([fehlt.fehler, fehlt.text]).toEqual([true, expect.stringContaining("Das Dokument wochen/2020-KW01 gibt es im Stand")]);

		// Audit: Zeit, Nutzer, Nutzer-ID, Tool, Parameter, Anzahl, ok
		expect(audits.map((eintrag) => [eintrag[1], eintrag[3], eintrag[4], eintrag[5], eintrag[6]])).toEqual([
			["routine@kromeichpartner.de", "dashboard_daten", '{"dokument":"meta/stand"}', 1, 1],
			["routine@kromeichpartner.de", "dashboard_daten", '{"dokument":"wochen/2026-KW46","stand":"2026-11-12T09:47:42.960000+01:00"}', 1, 1],
			["routine@kromeichpartner.de", "dashboard_daten", '{"dokument":"wochen/2020-KW01"}', null, 0],
		]);
	});

	it('dokument = "alles": eine Zeile; jeder Wert Zeichen für Zeichen wie der Einzelabruf; im Audit die Zahl der Dokumente', async () => {
		const { aufruf, audits } = await verbinden(kleineWelt());
		const alles = await aufruf({ dokument: "alles" });
		expect(alles.fehler).toBe(false);
		const namen = ["meta/stand", "meta/projekte", "wochen/2026-KW44", "wochen/2026-KW45", "wochen/2026-KW46", "pruefung/teil-01"];
		const teile: string[] = [];
		for (const name of namen) teile.push(`${JSON.stringify(name)}:${(await aufruf({ dokument: name, stand: "2026-11-12T09:47:42.960000+01:00" })).text}`);
		expect(alles.text).toBe(`{"stand":"2026-11-12T09:47:42.960000+01:00","dokumente":{${teile.join(",")}}}`);
		expect(alles.text).not.toMatch(/\n/);
		expect(audits[0].slice(3, 7)).toEqual(["dashboard_daten", '{"dokument":"alles"}', 6, 1]);
	});

	it("solange der Stand nicht fertig ist: fortsetzen: true statt eines Dokuments, im Audit mit Anzahl 0", async () => {
		const { aufruf, audits } = await verbinden(grosseWelt());
		const { fehler, text } = await aufruf({ dokument: "meta/stand" });
		expect(fehler).toBe(false);
		expect(JSON.parse(text)).toMatchObject({ fortsetzen: true, phase: "Anlagedatum je Projekt" });
		expect(audits[0][5]).toBe(0);
	});
});
