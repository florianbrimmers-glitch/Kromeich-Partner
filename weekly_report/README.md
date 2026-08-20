# Wochenreport (Propstack → Slack-DM)

Schickt jeden **Dienstag 19:00 Berliner Zeit** eine Slack-DM an Oguzhan Sahin (`U087H2UMREF`) mit dem, was in den letzten 7 Tagen in Propstack passiert ist: neu angelegte Projekte, neu angelegte Objekte/Einheiten und abgeschlossene Prüfaufgaben – jeweils Anzahl plus kurze Details.

Läuft als GitHub-Actions-Cron (`.github/workflows/weekly-report.yml`), Entrypoint `python -m weekly_report.main`.

Eigenständiges Paket, **rein lesend** – keine Propstack-Writes, kein Code-Sharing mit `objekte_handler/` oder `src/`.

## Ablauf

1. **Stunden-Guard**: Lauf nur, wenn es in Berlin `RUN_HOUR_BERLIN` Uhr ist (siehe Zeitzonen unten).
2. Fenster `[jetzt − REPORT_HOURS, jetzt)` berechnen – rollierend, kein persistierter Zustand. Fällt ein Lauf aus, ist die Woche danach wieder korrekt.
3. **Neue Einheiten**: `GET /v1/units?expand=1&created_at_from=…&created_at_to=…`, seitenweise. Der Serverfilter wirkt nur tagesgenau, also wird er um je einen Tag geweitet und der exakte Schnitt clientseitig gezogen. `expand=1` ist zwingend, sonst ist `created_at` im Payload `null`.
4. **Projekte** aus den `project_id`s der neuen Einheiten bündeln und je Projekt über die **früheste Einheit** datieren (`GET /v1/units?project_id=…&sort_by=created_at&order=asc&per=1`) → *neues Projekt* vs. *bestehendes Projekt mit neuen Einheiten*.
5. **Prüfaufgaben**: `GET /v1/activities?item_type=reminder&broker_id=…&sort_by=updated_at&order=desc`, absteigend lesen und abbrechen, sobald `updated_at` aus dem Fenster fällt. Gemeldet wird, was `done = true` trägt.
6. Nachricht bauen und per `chat.postMessage` als DM senden; eine JSONL-Zeile pro Lauf ins Report-Log (Actions-Artefakt, 30 Tage).

## Was die API hergibt – und was nicht

Ergebnisse aus direkten Tests gegen die Propstack-API (20.08.2026). Das Repo hatte vorher keinen einzigen Datumsfilter, an dem man sich orientieren konnte.

| Aufruf | Ergebnis |
|---|---|
| `GET /v1/units?created_at_from=…&created_at_to=…` | ✅ wirkt serverseitig (2201 → 31 → 21), aber nur tagesgenau |
| `GET /v1/units` ohne `expand=1` | ⚠️ `created_at` ist `null` |
| `GET /v1/units?sort_by=created_at&order=asc|desc` | ✅ funktioniert |
| `GET /v1/projects?created_at_from=…` | ❌ **wird ignoriert** (bleibt bei 345) |
| Projekt-Payload (Liste **und** `/v1/projects/:id`) | ❌ **enthält keinen Zeitstempel** |
| `GET /v1/activities?item_type=reminder` | ✅ mit `done`, `original_created_at`, `updated_at`, `broker_id` |
| `…&original_created_at_from/to=` | ✅ funktioniert |
| `…&updated_at_from/to=` | ❌ **wird ignoriert** → sortieren statt filtern |
| `…&broker_id=254958` | ✅ funktioniert |
| Unit-Payload `project` (auch mit `expand=1`) | ❌ ist `null` → Projekt-Titel separat holen |

**Bekannte Grenzen** (stehen auch als Fußnote in der Slack-Nachricht):

- Ein Projekt **ohne jede Einheit** erscheint nicht im Report – es gibt keinen Zeitstempel, über den man es finden könnte.
- Ein Projekt, das kurz vor dem Fenster angelegt wurde und dessen erste Einheit erst im Fenster entsteht, gilt als neu.
- Propstack führt kein `completed_at`. `updated_at` ist der einzige Zeitstempel für den Abschluss – bei abgeschlossenen Aufgaben liegt er durchweg deutlich nach der Anlage, das Signal ist also brauchbar.

