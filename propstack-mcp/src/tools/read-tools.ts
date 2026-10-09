import { z } from "zod";
import { AGGREGATE_MAX_GROUPS, DEAL_MAX_PAGES, DEAL_PAGE_SIZE } from "../config";
import { type CustomFieldEntity, type GroupEntity, type Page, PropstackClient, PropstackError, type Query } from "../propstack-client";
import {
	type ContactFilters,
	contactFilters,
	contactQuery,
	type DealFilters,
	dealFilters,
	dealQuery,
	type ObjectFilters,
	objectFilters,
	objectQuery,
} from "../propstack/filters";
import {
	compact,
	dealPrice,
	mapContactDetail,
	mapContactSummary,
	mapDeal,
	mapUnitDetail,
	mapUnitSummary,
	scalar,
	type StageInfo,
	stageIndex,
} from "../propstack/mappers";

// Lese-Tools (Phase 2). Jede Funktion liefert das gekürzte Ergebnis und eine
// Trefferzahl fürs Audit-Log. Kein Tool schreibt nach Propstack.

type Raw = Record<string, unknown>;
export interface ToolOutput {
	result: unknown;
	count: number | null;
}

type Client = Pick<
	PropstackClient,
	| "listBrokers"
	| "searchContacts"
	| "getContact"
	| "searchUnits"
	| "getUnit"
	| "searchDeals"
	| "listDealPipelines"
	| "listGroups"
	| "listSuperGroups"
	| "listCustomFieldGroups"
	| "listPropertyStatuses"
	| "listContactSources"
	| "listProjects"
>;

const SORT_ORDER = z.enum(["asc", "desc"]).optional();

function pageParams(input: { page?: number; per_page?: number }) {
	return { page: input.page ?? 1, per: input.per_page ?? 20 };
}

function pageResult(page: Page, items: unknown[], params: { page: number; per: number }) {
	return {
		total: page.total ?? undefined,
		page: params.page,
		per_page: params.per,
		has_more: page.total !== null ? params.page * params.per < page.total : items.length === params.per,
		items,
	};
}

function asObject(value: unknown): Raw {
	if (!value || typeof value !== "object" || Array.isArray(value)) {
		throw new PropstackError("Unerwartete Antwort von Propstack", 0);
	}
	return value as Raw;
}

// ---------- Kontakte ----------

export const searchContactsInput = {
	...contactFilters.shape,
	sort_by: z.enum(["last_contact_at", "created_at", "updated_at", "first_name", "last_name"]).optional(),
	order: SORT_ORDER,
};

export async function searchContacts(
	client: Client,
	input: ContactFilters & { sort_by?: string; order?: "asc" | "desc"; page?: number; per_page?: number },
): Promise<ToolOutput> {
	const params = pageParams(input);
	const page = await client.searchContacts({ ...contactQuery(input), order: input.order, sort_by: input.sort_by, ...params });
	const items = page.rows.map(mapContactSummary);
	return { count: page.total ?? items.length, result: pageResult(page, items, params) };
}

export async function getContact(client: Client, input: { id: number }): Promise<ToolOutput> {
	return { count: 1, result: mapContactDetail(asObject(await client.getContact(input.id))) };
}

// ---------- Objekte ----------

export const searchObjectsInput = {
	...objectFilters.shape,
	sort_by: z
		.enum(["created_at", "price", "base_rent", "property_space_value", "plot_area", "construction_year", "exposee_id", "unit_id.raw"])
		.optional(),
	order: SORT_ORDER,
};

export async function searchObjects(
	client: Client,
	input: ObjectFilters & { sort_by?: string; order?: "asc" | "desc"; page?: number; per_page?: number },
): Promise<ToolOutput> {
	const params = pageParams(input);
	const page = await client.searchUnits({ ...objectQuery(input), order: input.order, sort_by: input.sort_by, ...params });
	const items = page.rows.map(mapUnitSummary);
	return { count: page.total ?? items.length, result: pageResult(page, items, params) };
}

export async function getObject(client: Client, input: { id: number }): Promise<ToolOutput> {
	return { count: 1, result: mapUnitDetail(asObject(await client.getUnit(input.id))) };
}

