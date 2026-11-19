# #newsletter-Handler (Logistik-Deal Radar → Propstack)

Verarbeitet den täglichen **„Logistik-Deal Radar"** aus dem Slack-Kanal **#newsletter** (`C07NL0KET40`) – einen bot-generierten Digest von Logistikimmobilien-Marktnews (Neubauten, Transaktionen, Vermietungen) aus ganz Deutschland. **Phase 1:** aus jedem Digest nur die **Vermietungen** herausfiltern, gegen die eigenen Propstack-Objekte matchen und bei eindeutigem Treffer die Einheit auf **vermietet** setzen. Läuft als täglicher GitHub-Actions-Cron (`.github/workflows/newsletter-handler.yml`, 03:00 UTC), Entrypoint `python -m newsletter_handler.main`.

Eigenständiges Paket – **kein Code-Sharing** mit `src/` oder `objekte_handler/` (bewusst gespiegelt, um den produktiven objekte-Handler nicht zu koppeln).

## Ablauf

1. Digest-Nachrichten der letzten 50 h aus #newsletter lesen (Cron; lokal Standard 27 h). **Bot-Nachrichten werden hier NICHT übersprungen** – der Digest selbst ist bot-generiert. Nachrichten mit eigenem ✅ des Bots werden übersprungen (Verarbeitungsmarker, macht das Polling idempotent).
2. Extraktion per Claude (`claude-opus-4-8`): eine Nachricht → Liste aller Deal-Items, je mit `deal_typ` (`vermietung` / `transaktion` / `neubau` / `sonstiges`), `ist_vermietung`, Ort/Straße/Größe/Mieter/Vermieter/Projektname.
3. Nur **Vermietungen** werden gegen `GET /v1/units?q=` gematcht (lokale Nachfilterung: Straße + exakte Hausnummer + Stadt, Größen-Hinweis). Alles andere wird ignoriert.
4. Entscheidung je Deal:
   - **Kein Match** (Fremd-Deal, nicht im eigenen Bestand) → nur Log, keine Aktion.
   - **Stufe A** (Vermietung eindeutig einem eigenen Objekt zugeordnet, `DRY_RUN=false`): `rented=true` setzen, Doku-Notiz, offene Deals per Absage-Aktivität (Grund 256998) schließen.
   - **Stufe B** (mehrdeutig / geringe Confidence / `DRY_RUN=true`): Review-Aufgabe an den Objekt-Verantwortlichen (Fallback: Sammelpostfach 254958, heute Lena Klinnert), fällig +2 Werktage.
   - **Keine Aufgabe, wenn es nichts zu tun gibt** (Änderung vom 19.11.2026, gilt in beiden Betriebsarten):
     - Die zugeordnete Einheit ist in Propstack schon vermietet, „Abgeschlossen“ (Status 163676) oder archiviert → die KI wählt ein zweites Mal nur unter Einheiten in Vermarktung: bei sicherer erster Wahl nur am selben Ort (z. B. der richtige Datensatz neben einer stillgelegten Dublette), bei unsicherer unter allen Kandidaten. Bleibt das ohne Treffer → nur Log.
     - Zur Einheit liegt beim Review-Sitz schon eine offene Aufgabe „Newsletter-Vermietung prüfen“ aus den letzten 30 Tagen → keine zweite. (Der Radar wiederholt über Tage; eine Meldung Monate später ist meist eine neue Vermietung.) Verglichen wird über die Objekt-ID der Aufgabe (`GET /v1/activities`, Feld `property_ids`), nicht über den Titel – der wechselt von Tag zu Tag („Garbe“, „Garbe Industrial“).
     - Aufgaben ohne zugeordnete Einheit werden wie bisher immer angelegt. Lässt sich der Bestand der offenen Aufgaben nicht lesen, wird ebenfalls angelegt (eine doppelte Aufgabe schadet weniger als eine verlorene Meldung) – der Lauf endet dann aber rot.
   - Scheitert die Verarbeitung eines Deals, bekommt der Digest **kein** ✅; der nächste Lauf versucht es erneut.
