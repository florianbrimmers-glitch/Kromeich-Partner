import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { writeAuditEntry } from "../audit";
import type { Props } from "../auth/session";
import { PropstackClient, PropstackError } from "../propstack-client";
import { paginationShape } from "../propstack/filters";
import {
	aggregate,
	aggregateInput,
	getContact,
	getObject,
	getObjectInput,
	getProject,
	getProjectInput,
	listFields,
	listFieldsInput,
	listReference,
	listReferenceInput,
	listTags,
	listTagsInput,
	pipelineStatus,
	pipelineStatusInput,
	searchContacts,
	searchContactsInput,
	searchDeals,
	searchDealsInput,
	searchObjects,
	searchObjectsInput,
	type ToolOutput,
} from "./read-tools";
import {
	createContact,
	createContactInput,
	createObject,
	createObjectInput,
	TEST_TAG,
	updateContact,
	updateContactInput,
	updateObject,
	updateObjectInput,
} from "./write-tools";
import { imageUploadUrl, imageUploadUrlInput } from "../image-upload";
import { applyPlan, MAX_PLAN_ITEMS, planBulk, planBulkInput, planIdInput, undoPlan } from "./bulk-tools";
import {
	addImages,
	addImagesInput,
	createProject,
	createProjectInput,
	setProjectOwner,
	setProjectOwnerInput,
	updateProject,
	updateProjectInput,
} from "./project-tools";
import { type ZodRawShape, z } from "zod";
import { id } from "./params";

export interface ToolContext {
	env: Env;
	props: () => Props;
	/** Für Tests austauschbar. */
	createClient?: () => PropstackClient;
	now?: () => number;
}

type ToolResult = { content: { type: "text"; text: string }[]; isError?: boolean };

/** Fehler für Claude lesbar machen, ohne Interna preiszugeben. */
export function errorMessage(error: unknown): string {
	if (error instanceof PropstackError) return error.message;
	return "Interner Fehler im Propstack-Connector.";
}

/**
 * Führt ein Tool aus: frischer Client (Request-Budget je Aufruf), Audit-Eintrag,
 * kompakte JSON-Antwort bzw. isError mit verständlicher Meldung.
 */
export async function runTool(
	ctx: ToolContext,
	tool: string,
	params: unknown,
	fn: (client: PropstackClient) => Promise<ToolOutput>,
): Promise<ToolResult> {
	const now = ctx.now ?? Date.now;
	const started = now();
	const props = ctx.props();
	let output: ToolOutput | undefined;
	let failure: unknown;
	try {
		const client = ctx.createClient ? ctx.createClient() : new PropstackClient({ apiKey: ctx.env.PROPSTACK_API_KEY });
		output = await fn(client);
	} catch (error) {
		failure = error;
		if (!(error instanceof PropstackError)) console.error(`Tool ${tool} fehlgeschlagen`, error);
	}

	await writeAuditEntry(ctx.env.AUDIT_DB, {
		brokerId: props.brokerId,
		durationMs: now() - started,
		error: failure === undefined ? null : errorMessage(failure),
		ok: failure === undefined,
		params,
		resultCount: output?.count ?? null,
		tool,
		ts: new Date(started).toISOString(),
		userEmail: props.email,
	});

	if (failure !== undefined || !output) {
		return { content: [{ text: errorMessage(failure), type: "text" }], isError: true };
	}
	return { content: [{ text: JSON.stringify(output.result), type: "text" }] };
}

const READ_ONLY = { readOnlyHint: true, openWorldHint: false } as const;