// ---------- Deals ----------

export const searchDealsInput = {
	...dealFilters.shape,
	sort_by: z.enum(["created_at", "start_date"]).optional(),
	order: SORT_ORDER,
};

async function stages(client: Client): Promise<{ pipelines: Raw[]; index: Map<number, StageInfo> }> {
	const pipelines = (await client.listDealPipelines()).rows;
	return { index: stageIndex(pipelines), pipelines };
}

export async function searchDeals(
	client: Client,
	input: DealFilters & { sort_by?: string; order?: "asc" | "desc"; page?: number; per_page?: number },
): Promise<ToolOutput> {
	const params = pageParams(input);
	const { index } = await stages(client);
	const page = await client.searchDeals({
		...dealQuery(input),
		include: "client,property",
		order: input.order,
		sort_by: input.sort_by,
		...params,
	});
	const items = page.rows.map((row) => mapDeal(row, index));
	return { count: page.total ?? items.length, result: pageResult(page, items, params) };
}

/** Alle Deals zu einem Filter laden (für Wertsummen), mit Seitenbudget. */
async function loadAllDeals(client: Client, query: Query): Promise<{ rows: Raw[]; complete: boolean; total: number | null }> {
	const rows: Raw[] = [];
	let total: number | null = null;
	for (let page = 1; page <= DEAL_MAX_PAGES; page++) {
		const result = await client.searchDeals({ ...query, page, per: DEAL_PAGE_SIZE });
		total = result.total ?? total;
		rows.push(...result.rows);
		if (result.rows.length < DEAL_PAGE_SIZE || (total !== null && rows.length >= total)) {
			return { complete: true, rows, total };
		}
	}
	return { complete: false, rows, total };
}

const round = (n: number) => Math.round(n * 100) / 100;

/** Deals einer Pipeline je Phase: Anzahl, Summe Preis, gewichteter Wert (Preis × Chance). */
async function dealsByStage(client: Client, pipeline: Raw, filters: DealFilters) {
	const pipelineId = pipeline.id as number;
	const stageList = (Array.isArray(pipeline.deal_stages) ? (pipeline.deal_stages as Raw[]) : [])
		.filter((s) => typeof s.id === "number")
		.sort((a, b) => Number(a.position ?? 0) - Number(b.position ?? 0));
	const { rows, complete, total } = await loadAllDeals(client, { ...dealQuery(filters), deal_pipeline_id: pipelineId });

	const byStage = new Map<number, { count: number; sum: number; withoutPrice: number }>();
	for (const row of rows) {
		const stageId = row.deal_stage_id as number;
		const bucket = byStage.get(stageId) ?? { count: 0, sum: 0, withoutPrice: 0 };
		bucket.count++;
		const price = dealPrice(row);
		if (price === null) bucket.withoutPrice++;
		else bucket.sum += price;
		byStage.set(stageId, bucket);
	}

	const totals = { count: 0, sum_price: 0, weighted_value: 0 };
	const stagesOut = stageList.map((stage) => {
		const bucket = byStage.get(stage.id as number) ?? { count: 0, sum: 0, withoutPrice: 0 };
		const chance = typeof stage.chance === "number" ? stage.chance : null;
		const weighted = chance === null ? undefined : bucket.sum * chance;
		totals.count += bucket.count;
		totals.sum_price += bucket.sum;
		totals.weighted_value += weighted ?? 0;
		return compact({
			id: stage.id,
			name: scalar(stage.name),
			chance,
			count: bucket.count,
			sum_price: round(bucket.sum),
			weighted_value: weighted === undefined ? undefined : round(weighted),
			deals_without_price: bucket.withoutPrice || undefined,
		});
	});
	totals.sum_price = round(totals.sum_price);
	totals.weighted_value = round(totals.weighted_value);
	return {
		complete,
		note: complete ? undefined : `Nur die ersten ${rows.length} von ${total ?? "?"} Deals ausgewertet. Bitte Filter enger setzen.`,
		pipeline: { id: pipelineId, name: scalar(pipeline.name) },
		stages: stagesOut,
		totals,
	};
}