5. Nach Verarbeitung **aller** Deals einer Nachricht: eine Sammel-Antwort als Thread-Reply + ✅-Reaction. Jeder Deal landet als JSONL-Zeile im Entscheidungslog (nur lokal, siehe unten).

## Betriebsmodi

| Modus | Propstack-Writes | ✅ + Thread-Reply | JSONL-Log | Zweck |
|---|---|---|---|---|
| `NO_WRITE=true` | keine | keine | ja | Testen mit echten Slack-Daten, beliebig wiederholbar |
| `DRY_RUN=true` (**Default**) | nur Review-Tasks (Stufe B) | ja | ja | Testbetrieb – Vermietungen nur als Review-Aufgabe |
| `DRY_RUN=false` | Stufe A + B | ja | ja | Normalbetrieb (auto set_rented) |

**`DRY_RUN=true` ist der gewählte Dauerbetrieb – kein offener Testlauf.** Der Cron
läuft dauerhaft so: Vermietungen gehen immer als Review-Aufgabe an einen Menschen,
der Handler setzt nie selbst `rented`. Das ist bewusst anders als beim objekte- und
events-Handler, die scharf laufen.

Grundlage ist die Auswertung der Läufe 68–74: von **13 Vermietungen** waren nur **2
eindeutig** gematcht (6× mehrdeutig mit KI-Konfidenz 0,55–0,70, 5× gar nicht im
Bestand). Scharfbetrieb spart also rund zwei Handgriffe je zwei Wochen – zu wenig
gegen das Risiko, bei einem falschen Treffer eigenständig eine Fläche auf vermietet
zu setzen und offene Deals abzusagen. Die mehrdeutigen Fälle landen ohnehin bei
einem Menschen, daran ändert der Schalter nichts.

Auf `DRY_RUN=false` umstellen also nur nach bewusster Entscheidung – es ist kein
überfälliger nächster Schritt.

### Befund vom 19.11.2026: Die Review-Aufgaben werden nicht abgearbeitet

Nur gelesen, Review-Sitz 254958: Von **157** je angelegten Aufgaben „Newsletter-Vermietung
prüfen“ ist **eine** erledigt, 156 sind offen. Der Handler war damit die größte Quelle
des Rückstaus an diesem Sitz (156 von 510 offenen Aufgaben).

- **58** der 156 wiederholten nur eine ältere offene Aufgabe zur selben Einheit – der
  Radar meldet dieselbe Vermietung an mehreren Tagen (Westring 8 in Dissen: 7 Aufgaben
  in 14 Tagen, Salzgitter 7, Frickenhausen 5).
- **40** zeigen auf Einheiten, die heute in Propstack vermietet, abgeschlossen oder
  archiviert sind – die Aufgabe hat sich damit erledigt, egal wann. Bei Dissen ist es
  belegt: abgeschlossen seit dem 12.10., alle 7 Aufgaben entstanden danach.
- Zusammen **81 von 156** (52 %) lassen sich ohne inhaltliche Prüfung schließen. Dass
  solche Aufgaben neu entstehen, stellt die Änderung vom 19.11.2026 ab (Ablauf, Punkt 4).

Der vorhandene Bestand lässt sich mit `scripts/pruefaufgaben_aufraeumen.py` sichten und –
erst nach Freigabe – schließen. Offen bleibt die eigentliche Frage: Die übrigen 75
Aufgaben sind echte Prüfaufträge, die ebenfalls niemand erledigt hat. „Die mehrdeutigen
Fälle landen ohnehin bei einem Menschen“ stimmt für die Zustellung, nicht für die
Bearbeitung.

### Vorprüfung vom 19.11.2026: alle 129 offenen Aufgaben einzeln gelesen

