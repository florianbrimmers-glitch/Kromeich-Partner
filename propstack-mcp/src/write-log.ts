import { AUDIT_RETENTION_MONTHS } from "./config";
import { retentionCutoff } from "./audit";
import { PropstackError } from "./propstack-client";

// Write-Log mit Snapshots. Anders als das Audit-Log ist es fail-closed:
// Kann der Eintrag vor dem Write nicht geschrieben werden, wird NICHT nach Propstack geschrieben.

export interface WriteStart {
	userEmail: string;
	brokerId: number;
	tool: string;
	entity: "contact" | "object" | "tag" | "project" | "image" | "task";
	entityId: number | null;
	action: "create" | "update";
	before: Record<string, unknown> | null;
	request: Record<string, unknown>;
	warnings: string[];
	overrideReason: string | null;
}

export type WriteStatus = "done" | "done_with_gaps" | "failed" | "blocked";

const json = (value: unknown) => (value === null || value === undefined ? null : JSON.stringify(value));

export async function beginWrite(db: D1Database | undefined, entry: WriteStart, now = new Date()): Promise<number> {
	if (!db) throw new PropstackError("Write-Log nicht verfügbar – aus Sicherheitsgründen wird nichts gespeichert.", 0);
	try {
		const result = await db
			.prepare(
				"INSERT INTO write_log (ts, user_email, broker_id, tool, entity, entity_id, action, before, request, status, warnings, override_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
			)
			.bind(
				now.toISOString(),
				entry.userEmail,
				entry.brokerId,
				entry.tool,
				entry.entity,
				entry.entityId,
				entry.action,
				json(entry.before),
				JSON.stringify(entry.request),
				entry.warnings.length ? JSON.stringify(entry.warnings) : null,
				entry.overrideReason,
			)
			.run();
		const id = result.meta.last_row_id;
		if (!id) throw new Error("keine ID");
		return id;
	} catch (error) {
		console.error("Write-Log: Eintrag fehlgeschlagen", error);
		throw new PropstackError("Write-Log nicht verfügbar – aus Sicherheitsgründen wird nichts gespeichert.", 0);
	}
}

/** Abschluss protokollieren. Fehler hier blockieren nichts mehr (der Write ist schon passiert). */
export async function finishWrite(
	db: D1Database | undefined,
	id: number,
	update: { status: WriteStatus; entityId?: number | null; notApplied?: string[]; error?: string | null },
	now = new Date(),
): Promise<void> {
	if (!db) return;
	try {
		await db
			.prepare(
				"UPDATE write_log SET status = ?, entity_id = COALESCE(?, entity_id), not_applied = ?, error = ?, finished_ts = ? WHERE id = ?",
			)
			.bind(
				update.status,
				update.entityId ?? null,
				update.notApplied?.length ? JSON.stringify(update.notApplied) : null,
				update.error ?? null,
				now.toISOString(),
				id,
			)
			.run();
	} catch (error) {
		console.error("Write-Log: Abschluss fehlgeschlagen", error);
	}
}

export async function purgeOldWriteLog(db: D1Database, now = new Date()): Promise<number> {
	const result = await db.prepare("DELETE FROM write_log WHERE ts < ?").bind(retentionCutoff(now, AUDIT_RETENTION_MONTHS)).run();
	return result.meta.changes ?? 0;
}
