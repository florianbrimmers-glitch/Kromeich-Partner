# #newsletter-Handler (Logistik-Deal Radar → Propstack)

Verarbeitet den täglichen **„Logistik-Deal Radar"** aus dem Slack-Kanal **#newsletter** (`C07NL0KET40`) – einen bot-generierten Digest von Logistikimmobilien-Marktnews (Neubauten, Transaktionen, Vermietungen) aus ganz Deutschland. **Phase 1:** aus jedem Digest nur die **Vermietungen** herausfiltern, gegen die eigenen Propstack-Objekte matchen und bei eindeutigem Treffer die Einheit auf **vermietet** setzen. Läuft als täglicher GitHub-Actions-Cron (`.github/workflows/newsletter-handler.yml`, 03:00 UTC), Entrypoint `python -m newsletter_handler.main`.

Eigenständiges Paket – **kein Code-Sharing** mit `src/` oder `objekte_handler/` (bewusst gespiegelt, um den produktiven objekte-Handler nicht zu koppeln).

## Ablauf

1. Digest-Nachrichten der letzten 27h aus #newsletter lesen. **Bot-Nachrichten werden hier NICHT übersprungen** – der Digest selbst ist bot-generiert. Nachrichten mit eigenem ✅ des Bots werden übersprungen (Verarbeitungsmarker, macht das Polling idempotent).
2. Extraktion per Claude (`claude-opus-4-8`): eine Nachricht → Liste aller Deal-Items, je mit `deal_typ` (`vermietung` / `transaktion` / `neubau` / `sonstiges`), `ist_vermietung`, Ort/Straße/Größe/Mieter/Vermieter/Projektname.
3. Nur **Vermietungen** werden gegen `GET /v1/units?q=` gematcht (lokale Nachfilterung: Straße + exakte Hausnummer + Stadt, Größen-Hinweis). Alles andere wird ignoriert.
4. Entscheidung je Deal:
   - **Kein Match** (Fremd-Deal, nicht im eigenen Bestand) → nur Log, keine Aktion.
   - **Stufe A** (Vermietung eindeutig einem eigenen Objekt zugeordnet, `DRY_RUN=false`): `rented=true` setzen, Doku-Notiz, offene Deals per Absage-Aktivität (Grund 256998) schließen.
   - **Stufe B** (mehrdeutig / geringe Confidence / `DRY_RUN=true`): Review-Aufgabe an den Objekt-Verantwortlichen (Fallback: Sammelpostfach 254958, heute Lena Klinnert), fällig +2 Werktage.
5. Nach Verarbeitung **aller** Deals einer Nachricht: eine Sammel-Antwort als Thread-Reply + ✅-Reaction. Jeder Deal landet als JSONL-Zeile im Entscheidungslog (Actions-Artefakt).

## Betriebsmodi

| Modus | Propstack-Writes | ✅ + Thread-Reply | JSONL-Log | Zweck |
|---|---|---|---|---|
| `NO_WRITE=true` | keine | keine | ja | Testen mit echten Slack-Daten, beliebig wiederholbar |
| `DRY_RUN=true` (**Default**) | nur Review-Tasks (Stufe B) | ja | ja | Testbetrieb – Vermietungen nur als Review-Aufgabe |
| `DRY_RUN=false` | Stufe A + B | ja | ja | Normalbetrieb (auto set_rented) |

**Start im Dry-Run:** Der Cron läuft zunächst mit `DRY_RUN=true`. Scharfschalten (Cron-Env auf `false`) erst nach Auswertung der ersten Läufe – analog zum objekte-Handler.

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | ja | – | Bot-Token (siehe Scopes unten) |
| `ANTHROPIC_API_KEY` | ja | – | Claude-Extraktion (`claude-opus-4-8`) |
| `PROPSTACK_API_KEY` | ja | – | Propstack-v1-Key (units, deals, tasks) – dasselbe Secret wie die anderen Pipelines |
| `PROPSTACK_KEY_OBJEKTE` | nein | – | Optionaler Override: separater Key für units/deals |
| `PROPSTACK_KEY_TASKS` | nein | – | Optionaler Override: separater Key für Aktivitäten/Tasks |
| `DRY_RUN` | nein | `true` | Vermietungen nur als Stufe B; `false` = auto set_rented |
| `NO_WRITE` | nein | `false` | Reiner Lese-/Loglauf, überstimmt alles |
| `SCAN_HOURS` | nein | `27` | Scan-Fenster (deckt den ~22:18-CEST-Digest des Vortags + Überlappung ab) |
| `SCAN_LATEST_HOURS` | nein | `0` | Obere Fenstergrenze (0 = bis jetzt), für Backfill |
| `DECISION_LOG_PATH` | nein | `newsletter_decisions.jsonl` | Pfad des Entscheidungslogs |

## Secrets-Setup

Der Handler nutzt die bestehenden GitHub Secrets `SLACK_BOT_TOKEN`, `ANTHROPIC_API_KEY` und `PROPSTACK_API_KEY` (wie die anderen Pipelines). Getrennte Propstack-Keys optional via `PROPSTACK_KEY_OBJEKTE`/`PROPSTACK_KEY_TASKS`.

**Slack:** Der bestehende Bot wird mitgenutzt. Benötigte Scopes: `channels:history`, `channels:read`, `chat:write`, `reactions:read`, `reactions:write`. Der Bot muss Mitglied in #newsletter sein (`/invite @Bot`).

## Lokale Ausführung

```bash
pip install -r requirements.txt
NO_WRITE=true DRY_RUN=true SCAN_HOURS=168 python -m newsletter_handler.main
```

Tests (ohne Netz/Credentials):

```bash
pip install -r requirements-dev.txt
pytest tests/newsletter_handler/ -v
```

## Auswertung des Entscheidungslogs

```bash
# Verteilung der Deal-Typen
jq -r '.deal.deal_typ // "fehler"' newsletter_decisions.jsonl | sort | uniq -c

# Erkannte Vermietungen mit Match-Status
jq -r 'select(.deal.ist_vermietung == true) | "\(.message_ts)#\(.deal_index)  \(.match.status // "-")  \(.decision.tier)"' newsletter_decisions.jsonl

# Fehler
jq -r 'select(.fehler) | "\(.message_ts)  \(.fehler)"' newsletter_decisions.jsonl
```

## Bekannte Einschränkungen

- Der Radar meldet **fremde** Marktdeals aus ganz Deutschland; die meisten Vermietungen haben **keinen** Treffer im eigenen Propstack-Bestand → dann passiert nichts (nur Log). `rented` wird nur bei eindeutigem Match des eigenen Bestands gesetzt.
- Fehlmatch-Risiko (fremde Vermietung trifft zufällig eine eigene Einheit derselben Straße) wird durch UNIQUE-/Confidence-Gating und den Dry-Run-Start abgefangen; erste Läufe im Decision-Log gegenprüfen, bevor scharf geschaltet wird.
- Wird die ganze Digest-Nachricht mit ✅ markiert; einzelne Deals werden nicht separat quittiert.
- `ignorieren`/Nicht-Vermietungen bekommen kein eigenes Signal – sie stehen nur im Log.

## Explizit außerhalb des Scopes (Phase 1)

- Anlage von Leads/Kontakten aus genannten Firmen (Apollo) – bewusst nicht enthalten.
- Review-Aufgaben für Vermietungen **ohne** eigenen Bestands-Match (würde eine Task-Flut erzeugen).
- Transaktionen und Neubauten (werden ignoriert).
