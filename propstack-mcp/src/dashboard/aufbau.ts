import { z } from "zod";
import type { Page, PropstackClient, Query } from "../propstack-client";
import { PropstackError } from "../propstack-client";
import { id } from "../tools/params";
import type { ToolOutput } from "../tools/read-tools";
import {
	type Aufgabe,
	baueDokumente,
	type Einheit,
	imFenster,
	mitId,
	neuesteZuerst,
	ohneDoppelte,
	projektTitel,
	serialisiere,
	STANDARD_TAGE,
	zuAufgabe,
	zuEinheit,
} from "./dokumente";
import type { Cursor, DashboardStore, Phase, Stand, TeilEintrag } from "./store";
import { berlinTag, berlinZeit, minusTage } from "./zeit";

// Tool dashboard_daten: Daten für das Propstack-Dashboard (claude.ai-Artifact „Objektanlage & Prüfaufgaben“).
//
// Bisher holte eine tägliche Routine die Daten mit weekly_report/dashboard_export.py – mit API-Keys in der
// Claude-Umgebung. Jetzt holt der Connector sie; der Key bleibt im Worker.
//
// Ein vollständiger Stand braucht rund 110 Propstack-Abfragen (je Projekt eine für das Anlagedatum), ein
// Tool-Aufruf darf höchstens 45. Deshalb wird der Stand über mehrere Aufrufe aufgebaut und in D1
// zwischengespeichert: Solange er nicht fertig ist, antwortet das Tool mit fortsetzen: true; danach kommen
// die Dokumente 30 Minuten lang aus dem Zwischenspeicher.
//
// Reihenfolge wie im bisherigen Export: Einheiten im Fenster → Projektliste → früheste Einheit je Projekt →
// Aufgaben der Prüfer. Der Zeitpunkt des Stands („aktualisiert“) ist der Beginn des Aufbaus.

type Raw = Record<string, unknown>;

/** Sitz, auf dem die Prüfaufgaben gepflegt werden (früher Oguzhan Sahin, jetzt Lena Klinnert). */
export const STANDARD_BROKER_IDS = [254958];

export interface Grenzen {
	/** Propstack-Anfragen je Tool-Aufruf (Client-Grenze 45; Cloudflare Free erlaubt 50 Subrequests). */
	anfragen: number;
	/** Nach so vielen Millisekunden beginnt ein Aufruf keine neue Anfrage mehr. */
	zeitMs: number;
	/** Fertiger Stand: so lange kommen Dokumente aus dem Zwischenspeicher. */
	gueltigMs: number;
	/** Unfertiger Stand: älter als das → verwerfen und neu beginnen (sonst wären die Daten beim Fertigwerden schon alt). */
	aufbauMaxMs: number;
	/** So lange hält ein Aufruf den Aufbau für sich, falls er abbricht, ohne die Sperre zu lösen. */
	sperreMs: number;
	/** Stände, die älter sind, werden beim nächsten Aufbau gelöscht. */
	aufbewahrungMs: number;
	seiteEinheiten: number;
	seiteProjekte: number;
	seiteAufgaben: number;
	/** Reißleine wie im bisherigen Export (dort 40 Seiten zu 200). */
	maxSeitenEinheiten: number;
	maxSeitenProjekte: number;
	maxSeitenAufgaben: number;
}

export const STANDARD_GRENZEN: Grenzen = {
	anfragen: 40,
	aufbauMaxMs: 30 * 60_000,
	aufbewahrungMs: 24 * 3_600_000,
	gueltigMs: 30 * 60_000,
	// Einheiten mit expand=1 sind groß (rund 33 KB je Einheit): 100 je Seite = 3,3 MB und rund 3 Sekunden.
	maxSeitenAufgaben: 40,
	maxSeitenEinheiten: 80,
	maxSeitenProjekte: 40,
	seiteAufgaben: 200,
	seiteEinheiten: 100,
	seiteProjekte: 200,
	sperreMs: 120_000,
	zeitMs: 20_000,
};

/** Alle Dokumente eines Stands in einer Antwort (statt eines einzelnen Dokuments). */
export const ALLES = "alles";

export const DOKUMENT_MUSTER = /^(alles|meta\/stand|meta\/projekte|wochen\/\d{4}-KW\d{2}|pruefung\/teil-\d{2})$/;