export const pipelineStatusInput = {
	pipeline_id: z.number().int().positive().optional().describe("Ohne ID: Liste aller Pipelines mit Phasen"),
	broker_id: dealFilters.shape.broker_id,
	project_id: dealFilters.shape.project_id,
	object_id: dealFilters.shape.object_id,
	category: dealFilters.shape.category,
	created_from: dealFilters.shape.created_from,
	created_to: dealFilters.shape.created_to,
};

export async function pipelineStatus(
	client: Client,
	input: { pipeline_id?: number } & Omit<DealFilters, "pipeline_id" | "stage_ids">,
): Promise<ToolOutput> {
	const { pipelines } = await stages(client);
	if (input.pipeline_id === undefined) {
		const list = pipelines.map((p) =>
			compact({
				id: p.id,
				name: scalar(p.name),
				stages: (Array.isArray(p.deal_stages) ? (p.deal_stages as Raw[]) : [])
					.sort((a, b) => Number(a.position ?? 0) - Number(b.position ?? 0))
					.map((s) => compact({ id: s.id, name: scalar(s.name), chance: s.chance })),
			}),
		);
		return { count: list.length, result: { pipelines: list } };
	}
	const pipeline = pipelines.find((p) => p.id === input.pipeline_id);
	if (!pipeline) throw new PropstackError(`Pipeline ${input.pipeline_id} nicht gefunden`, 404);
	const result = await dealsByStage(client, pipeline, input);
	return { count: result.totals.count, result };
}

// ---------- Merkmale, Felder, Stammdaten ----------

const TAG_ENTITY: Record<string, GroupEntity> = {
	activities: "for_activities",
	contacts: "for_clients",
	objects: "for_properties",
};

export const listTagsInput = {
	entity: z.enum(["contacts", "objects", "activities"]).describe("Merkmale für Kontakte, Objekte oder Aktivitäten"),
};

export async function listTags(client: Client, input: { entity: "contacts" | "objects" | "activities" }): Promise<ToolOutput> {
	const entity = TAG_ENTITY[input.entity];
	const [groups, superGroups] = await Promise.all([client.listGroups(entity), client.listSuperGroups(entity)]);
	const superNames = new Map(superGroups.rows.map((s) => [s.id, scalar(s.name)]));
	const buckets = new Map<string, { id: number; name: unknown }[]>();
	for (const group of groups.rows) {
		const key = String(superNames.get(group.super_group_id) ?? "Ohne Obermerkmal");
		const list = buckets.get(key) ?? [];
		list.push({ id: group.id as number, name: scalar(group.name) });
		buckets.set(key, list);
	}
	const categories = [...buckets.entries()].map(([name, tags]) => {
		const superGroup = superGroups.rows.find((s) => scalar(s.name) === name);
		return compact({ super_group_id: superGroup?.id, name, tags });
	});
	return { count: groups.rows.length, result: { entity: input.entity, categories } };
}

const FIELD_ENTITY: Record<string, CustomFieldEntity> = {
	contacts: "for_clients",
	deals: "for_deals",
	objects: "for_properties",
	projects: "for_projects",
};

export const listFieldsInput = {
	entity: z.enum(["contacts", "objects", "deals", "projects"]).describe("Custom-Felder für diese Entität"),
};

export async function listFields(client: Client, input: { entity: "contacts" | "objects" | "deals" | "projects" }): Promise<ToolOutput> {
	const groups = await client.listCustomFieldGroups(FIELD_ENTITY[input.entity]);
	let count = 0;
	const result = groups.rows.map((group) => {
		const fields = (Array.isArray(group.custom_fields) ? (group.custom_fields as Raw[]) : []).map((f) => {
			count++;
			const options = Array.isArray(f.custom_options) ? (f.custom_options as Raw[]).map((o) => scalar(o.name)) : [];
			return compact({ key: f.name, label: f.pretty_name, type: f.field_type, options });
		});
		return compact({ group: scalar(group.name), fields });
	});
	return {
		count,
		result: {
			entity: input.entity,
			filter_hint: "Filtern über cf_<key>, z. B. cf_marketing_channel=Lead (nur Kontakte/Objekte)",
			groups: result,
		},
	};
}

