-- Write-Log mit Snapshots (Phase 3): wird VOR jedem Schreibzugriff angelegt (fail-closed).
-- before = nur die Felder, die geändert werden (Werte vor dem Write), request = angefragte Werte.
-- Aufbewahrung 12 Monate (Löschung per Cron, siehe src/write-log.ts).
CREATE TABLE IF NOT EXISTS write_log (
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	ts TEXT NOT NULL,
	user_email TEXT NOT NULL,
	broker_id INTEGER NOT NULL,
	tool TEXT NOT NULL,
	entity TEXT NOT NULL,
	entity_id INTEGER,
	action TEXT NOT NULL,
	before TEXT,
	request TEXT NOT NULL,
	status TEXT NOT NULL,
	warnings TEXT,
	override_reason TEXT,
	not_applied TEXT,
	error TEXT,
	finished_ts TEXT
);
CREATE INDEX IF NOT EXISTS idx_write_log_ts ON write_log (ts);
CREATE INDEX IF NOT EXISTS idx_write_log_entity ON write_log (entity, entity_id);
