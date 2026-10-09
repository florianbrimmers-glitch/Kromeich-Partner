// Kürzen der Propstack-Antworten auf relevante Felder (harte Regel: nie rohe JSONs).
// Bewusst NICHT ausgegeben werden sensible Kontaktdaten: Ausweis-/Steuernummer,
// Geburtsdaten, Einkommen, Nationalität und der Kundenportal-Token.

type Raw = Record<string, unknown>;

/** Propstack liefert manche Felder als {"label", "value"} bzw. {"value", "pretty_value"}. */
export function scalar(value: unknown): unknown {
	if (value && typeof value === "object" && !Array.isArray(value)) {
		const obj = value as Raw;
		if ("pretty_value" in obj && obj.pretty_value !== null && obj.pretty_value !== undefined) return obj.pretty_value;
		if ("value" in obj) return obj.value;
	}
	return value;
}

export function truncate(value: unknown, max: number): string | undefined {
	const text = scalar(value);
	if (typeof text !== "string" || !text.trim()) return undefined;
	const clean = text.trim();
	return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

/** Entfernt leere Werte, damit die Antworten kurz bleiben. */
export function compact<T extends Raw>(obj: T): Partial<T> {
	const out: Raw = {};
	for (const [key, value] of Object.entries(obj)) {
		if (value === null || value === undefined || value === "") continue;
		if (Array.isArray(value) && value.length === 0) continue;
		if (typeof value === "object" && !Array.isArray(value) && Object.keys(value as Raw).length === 0) continue;
		out[key] = value;
	}
	return out as Partial<T>;
}

function pick(raw: Raw, keys: string[]): Raw {
	const out: Raw = {};
	for (const key of keys) out[key] = scalar(raw[key]);
	return out;
}

function nameOf(value: unknown): string | undefined {
	if (value && typeof value === "object") {
		const obj = value as Raw;
		const name = scalar(obj.name) ?? scalar(obj.label) ?? scalar(obj.title);
		return typeof name === "string" ? name : undefined;
	}
	return typeof value === "string" ? value : undefined;
}

function idName(value: unknown): { id?: unknown; name?: string } | undefined {
	if (!value || typeof value !== "object") return undefined;
	const obj = value as Raw;
	return compact({ id: obj.id, name: nameOf(obj) });
}

/** Custom-Felder: nur befüllte, als {schlüssel: wert}. */
export function customFields(value: unknown): Raw | undefined {
	if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
	const out: Raw = {};
	for (const [key, field] of Object.entries(value as Raw)) {
		const v = scalar(field);
		if (v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) continue;
		out[key] = typeof v === "string" && v.length > 300 ? `${v.slice(0, 300)}…` : v;
	}
	return Object.keys(out).length ? out : undefined;
}

function groupNames(value: unknown): unknown[] | undefined {
	if (!Array.isArray(value)) return undefined;
	const names = value.map((g) => (g && typeof g === "object" ? compact({ id: (g as Raw).id, name: nameOf(g) }) : g));
	return names.length ? names : undefined;
}

const GDPR = ["keine Angabe", "ignoriert", "zugestimmt", "widerrufen"];

// ---------- Kontakte ----------

export function mapContactSummary(raw: Raw) {
	return compact({
		...pick(raw, ["id", "name", "company", "is_company", "email", "broker_id", "client_status_id", "client_source_id"]),
		phone: scalar(raw.phone) ?? scalar(raw.home_cell) ?? scalar(raw.office_cell) ?? scalar(raw.office_phone) ?? scalar(raw.home_phone),
		tags: groupNames(raw.groups),
		last_contact_at: raw.last_contact_at,
		created_at: raw.created_at,
		archived: raw.archived === true ? true : undefined,
	});
}

export function mapContactDetail(raw: Raw) {
	const gdpr = typeof raw.gdpr_status === "number" ? GDPR[raw.gdpr_status] : undefined;
	return compact({
		...pick(raw, [
			"id",
			"item_id",
			"salutation",
			"academic_title",
			"first_name",
			"last_name",
			"name",
			"is_company",
			"company",
			"position",
			"email",
			"home_phone",
			"home_cell",
			"office_phone",
			"office_cell",
			"broker_id",
			"parent_id",
			"children_size",
			"client_status_id",
			"client_source_id",
			"rating",
			"newsletter",
			"accept_contact",
			"language",
			"last_contact_at",
			"created_at",
			"updated_at",
		]),
		emails: Array.isArray(raw.emails) && raw.emails.length > 1 ? raw.emails : undefined,
		status: idName(raw.status),
		home_address: addressOf(raw, "home"),
		office_address: addressOf(raw, "office"),
		description: truncate(raw.description, 1500),
		warning_notice: truncate(raw.warning_notice, 500),
		gdpr_status: gdpr,
		tags: groupNames(raw.groups),
		custom_fields: customFields(raw.custom_fields),
		archived: raw.archived === true ? true : undefined,
	});
}

function addressOf(raw: Raw, prefix: "home" | "office"): string | undefined {
	const direct = scalar(raw[`${prefix}_address`]);
	if (typeof direct === "string" && direct.trim()) return direct.trim();
	const street = [scalar(raw[`${prefix}_street`]), scalar(raw[`${prefix}_house_number`])].filter(Boolean).join(" ");
	const city = [scalar(raw[`${prefix}_zip_code`]), scalar(raw[`${prefix}_city`])].filter(Boolean).join(" ");
	const full = [street, city, scalar(raw[`${prefix}_country`])].filter(Boolean).join(", ");
	return full || undefined;
}

// ---------- Objekte ----------

function statusName(raw: Raw): string | undefined {
	return nameOf(raw.status) ?? nameOf(raw.property_status);
}

export function mapUnitSummary(raw: Raw) {
	return compact({
		...pick(raw, [
			"id",
			"unit_id",
			"exposee_id",
			"name",
			"title",
			"marketing_type",
			"object_type",
			"rs_type",
			"price",
			"base_rent",
			"total_rent",
			"living_space",
			"property_space_value",
			"plot_area",
			"number_of_rooms",
			"project_id",
			"broker_id",
		]),
		address: scalar(raw.short_address) ?? scalar(raw.address),
		status: statusName(raw),
		archived: raw.archived === true ? true : undefined,
		updated_at: scalar(raw.updated_at),
	});
}

export function mapUnitDetail(raw: Raw) {
	const images = Array.isArray(raw.images) ? raw.images.length : undefined;
	return compact({
		...mapUnitSummary(raw),
		...pick(raw, [
			"rs_category",
			"street",
			"house_number",
			"zip_code",
			"city",
			"lat",
			"lng",
			"floor",
			"construction_year",
			"number_of_bed_rooms",
			"number_of_bath_rooms",
			"courtage",
			"created_at",
		]),
		address: scalar(raw.address) ?? scalar(raw.short_address),
		broker: idName(raw.broker),
		project: nameOf(raw.project),
		tags: groupNames(raw.property_groups ?? raw.groups),
		description: truncate(raw.description_note, 1500),
		location: truncate(raw.location_note, 800),
		furnishing: truncate(raw.furnishing_note, 800),
		other: truncate(raw.other_note, 800),
		custom_fields: customFields(raw.custom_fields),
		image_count: images,
	});
}

// ---------- Deals ----------

export interface StageInfo {
	name: string;
	pipelineId: number;
	pipelineName: string;
	chance: number | null;
}

/** Preis eines Deals: Doku nennt `price`, das Beispiel `sold_price` – beides lesen. */
export function dealPrice(raw: Raw): number | null {
	for (const key of ["price", "sold_price"]) {
		const v = scalar(raw[key]);
		const n = typeof v === "string" ? Number(v) : v;
		if (typeof n === "number" && Number.isFinite(n)) return n;
	}
	return null;
}

export function mapDeal(raw: Raw, stages: Map<number, StageInfo>) {
	const stage = typeof raw.deal_stage_id === "number" ? stages.get(raw.deal_stage_id) : undefined;
	const client = raw.client && typeof raw.client === "object" ? (raw.client as Raw) : undefined;
	const property = raw.property && typeof raw.property === "object" ? (raw.property as Raw) : undefined;
	return compact({
		id: raw.id,
		pipeline: stage?.pipelineName,
		stage: stage?.name ?? raw.deal_stage_id,
		deal_pipeline_id: raw.deal_pipeline_id,
		deal_stage_id: raw.deal_stage_id,
		contact: client ? compact({ id: client.id, name: nameOf(client) }) : compact({ id: raw.client_id }),
		object: property
			? compact({ id: property.id, title: scalar(property.title), address: scalar(property.short_address) ?? scalar(property.address) })
			: compact({ id: raw.property_id }),
		project_id: raw.project_id,
		price: dealPrice(raw) ?? undefined,
		broker_id: raw.broker_id,
		reservation_reason_id: raw.reservation_reason_id,
		note: truncate(raw.note, 300),
		start_date: raw.start_date,
		created_at: raw.created_at,
	});
}

export function stageIndex(pipelines: Raw[]): Map<number, StageInfo> {
	const index = new Map<number, StageInfo>();
	for (const pipeline of pipelines) {
		const stages = Array.isArray(pipeline.deal_stages) ? (pipeline.deal_stages as Raw[]) : [];
		for (const stage of stages) {
			if (typeof stage.id !== "number") continue;
			index.set(stage.id, {
				chance: typeof stage.chance === "number" ? stage.chance : null,
				name: nameOf(stage) ?? String(stage.id),
				pipelineId: pipeline.id as number,
				pipelineName: nameOf(pipeline) ?? String(pipeline.id),
			});
		}
	}
	return index;
}
