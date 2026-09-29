/**
 * Propstack-REST-v1-Client mit den verifizierten Eigenheiten der API.
 *
 * - Read-Back nur ueber GET /units?expand=1&per=100&property_ids[]=...
 *   Der Einzel-GET liefert rs_category, floor_load, plot_area, broker_id usw.
 *   gar nicht. `per` ist Pflicht, sonst kommen trotz ID-Filter nur 20 Zeilen.
 * - Status nur ueber status.id im Einzel-GET.
 * - Eigentuemer nur ueber die paginierte Liste /relationships.
 * - Einige Standardfelder werden im POST und in Multi-Feld-PUTs still
 *   verworfen und muessen einzeln geschrieben werden (EINZELFELDER).
 */
import {
	abweichungen,
	bemerkungVoranstellen,
	type CfFeld,
	EINZELFELDER,
	heute,
	NICHT_IM_POST,
	pruefeCustomFields,
	pruefeStandardfelder,
	RegelVerstoss,
	WRAPPER,
} from "./regeln";

const BASE = "https://api.propstack.de/v1";

export type Json = any;

export class PropstackFehler extends Error {
	constructor(
		message: string,
		public status: number,
	) {
		super(message);
		this.name = "PropstackFehler";
	}
}

const schlaf = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function zeilen(d: Json): Json[] {
	if (Array.isArray(d)) return d;
	if (d && Array.isArray(d.data)) return d.data;
	return [];
}

function wert(v: Json) {
	return v && typeof v === "object" && !Array.isArray(v) && "value" in v ? v.value : v;
}

/** Custom Fields als cf.<name>, Status als status_id. */
export function flach(u: Json): Record<string, Json> {
	const f: Record<string, Json> = {};
	for (const [k, v] of Object.entries(u ?? {})) if (k !== "custom_fields") f[k] = wert(v);
	for (const [k, v] of Object.entries(u?.custom_fields ?? {})) {
		f[`cf.${k}`] = v && typeof v === "object" && !Array.isArray(v) ? (v as Json).value : v;
	}
	if (u?.status && typeof u.status === "object") f.status_id = u.status.id;
	return f;
}

export type Protokoll = (eintrag: Record<string, unknown>) => Promise<void> | void;

export class Propstack {
	private registryCache?: Map<string, CfFeld>;

	constructor(
		private objKey: string,
		private taskKey: string,
		private protokoll: Protokoll = () => {},
		private fetchImpl: typeof fetch = fetch,
	) {}

	async raw(method: string, path: string, body?: Json, key = this.objKey): Promise<Json> {
		const url = `${BASE}${path}${path.includes("?") ? "&" : "?"}api_key=${encodeURIComponent(key)}`;
		let letzter: Error | undefined;
		for (let versuch = 0; versuch < 4; versuch++) {
			let r: Response;
			try {
				r = await this.fetchImpl(url, {
					method,
					headers: body !== undefined ? { "content-type": "application/json" } : undefined,
					body: body !== undefined ? JSON.stringify(body) : undefined,
				});
			} catch (e) {
				letzter = e as Error;
				await schlaf(500 * 2 ** versuch);
				continue;
			}
			if (r.status === 429 || r.status >= 500) {
				letzter = new PropstackFehler(`${method} ${path} -> HTTP ${r.status}`, r.status);
				await schlaf(500 * 2 ** versuch);
				continue;
			}
			const text = await r.text();
			if (r.status >= 400) throw new PropstackFehler(`${method} ${path} -> HTTP ${r.status}: ${text.slice(0, 400)}`, r.status);
			return text ? JSON.parse(text) : null;
		}
		throw letzter ?? new Error(`${method} ${path} fehlgeschlagen`);
	}

	// ------------------------------------------------------------ Registry
	async registry(): Promise<Map<string, CfFeld>> {
		if (this.registryCache) return this.registryCache;
		const m = new Map<string, CfFeld>();
		for (const g of zeilen(await this.raw("GET", "/custom_field_groups"))) {
			if (g.for_properties === false) continue;
			for (const f of g.custom_fields ?? []) if (f.name) m.set(f.name, f);
		}
		this.registryCache = m;
		return m;
	}

	// --------------------------------------------------------------- Lesen
	/** Der einzige belastbare Read-Back-Kanal. Fehlende IDs werden gemeldet, nicht verschluckt. */
	async einheitenVoll(ids: number[]): Promise<{ daten: Map<number, Json>; fehlend: number[] }> {
		const daten = new Map<number, Json>();
		const eindeutig = [...new Set(ids)];
		for (let i = 0; i < eindeutig.length; i += 20) {
			const chunk = eindeutig.slice(i, i + 20);
			const qs = chunk.map((x) => `property_ids[]=${x}`).join("&");
			try {
				for (const r of zeilen(await this.raw("GET", `/units?expand=1&per=100&${qs}`))) daten.set(r.id, r);
			} catch {
				// pro Einheit weiter unten
			}
		}
		const fehlend = eindeutig.filter((x) => !daten.has(x));
		return { daten, fehlend };
	}

