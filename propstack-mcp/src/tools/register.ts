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
import { type ZodRawShape, z } from "zod";

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
		server.registerTool(name, { annotations: READ_ONLY, description, inputSchema: shape }, (async (input: z.infer<z.ZodObject<S>>) =>
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
		{ id: z.number().int().positive().describe("Propstack-Kontakt-ID") },
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
		"Ein Objekt mit Details abrufen: Adresse, Eckdaten, Status, Betreuer, Projekt, Merkmale, Beschreibungstexte (gekürzt) und befüllte Custom-Felder.",
		{ id: z.number().int().positive().describe("Propstack-Objekt-ID") },
		getObject,
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
