import { describe, expect, it } from "vitest";
import migration from "../migrations/0004_dashboard_cache.sql?raw";
import { dashboardDaten } from "../src/dashboard/aufbau";
import { D1DashboardStore, type DashboardStore, MemoryDashboardStore, purgeOldDashboardStands, type Stand } from "../src/dashboard/store";
import { PropstackClient } from "../src/propstack-client";
import { GOLDEN, kassette } from "./dashboard-golden";

// Der Zwischenspeicher gegen echtes SQLite: die Migration 0004 und jede SQL-Anweisung der D1-Variante laufen
// wirklich (D1 ist SQLite). Tippfehler in Spaltennamen oder SQL fallen so vor dem Deploy auf, nicht erst live.
// Dieselben Fälle laufen gegen die Arbeitsspeicher-Variante – beide müssen sich gleich verhalten.

interface Sqlite {
	exec(sql: string): void;
	prepare(sql: string): { all(...args: unknown[]): unknown[]; get(...args: unknown[]): unknown; run(...args: unknown[]): { changes: number | bigint } };
}

/** D1-Schnittstelle auf dem SQLite, das Node mitbringt (ohne Node-Typen im Projekt – deshalb der dynamische Import). */
async function d1(migrationen = 1): Promise<D1Database> {
	const modul = "node:sqlite";
	const { DatabaseSync } = (await import(/* @vite-ignore */ modul)) as { DatabaseSync: new (pfad: string) => Sqlite };
	const db = new DatabaseSync(":memory:");
	for (let i = 0; i < migrationen; i++) db.exec(migration);
	const befehl = (sql: string, args: unknown[] = []) => ({
		all: async () => ({ results: db.prepare(sql).all(...args).map((zeile) => ({ ...(zeile as object) })) }),
		bind: (...neu: unknown[]) => {
			// wie D1: undefined ist kein gültiger Wert
			if (neu.some((wert) => wert === undefined)) throw new Error(`D1_TYPE_ERROR: undefined in ${sql}`);
			return befehl(sql, neu);
		},
		first: async () => {
			const zeile = db.prepare(sql).get(...args);
			return zeile ? { ...(zeile as object) } : null;
		},
		run: async () => ({ meta: { changes: Number(db.prepare(sql).run(...args).changes) } }),
	});
	return {
		batch: async (befehle: { run(): Promise<unknown> }[]) => {
			db.exec("BEGIN");
			try {
				const ergebnisse = [];
				for (const b of befehle) ergebnisse.push(await b.run());
				db.exec("COMMIT");
				return ergebnisse;
			} catch (error) {
				db.exec("ROLLBACK");
				throw error;
			}
		},
		prepare: (sql: string) => befehl(sql),
	} as unknown as D1Database;
}

const stand = (felder: Partial<Stand> = {}): Stand => ({
	anfragen: 0,
	aufrufe: 0,
	broker_ids: [254958],
	cursor: { brokerIndex: 0, naechstesProjekt: 0, projektIds: [], seite: 1 },
	fehler: null,
	id: "s1",
	params: "91|254958",
	phase: "einheiten",
	ready_ts: null,
	since_iso: "2026-08-13T09:47:42.960000+02:00",
	since_ms: 1786607262960,
	sperre_bis: null,
	started_ts: "2026-11-12T08:47:42.960Z",
	status: "aufbau",
	tage: 91,
	until_iso: "2026-11-12T09:47:42.960000+01:00",
	until_ms: 1794473262960,
	updated_ts: "2026-11-12T08:47:42.960Z",
	user_email: "routine@kromeichpartner.de",
	...felder,
});

const DOKUMENTE = [
	{ bytes: 12, inhalt: '{"teil":"ä"}', name: "pruefung/teil-01" },
	{ bytes: 11, inhalt: '{"tage":91}', name: "meta/stand" },
];

const varianten: [string, () => Promise<{ store: DashboardStore; db?: D1Database }>][] = [
	["D1 (echtes SQLite mit Migration 0004)", async () => {
		const db = await d1();
		return { db, store: new D1DashboardStore(db) };
	}],
	["Arbeitsspeicher (Tests)", async () => ({ store: new MemoryDashboardStore() })],
];