export const dashboardDatenInput = {
	dokument: z
		.string()
		.regex(DOKUMENT_MUSTER)
		.describe('Welches Dokument: "alles" (alle Dokumente des Stands in einer Antwort), "meta/stand" (bei Einzelabrufen zuerst – nennt die Wochen und Prüfungs-Teile), "meta/projekte", "wochen/<JJJJ-KWnn>" (z. B. wochen/2026-KW46) oder "pruefung/teil-<nn>" (z. B. pruefung/teil-01)'),
	tage: z.number().int().min(1).max(STANDARD_TAGE).optional().describe(`Fenster in Tagen zurück ab jetzt (Standard ${STANDARD_TAGE}, höchstens ${STANDARD_TAGE})`),
	broker_ids: z.array(id).min(1).max(5).optional().describe(`Propstack-Nutzer, deren Aufgaben als Prüfaufgaben zählen (Standard [${STANDARD_BROKER_IDS.join(", ")}])`),
	stand: z
		.string()
		.max(40)
		.optional()
		.describe('Wert "aktualisiert" aus meta/stand bzw. "stand" aus der Antwort auf "alles". Dann kommt die Antwort genau aus diesem Stand (bis 24 Stunden lang) – oder ein Fehler, wenn es ihn nicht mehr gibt. Bei Einzelabrufen für alle Abrufe nach meta/stand angeben, damit alles aus demselben Stand stammt.'),
};

export type DashboardClient = Pick<PropstackClient, "listUnitsExpanded" | "listProjectsPage" | "listActivities" | "requestsUsed">;

export interface DashboardDeps {
	client: DashboardClient;
	store: DashboardStore | undefined;
	user: { email: string };
	now?: () => number;
	/** Für Tests: kleinere Seiten und Budgets. */
	grenzen?: Partial<Grenzen>;
	sleep?: (ms: number) => Promise<void>;
}

type Eingabe = z.infer<z.ZodObject<typeof dashboardDatenInput>>;

const PHASEN_TEXT: Record<Phase, string> = {
	aufgaben: "Aufgaben der Prüfer",
	einheiten: "neue Einheiten im Fenster",
	erste_einheit: "Anlagedatum je Projekt",
	projekte: "Projektliste",
};

function neueId(): string {
	return Array.from(crypto.getRandomValues(new Uint8Array(9)), (byte) => byte.toString(36).padStart(2, "0")).join("");
}

const iso = (ms: number) => new Date(ms).toISOString();

/** Lesende Anfrage mit einem zweiten Versuch bei Serverfehler oder Netzproblem (GET ist gefahrlos wiederholbar; 429 behandelt der Client selbst). */
async function lesen<T>(deps: DashboardDeps, anfrage: () => Promise<T>): Promise<T> {
	try {
		return await anfrage();
	} catch (error) {
		const wiederholbar = error instanceof PropstackError && (error.status >= 500 || (error.status === 0 && error.message.startsWith("Propstack nicht erreichbar")));
		if (!wiederholbar) throw error;
		await (deps.sleep ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))))(1000);
		return anfrage();
	}
}

function fortschritt(stand: Pick<Stand, "phase" | "cursor" | "broker_ids">): string {
	const { cursor } = stand;
	switch (stand.phase) {
		case "einheiten":
			return `Einheiten: ${cursor.seite - 1} Seite(n) gelesen`;
		case "projekte":
			return `Projektliste: ${cursor.seite - 1} Seite(n) gelesen, ${cursor.projektIds.length} Projekte gesucht`;
		case "erste_einheit":
			return `Anlagedatum: ${cursor.naechstesProjekt} von ${cursor.projektIds.length} Projekten`;
		case "aufgaben":
			return `Aufgaben: Nutzer ${cursor.brokerIndex + 1} von ${stand.broker_ids.length}, ${cursor.seite - 1} Seite(n) gelesen`;
	}
}

function nochNichtFertig(stand: Pick<Stand, "phase" | "cursor" | "broker_ids" | "anfragen" | "until_iso">, hinweis?: string): ToolOutput {
	return {
		count: 0,
		result: {
			fortsetzen: true,
			stand_von: stand.until_iso,
			phase: PHASEN_TEXT[stand.phase],
			fortschritt: fortschritt(stand),
			anfragen_bisher: stand.anfragen,
			hinweis: hinweis ?? "Der Stand wird aufgebaut. Denselben Aufruf wiederholen, bis das Dokument kommt – nacheinander, nicht parallel.",
		},
	};
}