	async einheit(id: number): Promise<Record<string, Json>> {
		const { daten, fehlend } = await this.einheitenVoll([id]);
		if (fehlend.length) throw new PropstackFehler(`Einheit ${id} nicht lesbar`, 404);
		const f = flach(daten.get(id));
		const einzel = await this.raw("GET", `/units/${id}`);
		f.status_id = einzel?.status?.id ?? null;
		f.status_name = einzel?.status?.name ?? null;
		f.lat = einzel?.lat ?? f.lat;
		f.lng = einzel?.lng ?? f.lng;
		f.bilder = (einzel?.images ?? []).map((b: Json) => ({ id: b.id, titel: b.title, grundriss: b.is_floorplan }));
		return f;
	}

	async statusId(id: number): Promise<number | null> {
		return (await this.raw("GET", `/units/${id}`))?.status?.id ?? null;
	}

	async einheitenDesProjekts(pid: number): Promise<Json[]> {
		return zeilen(await this.raw("GET", `/units?per=200&project_id=${pid}`));
	}

	async beziehungen(): Promise<Json[]> {
		const out: Json[] = [];
		for (let seite = 1; seite <= 80; seite++) {
			const z = zeilen(await this.raw("GET", `/relationships?per=200&page=${seite}`));
			if (!z.length) break;
			out.push(...z);
		}
		return out;
	}

	// ----------------------------------------------------------- Schreiben
	private async schreibe(resource: string, body: Json, id?: number, key = this.objKey): Promise<Json> {
		const method = id ? "PUT" : "POST";
		const res = await this.raw(method, id ? `/${resource}/${id}` : `/${resource}`, { [WRAPPER[resource]]: body }, key);
		await this.protokoll({ op: `${resource}.${method}`, id: res?.id ?? id, felder: Object.keys(body) });
		return res;
	}

	private async body(felder: Record<string, Json>, cf?: Record<string, Json>): Promise<Json> {
		const b = pruefeStandardfelder(felder);
		if (cf && Object.keys(cf).length) b.partial_custom_fields = pruefeCustomFields(cf, await this.registry());
		return b;
	}

	/**
	 * Buendeln -> Einzelfelder einzeln -> nachlesen -> Abweichungen melden.
	 * Gibt die Liste der Abweichungen zurueck; leer heisst: steht so in Propstack.
	 */
	async einheitAktualisieren(id: number, felder: Record<string, Json> = {}, cf: Record<string, Json> = {}) {
		const b = await this.body(felder, cf);
		const cfGeprueft = b.partial_custom_fields ?? {};
		const einzeln = Object.fromEntries(Object.entries(b).filter(([k]) => (EINZELFELDER as readonly string[]).includes(k)));
		const gebuendelt = Object.fromEntries(Object.entries(b).filter(([k]) => !(k in einzeln)));
		if (Object.keys(gebuendelt).length) await this.schreibe("units", gebuendelt, id);
		for (const [k, v] of Object.entries(einzeln)) await this.schreibe("units", { [k]: v }, id);
		return this.nachkontrolle(id, b, cfGeprueft);
	}

	async nachkontrolle(id: number, felder: Record<string, Json>, cf: Record<string, Json>) {
		const soll: Record<string, Json> = {};
		for (const [k, v] of Object.entries(felder)) if (k !== "partial_custom_fields" && !["lat", "lng"].includes(k)) soll[k] = v;
		for (const [k, v] of Object.entries(cf)) soll[`cf.${k}`] = v;
		const { daten, fehlend } = await this.einheitenVoll([id]);
		if (fehlend.length) return [{ feld: "*", soll: "lesbar", ist: "Einheit nicht zuruecklesbar" }];
		const ist = flach(daten.get(id));
		let d = abweichungen(soll, ist);
		// Standardfelder, die trotzdem fehlen: einzeln nachsetzen und neu pruefen
		const nach = d.filter((x) => !x.feld.startsWith("cf.") && x.feld in felder);
		if (nach.length) {
			for (const x of nach) await this.schreibe("units", { [x.feld]: felder[x.feld] }, id);
			const neu = await this.einheitenVoll([id]);
			d = abweichungen(soll, flach(neu.daten.get(id)));
		}
		return d;
	}

	async einheitAnlegen(projektId: number | null, felder: Record<string, Json>, cf: Record<string, Json> = {}) {
		const b = await this.body(felder, cf);
		const cfGeprueft = b.partial_custom_fields ?? {};
		delete b.partial_custom_fields;
		const post: Json = {};
		const spaeter: Json = {};
		for (const [k, v] of Object.entries(b)) {
			if (NICHT_IM_POST.has(k) || (EINZELFELDER as readonly string[]).includes(k)) spaeter[k] = v;
			else post[k] = v;
		}
		if (projektId) post.project_id = projektId;
		const res = await this.schreibe("units", post);
		const id: number = res.id;
		if (Object.keys(cfGeprueft).length) await this.schreibe("units", { partial_custom_fields: cfGeprueft }, id);
		const fehler: string[] = [];
		for (const [k, v] of Object.entries(spaeter)) {
			try {
				await this.schreibe("units", { [k]: v }, id);
			} catch (e) {
				fehler.push(`${k}: ${(e as Error).message.slice(0, 120)}`);
			}
		}
		const abw = await this.nachkontrolle(id, { ...post, ...spaeter }, cfGeprueft);
		return { id, abweichungen: abw, fehler };
	}

