import OAuthProvider from "@cloudflare/workers-oauth-provider";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpAgent } from "agents/mcp";
import { z } from "zod";
import { handleAccessRequest } from "./access-handler";
import { flach, type Json, Propstack, zeilen } from "./propstack";
import {
	BROKER_PRUEFER,
	COURTAGE_FREI,
	COURTAGE_NOTE_FREI,
	COURTAGE_NOTE_PFLICHTIG,
	heute,
	namenInTexten,
	OPT,
	PROVISION_EXTERN_PFLICHTIG,
	RegelVerstoss,
	STATUS,
} from "./regeln";
import type { Props } from "./workers-oauth-utils";

const ok = (daten: unknown) => ({ content: [{ type: "text" as const, text: JSON.stringify(daten, null, 1) }] });
const fehler = (e: unknown) => ({
	isError: true,
	content: [
		{
			type: "text" as const,
			text: e instanceof RegelVerstoss ? `REGELVERSTOSS - nichts geschrieben: ${e.message}` : `Fehler: ${(e as Error).message}`,
		},
	],
});
async function sicher<T>(f: () => Promise<T>) {
	try {
		return ok(await f());
	} catch (e) {
		return fehler(e);
	}
}

/** Kompakte Sicht auf eine Einheit fuer Suchlisten. */
function kurz(u: Json) {
	const f = flach(u);
	return {
		id: f.id,
		projekt_id: f.project_id,
		einheit: f.unit_id,
		titel: f.title,
		adresse: [f.street, f.house_number, f.zip_code, f.city].filter(Boolean).join(" "),
		halle_m2: f["cf.lagerflache"],
		verfuegbar: f["cf.lagerflache_verfugbar"],
		vermietet: f.rented,
		eigentuemer: f["cf.eigentumer"],
		angelegt: String(f.created_at ?? "").slice(0, 10),
	};
}

/** Propstack-Aufgaben vertragen keine Sonderzeichen im Text - vorher umschreiben. */
function ascii(t: string): string {
	return t
		.replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue")
		.replace(/Ä/g, "Ae").replace(/Ö/g, "Oe").replace(/Ü/g, "Ue")
		.replace(/ß/g, "ss").replace(/[–—]/g, "-").replace(/²/g, "2")
		.normalize("NFKD").replace(/[^\x00-\x7F]/g, "");
}

const felderSchema = z.record(z.string(), z.any()).describe("Standardfelder der Einheit, z. B. title, unit_id, street, zip_code, city, description_note, rs_type, rs_category, industrial_area, hall_height, floor_load, plot_area, rented, free_from");
const cfSchema = z.record(z.string(), z.any()).describe("Custom Fields nach API-Name, z. B. lagerflache (Zahl), lagerflache_verfugbar (Text), buroflache, mezzanineflache_gesamt, hallenhohe, ramepntore (Text), anzahl_rampentore_2 (Zahl = ebenerdige Tore), eigentumer, intern_mietpreis_hallenflache. Zahlenfelder als Zahl, nie als formatierter Text.");

export class PropstackMCP extends McpAgent<Env, Record<string, never>, Props> {
	server = new McpServer({ name: "Propstack Kromeich & Partner", version: "0.1.0" });

	private ps!: Propstack;

	private async protokoll(eintrag: Record<string, unknown>) {
		const e = { ...eintrag, nutzer: this.props?.email, zeit: new Date().toISOString() };
		console.log(JSON.stringify({ audit: e }));
		try {
			await this.env.AUDIT_KV.put(`log:${e.zeit}:${crypto.randomUUID().slice(0, 8)}`, JSON.stringify(e), {
				expirationTtl: 60 * 60 * 24 * 365,
			});
		} catch {
			// Protokoll darf den Schreibzugriff nicht verhindern; console.log bleibt in den Worker-Logs
		}
	}

