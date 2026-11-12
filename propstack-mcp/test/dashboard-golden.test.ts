import { describe, expect, it } from "vitest";
import { dashboardDaten, type Grenzen } from "../src/dashboard/aufbau";
import { MemoryDashboardStore } from "../src/dashboard/store";
import { PropstackClient } from "../src/propstack-client";
import { GOLDEN, kassette, type Szenario } from "./dashboard-golden";

// Gesamtabgleich mit dem bisherigen Python-Export.
//
// Je Szenario hat der echte Export (weekly_report.dashboard_export.main()) gegen eine nachgestellte Propstack-API
// gearbeitet; aufgezeichnet sind seine Anfragen, die Antworten und die Dokumente, die er geschrieben hat.
// Hier bekommt der Connector dieselben Antworten vorgespielt – über den echten PropstackClient, also inklusive
// der URLs, die er baut. Bestanden ist der Abgleich nur, wenn
//   1. der Connector keine Anfrage stellt, die der Export nicht gestellt hat,
//   2. jedes Dokument inhaltlich exakt dem des Exports entspricht und
//   3. es genau dieselben Dokumente gibt.

const USER = { email: "routine@kromeichpartner.de" };

async function durchlauf(szenario: Szenario, grenzen: Partial<Grenzen>) {
	const band = kassette(szenario);
	const store = new MemoryDashboardStore();
	const basis = { tage: szenario.tage, broker_ids: szenario.broker_ids };
	let aufrufe = 0;
	let anfragen = 0;
	const aufruf = async (dokument: string, stand?: string) => {
		// je Tool-Aufruf ein frischer Client – wie runTool
		const client = new PropstackClient({ apiKey: "test", fetchFn: band.fetchFn, sleep: async () => {} });
		const ausgabe = await dashboardDaten(
			{ client, grenzen: { seiteAufgaben: GOLDEN.seite, seiteEinheiten: GOLDEN.seite, seiteProjekte: GOLDEN.seite, ...grenzen }, now: () => szenario.until_ms, store, user: USER },
			{ ...basis, dokument, ...(stand ? { stand } : {}) },
		);
		aufrufe++;
		anfragen += client.requestsUsed;
		return ausgabe.result as Record<string, unknown>;
	};

	let stand = await aufruf("meta/stand");
	while (stand.fortsetzen === true) {
		expect(aufrufe, "der Aufbau muss enden").toBeLessThan(200);
		stand = await aufruf("meta/stand");
	}
	return { anfragen, aufruf, aufrufe, band, stand, store };
}

