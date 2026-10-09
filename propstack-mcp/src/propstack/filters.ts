import { z } from "zod";
import type { Query } from "../propstack-client";

// Eingabeschemas und Übersetzung in Propstack-V1-Parameter (laut docs.propstack.de).

const id = z.number().int().positive();
const ids = z.array(id).min(1).max(50);
const date = z
	.string()
	.regex(/^\d{4}-\d{2}-\d{2}$/, "Datum im Format JJJJ-MM-TT")
	.describe("Datum JJJJ-MM-TT");
const archived = z
	.enum(["exclude", "include", "only"])
	.optional()
	.describe("Archivierte: exclude (Standard), include oder only");

/** Offset von Europe/Berlin an einem Datum, z. B. "+02:00". */
export function berlinOffset(isoDate: string): string {
	const probe = new Date(`${isoDate}T12:00:00Z`);
	const parts = new Intl.DateTimeFormat("en-US", {
		hour: "2-digit",
		hourCycle: "h23",
		timeZone: "Europe/Berlin",
	}).formatToParts(probe);
	const hour = Number(parts.find((p) => p.type === "hour")?.value ?? "13");
	const diff = hour - 12;
	return `${diff >= 0 ? "+" : "-"}${String(Math.abs(diff)).padStart(2, "0")}:00`;
}

/** Tagesgrenzen in deutscher Zeit im von Propstack verlangten Format. */
export function dayStart(isoDate: string): string {
	return `${isoDate}T00:00:00${berlinOffset(isoDate)}`;
}
export function dayEnd(isoDate: string): string {
	return `${isoDate}T23:59:59${berlinOffset(isoDate)}`;
}

function archivedParam(value: "exclude" | "include" | "only" | undefined): string | undefined {
	if (value === "include") return "-1";
	if (value === "only") return "1";
	return undefined;
}

const orUndefined = <T>(value: T | undefined, fn: (v: T) => string) => (value === undefined ? undefined : fn(value));

// ---------- Kontakte ----------

export const contactFilterShape = {
	query: z.string().min(1).max(200).optional().describe("Volltext: Name, E-Mail, Anschrift, Telefon"),
	email: z.string().max(200).optional().describe("Exakte E-Mail"),
	phone: z.string().max(50).optional().describe("Exakte Telefonnummer (Leerzeichen/Bindestriche egal)"),
	tag_ids: ids.optional().describe("Kontakt muss diese Merkmal-IDs haben (IDs über list_tags)"),
	exclude_tag_ids: ids.optional().describe("Kontakt darf diese Merkmal-IDs nicht haben"),
	source_ids: ids.optional().describe("Kontakt-Quellen-IDs (über list_reference kind=contact_sources)"),
	broker_id: id.optional().describe("Betreuer (Propstack-Nutzer-ID, über list_reference kind=users)"),
	project_ids: ids.optional().describe("Mit diesen Projekten verknüpft"),
	gdpr_status: z.enum(["keine_angabe", "ignoriert", "zugestimmt", "widerrufen"]).optional(),
	newsletter: z.boolean().optional(),
	owner: z.boolean().optional().describe("Nur Eigentümer"),
	created_from: date.optional(),
	created_to: date.optional(),
	updated_from: date.optional(),
	updated_to: date.optional(),
	archived,
};
export const contactFilters = z.object(contactFilterShape);
export type ContactFilters = z.infer<typeof contactFilters>;

const GDPR_CODES = { ignoriert: 1, keine_angabe: 0, widerrufen: 3, zugestimmt: 2 } as const;

export function contactQuery(f: ContactFilters): Query {
	return {
		archived: archivedParam(f.archived),
		created_at_from: orUndefined(f.created_from, dayStart),
		created_at_to: orUndefined(f.created_to, dayEnd),
		email: f.email,
		gdpr_status: f.gdpr_status === undefined ? undefined : GDPR_CODES[f.gdpr_status],
		group: f.tag_ids,
		newsletter: f.newsletter,
		not_in_group: f.exclude_tag_ids,
		owner: f.owner,
		phone_number: f.phone,
		project_ids: f.project_ids,
		q: f.query,
		sources: f.source_ids,
		updated_at_from: orUndefined(f.updated_from, dayStart),
		updated_at_to: orUndefined(f.updated_to, dayEnd),
		broker_id: f.broker_id,
	};
}

