import roh from "./dashboard-golden.fixture.json";

// Vergleichsdaten aus dem bisherigen Python-Export (weekly_report/dashboard_export.py), erzeugt mit
// test/dashboard-golden.erzeugen.py: aufgezeichnete Propstack-Anfragen samt Antworten und die Dokumente,
// die der echte Export daraus gemacht hat – dazu eine Tabelle mit Pythons Zeitrechnung.

export interface Anfrage {
	pfad: string;
	params: Record<string, string>;
	antwort: unknown;
}

export interface Szenario {
	name: string;
	until_ms: number;
	tage: number;
	broker_ids: number[];
	anfragen: Anfrage[];
	dokumente: Record<string, unknown>;
}

export interface Fenster {
	until_ms: number;
	tage: number;
	until_iso: string;
	since_iso: string;
	since_ms: number;
	created_at_from: string;
	created_at_to: string;
}

export interface Golden {
	/** Seitengröße, mit der aufgezeichnet wurde – der Connector muss im Test dieselbe nutzen. */
	seite: number;
	szenarien: Szenario[];
	zeit: {
		wochen: [string, string][];
		isoformat: [string, string][];
		fenster: Fenster[];
		aufgaben_art: [unknown, string][];
	};
}

export const GOLDEN = roh as unknown as Golden;

/** Eine Anfrage als Schlüssel: Pfad plus sortierte Parameter. */
export function anfrageSchluessel(pfad: string, params: Record<string, string>): string {
	return `${pfad}?${Object.keys(params)
		.sort()
		.map((key) => `${key}=${params[key]}`)
		.join("&")}`;
}

/**
 * fetch-Ersatz, der nur die aufgezeichneten Anfragen beantwortet. Jede andere Anfrage ist ein Fehler:
 * Der Connector muss genau die Abfragen stellen, die der bisherige Export gestellt hat.
 */
export function kassette(szenario: Szenario) {
	const antworten = new Map(szenario.anfragen.map((anfrage) => [anfrageSchluessel(anfrage.pfad, anfrage.params), anfrage.antwort]));
	const benutzt = new Set<string>();
	const unbekannt: string[] = [];
	const fetchFn = (async (input: RequestInfo | URL, init?: RequestInit) => {
		const url = new URL(String(input));
		const schluessel = anfrageSchluessel(url.pathname.replace(/^\/v1/, ""), Object.fromEntries(url.searchParams));
		if ((init?.method ?? "GET") !== "GET" || !antworten.has(schluessel)) {
			unbekannt.push(`${init?.method ?? "GET"} ${schluessel}`);
			return new Response("{}", { status: 404 });
		}
		benutzt.add(schluessel);
		return new Response(JSON.stringify(antworten.get(schluessel)), { headers: { "Content-Type": "application/json" }, status: 200 });
	}) as unknown as typeof fetch;
	return {
		benutzt,
		fetchFn,
		unbekannt,
		/** Aufgezeichnete Anfragen, die der Connector nicht gestellt hat. */
		unbenutzt: () => [...antworten.keys()].filter((schluessel) => !benutzt.has(schluessel)),
	};
}