describe("Abgleich mit dem bisherigen Python-Export", () => {
	it("die Vergleichsdaten decken die Sonderfälle ab", () => {
		expect(GOLDEN.szenarien.map((s) => s.name)).toEqual([
			"Sommerzeit-Ende im Fenster, ein Prüfer",
			"Jahreswechsel, zwei Prüfer, Seite exakt voll",
			"Fensterbeginn in der Lücke am Beginn der Sommerzeit",
			"Fensterbeginn in der doppelten Stunde, keine Projekte",
		]);
		const [erstes, zweites] = GOLDEN.szenarien;
		const projekte = (erstes.dokumente["meta/projekte"] as { projekte: Record<string, { vorhanden: boolean; erste_einheit: string | null }> }).projekte;
		expect(Object.values(projekte).some((p) => !p.vorhanden)).toBe(true);
		expect(Object.values(projekte).some((p) => p.erste_einheit === null)).toBe(true);
		expect(Object.keys(zweites.dokumente)).toEqual(expect.arrayContaining(["wochen/2026-KW53", "wochen/2027-KW01"]));
	});

	for (const szenario of GOLDEN.szenarien) {
		for (const [bezeichnung, grenzen] of [
			["in einem Zug", { anfragen: 40 }],
			["in vielen kleinen Etappen (3 Anfragen je Aufruf)", { anfragen: 3 }],
		] as const) {
			it(`${szenario.name} – ${bezeichnung}: jedes Dokument exakt wie der Export, keine fremde Anfrage`, async () => {
				const lauf = await durchlauf(szenario, grenzen);

				// meta/stand kommt direkt als Dokument – ohne Hülle, ohne Zusatzfelder
				expect(lauf.stand).toEqual(szenario.dokumente["meta/stand"]);

				// alle weiteren Dokumente, fest auf diesen Stand bezogen
				const aktualisiert = lauf.stand.aktualisiert as string;
				for (const [name, erwartet] of Object.entries(szenario.dokumente)) {
					expect(await lauf.aufruf(name, aktualisiert), name).toEqual(erwartet);
				}

				// genau dieselben Dokumente, nicht mehr und nicht weniger
				const stand = lauf.store.staende[0];
				expect((await lauf.store.dokumente(stand.id)).map((d) => d.name).sort()).toEqual(Object.keys(szenario.dokumente).sort());

				// keine Anfrage, die der Export nicht gestellt hat
				expect(lauf.band.unbekannt).toEqual([]);
				// … und alle, die er gestellt hat. Einzige Ausnahme: Ohne Projekte im Fenster spart sich der Connector die Projektliste.
				const ohneProjekte = (lauf.stand.anzahl_projekte as number) === 0;
				expect(lauf.band.unbenutzt().filter((schluessel) => !(ohneProjekte && schluessel.startsWith("/projects?")))).toEqual([]);
				expect(lauf.anfragen).toBe(lauf.band.benutzt.size);
				expect(stand.anfragen).toBe(lauf.anfragen);
				expect(stand.status).toBe("fertig");
				// Rohdaten sind nach dem Fertigstellen gelöscht
				expect(lauf.store.teilZeilen).toEqual([]);

				// Etappen: je Aufruf höchstens so viele Anfragen wie erlaubt, kein Aufruf ohne Fortschritt
				expect(lauf.aufrufe).toBe(Math.ceil(lauf.anfragen / grenzen.anfragen));
			});
		}
	}

	it("Seitengröße ist für das Ergebnis egal: mit 5 statt 7 je Seite entstehen dieselben Dokumente", async () => {
		// Die echte API liefert bei 100 und 200 je Seite dieselbe Reihenfolge (live geprüft am 12.11.2026). Hier: andere Seitengröße
		// gegen dieselben Daten – dafür braucht es eine API, die jede Seitengröße bedient.
		const szenario = GOLDEN.szenarien[0];
		const alle = (pfad: string, filter: (params: Record<string, string>) => boolean) =>
			szenario.anfragen.filter((a) => a.pfad === pfad && filter(a.params)).flatMap((a) => (Array.isArray(a.antwort) ? a.antwort : (a.antwort as { data: unknown[] }).data));
		const einheiten = alle("/units", (p) => !("project_id" in p));
		const projekte = alle("/projects", () => true);
		const aufgaben = alle("/activities", () => true);
		const fruehste = new Map(szenario.anfragen.filter((a) => a.pfad === "/units" && "project_id" in a.params).map((a) => [a.params.project_id, a.antwort]));
		const fetchFn = (async (input: RequestInfo | URL) => {
			const url = new URL(String(input));
			const per = Number(url.searchParams.get("per"));
			const page = Number(url.searchParams.get("page") ?? 1);
			const seite = (zeilen: unknown[]) => zeilen.slice((page - 1) * per, page * per);
			const pfad = url.pathname.replace(/^\/v1/, "");
			const antwort =
				pfad === "/units" && url.searchParams.has("project_id")
					? fruehste.get(url.searchParams.get("project_id") as string)
					: pfad === "/units"
						? { data: seite(einheiten) }
						: pfad === "/projects"
							? seite(projekte)
							: { data: seite(aufgaben) };
			return new Response(JSON.stringify(antwort), { status: 200 });
		}) as unknown as typeof fetch;
		const store = new MemoryDashboardStore();
		const aufruf = async (dokument: string) =>
			(
				await dashboardDaten(
					{ client: new PropstackClient({ apiKey: "test", fetchFn }), grenzen: { anfragen: 40, seiteAufgaben: 5, seiteEinheiten: 5, seiteProjekte: 5 }, now: () => szenario.until_ms, store, user: USER },
					{ broker_ids: szenario.broker_ids, dokument, tage: szenario.tage },
				)
			).result as Record<string, unknown>;
		let stand = await aufruf("meta/stand");
		for (let i = 0; stand.fortsetzen === true && i < 50; i++) stand = await aufruf("meta/stand");
		expect(stand).toEqual(szenario.dokumente["meta/stand"]);
		for (const [name, erwartet] of Object.entries(szenario.dokumente)) expect(await aufruf(name), name).toEqual(erwartet);
	});
});
