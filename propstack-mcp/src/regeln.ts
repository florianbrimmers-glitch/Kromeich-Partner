/**
 * Hausregeln fuer Schreibzugriffe auf Propstack.
 *
 * Alles hier ist reine Logik ohne Netzwerk, damit es sich testen laesst.
 * Die Regeln stammen aus der Anleitung (Skill propstack-expose-workflow),
 * den Notion-Korrekturen und den Vorgaben von Florian Brimmers. Sie gelten
 * fuer JEDEN, der ueber den Server schreibt - nicht nur fuer eine Session.
 */

export const SHOP = 126208;
export const BROKER_STANDARD = 259613; // Denise Kromeich
export const BROKER_PRUEFER = 254958; // Lena Klinnert - Aufgaben immer an Lena

export const STATUS = {
	akquise: 163672,
	vorbereitung: 163673,
	vermarktung: 163674,
	reserviert: 163675,
	abgeschlossen: 163676,
} as const;

export const OPT = {
	aktiv: 182817,
	inaktiv: 182818,
	altbau: 180608,
	neubau: 180609,
	spekulativ_ja: 180606,
	spekulativ_nein: 180607,
} as const;

export const COURTAGE_FREI = "Provisionsfrei";
export const COURTAGE_NOTE_FREI = "Die Anmietung erfolgt provisionsfrei für den Mieter.";
export const PROVISION_EXTERN_PFLICHTIG = "Provisionspflichtig für den Mieter";
/** Wissensdatenbank 1.5 - Staffel nach Mietvertragslaufzeit, wortgleich mit dem Bestand. */
export const COURTAGE_NOTE_PFLICHTIG =
	"Bei Mietverträgen mit einer Laufzeit von weniger als fünf (5) Jahren beträgt der Provisionsanspruch zwei (2) Nettokaltmieten zzgl. MwSt.\n\n" +
	"Bei Mietverträgen mit einer Laufzeit von mehr als oder gleich fünf (5), jedoch weniger als sieben (7) Jahren beträgt der Provisionsanspruch drei (3) Nettokaltmieten zzgl. MwSt.\n\n" +
	"Bei Mietverträgen mit einer Laufzeit von mehr als oder gleich sieben (7), jedoch weniger als zehn (10) Jahren beträgt der Provisionsanspruch dreieinhalb (3,5) Nettokaltmieten zzgl. MwSt.\n\n" +
	"Bei Mietverträgen mit einer Laufzeit ab zehn (10) Jahren beträgt der Provisionsanspruch vier (4) Nettokaltmiete zzgl. MwSt.";

export const WRAPPER: Record<string, string> = {
	units: "property",
	projects: "project",
	contacts: "client",
	tasks: "task",
	images: "image",
	relationships: "relationship",
	client_properties: "client_property",
};

/** Exposé-/portalsichtbare Geldfelder: interne Mieten duerfen hier nie landen. */
export const PUBLIC_MONEY = new Set([
	"base_rent",
	"total_rent",
	"price",
	"price_per_sqm",
	"service_charge",
	"heating_costs",
	"deposit",
	"parking_space_price",
	"property_rent_per_sqm_from_value",
	"property_additional_costs_per_sqm_from_value",
	"valuation_price_from",
	"valuation_price_to",
]);

/** Custom Fields, die nur geleert werden duerfen (jeder Wert bricht eine Automatisierung). */
export const CF_NUR_NULL = new Set(["provisionspflichtig"]);

/**
 * Custom Fields, die nie beschrieben werden.
 * `mezzanineflache` ist das Feld der PREISE-Sektion (Einheit Euro) - eine
 * Flaeche darin erscheint als Geldbetrag. Am 13.08.2026 sind so 664
 * Einheiten verdorben worden.
 */
export const CF_GESPERRT: Record<string, string> = {
	mezzanineflache:
		"mezzanineflache ist ein Euro-Feld der Preise-Sektion. Flaeche gehoert in mezzanineflache_gesamt / mezzanineflache_verfugbar, Miete in intern_mietpreis_mezzanine.",
};

/**
 * Standardfelder, die die API im POST und in Multi-Feld-PUTs still verwirft.
 * Sie werden einzeln, ein Feld pro Request, geschrieben.
 */