/**
 * Alle Dokumente eines fertigen Stands in einer Antwort: {"stand": <aktualisiert>, "dokumente": {"meta/stand": …, …}}.
 * Für Abläufe, die die Dokumente als Datei weiterverarbeiten: Die Antwort ist zu groß für ein Gespräch, eine
 * Claude-Sitzung legt sie deshalb als Datei ab – so läuft kein Dokument durch das Sprachmodell.
 * Reihenfolge der Schlüssel: meta/stand, meta/projekte, dann Wochen und Teile so, wie meta/stand sie nennt.
 * Die Werte sind dieselben wie bei den Einzelabrufen (gleiche gespeicherte Dokumente).
 */
async function allesAus(store: DashboardStore, stand: Stand): Promise<ToolOutput> {
	const zeilen = new Map((await store.dokumente(stand.id)).map((zeile) => [zeile.name, zeile.inhalt]));
	const meta = zeilen.get("meta/stand");
	const inhalt = meta ? (JSON.parse(meta) as { wochen?: string[]; pruefung_teile?: string[] }) : {};
	const namen = ["meta/stand", "meta/projekte", ...(inhalt.wochen ?? []).map((woche) => `wochen/${woche}`), ...(inhalt.pruefung_teile ?? []).map((teil) => `pruefung/${teil}`)];
	// Genau die Dokumente, die meta/stand nennt – lieber ein Fehler als ein unbemerkt unvollständiger Stand.
	const fehlt = namen.filter((name) => !zeilen.has(name));
	const zuviel = [...zeilen.keys()].filter((name) => !namen.includes(name));
	if (fehlt.length || zuviel.length) {
		throw new PropstackError(
			`Der Stand ${stand.until_iso} ist nicht vollständig gespeichert (es fehlt: ${fehlt.join(", ") || "nichts"}; nicht in meta/stand genannt: ${zuviel.join(", ") || "nichts"}). Bitte melden – ein Abruf ohne stand baut nach 30 Minuten einen neuen Stand auf.`,
			0,
		);
	}
	const dokumente: Record<string, unknown> = {};
	for (const name of namen) dokumente[name] = JSON.parse(zeilen.get(name) as string);
	return { count: namen.length, result: { stand: stand.until_iso, dokumente } };
}

async function dokumentAus(store: DashboardStore, stand: Stand, name: string): Promise<ToolOutput> {
	if (name === ALLES) return allesAus(store, stand);
	const zeile = await store.dokument(stand.id, name);
	if (zeile) return { count: 1, result: JSON.parse(zeile.inhalt) };
	const meta = await store.dokument(stand.id, "meta/stand");
	const inhalt = meta ? (JSON.parse(meta.inhalt) as { wochen?: string[]; pruefung_teile?: string[] }) : {};
	const wochen = (inhalt.wochen ?? []).map((woche) => `wochen/${woche}`);
	const teile = (inhalt.pruefung_teile ?? []).map((teil) => `pruefung/${teil}`);
	throw new PropstackError(
		`Das Dokument ${name} gibt es im Stand ${stand.until_iso} nicht. Vorhanden: ${["meta/stand", "meta/projekte", ...wochen, ...teile].join(", ")}.`,
		404,
	);
}

function neuerStand(params: string, tage: number, brokerIds: number[], jetzt: number, email: string): Stand {
	const until = berlinZeit(jetzt);
	const since = minusTage(until, tage);
	return {
		anfragen: 0,
		aufrufe: 0,
		broker_ids: brokerIds,
		cursor: { brokerIndex: 0, naechstesProjekt: 0, projektIds: [], seite: 1 },
		fehler: null,
		id: neueId(),
		params,
		phase: "einheiten",
		ready_ts: null,
		since_iso: since.iso,
		since_ms: since.ms,
		sperre_bis: null,
		started_ts: iso(jetzt),
		status: "aufbau",
		tage,
		until_iso: until.iso,
		until_ms: until.ms,
		updated_ts: iso(jetzt),
		user_email: email,
	};
}