export function registerReadTools(server: McpServer, ctx: ToolContext): void {
	const register = <S extends ZodRawShape>(
		name: string,
		description: string,
		shape: S,
		fn: (client: PropstackClient, input: z.infer<z.ZodObject<S>>) => Promise<ToolOutput>,
	) => {
		server.registerTool(name, { annotations: READ_ONLY, description, inputSchema: z.strictObject(shape) }, (async (input: z.infer<z.ZodObject<S>>) =>
			runTool(ctx, name, input, (client) => fn(client, input))) as never);
	};

	register(
		"search_contacts",
		"Kontakte in Propstack suchen (Personen und Firmen). Liefert eine gekürzte Trefferliste mit Gesamtzahl und Betreuername. Mehrere Merkmale: tag_match=any (mindestens eines, Standard) oder all (alle gleichzeitig). Merkmal-, Quellen- und Nutzer-IDs vorher über list_tags bzw. list_reference holen. Hinweis: last_contact_at kann in der Zukunft liegen, wenn Termine geplant sind.",
		{ ...searchContactsInput, ...paginationShape },
		searchContacts,
	);
	register(
		"get_contact",
		"Einen Kontakt mit Details abrufen: Kontaktdaten, Adressen, Betreuer, Merkmale, befüllte Custom-Felder, DSGVO-Status. Sensible Daten wie Ausweis- und Steuernummer oder Geburtsdaten werden nicht ausgegeben.",
		{ id: id.describe("Propstack-Kontakt-ID") },
		getContact,
	);
	register(
		"search_objects",
		"Objekte (Einheiten) in Propstack suchen. Für Orte immer city bzw. zip_prefix nutzen, query ist eine unscharfe Volltextsuche. Weitere Filter: Status, Vermarktungsart, Objektart, Merkmale (tag_match any/all), Preis- und Flächenbereiche. Liefert eine gekürzte Trefferliste mit Gesamtzahl. Bei Statusfilter wird gemeldet, wie viele passende Objekte keinen Status haben.",
		{ ...searchObjectsInput, ...paginationShape },
		searchObjects,
	);
	register(
		"get_object",
		"Ein Objekt mit Details abrufen: Adresse, Eckdaten, Status, Betreuer, Projekt, Merkmale, Beschreibungstexte (gekürzt), befüllte Custom-Felder und Bilder mit Titel (zum Prüfen, ob sie benannt sind).",
		getObjectInput,
		getObject,
	);
	register(
		"get_project",
		"Ein Projekt mit Details abrufen: Name, Überschrift, Unterzeile, Adresse, Koordinaten, Provision, Exposé-Texte (gekürzt), Bilder mit Titel, Links und die Einheiten des Projekts (ID, Einheitennummer, Status). Zum Prüfen vor und nach Änderungen.",
		getProjectInput,
		getProject,
	);
	register(
		"search_deals",
		"Deals (Interessent ↔ Objekt in einer Pipeline-Phase) suchen, z. B. alle Deals eines Kontakts, eines Objekts, einer Phase oder eines Betreuers. Liefert Phase, Kontakt, Objekt, Preis und Notiz.",
		{ ...searchDealsInput, ...paginationShape },
		searchDeals,
	);
	register(
		"pipeline_status",
		"Ohne pipeline_id: alle Deal-Pipelines mit ihren Phasen. Mit pipeline_id: Stand der Pipeline je Phase – Anzahl Deals, Summe Preis und gewichteter Wert (Preis × in Propstack hinterlegte Phasen-Wahrscheinlichkeit), optional gefiltert. Deals ohne Phase werden separat gezählt; ohne gepflegte Deal-Preise gibt es keine Summen.",
		pipelineStatusInput,
		pipelineStatus,
	);
	register(
		"list_tags",
		"Merkmale (Tags) für Kontakte, Objekte oder Aktivitäten auflisten, gruppiert nach Obermerkmal – mit IDs für Filter in den Such-Tools.",
		listTagsInput,
		listTags,
	);
	register(
		"list_fields",
		"Custom-Felder für Kontakte, Objekte, Deals oder Projekte auflisten (Schlüssel, Bezeichnung, Typ, Auswahlwerte).",
		listFieldsInput,
		listFields,
	);
	register(
		"list_reference",
		"Stammdaten mit IDs: Objekt-Status, Kontakt-Quellen, Nutzer (Makler) oder Projekte. Für Filter in Such- und Auswertungs-Tools.",
		listReferenceInput,
		listReference,
	);
	register(
		"aggregate",
		"Auswertungen: zählt Kontakte, Objekte oder Deals gruppiert nach einer Dimension, mit den Filtern der Such-Tools (Merkmale nur mit ODER, ohne city/zip_prefix). Deals nach Phase liefern zusätzlich Summe Preis und gewichteten Wert.",
		aggregateInput,
		aggregate,
	);
}

