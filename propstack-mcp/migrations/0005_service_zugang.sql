-- Service-Zugang (objekte-handler, ab v0.16.0): Audit- und Write-Log halten fest, welcher Ablauf im Namen welches
-- Propstack-Nutzers geschrieben hat und zu welchem Auftrag (Slack-Zeitstempel). Bei Menschen bleiben beide leer.
ALTER TABLE audit_log ADD COLUMN service TEXT;
ALTER TABLE audit_log ADD COLUMN service_ref TEXT;
ALTER TABLE write_log ADD COLUMN service TEXT;
ALTER TABLE write_log ADD COLUMN service_ref TEXT;