	async init() {
		const email = (this.props?.email ?? "").toLowerCase();
		const domain = (this.env.ERLAUBTE_DOMAIN || "kromeichpartner.de").toLowerCase();
		if (!email.endsWith(`@${domain}`)) {
			this.server.tool("zugang", "Zeigt, warum keine Werkzeuge verfuegbar sind.", {}, async () =>
				ok({ hinweis: `Nur Konten @${domain} haben Zugriff. Angemeldet: ${email || "unbekannt"}` }),
			);
			return;
		}
		this.ps = new Propstack(this.env.PROPSTACK_OBJ_KEY, this.env.PROPSTACK_TASK_KEY, (e) => this.protokoll(e));
		const ps = this.ps;
		const wer = this.props?.name || email;

		// ================================================================ LESEN
		this.server.tool(
			"einheit_lesen",
			"Liest eine Einheit vollstaendig (alle Standard- und Custom Fields ueber den belastbaren expand-Kanal, dazu Status, Koordinaten und Bilder).",
			{ id: z.number().int() },
			async ({ id }) => sicher(() => ps.einheit(id)),
		);

		this.server.tool(
			"einheiten_suchen",
			"Sucht Einheiten fuer die Existenzpruefung vor jeder Neuanlage. Immer ueber PLZ UND Strasse suchen, dazu Ort und Eigentuemer. Findet auch projektlose Einheiten aus dem Import vom 13.01.2025.",
			{
				suchtext: z.string().describe("Strasse, PLZ, Ort, Titel oder Eigentuemer"),
				plz: z.string().optional().describe("filtert das Ergebnis auf diese PLZ"),
			},
			async ({ suchtext, plz }) =>
				sicher(async () => {
					const z1 = zeilen(await ps.raw("GET", `/units?expand=1&per=100&q=${encodeURIComponent(suchtext)}`));
					return z1.filter((u) => !plz || String(u.zip_code ?? "") === plz).map(kurz);
				}),
		);

		this.server.tool(
			"projekte_suchen",
			"Sucht Projekte ueber Name, PLZ oder Strasse (q durchsucht den Namen, darum PLZ und Strasse getrennt probieren).",
			{ suchtext: z.string() },
			async ({ suchtext }) =>
				sicher(async () =>
					zeilen(await ps.raw("GET", `/projects?per=100&q=${encodeURIComponent(suchtext)}`)).map((p) => ({
						id: p.id,
						name: p.name,
						adresse: [p.street, p.house_number, p.zip_code, p.city].filter(Boolean).join(" "),
					})),
				),
		);

		this.server.tool(
			"projekt_lesen",
			"Liest ein Projekt mit Beschreibung, Bildern, Eigentuemer-Verknuepfung und allen Einheiten.",
			{ id: z.number().int() },
			async ({ id }) =>
				sicher(async () => {
					const p = await ps.raw("GET", `/projects/${id}`);
					const units = await ps.einheitenDesProjekts(id);
					return {
						...p,
						bilder: (p.images ?? []).map((b: Json) => ({ id: b.id, titel: b.title, grundriss: b.is_floorplan })),
						images: undefined,
						einheiten: units.map(kurz),
					};
				}),
		);

		this.server.tool(
			"kontakte_suchen",
			"Sucht Kontakte und Firmen (Eigentuemer, Ansprechpartner). Vor dem Anlegen eines Kontakts immer suchen.",
			{ suchtext: z.string() },
			async ({ suchtext }) =>
				sicher(async () =>
					zeilen(await ps.raw("GET", `/contacts?per=50&q=${encodeURIComponent(suchtext)}`)).map((k) => ({
						id: k.id,
						name: k.name,
						firma: k.company,
						email: k.email,
						ist_firma: k.is_company,
					})),
				),
		);

		this.server.tool(
			"feld_nachschlagen",
			"Schlaegt Custom Fields in der Feld-Registry nach: Typ (Number/String/Dropdown), Einheit (sqm/euro) und erlaubte Optionen. Vor dem ersten Schreiben eines unbekannten Feldes benutzen.",
			{ suchtext: z.string().describe("Teil des API-Namens oder der Beschriftung, z. B. 'mezzanine' oder 'tore'") },
			async ({ suchtext }) =>
				sicher(async () => {
					const s = suchtext.toLowerCase();
					return [...(await ps.registry()).values()]
						.filter((f: Json) => f.name.toLowerCase().includes(s) || String(f.pretty_name ?? "").toLowerCase().includes(s))
						.map((f: Json) => ({
							name: f.name,
							beschriftung: f.pretty_name,
							typ: f.field_type,
							einheit: f.unit,
							optionen: (f.custom_options ?? []).map((o: Json) => `${o.name} (${o.id})`),
						}));
				}),
		);

		this.server.tool(
			"pipelines_lesen",
			"Listet die Deal-Pipelines mit ihren Stufen und IDs (z. B. '300 Leverkusen', '300 Mieter').",
			{},
			async () =>
				sicher(async () =>
					zeilen(await ps.raw("GET", "/deal_pipelines")).map((p) => ({
						id: p.id,
						name: p.name,
						stufen: (p.deal_stages ?? []).map((s: Json) => ({ id: s.id, name: s.name })),
					})),
				),
		);

		this.server.tool(
			"deals_lesen",
			"Liest Deals (client_properties) zu einem Projekt, einer Einheit oder einem Kontakt, mit Pipeline, Stufe und Betreuer.",
			{
				projekt_id: z.number().int().optional(),
				einheit_id: z.number().int().optional(),
				kontakt_id: z.number().int().optional(),
			},
			async ({ projekt_id, einheit_id, kontakt_id }) =>
				sicher(async () => {
					const out: Json[] = [];
					for (let seite = 1; seite <= 40; seite++) {
						const z1 = zeilen(await ps.raw("GET", `/client_properties?per=500&page=${seite}`));
						if (!z1.length) break;
						out.push(
							...z1.filter(
								(d) =>
									(!projekt_id || d.project_id === projekt_id) &&
									(!einheit_id || d.property_id === einheit_id) &&
									(!kontakt_id || d.client_id === kontakt_id),
							),
						);
					}
					return out.map((d) => ({
						id: d.id,
						kontakt_id: d.client_id,
						projekt_id: d.project_id,
						einheit_id: d.property_id,
						pipeline_id: d.deal_pipeline_id,
						stufe_id: d.deal_stage_id,
						betreuer: d.broker_id,
						angelegt: String(d.created_at ?? "").slice(0, 16),
					}));
				}),
		);

		// ============================================================ SCHREIBEN
		this.server.tool(
			"projekt_anlegen",
			"Legt ein Projekt an. Titelschema: 'Logistikhalle in (<PLZ-2>) <Ort> – <Strasse>'. Keine Eigentuemer- oder Markennamen in Titel und Texten. Eigentuemer danach mit eigentuemer_setzen verknuepfen.",
			{
				felder: z.record(z.string(), z.any()).describe("name, title, street, house_number, zip_code, city, country, for_rent, broker_id, courtage, description_note, location_note, furnishing_note"),
				verbotene_namen: z.array(z.string()).describe("Eigentuemer-, Entwickler- und Markennamen, die nicht in den Texten stehen duerfen"),
			},
			async ({ felder, verbotene_namen }) =>
				sicher(async () => {
					const t = namenInTexten(felder, verbotene_namen);
					if (t.length) throw new RegelVerstoss(`Eigentuemer-/Markenname in exposé-sichtbarem Text: ${t.join("; ")}`);
					return { projekt_id: await ps.projektAnlegen(felder) };
				}),
		);

		this.server.tool(
			"projekt_aktualisieren",
			"Aendert Standardfelder eines Projekts (Texte, Adresse, courtage). Projekte haben kein per API beschreibbares Notizfeld.",
			{ id: z.number().int(), felder: z.record(z.string(), z.any()), verbotene_namen: z.array(z.string()) },
			async ({ id, felder, verbotene_namen }) =>
				sicher(async () => {
					const t = namenInTexten(felder, verbotene_namen);
					if (t.length) throw new RegelVerstoss(`Eigentuemer-/Markenname in exposé-sichtbarem Text: ${t.join("; ")}`);
					const p = await ps.projektAktualisieren(id, felder);
					return { id, gespeichert: Object.fromEntries(Object.keys(felder).map((k) => [k, p?.[k]])) };
				}),
		);

		this.server.tool(
			"einheit_anlegen",
			"Legt eine Einheit an (optional in einem Projekt). Prueft die Hausregeln, schreibt die still verworfenen Felder einzeln nach und liest danach alles zurueck. Rueckgabe 'abweichungen: []' heisst: steht so in Propstack. Provision muss immer mitgegeben werden. Flaechenfelder: alle Varianten setzen (lagerflache, _gesamt, _verfugbar, _teilbar_ab), mezzanineflache nie.",
			{
				projekt_id: z.number().int().nullable(),
				felder: felderSchema,
				custom_fields: cfSchema,
				provision: z.enum(["frei", "pflichtig"]).describe("frei = provisionsfrei fuer den Mieter; pflichtig = Staffel nach Wissensdatenbank 1.5"),
				provision_quelle: z.string().describe("Woher die Provisionsregel stammt, z. B. 'Vorgabe Florian Brimmers vom 24.09.2026' oder 'Expose S. 3'"),
				verbotene_namen: z.array(z.string()).describe("Eigentuemer-, Entwickler- und Markennamen"),
				bemerkung: z.string().describe("Interne Quelle, Widersprueche, abgeleitete Werte, offene Punkte"),
			},
			async ({ projekt_id, felder, custom_fields, provision, provision_quelle, verbotene_namen, bemerkung }) =>
				sicher(async () => {
					const t = namenInTexten(felder, verbotene_namen);
					if (t.length) throw new RegelVerstoss(`Eigentuemer-/Markenname in exposé-sichtbarem Text: ${t.join("; ")}`);
					const frei = provision === "frei";
					const std = {
						price_on_inquiry: true,
						...felder,
						courtage: frei ? COURTAGE_FREI : "Provisionspflichtig",
						courtage_note: frei ? COURTAGE_NOTE_FREI : COURTAGE_NOTE_PFLICHTIG,
					};
					const cf = {
						...custom_fields,
						provision_extern: frei ? COURTAGE_FREI : PROVISION_EXTERN_PFLICHTIG,
						provision_interne_notiz: `${frei ? "Provisionsfrei" : "Provisionspflichtig"} (${provision_quelle}); gesetzt ${heute()} ueber MCP durch ${wer}.`,
					};
					const r = await ps.einheitAnlegen(projekt_id, std, cf);
					const bem = await ps.bemerkungErgaenzen(r.id, `- Stand ${heute()} (${wer}, ueber MCP): NEU ANGELEGT.\n${bemerkung}`);
					return { ...r, bemerkung_gespeichert: bem };
				}),
		);

		this.server.tool(
			"einheit_aktualisieren",
			"Aendert Felder einer bestehenden Einheit mit Regelpruefung und Nachkontrolle. Custom Field leeren: null. bemerkung nicht hierueber - dafuer bemerkung_ergaenzen.",
			{
				id: z.number().int(),
				felder: felderSchema.optional(),
				custom_fields: cfSchema.optional(),
				verbotene_namen: z.array(z.string()).default([]),
			},
			async ({ id, felder, custom_fields, verbotene_namen }) =>
				sicher(async () => {
					const t = namenInTexten(felder ?? {}, verbotene_namen);
					if (t.length) throw new RegelVerstoss(`Eigentuemer-/Markenname in exposé-sichtbarem Text: ${t.join("; ")}`);
					return { id, abweichungen: await ps.einheitAktualisieren(id, felder ?? {}, custom_fields ?? {}) };
				}),
		);

		this.server.tool(
			"provision_setzen",
			"Setzt die Provision einer Einheit auf provisionsfrei oder provisionspflichtig (Staffel Wissensdatenbank 1.5). Das Feld provisionspflichtig wird dabei nie beruehrt.",
			{ id: z.number().int(), provision: z.enum(["frei", "pflichtig"]), quelle: z.string() },
			async ({ id, provision, quelle }) =>
				sicher(async () => {
					const frei = provision === "frei";
					return {
						id,
						abweichungen: await ps.einheitAktualisieren(
							id,
							{ courtage: frei ? COURTAGE_FREI : "Provisionspflichtig", courtage_note: frei ? COURTAGE_NOTE_FREI : COURTAGE_NOTE_PFLICHTIG },
							{
								provision_extern: frei ? COURTAGE_FREI : PROVISION_EXTERN_PFLICHTIG,
								provision_interne_notiz: `${frei ? "Provisionsfrei" : "Provisionspflichtig"} (${quelle}); gesetzt ${heute()} ueber MCP durch ${wer}.`,
							},
						),
					};
				}),
		);

		this.server.tool(
			"vermietet_setzen",
			"Markiert eine Einheit als vermietet: rented=true, Status Abgeschlossen, status_logistik Inaktiv. Die reale Flaeche bleibt im Feld - 0 m² ist nie richtig.",
			{ id: z.number().int(), quelle: z.string().describe("Beleg, z. B. 'Dealmeldung bauwo 24.09.2026'") },
			async ({ id, quelle }) =>
				sicher(async () => {
					const abw = await ps.einheitAktualisieren(id, { rented: true, free_from: "vermietet" }, { status_logistik: "Inaktiv", aktiv: OPT.inaktiv });
					const st = await ps.statusSetzen(id, STATUS.abgeschlossen);
					const bem = await ps.bemerkungErgaenzen(id, `- Stand ${heute()} (${wer}, ueber MCP): VERMIETET. ${quelle}. Reale Flaeche bleibt im Feld.`);
					return { id, abweichungen: abw, status_gesetzt: st, bemerkung_gespeichert: bem };
				}),
		);

		this.server.tool(
			"status_setzen",
			"Setzt den Objektstatus einer Einheit und prueft ihn nach.",
			{ id: z.number().int(), status: z.enum(["akquise", "vorbereitung", "vermarktung", "reserviert", "abgeschlossen"]) },
			async ({ id, status }) => sicher(async () => ({ id, status, bestaetigt: await ps.statusSetzen(id, STATUS[status]) })),
		);

		this.server.tool(
			"eigentuemer_setzen",
			"Verknuepft einen bestehenden Kontakt als Eigentuemer mit einem Projekt und prueft die Verknuepfung nach.",
			{ projekt_id: z.number().int(), kontakt_id: z.number().int() },
			async ({ projekt_id, kontakt_id }) => sicher(async () => ({ projekt_id, kontakt_id, bestaetigt: await ps.eigentuemerSetzen(projekt_id, kontakt_id) })),
		);

		this.server.tool(
			"bemerkung_ergaenzen",
			"Stellt einen Eintrag vor die interne Bemerkung einer Einheit. Der alte Text bleibt als Historie erhalten - nie ueberschreiben.",
			{ id: z.number().int(), text: z.string() },
			async ({ id, text }) => sicher(async () => ({ id, gespeichert: await ps.bemerkungErgaenzen(id, `- Stand ${heute()} (${wer}, ueber MCP): ${text}`) })),
		);

		this.server.tool(
			"bild_hochladen",
			"Laedt ein Bild an eine Einheit oder ein Projekt. Vorher pruefen: keine Firmenschriftzuege auf dem Bild (Wissensdatenbank 1.10) - Logos wegschneiden oder wegretuschieren. Grundrisse als solche kennzeichnen, Bilder sinnvoll betiteln. Quelle: oeffentliche URL oder Base64.",
			{
				ziel: z.enum(["einheit", "projekt"]),
				id: z.number().int(),
				titel: z.string(),
				grundriss: z.boolean(),
				url: z.string().url().optional(),
				base64: z.string().optional(),
				mime: z.string().default("image/jpeg"),
				keine_schriftzuege_bestaetigt: z.literal(true).describe("Bestaetigung, dass das Bild auf Firmenschriftzuege geprueft ist"),
			},
			async ({ ziel, id, titel, grundriss, url, base64, mime }) =>
				sicher(async () => {
					let blob: Blob;
					if (url) {
						const r = await fetch(url);
						if (!r.ok) throw new Error(`Bild nicht ladbar: HTTP ${r.status}`);
						blob = await r.blob();
					} else if (base64) {
						const bin = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
						blob = new Blob([bin], { type: mime });
					} else throw new Error("url oder base64 angeben");
					return ps.bildHochladen(ziel === "projekt" ? "Project" : "Property", id, blob, `${titel.replace(/[^\w-]+/g, "_")}.jpg`, titel, grundriss);
				}),
		);

		this.server.tool(
			"pruefaufgabe_anlegen",
			"Legt die Pruefungsaufgabe nach einer Anlage oder Aenderung an - immer an Lena Klinnert. Inhalt: Quelle, was geaendert wurde, Widersprueche, bewusst leer gelassene Felder, manuell Nachzuholendes. Umlaute werden automatisch umgeschrieben.",
			{
				titel: z.string(),
				absaetze: z.array(z.string()).describe("Je Absatz ein Punkt; einfaches HTML wie <b> erlaubt"),
				faellig: z.string().describe("ISO-Datum, z. B. 2026-10-01T09:00:00"),
				projekte: z.array(z.number().int()).default([]),
				einheiten: z.array(z.number().int()).default([]),
			},
			async ({ titel, absaetze, faellig, projekte, einheiten }) =>
				sicher(async () => {
					const text = absaetze.map((a) => `<p>${ascii(a)}</p>`).join("") + `<p><i>Angelegt ueber MCP durch ${ascii(wer)}.</i></p>`;
					return ps.aufgabeAnlegen({ titel: ascii(titel), text, bearbeiter: BROKER_PRUEFER, faellig, projekte, einheiten });
				}),
		);

		this.server.tool(
			"deals_aktualisieren",
			"Verschiebt Deals in eine Pipeline/Stufe und setzt den Betreuer. Loeschen gibt es nicht - Dubletten dem User zum Loeschen in der UI melden.",
			{
				deal_ids: z.array(z.number().int()).max(500),
				pipeline_id: z.number().int().optional(),
				stufe_id: z.number().int().optional(),
				betreuer_id: z.number().int().optional(),
			},
			async ({ deal_ids, pipeline_id, stufe_id, betreuer_id }) =>
				sicher(async () => {
					const soll = { deal_pipeline_id: pipeline_id, deal_stage_id: stufe_id, broker_id: betreuer_id };
					const felder = Object.fromEntries(Object.entries(soll).filter(([, v]) => v !== undefined));
					const falsch: Json[] = [];
					for (const id of deal_ids) {
						const r = await ps.dealAktualisieren(id, felder);
						for (const [k, v] of Object.entries(felder)) if ((r as Json)[k] !== v) falsch.push({ id, feld: k, ist: (r as Json)[k] });
					}
					return { aktualisiert: deal_ids.length, abweichungen: falsch };
				}),
		);
	}
}

export default new OAuthProvider({
	apiHandler: PropstackMCP.serve("/mcp"),
	apiRoute: "/mcp",
	authorizeEndpoint: "/authorize",
	clientRegistrationEndpoint: "/register",
	defaultHandler: { fetch: handleAccessRequest as any },
	tokenEndpoint: "/token",
});
