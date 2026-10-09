import { AUDIT_RETENTION_MONTHS } from "./config";

// Audit-Log in D1: wer, wann, welches Tool, welche Parameter, Trefferzahl, Erfolg.
// Keine Ergebnisdaten. Aufbewahrung 12 Monate (purgeOldAuditEntries per Cron).

export interface AuditEntry {
	ts: string;
	userEmail: string;
	brokerId: number;
	tool: string;
	params: unknown;
	resultCount: number | null;
	ok: boolean;
	error: string | null;
	durationMs: number;
}

const MAX_PARAMS_LENGTH = 2000;

export function serializeParams(params: unknown): string {
	let text: string;
	try {
		text = JSON.stringify(params ?? {});
	} catch {
		text = "{}";
	}
	return text.length > MAX_PARAMS_LENGTH ? `${text.slice(0, MAX_PARAMS_LENGTH)}…` : text;
}

/**
 * Schreibt einen Audit-Eintrag. Bei Lese-Tools „best effort“: Ein Fehler im Log
 * bricht die Abfrage nicht ab, wird aber geloggt. (Für Schreib-Tools ab Phase 3
 * muss das Log vor dem Write erfolgreich sein.)
 */
export async function writeAuditEntry(db: D1Database | undefined, entry: AuditEntry): Promise<void> {
	if (!db) {
		console.error("Audit-Log: AUDIT_DB-Binding fehlt");
		return;
	}
	try {
		await db
			.prepare(
				"INSERT INTO audit_log (ts, user_email, broker_id, tool, params, result_count, ok, error, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
			)
			.bind(
				entry.ts,
				entry.userEmail,
				entry.brokerId,
				entry.tool,
				serializeParams(entry.params),
				entry.resultCount,
				entry.ok ? 1 : 0,
				entry.error,
				entry.durationMs,
			)
			.run();
	} catch (error) {
		console.error("Audit-Log: Schreiben fehlgeschlagen", error);
	}
}

/** Stichtag für die Löschung: alles älter als AUDIT_RETENTION_MONTHS. */
export function retentionCutoff(now: Date, months = AUDIT_RETENTION_MONTHS): string {
	const cutoff = new Date(now);
	cutoff.setUTCMonth(cutoff.getUTCMonth() - months);
	return cutoff.toISOString();
}

export async function purgeOldAuditEntries(db: D1Database, now = new Date()): Promise<number> {
	const result = await db.prepare("DELETE FROM audit_log WHERE ts < ?").bind(retentionCutoff(now)).run();
	return result.meta.changes ?? 0;
}