	async projektAnlegen(felder: Record<string, Json>) {
		const b = pruefeStandardfelder(felder);
		if ("relationships_attributes" in b) {
			throw new RegelVerstoss("Eigentuemer nicht im Projekt-POST setzen (scheitert bei Fremd-Shop-Kontakten) - danach eigentuemer_setzen verwenden.");
		}
		const res = await this.schreibe("projects", b);
		return res.id as number;
	}

	async projektAktualisieren(id: number, felder: Record<string, Json>) {
		const b = pruefeStandardfelder(felder);
		await this.schreibe("projects", b, id);
		return this.raw("GET", `/projects/${id}`);
	}

	async eigentuemerSetzen(projektId: number, kontaktId: number): Promise<boolean> {
		const hat = async () =>
			(await this.beziehungen()).some(
				(r) => r.project_id === projektId && r.internal_name === "owner" && r.related_client_id === kontaktId,
			);
		if (await hat()) return true;
		try {
			await this.schreibe("projects", { relationships_attributes: [{ internal_name: "owner", related_client_id: kontaktId }] }, projektId);
		} catch (e) {
			const m = (e as Error).message;
			if (!m.includes("bereits mit dem Kontakt verbunden") && !m.includes("Verknüpfung existiert bereits")) throw e;
		}
		return hat();
	}

	async statusSetzen(id: number, statusId: number): Promise<boolean> {
		await this.schreibe("units", { property_status_id: statusId }, id);
		return (await this.statusId(id)) === statusId;
	}

	async bemerkungErgaenzen(id: number, text: string): Promise<boolean> {
		const alt = flach((await this.einheitenVoll([id])).daten.get(id))["cf.bemerkung"];
		const neu = bemerkungVoranstellen(alt, text, heute());
		await this.schreibe("units", { partial_custom_fields: { bemerkung: neu } }, id);
		const ist = flach((await this.einheitenVoll([id])).daten.get(id))["cf.bemerkung"] ?? "";
		return ist.includes(text.slice(0, 60));
	}

	async bildHochladen(typ: "Property" | "Project", objektId: number, bild: Blob, dateiname: string, titel: string, grundriss: boolean) {
		const fd = new FormData();
		fd.set("api_key", this.objKey);
		fd.set("image[imageable_type]", typ);
		fd.set("image[imageable_id]", String(objektId));
		fd.set("image[title]", titel);
		fd.set("image[is_floorplan]", grundriss ? "true" : "false");
		// image[photo] - image[file] erzeugt HTTP 500 und ein leeres Bildobjekt
		fd.set("image[photo]", bild, dateiname);
		const r = await this.fetchImpl(`${BASE}/images`, { method: "POST", body: fd });
		const t = await r.text();
		if (r.status >= 400) throw new PropstackFehler(`Bild-Upload -> HTTP ${r.status}: ${t.slice(0, 200)}`, r.status);
		const d = t ? JSON.parse(t) : {};
		await this.protokoll({ op: "images.POST", id: d.id, objekt: `${typ} ${objektId}`, titel });
		const obj = await this.raw("GET", typ === "Project" ? `/projects/${objektId}` : `/units/${objektId}`);
		const da = (obj?.images ?? []).find((i: Json) => i.id === d.id);
		return { id: d.id as number, bestaetigt: Boolean(da), grundriss: Boolean(da?.is_floorplan) };
	}

	async aufgabeAnlegen(a: { titel: string; text: string; bearbeiter: number; faellig: string; projekte?: number[]; einheiten?: number[] }) {
		const res = await this.schreibe(
			"tasks",
			{
				title: a.titel,
				body: a.text,
				broker_id: a.bearbeiter,
				is_reminder: true,
				due_date: a.faellig,
				project_ids: a.projekte ?? [],
				property_ids: a.einheiten ?? [],
			},
			undefined,
			this.taskKey,
		);
		const g = await this.raw("GET", `/tasks/${res.id}`, undefined, this.taskKey);
		return { id: res.id as number, bearbeiter: g?.broker_id, projekte: (g?.projects ?? []).length, einheiten: (g?.units ?? []).length };
	}

	async dealAktualisieren(id: number, felder: { deal_pipeline_id?: number; deal_stage_id?: number; broker_id?: number }) {
		const r = await this.schreibe("client_properties", felder, id);
		return { id, deal_pipeline_id: r?.deal_pipeline_id, deal_stage_id: r?.deal_stage_id, broker_id: r?.broker_id };
	}
}