export const EINZELFELDER = [
	"rs_category",
	"total_floor_space",
	"industrial_area",
	"hall_height",
	"floor_load",
	"broker_id",
	"rented",
	"plot_area",
	"lat",
	"lng",
] as const;

/** Felder, die im POST /units einen HTTP 500 ausloesen koennen - erst danach einzeln setzen. */
export const NICHT_IM_POST = new Set(["object_type", "lat", "lng", "plot_area", "construction_year"]);

/** Nur Ganzzahl - 82600.0 als Float erzeugt bei plot_area einen HTTP 500. */
export const GANZZAHL = new Set(["plot_area", "construction_year", "floor_load"]);

/** Flaechenfelder, in denen eine 0 nie richtig ist (Vorgabe 07.09.2026). */
export const FLAECHEN_CF = [
	"lagerflache",
	"lagerflache_gesamt",
	"lagerflache_verfugbar",
	"lagerflache_teilbar_ab",
	"buroflache",
	"buroflache_gesamt",
	"buroflache_verfugbar",
	"buroflache_teilbar_ab",
	"mezzanineflache_gesamt",
	"mezzanineflache_verfugbar",
	"gebaudeflache_gesamt",
	"gebaudeflache_verfugbar",
];
export const FLAECHEN_STD = ["industrial_area", "total_floor_space", "plot_area"];

/** Texte, die im Exposé erscheinen. */
export const EXPOSE_TEXTE = ["title", "description_note", "location_note", "furnishing_note"];

export class RegelVerstoss extends Error {
	constructor(message: string) {
		super(message);
		this.name = "RegelVerstoss";
	}
}

export type CfFeld = {
	name: string;
	field_type?: string;
	unit?: string | null;
	custom_options?: { id: number; name: string }[];
};

/** Nullwerte in Flaechen: "0", 0, "0 m²", "0 m² (vermietet)". */
export function istNullflaeche(v: unknown): boolean {
	if (v === null || v === undefined || v === "") return false;
	if (typeof v === "number") return v === 0;
	if (typeof v === "string") {
		const m = v.match(/^\s*(?:ca\.\s*)?(\d+(?:[.,]\d+)?)/i);
		return m !== null && Number.parseFloat(m[1].replace(",", ".")) === 0;
	}
	return false;
}

/** Prueft Standardfelder eines Schreibzugriffs. Wirft RegelVerstoss. */
export function pruefeStandardfelder(felder: Record<string, unknown>): Record<string, unknown> {
	const out: Record<string, unknown> = {};
	for (const [k, v] of Object.entries(felder)) {
		if (PUBLIC_MONEY.has(k) && v !== null && v !== undefined) {
			throw new RegelVerstoss(
				`${k} ist exposé-sichtbar. Mietpreise gehoeren nur in intern_mietpreis_hallenflache / _buro / _mezzanine, mit price_on_inquiry=true.`,
			);
		}
		if (k === "note") {
			throw new RegelVerstoss("note wird von der API still verworfen - interne Notizen gehoeren ins Custom Field bemerkung.");
		}
		if (k === "name") {
			throw new RegelVerstoss("name ist auf Einheiten nicht schreibbar - title (Ueberschrift) und unit_id (Einheitennummer) verwenden.");
		}
		if (FLAECHEN_STD.includes(k) && istNullflaeche(v)) {
			throw new RegelVerstoss(`${k}=0 ist nie richtig. Reale Groesse eintragen; Vermietung ueber rented + Status abbilden, fehlende Flaeche leer lassen.`);
		}
		if (GANZZAHL.has(k) && typeof v === "number") {
			out[k] = Math.round(v);
			continue;
		}
		if (typeof v === "string" && /^-?\d+,\d+$/.test(v)) {
			throw new RegelVerstoss(`${k}=${JSON.stringify(v)}: Zahl mit Komma wird still gekuerzt. Als Zahl mit Punkt senden.`);
		}
		out[k] = v;
	}
	return out;
}