Am selben Abend wurden 34 Dubletten mit Freigabe geschlossen (sieben weitere Aufgaben zur
selben Einheit, aber mit anderer Meldung, blieben offen). Die verbleibenden 129 Aufgaben wurden einzeln
gegen Propstack gelesen – Meldung, gewählte Einheit, Eigentümer, Fläche, Nachbar-Einheiten;
in drei Fällen auch die Pressemitteilung des Eigentümers. Ergebnis in
`scripts/radar_vorpruefung_2026-11-19.json` (85 Vorgänge):

| Urteil | Aufgaben |
|---|---|
| Erledigt – die gemeinte Einheit ist schon geschlossen | 49 |
| Betrifft uns nicht – fremdes Objekt, Verlängerung, Verkauf | 28 |
| Eintragen – laut Meldung vermietet, bei uns offen, Zuordnung eindeutig | 7 |
| Klären – wahrscheinlich unser Objekt, Einheit oder Umfang offen | 26 |
| Schwache Spur – nur der Ort passt | 19 |

Nur 33 der 129 Aufgaben (26 %) verlangen also eine Handlung. Was die Durchsicht über die
Zuordnung gelehrt hat:

- **Die Regel „Einheit geschlossen → Aufgabe gegenstandslos“ reicht nicht.** Sie trifft 40
  Aufgaben; bei drei davon hing die Aufgabe an der falschen Einheit, und die gemeinte ist
  noch offen (Frankfurt (Oder): 94.000 m² vermietet, neun Einheiten stehen auf „sofort“).
  Geschlossen wird deshalb nach Urteil, nicht nach dieser Regel (`--urteile`).
- **Der Eigentümer trennt Treffer von Rauschen, und die KI bekommt ihn nicht zu sehen.**
  `_candidate_line` gibt Name, Adresse, Fläche und Makler weiter, das Feld `eigentumer` nicht.
  Gemessen an den Urteilen: Stimmt der Eigentümer der gewählten Einheit mit dem Vermieter der
  Meldung überein (43 Aufgaben), fielen 40 unter „erledigt“, „eintragen“ oder „klären“. Widerspricht
  er (22 Aufgaben), war die gewählte Einheit nur in zwei Fällen erkennbar die gemeinte (Langenselbold,
  womöglich Oyten) – sonst nicht, darunter Moers (Ixocon-Meldung an einer
  BEOS-Halle, die Ixocon-Halle lag unter den Kandidaten) und Rostock (VGP-Meldung an einer
  CTP-Einheit). Bei 48 Aufgaben ist am Objekt kein Eigentümer hinterlegt.
- **Die KI wählt eine Einheit, Vermietungen betreffen oft mehrere.** Oberhausen (18.400 m² =
  Unit 1 + Unit 2), Kamen, Mülheim, Rheinau: Die Summe zweier Einheiten passt, eine einzelne nicht.
- **Verlängerungen und Verkäufe werden als Vermietung gewertet** (Wezel/CTP, Maersk, Decathlon,
  Sebold): vier Aufgaben, bei denen nichts frei geworden oder vergeben worden ist.
- **Regel 3 im Auswahl-Prompt** („ein Kandidat in der Gemeinde ist ein STARKER Treffer – auch ohne
  Projektname und ohne Flächenübereinstimmung“) erzeugt genau die 19 schwachen Spuren.

Nicht geändert: Eine Änderung am Prompt lässt sich ohne Schlüssel hier nicht ausprobieren. Die
129 Urteile sind aber der erste belastbare Prüfsatz für diesen Handler – der nächste Schritt ist,
den Eigentümer in die Kandidatenzeile zu nehmen, den Prompt anzupassen und beides gegen diese
Urteile zu messen, bevor es in den täglichen Lauf geht.

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

Das Entscheidungslog entsteht nur beim lokalen Lauf (`DECISION_LOG_PATH`); Cron-Läufe
laden es nicht hoch. Zum Auswerten den Handler lokal gegen das gewünschte Zeitfenster
laufen lassen (Beispiel oben, `SCAN_HOURS` passend gesetzt), dann z.B.:

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
