# #personalkarussel-logistik-Handler (Slack → Propstack)

Liest Meldungen über Arbeitgeberwechsel aus dem privaten Slack-Kanal **#personalkarussel-logistik** (`C090NSRC36U`) und zieht sie in Propstack nach – mit zwei Sicherheitsstufen wie der #objekte-Handler. Läuft als täglicher GitHub-Actions-Cron (`.github/workflows/personalkarussell-handler.yml`, 03:45 UTC), Entrypoint `python -m personalkarussell_handler.main`.

Eigenständiges Paket – **kein Code-Sharing mit `src/`** oder den anderen Handlern.

## Ablauf

1. Nachrichten (inkl. Thread-Antworten) der letzten 50 h lesen (Cron; lokal Standard 26 h); Nachrichten mit eigenem ✅ des Bots werden übersprungen.
2. Klassifikation per Claude: `wechsel` / `abgang` / `umfirmierung` / `linkedin` / `ignorieren`, dazu pro Person Vorname, Nachname, alte und neue Firma. Eine Nachricht kann mehrere Wechsel enthalten („Moritz Kalisch und Patrick Frank sind jetzt beide Marq").
3. Abgleich mit Propstack (`matcher.py`):
   - Person: exakter Vor- und Nachname (Umlaute egal: Fröhlich = Froehlich). Zwei Treffer = Dublette → Stufe B.
   - Zielfirma: Suche nur mit den markanten Wörtern („Marq logistik" sucht „marq"), Rechtsform/„Logistik"/„Deutschland" zählen nicht. Mehrere passende Firmen (Aurelis, Swiss Life) gelten nur dann als eindeutig, wenn die Person schon mit genau einer verknüpft ist.
   - Alte Firma: muss zu Firmenfeld oder Verknüpfungen passen, sonst Stufe B.
4. Entscheidung:
   - **Stufe A** (eindeutig, nur bei `DRY_RUN=false`): neue Firma verknüpfen → Verknüpfung zum bisherigen Arbeitgeber entfernen → Firmenfeld umstellen und Vermerk in der Beschreibung → Notiz am Kontakt. Steht die Person schon bei der neuen Firma, passiert nichts außer ✅.
   - **Stufe B**: Review-Aufgabe an das Sammelpostfach (254958, Lena Klinnert), fällig +2 Werktage, mit Original-Text, Permalink, Kandidaten und vorbereiteter Aktion. Immer Stufe B: Abgang ohne Ziel, LinkedIn-Links, Umfirmierungen, unbekannte Personen, Dubletten, Firma fehlt oder ist mehrdeutig, Widerspruch zur alten Firma, Confidence < 0,8.
5. ✅-Reaction + kurze Thread-Antwort; jede Entscheidung landet als JSONL-Zeile im Entscheidungslog.

E-Mail, Telefon und Position werden **nicht** geändert (die Meldung enthält sie nicht) – die Notiz am Kontakt weist darauf hin.

### Absicherung gegen Firmen-Umbenennung

Am 05.10.2026 hat das Ändern des Firmenfelds einer Person (Tim Hamacher) die bisher verknüpfte Firma in Propstack mitumbenannt („Swiss Life Asset Manager Deutschland" hieß danach wie die neue Firma). Mit frischen Testdaten ließ sich das nicht nachstellen. Stufe A merkt sich deshalb vor dem Ändern die Namen aller beteiligten Firmen, prüft sie danach und setzt einen veränderten Namen sofort zurück (Hinweis in der Notiz).

## Betriebsmodi

| Modus | Propstack-Writes | ✅ + Thread-Reply | JSONL-Log | Zweck |
|---|---|---|---|---|
| `NO_WRITE=true` | keine | keine | ja | Testen mit echten Slack-Daten, beliebig wiederholbar |
| `DRY_RUN=true` | nur Review-Aufgaben (Stufe B) | ja | ja | Testbetrieb – alles läuft als Stufe B |
| `DRY_RUN=false` | Stufe A + B | ja | ja | Normalbetrieb |

**Start im Testbetrieb:** Der Cron läuft zunächst mit `DRY_RUN=true`. Nach einigen Nächten mit plausiblen Review-Aufgaben in der Workflow-Datei auf `false` umstellen.

### Vor dem Scharfschalten (Prüfung vom 19.11.2026)

Der gerade Durchlauf von Stufe A ist richtig und vorsichtig. Gefährlich sind die Abbruchpfade. **Noch nicht scharf schalten**, solange die offenen Punkte nicht erledigt sind.

Mit der Änderung vom 19.11.2026 erledigt:
- Ein Lauf endet rot, wenn eine Meldung nicht verarbeitet werden konnte oder Slack nicht lesbar war, und der Cron liest 50 h zurück – der nächste Lauf holt sie nach (vorher: grün, die Meldung war am Folgetag außerhalb des 26-h-Fensters und damit verloren).
- Nachname allein reicht nicht mehr für einen Treffer („Setz ist jetzt bei Goodman“ → Stufe B, mit dem Hinweis, dass die Person vorhanden sein kann – nicht „neu anlegen“).
- Die neue Verknüpfung wird gegengelesen, bevor die alte gelöscht wird (HTTP 422 heißt nicht immer „besteht bereits“).

**Befund vom 21.11.2026 (nur gelesen): Der Handler hat lange nichts gelesen.** Slack antwortet auf
`conversations.history` für `C090NSRC36U` mit `channel_not_found` – so meldet Slack einen privaten Kanal, in dem der
Bot (`demo_app`, U0AK18H9LTU) nicht Mitglied ist. Den Kanal gibt es (privat, nicht archiviert). Bis zur Änderung vom
19.11.2026 schrieb der Handler das nur ins Log und lief grün mit „0 Nachrichten“ (so noch im Lauf vom 20.11.2026);
seit dem 21.11. ist der Lauf rot. Die Meldung vom 12.10.2026 im Kanal trägt kein ✅, sie ist also nie verarbeitet
worden. Ältere Protokolle sind bei GitHub abgelaufen, seit wann genau, ist offen. Abhilfe: in
#personalkarussel-logistik `/invite @demo_app`.
Nachtrag 22.11.2026: Bot eingeladen, danach antwortet Slack mit `missing_scope` – der App fehlt die Berechtigung für
private Kanäle (`groups:history`, `groups:read`, siehe „Einrichtung“). Sie wird unter api.slack.com/apps → App →
OAuth & Permissions → Bot Token Scopes ergänzt, danach „Reinstall to Workspace“.
Nachtrag 25.11.2026: Scopes ergänzt, Probelauf grün – der Kanal ist lesbar (1 Nachricht in 96 h, keine im 50-h-Fenster).

Offen:
1. **Abbruch mitten in Stufe A hinterlässt einen Teilzustand ohne Spur.** Scheitert das Entfernen der alten Verknüpfung, das Ändern des Firmenfelds oder die Notiz, bleibt der Kontakt halb umgestellt; welche Verknüpfung schon gelöscht ist, steht nirgends. Nötig: Exception in `_stufe_a` fangen, Review-Aufgabe „teilweise ausgeführt“ mit den erledigten Schritten anlegen.
2. **Die Absicherung gegen Firmen-Umbenennung greift nur im geraden Durchlauf.** Wirft der PUT nach dem Schreiben (Timeout) oder die Namensprüfung selbst, bleibt ein falsch umbenannter Firmenname stehen, und der nächste Lauf meldet „bereits aktuell“. Nötig: Prüfung in ein `finally`, jede Firma einzeln.
3. **Wechsel innerhalb einer Gruppe** („von Swiss Life Deutschland zu Swiss Life Logistics“) wird als „steht bereits bei …“ bestätigt – ohne Änderung, ohne Aufgabe, auch im Testbetrieb.
4. **Ein beaufsichtigter Live-Lauf an einem Testkontakt** (`workflow_dispatch`, `dry_run=false`, enges Fenster), danach Kontrolle in der Propstack-Oberfläche: Verknüpfung entfernen, Firmenfeld ändern, Firma zurückbenennen und die Notiz sind im Cron noch nie gelaufen und haben keinen Test.

## Einrichtung

- **Slack:** Der bestehende Bot wird mitgenutzt. Da der Kanal **privat** ist, braucht er zusätzlich `groups:history` und `groups:read` (neben `chat:write`, `reactions:read`, `reactions:write`) und muss im Kanal Mitglied sein: in #personalkarussel-logistik `/invite @Bot`.
- **Secrets** (alle schon vorhanden): `SLACK_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `PROPSTACK_API_KEY`, `PROPSTACK_API_V2_CONTACTS` (Repository-Secret, kein Environment-Secret).

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | ja | – | Bot-Token |
| `ANTHROPIC_API_KEY` | ja | – | Claude-Klassifikation |
| `PROPSTACK_API_KEY` | ja | – | Propstack v1 (Kontakte, Aufgaben) |
| `PROPSTACK_API_V2_CONTACTS` | ja | – | Propstack v2 (Firmen-Verknüpfungen) |
| `DRY_RUN` | nein | `true` | Alles als Stufe B |
| `NO_WRITE` | nein | `false` | Reiner Lese-/Loglauf, überstimmt alles |
| `SCAN_HOURS` | nein | `26` | Scan-Fenster |
| `SCAN_LATEST_HOURS` | nein | `0` | Obere Fenstergrenze (0 = bis jetzt), für Backfill |
| `THREAD_LOOKBACK_HOURS` | nein | `96` | Wie weit zurück Threads nach neuen Antworten durchsucht werden |
| `DECISION_LOG_PATH` | nein | `personalkarussell_decisions.jsonl` | Pfad des Entscheidungslogs |

## Lokale Ausführung

```bash
pip install -r requirements.txt
NO_WRITE=true DRY_RUN=true SCAN_HOURS=168 python -m personalkarussell_handler.main
```

Tests (ohne Netz/Credentials):

```bash
pip install -r requirements-dev.txt
pytest tests/personalkarussell_handler/ -v
```

## Bekannte Einschränkungen

- **LinkedIn-Links** sind nicht maschinell lesbar und werden immer zur Review-Aufgabe.
- **Neue Firmen** legt der Handler nicht selbst an – fehlt die Zielfirma, entsteht eine Review-Aufgabe.
- `ignorieren`-Nachrichten bekommen bewusst kein ✅ und werden in der Fenster-Überlappung ggf. einmal erneut klassifiziert.
- Editierte Nachrichten werden nach ✅ nicht erneut verarbeitet.
