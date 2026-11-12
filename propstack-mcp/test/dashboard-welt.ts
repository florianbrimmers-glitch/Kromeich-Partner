import { berlinTag, berlinZeit, zeitMs } from "../src/dashboard/zeit";
import { PropstackClient } from "../src/propstack-client";

// Nachgestelltes Propstack für die Dashboard-Tests – auf der Ebene von fetch, damit der echte PropstackClient
// mitläuft (URLs, Zähler der Anfragen, Wiederholung bei 429, Fehlertexte).
//
// Verhalten wie live geprüft (weekly_report/propstack.py):
//   /units?created_at_from/to   tagesgenauer Filter, feste Reihenfolge
//   /units?project_id&sort_by=created_at&order=asc&per=1   früheste Einheit eines Projekts
//   /projects                   nackte Liste ohne Zeitstempel
//   /activities?item_type=reminder&broker_id&sort_by=updated_at&order=desc

type Raw = Record<string, unknown>;

export const JETZT = zeitMs("2026-11-12T09:47:42.960+01:00");
const TAG = 86_400_000;

/** Propstack-Schreibweise eines Zeitpunkts (Berliner Zeit, Millisekunden). */
export function propstackZeit(ms: number): string {
	return berlinZeit(ms).iso.replace(/\.(\d{3})000([+-])/, ".$1$2").replace(/(T\d\d:\d\d:\d\d)([+-])/, "$1.000$2");
}

export interface Welt {
	einheiten: Raw[];
	projekte: Raw[];
	aufgaben: Map<number, Raw[]>;
	/** Jede Anfrage: "/pfad?sortierte=parameter". */
	log: string[];
	/** Störung: liefert für eine Anfrage eine eigene Antwort (z. B. 500) oder undefined für den Normalfall. */
	stoerung?: (schluessel: string, nummer: number) => Response | Promise<Response> | undefined;
	/** Läuft vor jeder Antwort – z. B. um die Uhr vorzustellen oder Daten zu verändern. */
	vorAntwort?: (schluessel: string, nummer: number) => void | Promise<void>;
	client(): PropstackClient;
}

export function neueWelt(daten: { einheiten?: Raw[]; projekte?: Raw[]; aufgaben?: Record<number, Raw[]> } = {}): Welt {
	const welt: Welt = {
		aufgaben: new Map(Object.entries(daten.aufgaben ?? {}).map(([broker, zeilen]) => [Number(broker), zeilen])),
		client: () => new PropstackClient({ apiKey: "test", fetchFn, sleep: async () => {} }),
		einheiten: daten.einheiten ?? [],
		log: [],
		projekte: daten.projekte ?? [],
	};
	const instant = (iso: unknown) => (typeof iso === "string" ? zeitMs(iso) : Number.NEGATIVE_INFINITY);
	const fetchFn = (async (input: RequestInfo | URL) => {
		const url = new URL(String(input));
		const pfad = url.pathname.replace(/^\/v1/, "");
		const p = Object.fromEntries(url.searchParams);
		const schluessel = `${pfad}?${Object.keys(p)
			.sort()
			.map((key) => `${key}=${p[key]}`)
			.join("&")}`;
		welt.log.push(schluessel);
		const nummer = welt.log.length;
		await welt.vorAntwort?.(schluessel, nummer);
		const gestoert = await welt.stoerung?.(schluessel, nummer);
		if (gestoert) return gestoert;

		const per = Number(p.per ?? 25);
		const page = Number(p.page ?? 1);
		const seite = (zeilen: Raw[]) => zeilen.slice((page - 1) * per, page * per);
		let antwort: unknown;
		if (pfad === "/units" && p.project_id) {
			if (p.expand !== "1" || p.sort_by !== "created_at" || p.order !== "asc") return new Response("{}", { status: 400 });
			const zeilen = welt.einheiten.filter((u) => Number(u.project_id) === Number(p.project_id) && u.created_at).sort((a, b) => instant(a.created_at) - instant(b.created_at));
			antwort = { data: seite(zeilen) };
		} else if (pfad === "/units") {
			// ohne expand=1 liefert Propstack kein created_at – dann fände der Connector nichts
			const zeilen = welt.einheiten
				.filter((u) => {
					if (typeof u.created_at !== "string") return true;
					const tag = berlinTag(berlinZeit(zeitMs(u.created_at)));
					return p.created_at_from <= tag && tag <= p.created_at_to;
				})
				.sort((a, b) => Number(b.id) - Number(a.id))
				.map((u) => (p.expand === "1" ? u : { ...u, created_at: null }));
			antwort = { data: seite(zeilen), meta: { total_count: zeilen.length } };
		} else if (pfad === "/projects") {
			antwort = seite(welt.projekte);
		} else if (pfad === "/activities") {
			if (p.item_type !== "reminder") return new Response("{}", { status: 400 });
			const zeilen = [...(welt.aufgaben.get(Number(p.broker_id)) ?? [])];
			if (p.sort_by === "updated_at") zeilen.sort((a, b) => (p.order === "desc" ? instant(b.updated_at) - instant(a.updated_at) : instant(a.updated_at) - instant(b.updated_at)));
			antwort = { data: seite(zeilen), meta: { total_count: zeilen.length } };
		} else {
			return new Response("{}", { status: 404 });
		}
		return new Response(JSON.stringify(antwort), { headers: { "Content-Type": "application/json" }, status: 200 });
	}) as unknown as typeof fetch;
	return welt;
}

