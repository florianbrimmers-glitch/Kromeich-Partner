import { type BerlinZeit, pythonIsoformat, wochenSchluessel, zeitMs } from "./zeit";

// Dokumente für das Propstack-Dashboard (claude.ai-Artifact „Objektanlage & Prüfaufgaben“).
// Portierung von weekly_report/dashboard_export.py und weekly_report/propstack.py – reine Funktionen,
// ohne Netz testbar. Das Dashboard-HTML bleibt unverändert: Feldnamen, Wochenschlüssel, Sortierung
// und die Regel für die „Art“ einer Prüfaufgabe müssen exakt dem bisherigen Export entsprechen.
//
//   meta/stand            Zeitpunkt, Fenster, Zähler, Liste der Wochen und Prüfungs-Teile
//   meta/projekte         alle Projekte, auf die Einheiten im Fenster zeigen, mit Titel und frühester
//                         Einheit (= Anlagedatum, Propstack führt für Projekte keinen Zeitstempel)
//   wochen/<JJJJ-KWnn>    neue Einheiten je ISO-Woche (Berliner Zeit)
//   pruefung/teil-<nn>    Prüfaufgaben: der ganze offene Bestand plus alles, was im Fenster
//                         angelegt oder erledigt wurde – in Paketen zu je AUFGABEN_PRO_TEIL

type Raw = Record<string, unknown>;

export const STANDARD_TAGE = 91; // 13 volle Wochen für den Verlauf
export const MAX_DOKUMENT_BYTES = 256 * 1024; // Grenze der Artifact-Datenbank je Dokument
export const AUFGABEN_PRO_TEIL = 400;

/** Eine im Fenster angelegte Einheit – nur die Felder, die das Dashboard braucht. */
export interface Einheit {
	id: number;
	title: string | null;
	name: string | null;
	address: string | null;
	city: string | null;
	property_space_value: number | null;
	marketing_type: string | null;
	project_id: number | null;
	created_at: string | null;
}

/** Eine Aufgabe aus GET /v1/activities?item_type=reminder. */
export interface Aufgabe {
	id: number;
	title: string | null;
	done: boolean | null;
	original_created_at: string | null;
	updated_at: string | null;
	property_names: string[];
	project_names: string[];
}

// ---------- Propstack-Antworten lesen (wie _to_unit, _to_project, _to_task) ----------

/**
 * Wie _scalar(): Propstack liefert manche Felder als Custom-Field-Objekt {"label": …, "value": …} – auf den
 * reinen Wert reduzieren. Bewusst nicht scalar() aus den Mappern: das bevorzugt pretty_value ("Miete" statt
 * "RENT"), der bisherige Export nimmt immer value.
 */
function scalar(value: unknown): unknown {
	if (value && typeof value === "object" && !Array.isArray(value) && "value" in value) return (value as Raw).value;
	return value;
}

const text = (value: unknown): string | null => {
	const v = scalar(value);
	return typeof v === "string" ? v : null;
};

/** Wie _float(): leer → null; Zahl oder Zahl als Text → Zahl; alles andere (z. B. "7,25") → null. */
export function kommazahl(value: unknown): number | null {
	const v = scalar(value);
	if (v === null || v === undefined || v === "") return null;
	if (typeof v === "number") return Number.isFinite(v) ? v : null;
	if (typeof v === "boolean") return v ? 1 : 0;
	if (typeof v === "string" && /^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$/.test(v)) return Number(v);
	return null;
}

function ganzzahl(value: unknown): number | null {
	const v = scalar(value);
	if (typeof v === "number") return Number.isInteger(v) ? v : null;
	if (typeof v === "string" && /^\s*[+-]?\d+\s*$/.test(v)) return Number(v);
	return null;
}

/** Wie pydantic bool | None im toleranten Modus. */
function wahrheitswert(value: unknown): boolean | null {
	const v = scalar(value);
	if (typeof v === "boolean") return v;
	if (v === 1 || v === 0) return v === 1;
	if (typeof v === "string") {
		const t = v.trim().toLowerCase();
		if (["1", "true", "t", "yes", "y", "on"].includes(t)) return true;
		if (["0", "false", "f", "no", "n", "off"].includes(t)) return false;
	}
	return null;
}

function namen(value: unknown): string[] {
	return Array.isArray(value) ? value.filter(Boolean).map((v) => String(v)) : [];
}

/** Zeilen mit ID – wie _rows(): Einträge ohne id zählen nicht. */
export function mitId(rows: Raw[]): Raw[] {
	return rows.filter((row) => Boolean(row && typeof row === "object" && row.id));
}