export const listReferenceInput = {
	kind: z
		.enum(["object_statuses", "contact_sources", "users", "projects"])
		.describe("Stammdaten: Objekt-Status, Kontakt-Quellen, Nutzer (Makler) oder Projekte – jeweils mit ID für Filter"),
};

function brokerRows(raw: unknown): Raw[] {
	return (Array.isArray(raw) ? raw : []).filter((b): b is Raw => !!b && typeof b === "object");
}

export async function listReference(
	client: Client,
	input: { kind: "object_statuses" | "contact_sources" | "users" | "projects" },
): Promise<ToolOutput> {
	let items: unknown[];
	switch (input.kind) {
		case "object_statuses":
			items = (await client.listPropertyStatuses()).rows.map((s) => compact({ id: s.id, name: scalar(s.name), position: s.position }));
			break;
		case "contact_sources":
			items = (await client.listContactSources()).rows.map((s) => compact({ id: s.id, name: scalar(s.name) }));
			break;
		case "users":
			items = brokerRows(await client.listBrokers()).map((b) =>
				compact({ id: b.id, name: scalar(b.name), email: b.email, position: b.position }),
			);
			break;
		case "projects":
			items = (await client.listProjects()).rows.map((p) =>
				compact({ id: p.id, title: scalar(p.title) ?? scalar(p.name), status: scalar((p.status as Raw | undefined)?.label), city: p.city, broker_id: p.broker_id }),
			);
			break;
	}
	return { count: items.length, result: { kind: input.kind, items } };
}

// ---------- aggregate ----------

const GROUP_BY = {
	contacts: ["source", "tag", "broker", "gdpr_status", "newsletter"],
	deals: ["stage", "broker", "category"],
	objects: ["status", "marketing_type", "tag", "project"],
} as const;

export const aggregateInput = {
	entity: z.enum(["contacts", "objects", "deals"]),
	group_by: z
		.enum(["source", "tag", "broker", "gdpr_status", "newsletter", "status", "marketing_type", "project", "stage", "category"])
		.describe(
			"Kontakte: source, tag, broker, gdpr_status, newsletter · Objekte: status, marketing_type, tag, project · Deals: stage (mit Summen), broker, category",
		),
	tag_super_group_id: z.number().int().positive().optional().describe("Bei group_by=tag: nur Merkmale dieses Obermerkmals (über list_tags)"),
	contact_filters: contactFilters.optional(),
	object_filters: objectFilters.optional(),
	deal_filters: dealFilters.optional(),
};

export interface AggregateInput {
	entity: "contacts" | "objects" | "deals";
	group_by: string;
	tag_super_group_id?: number;
	contact_filters?: ContactFilters;
	object_filters?: ObjectFilters;
	deal_filters?: DealFilters;
}

interface GroupValue {
	id?: number | string;
	name: string;
	query: Query;
}

async function tagValues(client: Client, entity: GroupEntity, superGroupId: number | undefined, param: (id: number) => Query) {
	const groups = (await client.listGroups(entity)).rows.filter(
		(g) => superGroupId === undefined || g.super_group_id === superGroupId,
	);
	return groups.map((g) => ({ id: g.id as number, name: String(scalar(g.name)), query: param(g.id as number) }));
}

async function brokerValues(client: Client, key: string): Promise<GroupValue[]> {
	return brokerRows(await client.listBrokers()).map((b) => ({ id: b.id as number, name: String(scalar(b.name)), query: { [key]: b.id as number } }));
}

