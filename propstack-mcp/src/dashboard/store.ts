// Zwischenspeicher für das Dashboard (D1, Tabellen aus migrations/0004_dashboard_cache.sql).
// Als Interface, damit der Ablauf ohne D1 testbar ist – wie beim Speicher für Massenänderungen.
//
// Der Speicher sichert drei Dinge ab, die bei gleichzeitigen Aufrufen sonst schiefgehen könnten:
//   1. Je Parametersatz gibt es höchstens einen Stand im Aufbau (eindeutiger Index) – zwei gleichzeitige
//      Aufrufe bauen nie zwei Stände nebeneinander.
//   2. Die Sperre bekommt nur ein Aufruf zur selben Zeit, und nur für einen Stand im Aufbau.
//   3. Fertigstellen wirkt nur, solange der Stand im Aufbau ist. Wer zu spät kommt (z. B. ein hängender Aufruf,
//      dessen Sperre abgelaufen war), überschreibt die fertigen Dokumente nicht.

export type Phase = "einheiten" | "projekte" | "erste_einheit" | "aufgaben";
export type StandStatus = "aufbau" | "fertig" | "fehler";
export type TeilArt = "einheiten" | "projekte" | "erste_einheit" | "aufgaben";

export interface Cursor {
	/** Nächste Seite der laufenden Phase (ab 1). */
	seite: number;
	/** Projekt-IDs der Einheiten im Fenster, aufsteigend – steht nach der Phase „einheiten“ fest. */
	projektIds: number[];
	/** Index des nächsten Projekts in der Phase „erste_einheit“. */
	naechstesProjekt: number;
	/** Index des laufenden Nutzers in der Phase „aufgaben“. */
	brokerIndex: number;
}

export interface Stand {
	id: string;
	/** Parametersatz, z. B. "91|254958". */
	params: string;
	status: StandStatus;
	started_ts: string;
	updated_ts: string;
	ready_ts: string | null;
	until_iso: string;
	until_ms: number;
	since_iso: string;
	since_ms: number;
	tage: number;
	broker_ids: number[];
	phase: Phase;
	cursor: Cursor;
	/** Propstack-Anfragen bisher. */
	anfragen: number;
	/** Tool-Aufrufe, die an diesem Stand gebaut haben. */
	aufrufe: number;
	/** Solange ein Aufruf baut (UTC), bauen andere nicht mit. */
	sperre_bis: string | null;
	fehler: string | null;
	user_email: string;
}

/** Was ein bauender Aufruf fortschreiben darf – der Status gehört nicht dazu (dafür: fertigstellen, verwerfen). */
export type Fortschritt = Partial<Pick<Stand, "phase" | "cursor" | "anfragen" | "sperre_bis" | "updated_ts">>;

export interface DokumentZeile {
	name: string;
	inhalt: string;
	bytes: number;
}

export interface TeilEintrag {
	seq: number;
	daten: unknown;
}

export interface DashboardStore {
	/** Jüngster Stand zu diesem Parametersatz. */
	neuester(params: string): Promise<Stand | null>;
	/** Fertiger Stand mit genau diesem Zeitpunkt („aktualisiert“ aus meta/stand). */
	fertiger(params: string, untilIso: string): Promise<Stand | null>;
	stand(id: string): Promise<Stand | null>;
	/** Legt den Stand an – außer zu diesen Parametern ist schon einer im Aufbau (dann geschieht nichts). */
	anlegen(stand: Stand): Promise<void>;
	aktualisieren(id: string, felder: Fortschritt): Promise<void>;
	/** Nimmt die Sperre, wenn der Stand im Aufbau und die Sperre frei oder abgelaufen ist. */
	sperren(id: string, bis: string, jetzt: string): Promise<boolean>;
	/** Markiert einen Stand im Aufbau als fehlgeschlagen; ein fertiger Stand bleibt fertig. */
	verwerfen(id: string, grund: string, ts: string): Promise<void>;
	/** Rohdaten ablegen; derselbe Schlüssel (Art, seq) wird überschrieben – wiederholtes Ablegen schadet nicht. */
	teileSpeichern(standId: string, art: TeilArt, eintraege: TeilEintrag[]): Promise<void>;
	teile(standId: string, art: TeilArt): Promise<unknown[]>;
	/** Nur solange der Stand im Aufbau ist: Dokumente ablegen und als fertig markieren. Rohdaten werden in jedem Fall entfernt. */
	fertigstellen(standId: string, dokumente: DokumentZeile[], readyTs: string): Promise<void>;
	dokument(standId: string, name: string): Promise<DokumentZeile | null>;
	dokumente(standId: string): Promise<DokumentZeile[]>;
	/** Stände, die vor diesem Zeitpunkt begonnen wurden, samt Rohdaten und Dokumenten löschen. */
	aufraeumen(vorTs: string): Promise<void>;
}