export function registerWriteTools(server: McpServer, ctx: ToolContext): void {
	const register = <S extends ZodRawShape>(
		name: string,
		description: string,
		shape: S,
		destructive: boolean,
		fn: (
			deps: { client: PropstackClient; db: D1Database | undefined; user: Props; kv: KVNamespace | undefined },
			input: z.infer<z.ZodObject<S>>,
		) => Promise<ToolOutput>,
	) => {
		server.registerTool(
			name,
			{
				annotations: { destructiveHint: destructive, idempotentHint: false, openWorldHint: false, readOnlyHint: false },
				description,
				// strict: unbekannte Parameter (z. B. aus einer veralteten Tool-Liste) abweisen statt still verwerfen
				inputSchema: z.strictObject(shape),
			},
			(async (input: z.infer<z.ZodObject<S>>) =>
				runTool(ctx, name, input, (client) => fn({ client, db: ctx.env.AUDIT_DB, kv: ctx.env.OAUTH_KV, user: ctx.props() }, input))) as never,
		);
	};

	const objectRules =
		"Regeln (Team-How-to und Feld-Mapping): Einheiten im Projekt übernehmen Adresse, Überschrift, Beschreibung, Lage, Ausstattung, Provision und Koordinaten vom Projekt – dort nur unit_id, Objektart, Flächen, Ausstattungsfelder und Abweichungen angeben. Die im How-to genannten Felder haben eigene Parameter (teilbar ab, Mezzanine, Stellplätze, Rampentore, ebenerdige Tore, WGK, Beleuchtung, Sprinkler, Heizung, Zertifizierung). Mietpreise intern in internal_rent_*; ÖFFENTLICHE Preise (price, base_rent, mietpreis_*, Preise in Texten) nur, wenn der Nutzer es ausdrücklich ansagt oder auf Nachfrage bestätigt – dann public_price_confirmed: true; sonst „Preis auf Anfrage“. Exposé-Texte ohne Eigentümernamen, Adresse und Preise, Ausstattung als Liste – Verstöße werden abgewiesen. Interna in source_link, mandate, internal_commission und bemerkung_append. provisionspflichtig nie setzen. Kritische Felder (rs_category, Flächen, Hallenhöhe, Bodentragkraft, Status, rented, Betreuer) werden einzeln geschrieben und zurückgelesen. Aus dem Ergebnis dem Nutzer melden: not_applied, not_verifiable, write_errors, text_warnings und howto_not_provided (was laut How-to wichtig ist, aber fehlt – nachfragen oder im Exposé nachsehen).";
	const rules = `Betreuer wird immer der angemeldete Nutzer. Testdaten immer mit test=true anlegen (Merkmal ${TEST_TAG}). Es gibt keine Lösch-Funktion.`;
	const commissionRules =
		"Provision: commission=provisionsfrei oder staffel setzt die Standardtexte. Feste Regeln (Wissensdatenbank, Stand 09/2026): Mileway immer provisionsfrei; Scheren Logistik provisionspflichtig, auch wenn deren Exposé „provisionsfrei“ nennt.";
	register(
		"create_contact",
		`Kontakt (Person) in Propstack anlegen. Vorher automatische Dublettenprüfung: gleiche E-Mail blockiert immer, ohne persönliche E-Mail blockieren gleiche Mobilnummer oder gleicher Name + Firma; allgemeine Adressen (info@ …) und gleiche Festnetznummern erzeugen nur Warnungen. Bei Dublette nichts anlegen, sondern den Nutzer fragen und ggf. update_contact nutzen. ${rules}`,
		createContactInput,
		false,
		createContact,
	);
	register(
		"update_contact",
		"Vorhandenen Kontakt ändern: Kontaktdaten, Adresse, Merkmale hinzufügen/entfernen (taggen), Notiz ergänzen (wird angehängt, nie ersetzt), Custom-Felder. Nur geänderte Werte werden geschrieben, der vorherige Stand wird gesichert.",
		updateContactInput,
		true,
		updateContact,
	);
	const review = "Danach entsteht automatisch eine Prüfaufgabe an Lena (bei test=true an dich), fällig am nächsten Werktag 9:00 – mit Link, allen Lücken und den Schritten, die nur in Propstack selbst gehen.";
	register(
		"create_object",
		`Objekt (Einzelobjekt oder Einheit eines Projekts) in Propstack anlegen. Einzelobjekt: eine einzelne vermietbare Fläche – im Zweifel Einzelobjekt statt Projekt. Vorher Dublettenprüfung über Adresse bzw. Geokoordinaten + Vermarktungsart + Einheit (blockiert); gleiche Adresse mit anderer Vermarktungsart oder Einheit ist nur ein Hinweis. Eigentümer (owner_contact_id) und Ansprechpartner (contact_person_id) werden verknüpft. ${objectRules} ${commissionRules} ${review} Bei Einheiten im Projekt entsteht eine eigene Aufgabe nur bei Problemen. ${rules}`,
		createObjectInput,
		false,
		createObject,
	);
	register(
		"update_object",
		`Vorhandenes Objekt ändern: Eckdaten, Status, Vermietet, Aktiv, Flächen, Ausstattungsfelder, Provision, Texte, interne Bemerkung (angehängt), Custom-Felder, Koordinaten (lat+lng). Nur geänderte Werte werden geschrieben, der vorherige Stand wird gesichert. Bei Adress-/Einheiten-/Vermarktungsänderung erneute Dublettenprüfung. Eigentümer/Ansprechpartner: set_project_owner. ${objectRules} ${commissionRules}`,
		updateObjectInput,
		true,
		updateObject,
	);
	register(
		"create_project",
		`Projekt (Standort mit Einheiten) in Propstack anlegen – nur wenn es tatsächlich mindestens zwei getrennt vermietbare Einheiten gibt; eine einzelne Fläche ist ein Einzelobjekt (create_object ohne project_id). Vorher Dublettenprüfung über die Adresse. Nach Team-How-to: Name „Logistikhalle in (XX) Ort“ (Überschrift gleich), Unterzeile, interne Notiz (source_link, mandate, internal_rents, internal_commission, developer_project_name), Eigentümer und Ansprechpartner verknüpfen, Provision, Projektbeschreibung, Lage, Ausstattung. Exposé-Texte ohne Eigentümernamen, Adresse und Preise – Verstöße werden abgewiesen. ${commissionRules} Danach die Einheiten mit create_object + project_id. ${review} Aus dem Ergebnis dem Nutzer melden: not_applied, text_warnings, howto_not_provided, ui_steps. ${rules}`,
		createProjectInput,
		false,
		createProject,
	);
	register(
		"update_project",
		`Vorhandenes Projekt ändern: Name, Überschrift, Unterzeile, Adresse, Provision (commission bzw. courtage/courtage_note), Exposé-Texte, Adresse ausblenden, Koordinaten (lat+lng, Stufen-Trick). Nur geänderte Werte werden geschrieben, der vorherige Stand wird gesichert, verworfene Felder einzeln nachgesetzt. Bei Adressänderung Dublettenprüfung. Geänderte Texte und Provision kommen NICHT von selbst an den Einheiten an – danach laut units_hint übertragen. Eigentümer/Ansprechpartner: set_project_owner. ${commissionRules} Es gibt keine Lösch-Funktion.`,
		updateProjectInput,
		true,
		updateProject,
	);
	register(
		"set_project_owner",
		"Kontakt (aus dem eigenen Shop) mit einem Projekt (project_id) oder einer Einheit (object_id) verknüpfen – als Eigentümer (Standard) oder mit role=contact_person als Ansprechpartner. Vorhandene Verknüpfungen bleiben bestehen. Ergebnis linked: true/false/„nicht prüfbar“.",
		setProjectOwnerInput,
		false,
		setProjectOwner,
	);
	register(
		"add_images",
		"Bilder per öffentlicher https-URL an ein Objekt oder Projekt hängen (Propstack lädt sie selbst). Jede URL wird vorher geprüft (erreichbar, wirklich ein Bild). Mit titles benennen (z. B. „Außenansicht“) – Bilder müssen in Propstack benannt sein. Das erste Bild eines Objekts wird Titelbild – bestes Außenfoto zuerst. Allgemeine Bilder (Außenansicht des Standorts) gehören ans Projekt. Bilder aus dem Chat-Upload gehen NICHT, nur URLs – dafür image_upload_url. Keine Firmenschriftzüge, Bildrechte beachten.",
		addImagesInput,
		false,
		addImages,
	);
	register(
		"image_upload_url",
		"Bilder als DATEI hochladen (Claude Code / Cowork): liefert eine Einmal-Upload-Adresse für ein Objekt oder Projekt (15 min gültig, an dich und dieses Ziel gebunden). Danach die Dateien selbst per curl hochladen, je Bild mit Titel: curl -sS -F \"image[photo]=@bild1.jpg\" -F \"title=Außenansicht\" -F \"image[photo]=@bild2.jpg\" -F \"title=Halle innen\" \"<upload_url>\" – Reihenfolge = Reihenfolge in Propstack, das erste Bild wird Titelbild. Bilder müssen benannt sein (kein Firmen- oder Eigentümername im Titel), keine Firmenschriftzüge; allgemeine Bilder ans Projekt, Grundrisse danach in Propstack kennzeichnen. Die curl-Antwort enthält die Bild-IDs; dem Nutzer melden. JPEG/PNG/WebP, max. 15 MB je Bild. Für Bilder, die nur als URL vorliegen: add_images.",
		imageUploadUrlInput,
		false,
		imageUploadUrl,
	);
	register(
		"plan",
		`Massenänderung PLANEN (ändert noch nichts): Kontakte oder Objekte per ID-Liste oder Filter (wie search_contacts/search_objects) auswählen, Änderung festlegen – Kontakte: Merkmale hinzufügen/entfernen, Betreuer, Quelle, Kontaktstatus, Custom-Felder; Objekte: Status, vermietet, Provision und Exposé-Texte (z. B. vom Projekt auf alle Einheiten übertragen: object_filter {project_id}), Custom-Felder (keine Merkmale). Liefert plan_id, Anzahl und Vorschau; max. ${MAX_PLAN_ITEMS} Datensätze. Danach dem Nutzer die Vorschau zeigen und ausdrücklich bestätigen lassen – erst dann apply_plan. Die plan_id verfällt nach 10 Minuten.`,
		planBulkInput,
		false,
		planBulk,
	);
	register(
		"apply_plan",
		"Bestätigten Plan AUSFÜHREN. Nur nach ausdrücklicher Bestätigung durch den Nutzer und nur durch den, der geplant hat. Je Datensatz dieselben Regeln, Prüfungen und Write-Log wie update_contact/update_object. Läuft in Etappen: solange remaining > 0, erneut mit derselben plan_id aufrufen (ohne erneute Rückfrage). Rückgängig 7 Tage lang mit undo_plan.",
		planIdInput,
		true,
		applyPlan,
	);
	register(
		"undo_plan",
		"Ausgeführten Plan RÜCKGÄNGIG machen (bis 7 Tage danach). Stellt je Datensatz den Stand vorher her – aber nur Felder, die seitdem niemand anders geändert hat; diese werden übersprungen und gemeldet. Bemerkungen werden nie zurückgesetzt. Läuft in Etappen wie apply_plan.",
		planIdInput,
		true,
		undoPlan,
	);
}