// ---------- Objekte ----------

const range = (label: string) => ({
	from: z.number().nonnegative().optional().describe(`${label} ab`),
	to: z.number().nonnegative().optional().describe(`${label} bis`),
});

export const objectFilterShape = {
	query: z.string().min(1).max(200).optional().describe("Volltext: Einheitennr., Straße, PLZ, Ort, Bezirk, Exposé-ID"),
	status_ids: ids.optional().describe("Objekt-Status-IDs (über list_reference kind=object_statuses)"),
	tag_ids: ids.optional().describe("Objekt hat eines dieser Merkmale (IDs über list_tags entity=objects)"),
	marketing_type: z.enum(["BUY", "RENT"]).optional().describe("BUY = Kauf, RENT = Miete"),
	rs_type: z.string().regex(/^[A-Z_]+$/).optional().describe("Objektart, z. B. HOUSE, APARTMENT, OFFICE, INDUSTRY, INVEST_HALL_STORAGE"),
	project_id: id.optional(),
	object_ids: ids.optional().describe("Nur diese Propstack-Objekt-IDs"),
	country: z.string().regex(/^[A-Z]{2}$/).optional().describe("ISO-Code, z. B. DE"),
	price: z.object(range("Kaufpreis")).optional(),
	base_rent: z.object(range("Kaltmiete")).optional(),
	area: z.object(range("Fläche m²")).optional(),
	living_space: z.object(range("Wohnfläche m²")).optional(),
	plot_area: z.object(range("Grundstücksfläche m²")).optional(),
	rooms: z.object(range("Zimmer")).optional(),
	archived,
};
export const objectFilters = z.object(objectFilterShape);
export type ObjectFilters = z.infer<typeof objectFilters>;

type Range = { from?: number; to?: number } | undefined;
function rangeParams(name: string, r: Range): Query {
	return r ? { [`${name}_from`]: r.from, [`${name}_to`]: r.to } : {};
}

export function objectQuery(f: ObjectFilters): Query {
	return {
		archived: archivedParam(f.archived),
		country: f.country,
		// /units verlangt laut Doku kommagetrennte Listen
		group: f.tag_ids?.join(","),
		marketing_type: f.marketing_type,
		project_id: f.project_id,
		property_ids: f.object_ids?.join(","),
		q: f.query,
		rs_type: f.rs_type,
		status: f.status_ids?.join(","),
		...rangeParams("price", f.price),
		...rangeParams("base_rent", f.base_rent),
		...rangeParams("property_space_value", f.area),
		...rangeParams("living_space", f.living_space),
		...rangeParams("plot_area", f.plot_area),
		...rangeParams("number_of_rooms", f.rooms),
	};
}

// ---------- Deals ----------

export const dealFilterShape = {
	pipeline_id: id.optional().describe("Deal-Pipeline-ID (über pipeline_status ohne ID)"),
	stage_ids: ids.optional().describe("Nur diese Deal-Phasen-IDs"),
	category: z.enum(["qualified", "unqualified", "lost"]).optional(),
	contact_id: id.optional().describe("Deals eines Kontakts"),
	object_id: id.optional().describe("Deals (Interessenten) eines Objekts"),
	project_id: id.optional(),
	broker_id: id.optional().describe("Besitzer des Deals"),
	created_from: date.optional(),
	created_to: date.optional(),
};
export const dealFilters = z.object(dealFilterShape);
export type DealFilters = z.infer<typeof dealFilters>;

export function dealQuery(f: DealFilters): Query {
	return {
		broker_id: f.broker_id,
		category: f.category,
		client_id: f.contact_id,
		created_at_from: orUndefined(f.created_from, dayStart),
		created_at_to: orUndefined(f.created_to, dayEnd),
		deal_pipeline_id: f.pipeline_id,
		deal_stage_ids: f.stage_ids,
		project_id: f.project_id,
		property_id: f.object_id,
	};
}

// ---------- Paginierung ----------

export const paginationShape = {
	page: z.number().int().min(1).max(1000).optional().describe("Seite, Standard 1"),
	per_page: z.number().int().min(1).max(50).optional().describe("Treffer pro Seite, Standard 20, max. 50"),
};