type Raw = Record<string, unknown>;

const JSON_SPALTEN = new Set(["broker_ids", "cursor"]);
const FORTSCHRITT_SPALTEN = new Set(["phase", "cursor", "anfragen", "sperre_bis", "updated_ts"]);

function zuZeile(felder: Raw): Raw {
	return Object.fromEntries(Object.entries(felder).map(([k, v]) => [k, JSON_SPALTEN.has(k) && v !== null && v !== undefined ? JSON.stringify(v) : v]));
}

function ausZeile(zeile: Raw | null): Stand | null {
	if (!zeile) return null;
	return Object.fromEntries(Object.entries(zeile).map(([k, v]) => [k, JSON_SPALTEN.has(k) && typeof v === "string" ? JSON.parse(v) : v])) as unknown as Stand;
}

const IM_AUFBAU = "EXISTS (SELECT 1 FROM dashboard_stand WHERE id = ? AND status = 'aufbau')";

export class D1DashboardStore implements DashboardStore {
	constructor(private readonly db: D1Database) {}

	async neuester(params: string) {
		// rowid: bei gleichem Zeitstempel gewinnt der zuletzt angelegte
		return ausZeile(await this.db.prepare("SELECT * FROM dashboard_stand WHERE params = ? ORDER BY started_ts DESC, rowid DESC LIMIT 1").bind(params).first<Raw>());
	}

	async fertiger(params: string, untilIso: string) {
		return ausZeile(
			await this.db
				.prepare("SELECT * FROM dashboard_stand WHERE params = ? AND until_iso = ? AND status = 'fertig' ORDER BY started_ts DESC, rowid DESC LIMIT 1")
				.bind(params, untilIso)
				.first<Raw>(),
		);
	}

	async stand(id: string) {
		return ausZeile(await this.db.prepare("SELECT * FROM dashboard_stand WHERE id = ?").bind(id).first<Raw>());
	}

	async anlegen(stand: Stand) {
		const z = zuZeile(stand as unknown as Raw);
		// OR IGNORE: Der eindeutige Index idx_dashboard_stand_aufbau lässt je Parametersatz nur einen Stand im Aufbau zu.
		await this.db
			.prepare(
				"INSERT OR IGNORE INTO dashboard_stand (id, params, status, started_ts, updated_ts, ready_ts, until_iso, until_ms, since_iso, since_ms, tage, broker_ids, phase, cursor, anfragen, aufrufe, sperre_bis, fehler, user_email) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
			)
			.bind(z.id, z.params, z.status, z.started_ts, z.updated_ts, z.ready_ts, z.until_iso, z.until_ms, z.since_iso, z.since_ms, z.tage, z.broker_ids, z.phase, z.cursor, z.anfragen, z.aufrufe, z.sperre_bis, z.fehler, z.user_email)
			.run();
	}

	async aktualisieren(id: string, felder: Fortschritt) {
		const eintraege = Object.entries(zuZeile(felder as Raw)).filter(([k, v]) => FORTSCHRITT_SPALTEN.has(k) && v !== undefined);
		if (!eintraege.length) return;
		await this.db
			.prepare(`UPDATE dashboard_stand SET ${eintraege.map(([k]) => `${k} = ?`).join(", ")} WHERE id = ?`)
			.bind(...eintraege.map(([, v]) => v), id)
			.run();
	}

	async sperren(id: string, bis: string, jetzt: string) {
		const ergebnis = await this.db
			.prepare("UPDATE dashboard_stand SET sperre_bis = ?, aufrufe = aufrufe + 1 WHERE id = ? AND status = 'aufbau' AND (sperre_bis IS NULL OR sperre_bis < ?)")
			.bind(bis, id, jetzt)
			.run();
		return (ergebnis.meta?.changes ?? 0) === 1;
	}