export async function aggregate(client: Client, input: AggregateInput): Promise<ToolOutput> {
	const allowed = GROUP_BY[input.entity] as readonly string[];
	if (!allowed.includes(input.group_by)) {
		throw new PropstackError(`group_by=${input.group_by} ist für ${input.entity} nicht möglich. Erlaubt: ${allowed.join(", ")}`, 400);
	}

	// Deals je Phase: einmal alle Deals laden und summieren.
	if (input.entity === "deals" && input.group_by === "stage") {
		const pipelineId = input.deal_filters?.pipeline_id;
		if (!pipelineId) throw new PropstackError("Für group_by=stage bitte deal_filters.pipeline_id angeben (IDs über pipeline_status)", 400);
		const out = await pipelineStatus(client, { ...input.deal_filters, pipeline_id: pipelineId });
		return out;
	}

	let base: Query;
	let count: (query: Query) => Promise<number | null>;
	let values: GroupValue[];
	const countWith = (search: (q: Query) => Promise<Page>) => async (q: Query) => (await search({ ...base, ...q, page: 1, per: 1 })).total;

	if (input.entity === "contacts") {
		base = contactQuery(input.contact_filters ?? {});
		count = countWith((q) => client.searchContacts(q));
		switch (input.group_by) {
			case "source":
				values = (await client.listContactSources()).rows.map((s) => ({ id: s.id as number, name: String(scalar(s.name)), query: { sources: [s.id as number] } }));
				break;
			case "tag":
				values = await tagValues(client, "for_clients", input.tag_super_group_id, (id) => ({ group: [id] }));
				break;
			case "broker":
				values = await brokerValues(client, "broker_id");
				break;
			case "gdpr_status":
				values = ["keine Angabe", "ignoriert", "zugestimmt", "widerrufen"].map((name, code) => ({ id: code, name, query: { gdpr_status: code } }));
				break;
			default:
				values = [
					{ name: "Newsletter ja", query: { newsletter: true } },
					{ name: "Newsletter nein", query: { newsletter: false } },
				];
		}
	} else if (input.entity === "objects") {
		base = objectQuery(input.object_filters ?? {});
		count = countWith((q) => client.searchUnits(q));
		switch (input.group_by) {
			case "status":
				values = (await client.listPropertyStatuses()).rows.map((s) => ({ id: s.id as number, name: String(scalar(s.name)), query: { status: String(s.id) } }));
				break;
			case "marketing_type":
				values = [
					{ id: "BUY", name: "Kauf", query: { marketing_type: "BUY" } },
					{ id: "RENT", name: "Miete", query: { marketing_type: "RENT" } },
				];
				break;
			case "tag":
				values = await tagValues(client, "for_properties", input.tag_super_group_id, (id) => ({ group: String(id) }));
				break;
			default:
				values = (await client.listProjects()).rows.map((p) => ({
					id: p.id as number,
					name: String(scalar(p.title) ?? scalar(p.name) ?? p.id),
					query: { project_id: p.id as number },
				}));
		}
	} else {
		base = dealQuery(input.deal_filters ?? {});
		count = countWith((q) => client.searchDeals(q));
		values =
			input.group_by === "broker"
				? await brokerValues(client, "broker_id")
				: (["qualified", "unqualified", "lost"] as const).map((c) => ({ id: c, name: c, query: { category: c } }));
	}

	if (values.length > AGGREGATE_MAX_GROUPS) {
		throw new PropstackError(
			`Zu viele Gruppen (${values.length}, max. ${AGGREGATE_MAX_GROUPS}).` +
				(input.group_by === "tag" ? " Bitte tag_super_group_id angeben (Obermerkmale über list_tags)." : " Bitte enger filtern."),
			400,
		);
	}

	const total = await count({});
	if (total === null) throw new PropstackError("Propstack liefert für diese Abfrage keine Gesamtzahl", 0);
	const counted: { id?: number | string; name: string; count: number }[] = [];
	for (const value of values) {
		const n = await count(value.query);
		if (n) counted.push(compact({ count: n, id: value.id, name: value.name }) as { id?: number | string; name: string; count: number });
	}
	counted.sort((a, b) => b.count - a.count);
	const grouped = counted.reduce((sum, g) => sum + g.count, 0);

	return {
		count: total,
		result: compact({
			entity: input.entity,
			group_by: input.group_by,
			total,
			groups: counted,
			groups_without_hits: values.length - counted.length || undefined,
			note:
				input.group_by === "tag"
					? "Merkmale können mehrfach vergeben sein – die Summe der Gruppen kann von total abweichen."
					: grouped !== total
						? `${total - grouped} ohne Zuordnung in dieser Dimension.`
						: undefined,
		}),
	};
}
