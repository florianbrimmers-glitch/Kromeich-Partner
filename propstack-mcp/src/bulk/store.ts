// Speicher für Massenänderungs-Pläne (D1, Tabellen aus migrations/0003_bulk_plans.sql).
// Als Interface, damit die Ablauflogik ohne D1 testbar ist.

type Raw = Record<string, unknown>;

export type PlanStatus = "planned" | "applying" | "applied" | "expired" | "undoing" | "undone";
export type ItemStatus = "pending" | "done" | "done_with_gaps" | "unchanged" | "failed";
export type UndoStatus = "undone" | "partial" | "skipped" | "failed";

export interface BulkPlan {
	id: string;
	created_ts: string;
	expires_ts: string;
	user_email: string;
	broker_id: number;
	entity: "contacts" | "objects";
	description: string;
	changes: Raw;
	status: PlanStatus;
	total: number;
	applied_ts: string | null;
	applied_by: string | null;
	undo_until: string | null;
	undone_ts: string | null;
	undone_by: string | null;
}

export interface BulkItem {
	plan_id: string;
	pos: number;
	entity_id: number;
	label: string | null;
	status: ItemStatus;
	before: Raw | null;
	changed: Raw | null;
	not_applied: string[] | null;
	error: string | null;
	undo_status: UndoStatus | null;
	undo_note: string | null;
}

export interface BulkStore {
	createPlan(plan: BulkPlan, items: { entity_id: number; label: string | null }[]): Promise<void>;
	getPlan(id: string): Promise<BulkPlan | null>;
	updatePlan(id: string, fields: Partial<BulkPlan>): Promise<void>;
	/** Nächste Einträge in Reihenfolge, die eine Bedingung erfüllen. */
	items(planId: string, where: "pending" | "undoable", limit: number): Promise<BulkItem[]>;
	updateItem(planId: string, entityId: number, fields: Partial<BulkItem>): Promise<void>;
	counts(planId: string): Promise<{ status: Record<string, number>; undo: Record<string, number> }>;
	recentErrors(planId: string, kind: "apply" | "undo", limit: number): Promise<{ entity_id: number; label: string | null; text: string }[]>;
}

const JSON_COLUMNS = new Set(["changes", "before", "changed", "not_applied"]);

function toRow(fields: Raw): Raw {
	return Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, JSON_COLUMNS.has(k) && v !== null && v !== undefined ? JSON.stringify(v) : v]));
}

function fromRow<T>(row: Raw | null): T | null {
	if (!row) return null;
	return Object.fromEntries(
		Object.entries(row).map(([k, v]) => [k, JSON_COLUMNS.has(k) && typeof v === "string" ? JSON.parse(v) : v]),
	) as T;
}

const PLAN_COLUMNS = new Set(["status", "expires_ts", "applied_ts", "applied_by", "undo_until", "undone_ts", "undone_by"]);
const ITEM_COLUMNS = new Set(["status", "before", "changed", "not_applied", "error", "undo_status", "undo_note"]);

export class D1BulkStore implements BulkStore {
	constructor(private readonly db: D1Database) {}

	async createPlan(plan: BulkPlan, items: { entity_id: number; label: string | null }[]): Promise<void> {
		const p = toRow(plan as unknown as Raw);
		const itemStatements = items.map((item, pos) =>
			this.db
				.prepare("INSERT INTO bulk_item (plan_id, pos, entity_id, label, status) VALUES (?, ?, ?, ?, 'pending')")
				.bind(plan.id, pos, item.entity_id, item.label),
		);
		// Einträge zuerst (in Blöcken), den Plan zuletzt: ein halb geschriebener Plan ist so nie sichtbar.
		for (let i = 0; i < itemStatements.length; i += 100) await this.db.batch(itemStatements.slice(i, i + 100));
		await this.db
			.prepare(
				"INSERT INTO bulk_plan (id, created_ts, expires_ts, user_email, broker_id, entity, description, changes, status, total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
			)
			.bind(p.id, p.created_ts, p.expires_ts, p.user_email, p.broker_id, p.entity, p.description, p.changes, p.status, p.total)
			.run();
	}

	async getPlan(id: string): Promise<BulkPlan | null> {
		return fromRow<BulkPlan>(await this.db.prepare("SELECT * FROM bulk_plan WHERE id = ?").bind(id).first<Raw>());
	}

	async updatePlan(id: string, fields: Partial<BulkPlan>): Promise<void> {
		const entries = Object.entries(toRow(fields as Raw)).filter(([k]) => PLAN_COLUMNS.has(k));
		if (!entries.length) return;
		await this.db
			.prepare(`UPDATE bulk_plan SET ${entries.map(([k]) => `${k} = ?`).join(", ")} WHERE id = ?`)
			.bind(...entries.map(([, v]) => v), id)
			.run();
	}

	async items(planId: string, where: "pending" | "undoable", limit: number): Promise<BulkItem[]> {
		const condition = where === "pending" ? "status = 'pending'" : "status IN ('done', 'done_with_gaps') AND undo_status IS NULL";
		const result = await this.db
			.prepare(`SELECT * FROM bulk_item WHERE plan_id = ? AND ${condition} ORDER BY pos LIMIT ?`)
			.bind(planId, limit)
			.all<Raw>();
		return (result.results ?? []).map((row) => fromRow<BulkItem>(row)!);
	}