	async verwerfen(id: string, grund: string, ts: string) {
		await this.db.prepare("UPDATE dashboard_stand SET status = 'fehler', fehler = ?, sperre_bis = NULL, updated_ts = ? WHERE id = ? AND status = 'aufbau'").bind(grund, ts, id).run();
	}

	async teileSpeichern(standId: string, art: TeilArt, eintraege: TeilEintrag[]) {
		if (!eintraege.length) return;
		const befehle = eintraege.map((eintrag) =>
			this.db.prepare("INSERT OR REPLACE INTO dashboard_teil (stand_id, art, seq, daten) VALUES (?, ?, ?, ?)").bind(standId, art, eintrag.seq, JSON.stringify(eintrag.daten)),
		);
		if (befehle.length === 1) await befehle[0].run();
		else await this.db.batch(befehle);
	}

	async teile(standId: string, art: TeilArt) {
		const ergebnis = await this.db.prepare("SELECT daten FROM dashboard_teil WHERE stand_id = ? AND art = ? ORDER BY seq").bind(standId, art).all<{ daten: string }>();
		return (ergebnis.results ?? []).map((zeile) => JSON.parse(zeile.daten) as unknown);
	}

	async fertigstellen(standId: string, dokumente: DokumentZeile[], readyTs: string) {
		// Ein Stapel = eine Transaktion. Die Dokumente entstehen nur, solange der Stand im Aufbau ist; erst danach kippt der Status.
		await this.db.batch([
			...dokumente.map((d) =>
				this.db.prepare(`INSERT OR REPLACE INTO dashboard_dokument (stand_id, name, inhalt, bytes) SELECT ?, ?, ?, ? WHERE ${IM_AUFBAU}`).bind(standId, d.name, d.inhalt, d.bytes, standId),
			),
			this.db.prepare("UPDATE dashboard_stand SET status = 'fertig', ready_ts = ?, updated_ts = ?, sperre_bis = NULL, fehler = NULL WHERE id = ? AND status = 'aufbau'").bind(readyTs, readyTs, standId),
			this.db.prepare("DELETE FROM dashboard_teil WHERE stand_id = ?").bind(standId),
		]);
	}

	async dokument(standId: string, name: string) {
		return await this.db.prepare("SELECT name, inhalt, bytes FROM dashboard_dokument WHERE stand_id = ? AND name = ?").bind(standId, name).first<DokumentZeile>();
	}

	async dokumente(standId: string) {
		const ergebnis = await this.db.prepare("SELECT name, inhalt, bytes FROM dashboard_dokument WHERE stand_id = ? ORDER BY name").bind(standId).all<DokumentZeile>();
		return ergebnis.results ?? [];
	}

	async aufraeumen(vorTs: string) {
		await this.db.batch([
			this.db.prepare("DELETE FROM dashboard_teil WHERE stand_id IN (SELECT id FROM dashboard_stand WHERE started_ts < ?)").bind(vorTs),
			this.db.prepare("DELETE FROM dashboard_dokument WHERE stand_id IN (SELECT id FROM dashboard_stand WHERE started_ts < ?)").bind(vorTs),
			this.db.prepare("DELETE FROM dashboard_stand WHERE started_ts < ?").bind(vorTs),
		]);
	}
}

/** Löschfrist für den Zwischenspeicher (täglicher Cron): Stände, die vor dem Stichtag begonnen wurden. */
export async function purgeOldDashboardStands(db: D1Database | undefined, cutoffIso: string): Promise<number> {
	if (!db) return 0;
	try {
		const vorher = await db.prepare("SELECT COUNT(*) AS n FROM dashboard_stand WHERE started_ts < ?").bind(cutoffIso).first<{ n: number }>();
		await new D1DashboardStore(db).aufraeumen(cutoffIso);
		return vorher?.n ?? 0;
	} catch (error) {
		console.error("Dashboard-Zwischenspeicher: Löschfrist fehlgeschlagen", error);
		return 0;
	}
}

/** Speicher im Arbeitsspeicher – für Tests. Verhält sich wie die D1-Variante (geprüft in dashboard-store.test.ts). */
export class MemoryDashboardStore implements DashboardStore {
	staende: Stand[] = [];
	teilZeilen: { standId: string; art: TeilArt; seq: number; daten: string }[] = [];
	dokumentZeilen: (DokumentZeile & { standId: string })[] = [];