/** Prueft und wandelt Custom Fields gegen die Feld-Registry. Wirft RegelVerstoss. */
export function pruefeCustomFields(
	cf: Record<string, unknown>,
	registry: Map<string, CfFeld>,
): Record<string, unknown> {
	const out: Record<string, unknown> = {};
	for (const [k, v] of Object.entries(cf)) {
		if (k in CF_GESPERRT) throw new RegelVerstoss(CF_GESPERRT[k]);
		if (CF_NUR_NULL.has(k) && v !== null) {
			throw new RegelVerstoss(`${k} darf nie gesetzt werden - jeder Wert bricht eine bestehende Automatisierung. Provision ueber courtage, courtage_note, provision_extern und provision_interne_notiz abbilden.`);
		}
		if (k === "bemerkung") {
			throw new RegelVerstoss("bemerkung wird nie direkt ueberschrieben (nicht versioniert). Das Werkzeug bemerkung_ergaenzen verwenden.");
		}
		const def = registry.get(k);
		if (!def) throw new RegelVerstoss(`Custom Field ${k} existiert in diesem Shop nicht.`);
		if (v === null) {
			out[k] = null;
			continue;
		}
		if (FLAECHEN_CF.includes(k) && istNullflaeche(v)) {
			throw new RegelVerstoss(`${k}=${JSON.stringify(v)}: 0 m² ist nie richtig. Im Feld steht die reale Groesse; vermietet wird ueber rented + Status abgebildet.`);
		}
		const t = def.field_type;
		if (t === "Number") {
			if (typeof v !== "number" || Number.isNaN(v)) {
				throw new RegelVerstoss(`${k} ist ein Zahlenfeld${def.unit ? ` (${def.unit})` : ""} - ${JSON.stringify(v)} abgelehnt. Als Zahl senden, z. B. 3475 statt "3.475 m²".`);
			}
			out[k] = v;
		} else if (t === "Dropdown" || t === "Multiselect") {
			const opts = def.custom_options ?? [];
			let id: number | undefined;
			if (typeof v === "number" && opts.some((o) => o.id === v)) id = v;
			else if (typeof v === "string") id = opts.find((o) => o.name === v)?.id;
			if (id === undefined) {
				throw new RegelVerstoss(`${k}: Option ${JSON.stringify(v)} unbekannt. Erlaubt: ${opts.map((o) => `${o.name} (${o.id})`).join(", ")}`);
			}
			out[k] = t === "Multiselect" ? [id] : id;
		} else {
			out[k] = v;
		}
	}
	return out;
}

/** Eigentuemer-/Markennamen in exposé-sichtbaren Texten finden (Korrektur 33). */
export function namenInTexten(felder: Record<string, unknown>, verboten: string[]): string[] {
	const treffer: string[] = [];
	for (const k of EXPOSE_TEXTE) {
		const t = felder[k];
		if (typeof t !== "string") continue;
		for (const n of verboten) {
			const w = n.trim();
			if (w.length >= 3 && t.toLowerCase().includes(w.toLowerCase())) treffer.push(`${k} enthaelt "${w}"`);
		}
	}
	return treffer;
}

/** Vergleich Soll/Ist fuer die Nachkontrolle. */
export function abweichungen(soll: Record<string, unknown>, ist: Record<string, unknown>, tol = 0.01) {
	const out: { feld: string; soll: unknown; ist: unknown }[] = [];
	for (const [k, s] of Object.entries(soll)) {
		const i = ist[k];
		let ok: boolean;
		if (Array.isArray(s) || Array.isArray(i)) {
			const a = (Array.isArray(s) ? s : [s]).map(String);
			const b = (Array.isArray(i) ? i : [i]).map(String);
			ok = a.length === b.length && a.every((x, n) => x === b[n]);
		} else if (typeof s === "number") {
			ok = i !== null && i !== undefined && i !== "" && Math.abs(Number(i) - s) <= tol;
		} else if (s === null) {
			ok = i === null || i === undefined || i === "";
		} else {
			ok = i === s;
		}
		if (!ok) out.push({ feld: k, soll: s, ist: i });
	}
	return out;
}

/** Neuer Eintrag vorne, alter Text bleibt als Historie erhalten. */
export function bemerkungVoranstellen(alt: string | null | undefined, neu: string, heute: string): string {
	const a = (alt ?? "").trim();
	if (!a) return neu;
	if (a.includes("HISTORISCH")) return `${neu}\n\n${a}`;
	return `${neu}\n\n--- HISTORISCH (uebernommen ${heute}) ---\n${a}`;
}

export function heute(): string {
	return new Date().toISOString().slice(0, 10);
}
