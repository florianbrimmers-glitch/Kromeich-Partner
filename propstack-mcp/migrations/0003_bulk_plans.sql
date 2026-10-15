-- Massenänderungen (Phase 4): plan → apply_plan → undo_plan.
-- bulk_plan: ein Plan; bulk_item: je Datensatz Stand vorher (before) und angefragte Änderung.
-- Plan-ID verfällt 10 min nach dem Planen (Spezifikation); Undo 7 Tage nach dem Ausführen (Entscheidung Florian).
-- Aufbewahrung 12 Monate (Löschung per Cron).
CREATE TABLE IF NOT EXISTS bulk_plan (
	id TEXT PRIMARY KEY,
	created_ts TEXT NOT NULL,
	expires_ts TEXT NOT NULL,
	user_email TEXT NOT NULL,
	broker_id INTEGER NOT NULL,
	entity TEXT NOT NULL,
	description TEXT NOT NULL,
	changes TEXT NOT NULL,
	status TEXT NOT NULL,
	total INTEGER NOT NULL,
	applied_ts TEXT,
	applied_by TEXT,
	undo_until TEXT,
	undone_ts TEXT,
	undone_by TEXT
);
CREATE TABLE IF NOT EXISTS bulk_item (
	plan_id TEXT NOT NULL,
	pos INTEGER NOT NULL,
	entity_id INTEGER NOT NULL,
	label TEXT,
	status TEXT NOT NULL,
	before TEXT,
	changed TEXT,
	not_applied TEXT,
	error TEXT,
	undo_status TEXT,
	undo_note TEXT,
	PRIMARY KEY (plan_id, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_bulk_plan_created ON bulk_plan (created_ts);
CREATE INDEX IF NOT EXISTS idx_bulk_item_status ON bulk_item (plan_id, status);