	private juengster(passend: Stand[]): Stand | null {
		// wie ORDER BY started_ts DESC, rowid DESC: bei gleichem Zeitstempel der zuletzt angelegte
		let bester: Stand | null = null;
		for (const stand of passend) if (!bester || stand.started_ts >= bester.started_ts) bester = stand;
		return bester ? structuredClone(bester) : null;
	}
	async neuester(params: string) {
		return this.juengster(this.staende.filter((s) => s.params === params));
	}
	async fertiger(params: string, untilIso: string) {
		return this.juengster(this.staende.filter((s) => s.params === params && s.until_iso === untilIso && s.status === "fertig"));
	}
	async stand(id: string) {
		const s = this.staende.find((x) => x.id === id);
		return s ? structuredClone(s) : null;
	}
	async anlegen(stand: Stand) {
		if (stand.status === "aufbau" && this.staende.some((s) => s.params === stand.params && s.status === "aufbau")) return;
		this.staende.push(structuredClone(stand));
	}
	async aktualisieren(id: string, felder: Fortschritt) {
		const s = this.staende.find((x) => x.id === id);
		if (!s) return;
		for (const [k, v] of Object.entries(felder)) if (FORTSCHRITT_SPALTEN.has(k) && v !== undefined) (s as unknown as Raw)[k] = structuredClone(v);
	}
	async sperren(id: string, bis: string, jetzt: string) {
		const s = this.staende.find((x) => x.id === id);
		if (!s || s.status !== "aufbau" || (s.sperre_bis !== null && s.sperre_bis >= jetzt)) return false;
		s.sperre_bis = bis;
		s.aufrufe += 1;
		return true;
	}
	async verwerfen(id: string, grund: string, ts: string) {
		const s = this.staende.find((x) => x.id === id);
		if (s?.status === "aufbau") Object.assign(s, { fehler: grund, sperre_bis: null, status: "fehler", updated_ts: ts });
	}
	async teileSpeichern(standId: string, art: TeilArt, eintraege: TeilEintrag[]) {
		for (const { seq, daten } of eintraege) {
			this.teilZeilen = this.teilZeilen.filter((t) => !(t.standId === standId && t.art === art && t.seq === seq));
			this.teilZeilen.push({ art, daten: JSON.stringify(daten), seq, standId });
		}
	}
	async teile(standId: string, art: TeilArt) {
		return this.teilZeilen
			.filter((t) => t.standId === standId && t.art === art)
			.sort((a, b) => a.seq - b.seq)
			.map((t) => JSON.parse(t.daten) as unknown);
	}
	async fertigstellen(standId: string, dokumente: DokumentZeile[], readyTs: string) {
		const s = this.staende.find((x) => x.id === standId);
		if (s?.status === "aufbau") {
			this.dokumentZeilen = this.dokumentZeilen.filter((d) => d.standId !== standId);
			this.dokumentZeilen.push(...dokumente.map((d) => ({ ...d, standId })));
			Object.assign(s, { fehler: null, ready_ts: readyTs, sperre_bis: null, status: "fertig", updated_ts: readyTs });
		}
		this.teilZeilen = this.teilZeilen.filter((t) => t.standId !== standId);
	}
	async dokument(standId: string, name: string) {
		const d = this.dokumentZeilen.find((x) => x.standId === standId && x.name === name);
		return d ? { bytes: d.bytes, inhalt: d.inhalt, name: d.name } : null;
	}
	async dokumente(standId: string) {
		return this.dokumentZeilen
			.filter((d) => d.standId === standId)
			.sort((a, b) => (a.name < b.name ? -1 : 1))
			.map((d) => ({ bytes: d.bytes, inhalt: d.inhalt, name: d.name }));
	}
	async aufraeumen(vorTs: string) {
		const alt = new Set(this.staende.filter((s) => s.started_ts < vorTs).map((s) => s.id));
		this.staende = this.staende.filter((s) => !alt.has(s.id));
		this.teilZeilen = this.teilZeilen.filter((t) => !alt.has(t.standId));
		this.dokumentZeilen = this.dokumentZeilen.filter((d) => !alt.has(d.standId));
	}
}