export function zuEinheit(raw: Raw): Einheit {
	return {
		address: text(raw.address),
		city: text(raw.city),
		created_at: text(raw.created_at),
		id: Number(raw.id),
		marketing_type: text(raw.marketing_type),
		name: text(raw.name),
		project_id: ganzzahl(raw.project_id),
		property_space_value: kommazahl(raw.property_space_value),
		title: text(raw.title),
	};
}

export function zuAufgabe(raw: Raw): Aufgabe {
	return {
		done: wahrheitswert(raw.done),
		id: Number(raw.id),
		original_created_at: text(raw.original_created_at),
		project_names: namen(raw.project_names),
		property_names: namen(raw.property_names),
		title: text(raw.title),
		updated_at: text(raw.updated_at),
	};
}

/** Anzeigename eines Projekts wie ProjectInfo.label(): Überschrift, sonst Name, sonst Adresse, sonst „Projekt <ID>“. */
export function projektTitel(raw: Raw): string {
	return text(raw.title) || text(raw.name) || text(raw.address) || `Projekt ${Number(raw.id)}`;
}

/** Im Fenster angelegt? Der Serverfilter ist nur tagesgenau – der exakte Schnitt fällt hier (since ≤ angelegt < until). */
export function imFenster(einheit: Einheit, since: BerlinZeit, until: BerlinZeit): boolean {
	if (!einheit.created_at) return false;
	const ms = zeitMs(einheit.created_at);
	return since.ms <= ms && ms < until.ms;
}

/** Neueste zuerst – wie sorted(key=created_at, reverse=True): Textvergleich, Reihenfolge bei Gleichstand bleibt. */
export function neuesteZuerst(einheiten: Einheit[]): Einheit[] {
	return [...einheiten].sort((a, b) => {
		const x = a.created_at ?? "";
		const y = b.created_at ?? "";
		return y > x ? 1 : y < x ? -1 : 0;
	});
}

/** Erstes Vorkommen je ID – schützt vor Dopplern, wenn sich die Liste während des Blätterns verschiebt. */
export function ohneDoppelte<T extends { id: number }>(zeilen: T[]): T[] {
	const gesehen = new Set<number>();
	return zeilen.filter((zeile) => (gesehen.has(zeile.id) ? false : (gesehen.add(zeile.id), true)));
}

// ---------- Dokumente bauen (wie baue_dokumente) ----------

const WORTGRENZE = "[\\p{L}\\p{N}_]";
const PRUEFUNG = new RegExp(`(?<!${WORTGRENZE})Pruefung(?!${WORTGRENZE})`, "gu");
const PRUEFEN = new RegExp(`(?<!${WORTGRENZE})pruefen(?!${WORTGRENZE})`, "gu");

/**
 * Art einer Prüfaufgabe = Titel vor dem ersten Doppelpunkt.
 * Die Automatisierungen benennen ihre Aufgaben nach festem Muster ("Pruefung Panattoni Welle 3: …",
 * "Newsletter-Vermietung prüfen: …"). Die ASCII-Schreibweise aus dem Exposé-Workflow ("Pruefung") wird
 * mit "Prüfung" zusammengeführt, sonst zerfiele eine Art in zwei Gruppen.
 */
export function aufgabenArt(titel: string | null | undefined): string {
	if (!titel || !titel.includes(":")) return "Sonstige";
	const art = titel.slice(0, titel.indexOf(":")).trim().replace(PRUEFUNG, "Prüfung").replace(PRUEFEN, "prüfen");
	return art || "Sonstige";
}

function einheitDokument(u: Einheit) {
	return {
		id: u.id,
		titel: u.title || u.name || u.address || `Einheit ${u.id}`,
		flaeche: u.property_space_value,
		vermarktung: u.marketing_type,
		stadt: u.city,
		projekt_id: u.project_id,
		angelegt: u.created_at,
	};
}

function aufgabeDokument(t: Aufgabe) {
	const bezug = t.property_names.length ? t.property_names : t.project_names;
	return {
		id: t.id,
		titel: (t.title ?? "").trim() || `Aufgabe ${t.id}`,
		art: aufgabenArt(t.title),
		erledigt: t.done === true,
		angelegt: t.original_created_at,
		// Propstack führt kein Abschlussdatum; bei erledigten Aufgaben ist die letzte Änderung der einzige Zeitstempel dafür.
		geaendert: t.updated_at,
		bezug: bezug.length ? bezug[0] : null,
	};
}