export async function dashboardDaten(deps: DashboardDeps, input: Eingabe): Promise<ToolOutput> {
	const { store } = deps;
	if (!store) throw new PropstackError("Der Zwischenspeicher für das Dashboard ist nicht verfügbar.", 0);
	const now = deps.now ?? Date.now;
	const grenzen = { ...STANDARD_GRENZEN, ...deps.grenzen };
	const tage = input.tage ?? STANDARD_TAGE;
	const brokerIds = [...new Set(input.broker_ids ?? STANDARD_BROKER_IDS)];
	const params = `${tage}|${brokerIds.join(",")}`;

	// Fest auf einen Stand bezogen: nur lesen, nie neu aufbauen. Ein leerer Wert zählt wie „nicht angegeben“.
	const gewuenscht = input.stand?.trim();
	if (gewuenscht) {
		const fest = await store.fertiger(params, gewuenscht);
		if (!fest) {
			throw new PropstackError(
				`Den Stand ${gewuenscht} gibt es für diese Parameter nicht (mehr). Neu beginnen: ohne den Parameter stand abrufen (meta/stand bzw. alles) und danach alle Dokumente neu holen.`,
				404,
			);
		}
		return dokumentAus(store, fest, input.dokument);
	}

	const jetzt = now();
	const frisch = (s: Stand): boolean => s.status === "fertig" && !!s.ready_ts && jetzt - Date.parse(s.ready_ts) <= grenzen.gueltigMs;
	let stand = await store.neuester(params);
	if (stand && frisch(stand)) return dokumentAus(store, stand, input.dokument);

	const laeuft = stand?.status === "aufbau" && jetzt - Date.parse(stand.started_ts) <= grenzen.aufbauMaxMs;
	if (!stand || !laeuft) {
		if (stand?.status === "aufbau") await store.verwerfen(stand.id, "Aufbau nicht abgeschlossen – verworfen und neu begonnen", iso(jetzt));
		await store.aufraeumen(iso(jetzt - grenzen.aufbewahrungMs));
		// Beginnen zwei Aufrufe gleichzeitig, legt nur einer den Stand an (je Parametersatz höchstens einer im Aufbau) –
		// beide lesen danach denselben.
		await store.anlegen(neuerStand(params, tage, brokerIds, jetzt, deps.user.email));
		stand = await store.neuester(params);
		if (!stand) throw new PropstackError("Der Zwischenspeicher für das Dashboard hat den neuen Stand nicht angenommen.", 0);
	}

	if (stand.status === "aufbau" && (await store.sperren(stand.id, iso(jetzt + grenzen.sperreMs), iso(jetzt)))) {
		// Mit der Sperre in der Hand den Stand frisch lesen: Der Fortschritt eines Aufrufs, der eben erst fertig wurde, zählt.
		const aktuell = await store.stand(stand.id);
		if (aktuell?.status === "aufbau") {
			const fertig = await baueWeiter(deps, grenzen, aktuell);
			return fertig ? dokumentAus(store, aktuell, input.dokument) : nochNichtFertig(aktuell);
		}
	}
	// Keine Sperre bekommen: Ein anderer Aufruf baut gerade – oder er ist in diesem Augenblick fertig geworden.
	const aktuell = (await store.stand(stand.id)) ?? stand;
	if (frisch(aktuell)) return dokumentAus(store, aktuell, input.dokument);
	return nochNichtFertig(aktuell, "Ein anderer Aufruf baut diesen Stand gerade auf. In einigen Sekunden denselben Aufruf wiederholen – nacheinander, nicht parallel.");
}

/**
 * Baut am Stand weiter, bis er fertig ist oder das Budget dieses Aufrufs (Anfragen, Zeit) verbraucht ist.
 * Der Fortschritt wird auch im Fehlerfall gesichert; `stand` wird dabei fortgeschrieben.
 */