	async updateItem(planId: string, entityId: number, fields: Partial<BulkItem>): Promise<void> {
		const entries = Object.entries(toRow(fields as Raw)).filter(([k]) => ITEM_COLUMNS.has(k));
		if (!entries.length) return;
		await this.db
			.prepare(`UPDATE bulk_item SET ${entries.map(([k]) => `${k} = ?`).join(", ")} WHERE plan_id = ? AND entity_id = ?`)
			.bind(...entries.map(([, v]) => v ?? null), planId, entityId)
			.run();
	}

	async counts(planId: string): Promise<{ status: Record<string, number>; undo: Record<string, number> }> {
		const status = await this.db.prepare("SELECT status AS k, COUNT(*) AS n FROM bulk_item WHERE plan_id = ? GROUP BY status").bind(planId).all<{ k: string; n: number }>();
		const undo = await this.db
			.prepare("SELECT undo_status AS k, COUNT(*) AS n FROM bulk_item WHERE plan_id = ? AND undo_status IS NOT NULL GROUP BY undo_status")
			.bind(planId)
			.all<{ k: string; n: number }>();
		const toMap = (rows: { k: string; n: number }[] | undefined) => Object.fromEntries((rows ?? []).map((r) => [r.k, r.n]));
		return { status: toMap(status.results), undo: toMap(undo.results) };
	}

	async recentErrors(planId: string, kind: "apply" | "undo", limit: number) {
		const sql =
			kind === "apply"
				? "SELECT entity_id, label, COALESCE(error, not_applied) AS text FROM bulk_item WHERE plan_id = ? AND status IN ('failed', 'done_with_gaps') ORDER BY pos LIMIT ?"
				: "SELECT entity_id, label, undo_note AS text FROM bulk_item WHERE plan_id = ? AND undo_status IN ('failed', 'partial', 'skipped') ORDER BY pos LIMIT ?";
		const result = await this.db.prepare(sql).bind(planId, limit).all<{ entity_id: number; label: string | null; text: string }>();
		return result.results ?? [];
	}
}

/** Löschfrist wie Audit-/Write-Log (12 Monate). */
export async function purgeOldBulkPlans(db: D1Database | undefined, cutoffIso: string): Promise<number> {
	if (!db) return 0;
	try {
		await db.prepare("DELETE FROM bulk_item WHERE plan_id IN (SELECT id FROM bulk_plan WHERE created_ts < ?)").bind(cutoffIso).run();
		const result = await db.prepare("DELETE FROM bulk_plan WHERE created_ts < ?").bind(cutoffIso).run();
		return result.meta.changes ?? 0;
	} catch (error) {
		console.error("Bulk-Pläne: Löschfrist fehlgeschlagen", error);
		return 0;
	}
}

/** In-Memory-Variante für Tests. */
export class MemoryBulkStore implements BulkStore {
	plans = new Map<string, BulkPlan>();
	rows: BulkItem[] = [];

	async createPlan(plan: BulkPlan, items: { entity_id: number; label: string | null }[]): Promise<void> {
		this.plans.set(plan.id, structuredClone(plan));
		items.forEach((item, pos) =>
			this.rows.push({ ...item, before: null, changed: null, error: null, not_applied: null, plan_id: plan.id, pos, status: "pending", undo_note: null, undo_status: null }),
		);
	}
	async getPlan(id: string) {
		const plan = this.plans.get(id);
		return plan ? structuredClone(plan) : null;
	}
	async updatePlan(id: string, fields: Partial<BulkPlan>) {
		const plan = this.plans.get(id);
		if (plan) Object.assign(plan, fields);
	}
	async items(planId: string, where: "pending" | "undoable", limit: number) {
		return this.rows
			.filter((r) => r.plan_id === planId && (where === "pending" ? r.status === "pending" : ["done", "done_with_gaps"].includes(r.status) && !r.undo_status))
			.sort((a, b) => a.pos - b.pos)
			.slice(0, limit)
			.map((r) => structuredClone(r));
	}
	async updateItem(planId: string, entityId: number, fields: Partial<BulkItem>) {
		const row = this.rows.find((r) => r.plan_id === planId && r.entity_id === entityId);
		if (row) Object.assign(row, fields);
	}
	async counts(planId: string) {
		const status: Record<string, number> = {};
		const undo: Record<string, number> = {};
		for (const r of this.rows.filter((x) => x.plan_id === planId)) {
			status[r.status] = (status[r.status] ?? 0) + 1;
			if (r.undo_status) undo[r.undo_status] = (undo[r.undo_status] ?? 0) + 1;
		}
		return { status, undo };
	}
	async recentErrors(planId: string, kind: "apply" | "undo", limit: number) {
		return this.rows
			.filter((r) => r.plan_id === planId && (kind === "apply" ? ["failed", "done_with_gaps"].includes(r.status) : ["failed", "partial", "skipped"].includes(r.undo_status ?? "")))
			.slice(0, limit)
			.map((r) => ({ entity_id: r.entity_id, label: r.label, text: kind === "apply" ? (r.error ?? JSON.stringify(r.not_applied)) : (r.undo_note ?? "") }));
	}
}