for (const [name, erzeugen] of varianten) {
	describe(`Dashboard-Zwischenspeicher – ${name}`, () => {
		it("anlegen und lesen: alle Felder kommen unverändert zurück (Listen und Cursor als JSON)", async () => {
			const { store } = await erzeugen();
			const s = stand({ broker_ids: [254958, 387451], cursor: { brokerIndex: 1, naechstesProjekt: 3, projektIds: [7, 8, 9], seite: 2 } });
			await store.anlegen(s);
			expect(await store.stand("s1")).toEqual(s);
			expect(await store.neuester("91|254958")).toEqual(s);
			expect(await store.neuester("7|254958")).toBeNull();
			expect(await store.stand("gibt-es-nicht")).toBeNull();
		});

		it("je Parametersatz höchstens ein Stand im Aufbau: der zweite wird nicht angelegt", async () => {
			const { store } = await erzeugen();
			await store.anlegen(stand({ id: "a" }));
			await store.anlegen(stand({ id: "b" }));
			await store.anlegen(stand({ id: "c", params: "7|254958" }));
			expect((await store.neuester("91|254958"))?.id).toBe("a");
			expect(await store.stand("b")).toBeNull();
			expect((await store.neuester("7|254958"))?.id).toBe("c");
			// nach dem Verwerfen ist Platz für einen neuen
			await store.verwerfen("a", "verworfen", "2026-11-12T09:00:00.000Z");
			await store.anlegen(stand({ id: "b" }));
			expect((await store.stand("b"))?.status).toBe("aufbau");
		});

		it("jüngster Stand: nach Beginn, bei gleichem Zeitstempel der zuletzt angelegte", async () => {
			const { store } = await erzeugen();
			await store.anlegen(stand({ id: "z-zuerst" }));
			await store.verwerfen("z-zuerst", "fehlgeschlagen", "2026-11-12T08:48:00.000Z");
			await store.anlegen(stand({ id: "a-danach" })); // gleicher started_ts
			expect((await store.neuester("91|254958"))?.id).toBe("a-danach");
			await store.verwerfen("a-danach", "fehlgeschlagen", "2026-11-12T08:49:00.000Z");
			await store.anlegen(stand({ id: "frueher", started_ts: "2026-11-12T07:00:00.000Z" }));
			expect((await store.neuester("91|254958"))?.id).toBe("a-danach");
		});

		it("Sperre: nur einer zur selben Zeit; frei nach Ablauf oder Freigabe; nie für einen fertigen Stand", async () => {
			const { store } = await erzeugen();
			await store.anlegen(stand());
			expect(await store.sperren("s1", "2026-11-12T08:50:00.000Z", "2026-11-12T08:48:00.000Z")).toBe(true);
			expect(await store.sperren("s1", "2026-11-12T08:51:00.000Z", "2026-11-12T08:49:00.000Z")).toBe(false);
			expect(await store.sperren("s1", "2026-11-12T08:53:00.000Z", "2026-11-12T08:50:00.001Z")).toBe(true); // abgelaufen
			await store.aktualisieren("s1", { sperre_bis: null });
			expect(await store.sperren("s1", "2026-11-12T08:55:00.000Z", "2026-11-12T08:51:00.000Z")).toBe(true); // freigegeben
			expect((await store.stand("s1"))?.aufrufe).toBe(3);
			expect(await store.sperren("gibt-es-nicht", "x", "y")).toBe(false);
			await store.fertigstellen("s1", DOKUMENTE, "2026-11-12T08:52:00.000Z");
			expect(await store.sperren("s1", "2026-11-12T09:55:00.000Z", "2026-11-12T09:00:00.000Z")).toBe(false);
		});

		it("Fortschritt: nur Phase, Cursor, Zähler, Sperre, Zeit – der Status lässt sich so nicht ändern", async () => {
			const { store } = await erzeugen();
			await store.anlegen(stand());
			await store.aktualisieren("s1", { anfragen: 40, cursor: { brokerIndex: 0, naechstesProjekt: 34, projektIds: [1, 2], seite: 1 }, phase: "erste_einheit", updated_ts: "2026-11-12T08:48:10.000Z" });
			await store.aktualisieren("s1", { status: "fertig", user_email: "x" } as never);
			await store.aktualisieren("s1", {});
			expect(await store.stand("s1")).toMatchObject({ anfragen: 40, cursor: { naechstesProjekt: 34, projektIds: [1, 2] }, phase: "erste_einheit", status: "aufbau", updated_ts: "2026-11-12T08:48:10.000Z", user_email: "routine@kromeichpartner.de" });
		});

		it("Rohdaten: in Reihenfolge der Schlüssel; gleicher Schlüssel überschreibt; je Art getrennt", async () => {
			const { store } = await erzeugen();
			await store.anlegen(stand());
			await store.teileSpeichern("s1", "einheiten", [{ daten: [{ id: 2 }], seq: 2 }]);
			await store.teileSpeichern("s1", "einheiten", [{ daten: [{ id: 1, title: "Größe „ä“" }], seq: 1 }]);
			await store.teileSpeichern("s1", "erste_einheit", [
				{ daten: [7, "2025-03-19T09:52:39.301+01:00"], seq: 0 },
				{ daten: [8, null], seq: 1 },
			]);
			await store.teileSpeichern("s1", "erste_einheit", [{ daten: [8, "2026-01-01T00:00:00.000+01:00"], seq: 1 }]);
			await store.teileSpeichern("s1", "erste_einheit", []);
			expect(await store.teile("s1", "einheiten")).toEqual([[{ id: 1, title: "Größe „ä“" }], [{ id: 2 }]]);
			expect(await store.teile("s1", "erste_einheit")).toEqual([
				[7, "2025-03-19T09:52:39.301+01:00"],
				[8, "2026-01-01T00:00:00.000+01:00"],
			]);
			expect(await store.teile("s1", "aufgaben")).toEqual([]);
			expect(await store.teile("anderer", "einheiten")).toEqual([]);
		});

		it("fertigstellen: Dokumente da, Status fertig, Sperre gelöst, Rohdaten weg", async () => {
			const { store } = await erzeugen();
			await store.anlegen(stand({ sperre_bis: "2026-11-12T08:50:00.000Z" }));
			await store.teileSpeichern("s1", "einheiten", [{ daten: [{ id: 1 }], seq: 1 }]);
			await store.fertigstellen("s1", DOKUMENTE, "2026-11-12T08:49:00.000Z");
			expect(await store.stand("s1")).toMatchObject({ fehler: null, ready_ts: "2026-11-12T08:49:00.000Z", sperre_bis: null, status: "fertig" });
			expect(await store.teile("s1", "einheiten")).toEqual([]);
			expect(await store.dokumente("s1")).toEqual([DOKUMENTE[1], DOKUMENTE[0]]); // nach Name
			expect(await store.dokument("s1", "pruefung/teil-01")).toEqual(DOKUMENTE[0]);
			expect(await store.dokument("s1", "wochen/2026-KW01")).toBeNull();
			expect(await store.fertiger("91|254958", "2026-11-12T09:47:42.960000+01:00")).toMatchObject({ id: "s1" });
			expect(await store.fertiger("91|254958", "2026-11-12T09:47:42+01:00")).toBeNull();
			expect(await store.fertiger("7|254958", "2026-11-12T09:47:42.960000+01:00")).toBeNull();
		});

		it("wer zu spät fertigstellt, überschreibt nichts: Dokumente und Zeitpunkt des ersten bleiben", async () => {
			const { store } = await erzeugen();
			await store.anlegen(stand());
			await store.fertigstellen("s1", DOKUMENTE, "2026-11-12T08:49:00.000Z");
			// ein hängender Aufruf legt noch Rohdaten ab und stellt dann mit unvollständigen Daten „fertig“
			await store.teileSpeichern("s1", "aufgaben", [{ daten: [], seq: 1 }]);
			await store.fertigstellen("s1", [{ bytes: 2, inhalt: "{}", name: "meta/stand" }, { bytes: 2, inhalt: "{}", name: "wochen/2026-KW01" }], "2026-11-12T08:55:00.000Z");
			expect(await store.dokumente("s1")).toEqual([DOKUMENTE[1], DOKUMENTE[0]]);
			expect((await store.stand("s1"))?.ready_ts).toBe("2026-11-12T08:49:00.000Z");
			expect(await store.teile("s1", "aufgaben")).toEqual([]); // die verwaisten Rohdaten sind trotzdem weg
			// auch verwerfen ändert einen fertigen Stand nicht
			await store.verwerfen("s1", "zu spät", "2026-11-12T08:56:00.000Z");
			expect(await store.stand("s1")).toMatchObject({ fehler: null, status: "fertig" });
		});

		it("verworfener Stand: fertigstellen legt keine Dokumente mehr an", async () => {
			const { store } = await erzeugen();
			await store.anlegen(stand());
			await store.verwerfen("s1", "Aufbau nicht abgeschlossen", "2026-11-12T09:20:00.000Z");
			await store.fertigstellen("s1", DOKUMENTE, "2026-11-12T09:21:00.000Z");
			expect(await store.stand("s1")).toMatchObject({ fehler: "Aufbau nicht abgeschlossen", ready_ts: null, status: "fehler" });
			expect(await store.dokumente("s1")).toEqual([]);
		});

		it("aufräumen: Stände vor dem Stichtag verschwinden samt Rohdaten und Dokumenten, jüngere bleiben", async () => {
			const { store, db } = await erzeugen();
			await store.anlegen(stand({ id: "alt", started_ts: "2026-11-11T08:00:00.000Z" }));
			await store.teileSpeichern("alt", "einheiten", [{ daten: [1], seq: 1 }]);
			await store.fertigstellen("alt", DOKUMENTE, "2026-11-11T08:02:00.000Z");
			await store.anlegen(stand({ id: "halb", params: "7|254958", started_ts: "2026-11-11T08:30:00.000Z" }));
			await store.teileSpeichern("halb", "einheiten", [{ daten: [1], seq: 1 }]);
			await store.anlegen(stand({ id: "neu" }));
			await store.fertigstellen("neu", DOKUMENTE, "2026-11-12T08:49:00.000Z");

			if (db) expect(await purgeOldDashboardStands(db, "2026-11-11T08:47:00.000Z")).toBe(2);
			else await store.aufraeumen("2026-11-11T08:47:00.000Z");
			expect([await store.stand("alt"), await store.stand("halb")]).toEqual([null, null]);
			expect(await store.dokumente("alt")).toEqual([]);
			expect(await store.teile("halb", "einheiten")).toEqual([]);
			expect((await store.stand("neu"))?.status).toBe("fertig");
			expect(await store.dokumente("neu")).toHaveLength(2);
			if (db) expect(await purgeOldDashboardStands(db, "2026-11-11T08:47:00.000Z")).toBe(0);
		});

		it("ganzer Durchlauf gegen diesen Speicher: dieselben Dokumente wie der bisherige Python-Export", async () => {
			const { store } = await erzeugen();
			const szenario = GOLDEN.szenarien[1]; // Jahreswechsel, zwei Prüfer
			const band = kassette(szenario);
			const aufruf = async (dokument: string, standVon?: string) =>
				(
					await dashboardDaten(
						{
							client: new PropstackClient({ apiKey: "test", fetchFn: band.fetchFn }),
							grenzen: { anfragen: 4, seiteAufgaben: GOLDEN.seite, seiteEinheiten: GOLDEN.seite, seiteProjekte: GOLDEN.seite },
							now: () => szenario.until_ms,
							store,
							user: { email: "routine@kromeichpartner.de" },
						},
						{ broker_ids: szenario.broker_ids, dokument, tage: szenario.tage, ...(standVon ? { stand: standVon } : {}) },
					)
				).result as Record<string, unknown>;
			let meta = await aufruf("meta/stand");
			for (let i = 0; meta.fortsetzen === true && i < 50; i++) meta = await aufruf("meta/stand");
			expect(meta).toEqual(szenario.dokumente["meta/stand"]);
			for (const [dokument, erwartet] of Object.entries(szenario.dokumente)) expect(await aufruf(dokument, meta.aktualisiert as string), dokument).toEqual(erwartet);
			expect(band.unbekannt).toEqual([]);
		});
	});
}

describe("Migration 0004", () => {
	it("lässt sich zweimal anwenden und legt genau die drei Tabellen an", async () => {
		const db = await d1(2);
		const namen = await db.prepare("SELECT name FROM sqlite_master WHERE type IN ('table', 'index') AND name LIKE '%dashboard%' ORDER BY name").all<{ name: string }>();
		expect(namen.results.map((zeile) => zeile.name).filter((name) => !name.startsWith("sqlite_autoindex"))).toEqual([
			"dashboard_dokument",
			"dashboard_stand",
			"dashboard_teil",
			"idx_dashboard_stand_aufbau",
			"idx_dashboard_stand_params",
		]);
		expect(migration).toMatch(/CREATE TABLE IF NOT EXISTS/);
		expect(migration).not.toMatch(/DROP|DELETE/i);
	});
});