async function baueWeiter(deps: DashboardDeps, grenzen: Grenzen, stand: Stand): Promise<boolean> {
	const { client } = deps;
	const store = deps.store as DashboardStore;
	const now = deps.now ?? Date.now;
	const beginn = now();
	const anfragenVorher = stand.anfragen - client.requestsUsed;
	const since = { iso: stand.since_iso, ms: stand.since_ms };
	const until = { iso: stand.until_iso, ms: stand.until_ms };
	const cursor: Cursor = stand.cursor;
	const darfWeiter = () => client.requestsUsed < grenzen.anfragen && now() - beginn < grenzen.zeitMs;
	const sichern = async () => {
		stand.anfragen = anfragenVorher + client.requestsUsed;
		await store.aktualisieren(stand.id, { anfragen: stand.anfragen, cursor, phase: stand.phase, sperre_bis: null, updated_ts: iso(now()) });
	};
	const abbruch = (text: string) => new PropstackError(`${text} Der Abruf wurde abgebrochen, weil das Ergebnis unvollständig wäre.`, 0);

	/** Eine Liste seitenweise lesen wie _paginate(): bis eine Seite leer oder kürzer als die Seitengröße ist. true = Liste zu Ende. */
	const blaettern = async (holen: (seite: number) => Promise<Page>, groesse: number, maxSeiten: number, was: string, ablegen: (zeilen: Raw[], seite: number) => Promise<void>): Promise<boolean> => {
		while (darfWeiter()) {
			if (cursor.seite > maxSeiten) throw abbruch(`${was}: mehr als ${maxSeiten} Seiten zu ${groesse}.`);
			const seite = cursor.seite;
			const zeilen = mitId((await lesen(deps, () => holen(seite))).rows);
			if (zeilen.length) await ablegen(zeilen, seite);
			cursor.seite = seite + 1;
			if (zeilen.length < groesse) return true;
		}
		return false;
	};

	// erste_einheit: Ergebnisse dieses Aufrufs gesammelt ablegen – auch wenn mittendrin ein Fehler kommt.
	// Je Projekt ein eigener Eintrag (Schlüssel = Position in der Projektliste): wiederholtes Ablegen überschreibt nur Gleiches.
	let beginnTeil: TeilEintrag[] = [];
	const beginnAblegen = async () => {
		const eintraege = beginnTeil;
		beginnTeil = [];
		await store.teileSpeichern(stand.id, "erste_einheit", eintraege);
	};

	try {
		if (stand.phase === "einheiten") {
			// created_at_from/to wirken nur tagesgenau und mit unklarer Zeitzone: Serverfenster um je einen Tag weiten,
			// der exakte Schnitt fällt hier. expand=1 ist zwingend, sonst ist created_at leer.
			const filter: Query = { created_at_from: berlinTag(since, -1), created_at_to: berlinTag(until, 1) };
			const zuEnde = await blaettern(
				(seite) => client.listUnitsExpanded({ ...filter, page: seite, per: grenzen.seiteEinheiten }),
				grenzen.seiteEinheiten,
				grenzen.maxSeitenEinheiten,
				"Einheiten im Fenster",
				async (zeilen, seite) => {
					const imBericht = zeilen.map(zuEinheit).filter((einheit) => imFenster(einheit, since, until));
					if (imBericht.length) await store.teileSpeichern(stand.id, "einheiten", [{ daten: imBericht, seq: seite }]);
				},
			);
			if (!zuEnde) return await sichern().then(() => false);
			const einheiten = (await store.teile(stand.id, "einheiten")).flat() as Einheit[];
			cursor.projektIds = [...new Set(einheiten.map((einheit) => einheit.project_id).filter((pid): pid is number => Boolean(pid)))].sort((a, b) => a - b);
			cursor.seite = 1;
			// Ohne Projekte braucht es weder die Projektliste noch Anlagedaten.
			stand.phase = cursor.projektIds.length ? "projekte" : "aufgaben";
		}

		if (stand.phase === "projekte") {
			// Projektliste komplett lesen (der Einheiten-Payload nennt den Projekttitel nicht) und nur die gesuchten behalten.
			const gesucht = new Set(cursor.projektIds);
			const zuEnde = await blaettern(
				(seite) => client.listProjectsPage({ page: seite, per: grenzen.seiteProjekte }),
				grenzen.seiteProjekte,
				grenzen.maxSeitenProjekte,
				"Projektliste",
				async (zeilen, seite) => {
					const treffer = zeilen.filter((zeile) => gesucht.has(Number(zeile.id))).map((zeile): [number, string] => [Number(zeile.id), projektTitel(zeile)]);
					if (treffer.length) await store.teileSpeichern(stand.id, "projekte", [{ daten: treffer, seq: seite }]);
				},
			);
			if (!zuEnde) return await sichern().then(() => false);
			cursor.seite = 1;
			cursor.naechstesProjekt = 0;
			stand.phase = "erste_einheit";
		}

		if (stand.phase === "erste_einheit") {
			// Propstack führt für Projekte keinen Zeitstempel: Anlagedatum = früheste Einheit des Projekts.
			while (cursor.naechstesProjekt < cursor.projektIds.length) {
				if (!darfWeiter()) {
					await beginnAblegen();
					return await sichern().then(() => false);
				}
				const pid = cursor.projektIds[cursor.naechstesProjekt];
				const zeilen = mitId((await lesen(deps, () => client.listUnitsExpanded({ order: "asc", per: 1, project_id: pid, sort_by: "created_at" }))).rows);
				beginnTeil.push({ daten: [pid, zeilen.length ? zuEinheit(zeilen[0]).created_at : null], seq: cursor.naechstesProjekt });
				cursor.naechstesProjekt += 1;
			}
			await beginnAblegen();
			cursor.seite = 1;
			cursor.brokerIndex = 0;
			stand.phase = "aufgaben";
		}

		if (stand.phase === "aufgaben") {
			// updated_at_from wird vom Server ignoriert – also alle Aufgaben des Nutzers lesen, gefiltert wird beim Bauen.
			while (cursor.brokerIndex < stand.broker_ids.length) {
				const brokerIndex = cursor.brokerIndex;
				const zuEnde = await blaettern(
					(seite) => client.listActivities({ broker_id: stand.broker_ids[brokerIndex], item_type: "reminder", order: "desc", page: seite, per: grenzen.seiteAufgaben, sort_by: "updated_at" }),
					grenzen.seiteAufgaben,
					grenzen.maxSeitenAufgaben,
					`Aufgaben des Nutzers ${stand.broker_ids[brokerIndex]}`,
					(zeilen, seite) => store.teileSpeichern(stand.id, "aufgaben", [{ daten: zeilen.map(zuAufgabe), seq: brokerIndex * 1000 + seite }]),
				);
				if (!zuEnde) return await sichern().then(() => false);
				cursor.brokerIndex += 1;
				cursor.seite = 1;
			}
		}

		await fertigstellen(store, stand, anfragenVorher + client.requestsUsed, since, until, now);
		return true;
	} catch (error) {
		// Fortschritt sichern und die Sperre lösen, damit der nächste Aufruf dort weitermacht.
		try {
			await beginnAblegen();
			await sichern();
		} catch (speicherFehler) {
			console.error("dashboard_daten: Fortschritt nicht gesichert", speicherFehler);
		}
		// Als fehlgeschlagen markierter Stand (Dokument zu groß): Der nächste Aufruf beginnt neu, hier gibt es nichts fortzusetzen.
		if (error instanceof PropstackError && stand.status !== "fehler") {
			throw new PropstackError(`${error.message} – Der Aufbau des Stands ist bis hierher gespeichert (${PHASEN_TEXT[stand.phase]}); ein erneuter Aufruf macht dort weiter.`, error.status);
		}
		throw error;
	}
}