## Prüfaufgaben: warum Broker 254958

`PRUEFER_BROKER_IDS` steht auf `254958`, weil dort die Prüfaufgaben tatsächlich gepflegt werden:

| | 254958 | 387451 (Marek) |
|---|---|---|
| Aufgaben insgesamt | **317** | 62 |
| davon `done = true` | **25** | 6 |
| jüngste abgeschlossene | 17.08.2026 | 03.08.2026 |

Die Konstante ist bewusst neutral benannt: `objekte_handler/config.py` kommentiert `254958` als „Oguzhan", `GET /v1/brokers` liefert für diese ID aber **Lena Klinnert**. Der Widerspruch soll sich hier nicht fortschreiben. Weitere Broker lassen sich kommagetrennt dazuschalten, ohne Code zu ändern.

Das Feld `done` wird nur auf dieser ID gepflegt (25 von 317). Sollte der Report zu dünn werden, schaltet `REPORT_INCLUDE_TOUCHED=true` einen zweiten Block „bearbeitet, aber offen" dazu (`updated_at > original_created_at`).

## Zeitzonen

GitHub-Actions-Cron kennt nur UTC, Berlin wechselt zwischen CET und CEST. Der Workflow feuert deshalb **zweimal** – `3 17 * * 2` und `3 18 * * 2` – und der Guard in `main.py` lässt je Saison genau einen Lauf durch. So kommt der Report ganzjährig um 19 Uhr Ortszeit an, statt nach der Zeitumstellung um eine Stunde zu verrutschen.

Bei `workflow_dispatch` ist der Guard standardmäßig **aus**, damit manuelle Läufe zu jeder Zeit funktionieren.

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | ja | – | Bot-Token, braucht `chat:write` + `im:write` |
| `PROPSTACK_API_KEY` | ja | – | Propstack-v1-Key – dasselbe Secret wie die anderen Handler |
| `PROPSTACK_KEY_OBJEKTE` | nein | – | Optionaler Override für units/projects |
| `PROPSTACK_KEY_TASKS` | nein | – | Optionaler Override für Aktivitäten |
| `DRY_RUN` | nein | `true` | Nur loggen, keine DM (Cron setzt explizit `false`) |
| `REPORT_HOURS` | nein | `168` | Berichtsfenster in Stunden zurück |
| `RUN_HOUR_BERLIN` | nein | `19` | Stunden-Guard; leer = aus |
| `REPORT_RECIPIENT` | nein | `U087H2UMREF` | Slack-User-ID des Empfängers |
| `PRUEFER_BROKER_IDS` | nein | `254958` | Kommagetrennte Broker-IDs für Prüfaufgaben |
| `REPORT_INCLUDE_TOUCHED` | nein | `false` | Zusatzblock „bearbeitet, aber offen" |
| `REPORT_LOG_PATH` | nein | `weekly_report.jsonl` | Pfad des Report-Logs |

Leere Werte gelten als „nicht gesetzt" – GitHub Actions reicht nicht belegte `workflow_dispatch`-Inputs als leeren String durch.

## Secrets-Setup

Nutzt die bestehenden Secrets `SLACK_BOT_TOKEN` und `PROPSTACK_API_KEY`. **Keine neuen Secrets nötig**, und kein `ANTHROPIC_API_KEY` – der Report enthält keine LLM-Aufrufe.

⚠️ Der Slack-Bot-Token und zwei Propstack-Keys stehen im Klartext in den Skill-Dateien (`propstack-expose-workflow`). Rotation empfohlen, siehe Hinweis in `objekte_handler/README.md`.

**Slack:** Für die DM braucht der Bot `chat:write` und `im:write` (beide vorhanden). Eine DM erfordert keinen Channel-Invite.

## Lokale Ausführung

```bash
pip install -r requirements.txt

# Trockenlauf gegen die echte API – liest nur, sendet nichts, Guard aus:
DRY_RUN=true RUN_HOUR_BERLIN= REPORT_HOURS=168 \
  SLACK_BOT_TOKEN=… PROPSTACK_API_KEY=… python -m weekly_report.main
```

Tests (ohne Netz/Credentials):

```bash
pytest tests/weekly_report/ -v
```