/** Offen (zählt immer zum Bestand) oder im Fenster angelegt bzw. erledigt. */
export function relevant(t: Aufgabe, since: BerlinZeit): boolean {
	if (t.done !== true) return true;
	if (t.original_created_at && zeitMs(t.original_created_at) >= since.ms) return true;
	return Boolean(t.updated_at) && zeitMs(t.updated_at as string) >= since.ms;
}

export interface DokumentEingabe {
	/** Einheiten im Fenster, neueste zuerst. */
	einheiten: Einheit[];
	/** Projekt-ID → Anzeigename; fehlt ein Projekt, gibt es das Projekt nicht mehr (404). */
	projektTitel: Map<number, string>;
	/** Projekt-ID → Anlagedatum der frühesten Einheit, so wie Propstack es liefert (oder null). */
	projektBeginn: Map<number, string | null>;
	aufgaben: Aufgabe[];
	since: BerlinZeit;
	until: BerlinZeit;
	tage: number;
	brokerIds: number[];
}

/** Rohdaten → {"sammlung/dokument": Inhalt}. */
export function baueDokumente(eingabe: DokumentEingabe): Record<string, unknown> {
	const { einheiten, since, until } = eingabe;

	const wochen = new Map<string, { woche: string; einheiten: unknown[] }>();
	for (const u of einheiten) {
		if (!u.created_at) continue;
		const key = wochenSchluessel(zeitMs(u.created_at));
		let woche = wochen.get(key);
		if (!woche) wochen.set(key, (woche = { woche: key, einheiten: [] }));
		woche.einheiten.push(einheitDokument(u));
	}

	const projektIds = [...new Set(einheiten.map((u) => u.project_id).filter((pid): pid is number => Boolean(pid)))].sort((a, b) => a - b);
	const projekte: Record<string, unknown> = {};
	for (const pid of projektIds) {
		const beginn = eingabe.projektBeginn.get(pid);
		projekte[String(pid)] = {
			titel: eingabe.projektTitel.get(pid) ?? null,
			// Fehlt der Titel, gibt es das Projekt nicht mehr (GET /projects/:id → 404), die Einheiten zeigen
			// aber noch darauf. Das Dashboard verlinkt es dann nicht.
			vorhanden: eingabe.projektTitel.has(pid),
			erste_einheit: beginn ? pythonIsoformat(beginn) : null,
		};
	}

	const pruefung = eingabe.aufgaben
		.filter((t) => relevant(t, since))
		.map(aufgabeDokument)
		.sort((a, b) => {
			const x = a.angelegt ?? "";
			const y = b.angelegt ?? "";
			return x < y ? -1 : x > y ? 1 : a.id - b.id;
		});
	const teile: (typeof pruefung)[] = [];
	for (let start = 0; start < pruefung.length; start += AUFGABEN_PRO_TEIL) teile.push(pruefung.slice(start, start + AUFGABEN_PRO_TEIL));
	const teilName = (nummer: number) => `teil-${String(nummer).padStart(2, "0")}`;

	const dokumente: Record<string, unknown> = {
		"meta/stand": {
			aktualisiert: until.iso,
			fenster_von: since.iso,
			fenster_bis: until.iso,
			tage: eingabe.tage,
			pruefer_broker_ids: eingabe.brokerIds,
			anzahl_einheiten: einheiten.length,
			anzahl_projekte: projektIds.length,
			anzahl_offen: pruefung.filter((a) => !a.erledigt).length,
			anzahl_aufgaben: pruefung.length,
			wochen: [...wochen.keys()].sort(),
			pruefung_teile: teile.map((_, index) => teilName(index + 1)),
		},
		"meta/projekte": { projekte },
	};
	for (const [key, body] of wochen) dokumente[`wochen/${key}`] = body;
	teile.forEach((teil, index) => {
		dokumente[`pruefung/${teilName(index + 1)}`] = { teil: index + 1, aufgaben: teil };
	});
	return dokumente;
}

/** Dokumente kompakt serialisieren und die Größengrenze der Artifact-Datenbank prüfen (wie der bisherige Export). */
export function serialisiere(dokumente: Record<string, unknown>): { name: string; inhalt: string; bytes: number }[] {
	const encoder = new TextEncoder();
	return Object.entries(dokumente).map(([name, body]) => {
		const inhalt = JSON.stringify(body);
		const bytes = encoder.encode(inhalt).length;
		if (bytes > MAX_DOKUMENT_BYTES) throw new Error(`${name}: ${bytes} Bytes, Grenze ${MAX_DOKUMENT_BYTES}`);
		return { bytes, inhalt, name };
	});
}