async function fertigstellen(store: DashboardStore, stand: Stand, anfragen: number, since: { iso: string; ms: number }, until: { iso: string; ms: number }, now: () => number): Promise<void> {
	const einheiten = neuesteZuerst(ohneDoppelte((await store.teile(stand.id, "einheiten")).flat() as Einheit[]));
	const titel = new Map<number, string>((await store.teile(stand.id, "projekte")).flat() as [number, string][]);
	const projektBeginn = new Map<number, string | null>((await store.teile(stand.id, "erste_einheit")) as [number, string | null][]);
	const aufgaben = ohneDoppelte((await store.teile(stand.id, "aufgaben")).flat() as Aufgabe[]);

	let dokumente: ReturnType<typeof serialisiere>;
	try {
		dokumente = serialisiere(baueDokumente({ aufgaben, brokerIds: stand.broker_ids, einheiten, projektBeginn, projektTitel: titel, since, tage: stand.tage, until }));
	} catch (error) {
		const text = `Ein Dokument ist größer als die Grenze der Dashboard-Datenbank (${(error as Error).message}).`;
		await store.verwerfen(stand.id, text, iso(now()));
		stand.status = "fehler";
		throw new PropstackError(text, 0);
	}
	stand.anfragen = anfragen;
	await store.aktualisieren(stand.id, { anfragen, cursor: stand.cursor, phase: stand.phase, updated_ts: iso(now()) });
	// Wirkt nur, solange der Stand im Aufbau ist: Hat ein anderer Aufruf ihn schon fertiggestellt, bleiben dessen Dokumente.
	await store.fertigstellen(stand.id, dokumente, iso(now()));
	stand.status = "fertig";
}