/**
 * Bestand in der Größenordnung vom 12.11.2026 (Referenzlauf des bisherigen Exports: 363 Einheiten, 104 Projekte,
 * 520 Prüfaufgaben, 112 Anfragen): 255 Einheiten im Serverfenster (250 im Bericht), 110 Projekte, 543 Aufgaben.
 */
export function grosseWelt(): Welt {
	const since = JETZT - 91 * TAG - 3_600_000; // 91 Tage zurück über das Ende der Sommerzeit: eine Stunde mehr als 91 × 24 h
	const projektIds = Array.from({ length: 110 }, (_, i) => 590_000 + i);
	const einheiten: Raw[] = [];
	for (let i = 0; i < 250; i++) {
		einheiten.push({
			city: { label: "Stadt", value: `Ort ${i % 30}` },
			created_at: propstackZeit(since + 60_000 + Math.floor(((JETZT - since - 120_000) / 250) * i)),
			id: 6_100_000 + i,
			marketing_type: i % 4 ? "RENT" : "BUY",
			project_id: i < 220 ? projektIds[i % 110] : null,
			property_space_value: 1000 + i * 10.5,
			title: { label: "Überschrift", value: `Logistikhalle in (${10 + (i % 80)}) Ort ${i % 30} – Halle ${i}` },
		});
	}
	// im geweiteten Serverfenster, aber außerhalb des Berichts
	for (let i = 0; i < 5; i++) einheiten.push({ created_at: propstackZeit(since - 3_600_000 * (i + 1)), id: 6_200_000 + i, project_id: 599_999, title: `Knapp zu alt ${i}` });
	// ältere Einheiten datieren jedes zweite Projekt vor das Fenster
	for (let i = 0; i < 110; i += 2) einheiten.push({ created_at: propstackZeit(since - (100 + i) * TAG), id: 5_000_000 + i, project_id: projektIds[i], title: `Alt ${i}` });

	const projekte: Raw[] = [];
	for (let i = 0; i < 429; i++) {
		const eigen = i < 220 && i % 2 === 0;
		const pid = eigen ? projektIds[i / 2] : 700_000 + i;
		// Projekt 590007 ist gelöscht: Einheiten zeigen noch darauf, die Liste kennt es nicht mehr
		if (pid !== 590_007) projekte.push({ address: `Parkweg ${i}`, id: pid, title: `Logistikpark ${pid}` });
	}

	const aufgaben: Raw[] = [];
	for (let i = 0; i < 543; i++) {
		const offen = i < 493;
		const imFenster = i < 520;
		const angelegt = offen ? since - (i % 400) * TAG + i * 1000 : imFenster ? since + (i - 492) * TAG : since - 200 * TAG;
		aufgaben.push({
			broker_id: 254958,
			done: offen ? null : true,
			id: 447_000_000 + i,
			original_created_at: propstackZeit(angelegt),
			project_names: [],
			property_names: [`Einheit ${i}`],
			title: i % 3 ? `Pruefung Panattoni Welle ${i % 5}: Park ${i}` : `Newsletter-Vermietung prüfen: Eigentümer ${i}`,
			updated_at: propstackZeit(imFenster ? angelegt + 3_600_000 : since - 150 * TAG),
		});
	}
	return neueWelt({ aufgaben: { 254958: aufgaben }, einheiten, projekte });
}
