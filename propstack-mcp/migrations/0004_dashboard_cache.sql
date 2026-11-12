-- Zwischenspeicher für das Propstack-Dashboard (Tool dashboard_daten).
-- Ein „Stand“ ist ein vollständiger Datenabzug für einen Parametersatz (Tage, Prüfer). Er braucht mehr
-- Propstack-Anfragen, als ein Tool-Aufruf darf (rund 110 statt 45), und wird deshalb über mehrere Aufrufe
-- hinweg aufgebaut: dashboard_stand hält den Fortschritt, dashboard_teil die Rohdaten je Abrufseite,
-- dashboard_dokument die fertigen Dokumente (30 Minuten gültig, danach wird neu gebaut).
-- Aufbewahrung: Stände älter als 24 Stunden werden beim nächsten Aufbau gelöscht.
CREATE TABLE IF NOT EXISTS dashboard_stand (
	id TEXT PRIMARY KEY,
	params TEXT NOT NULL,
	status TEXT NOT NULL,
	started_ts TEXT NOT NULL,
	updated_ts TEXT NOT NULL,
	ready_ts TEXT,
	until_iso TEXT NOT NULL,
	until_ms INTEGER NOT NULL,
	since_iso TEXT NOT NULL,
	since_ms INTEGER NOT NULL,
	tage INTEGER NOT NULL,
	broker_ids TEXT NOT NULL,
	phase TEXT NOT NULL,
	cursor TEXT NOT NULL,
	anfragen INTEGER NOT NULL DEFAULT 0,
	aufrufe INTEGER NOT NULL DEFAULT 0,
	sperre_bis TEXT,
	fehler TEXT,
	user_email TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dashboard_stand_params ON dashboard_stand (params, started_ts);
-- Je Parametersatz höchstens ein Stand im Aufbau: Beginnen zwei Aufrufe gleichzeitig, legt nur einer an.
CREATE UNIQUE INDEX IF NOT EXISTS idx_dashboard_stand_aufbau ON dashboard_stand (params) WHERE status = 'aufbau';
CREATE TABLE IF NOT EXISTS dashboard_teil (
	stand_id TEXT NOT NULL,
	art TEXT NOT NULL,
	seq INTEGER NOT NULL,
	daten TEXT NOT NULL,
	PRIMARY KEY (stand_id, art, seq)
);
CREATE TABLE IF NOT EXISTS dashboard_dokument (
	stand_id TEXT NOT NULL,
	name TEXT NOT NULL,
	inhalt TEXT NOT NULL,
	bytes INTEGER NOT NULL,
	PRIMARY KEY (stand_id, name)
);
