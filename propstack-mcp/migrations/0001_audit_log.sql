-- Audit-Log: wer hat wann welches Tool mit welchen Parametern aufgerufen.
-- Keine Ergebnisdaten. Aufbewahrung 12 Monate (Löschung per Cron, siehe src/audit.ts).
CREATE TABLE IF NOT EXISTS audit_log (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	ts TEXT NOT NULL,
	user_email TEXT NOT NULL,
	broker_id INTEGER NOT NULL,
	tool TEXT NOT NULL,
	params TEXT NOT NULL,
	result_count INTEGER,
	ok INTEGER NOT NULL,
	error TEXT,
	duration_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log (ts);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_ts ON audit_log (user_email, ts);
