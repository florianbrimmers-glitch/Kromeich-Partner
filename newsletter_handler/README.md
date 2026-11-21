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
   - **Eigentümer-Probe** (Änderung vom 20.11.2026): Die KI sieht je Kandidat den Eigentümer (`custom_fields.eigentumer`) und die Einheit und darf mehrere Einheiten desselben Objekts nennen (Summe der Flächen). Danach prüft der Code nach (`eigentuemer.py`, `match_ai.select_match_geprueft`): Gehört die gewählte Einheit erkennbar einem anderen als dem Vermieter der Meldung, wählt die KI ein zweites Mal nur unter den Einheiten dieses Vermieters am selben Ort. Bleibt das leer, behält die erste Wahl nur dann eine Aufgabe (als unsicherer Treffer), wenn die Fläche auf ±10 % passt – auf die Einheit, die Summe der gewählten oder die Summe der Adresse – oder Straße bzw. Projektname stimmen. Sonst: kein eigener Bestand, nur Log. Fehlt der Eigentümer am Objekt oder nennt die Meldung keinen Vermieter, ändert die Probe nichts.
   - **Verlängerungen** eines bestehenden Mietvertrags (`ist_verlaengerung`) ergeben keine Aufgabe: Es wird nichts frei und nichts neu vergeben. Nennt die Meldung einen Käufer, ist sie eine Transaktion.
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
  Aufgaben; bei zwei davon hing die Aufgabe an der falschen Einheit, und die gemeinte ist
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

**Ausgeführt am 20.11.2026** (mit Freigabe): alle 129 Aufgaben geschlossen, jede mit dem Urteil als erster Zeile
im Text; 28 Datensätze als vermietet eingetragen, Halle A in Frankfurt (Oder) wieder geöffnet. Die 18 „klären“-Vorgänge wurden an öffentlichen Quellen
nachgeprüft statt beim Eigentümer erfragt (`scripts/radar_nachpruefung_2026-11-20.json`). Zwei Lehren daraus:

- Bei 4 der 18 lag die KI im Ort daneben: Die Unizell-Halle steht in Schwanewede, nicht in Oyten; die Apex-Fläche in
  Witten, nicht in Bochum; in Dombühl und Pulheim war ein anderes Objekt gemeint. Adresse und Eigentümer standen
  jeweils in der Pressemitteilung, die der Radar verlinkt.
- Frankfurt (Oder): Die Aufgabe zur Meldung „Halle B vermietet“ hing an einer Einheit der Halle A. In Propstack stand
  seit dem 07.09. Halle A auf vermietet und Halle B (97.660 m²) auf frei – umgekehrt zur Meldung des Eigentümers. Ob
  die falsche Verknüpfung der Auslöser war, ist nicht belegt. Florian hat es am 20.11. bestätigt („Halle A ist leer,
  Halle B ist vermietet“); seither stimmt der Stand. Eine falsch verknüpfte Aufgabe kostet also nicht nur Lesezeit.

### Zuordnung nachgezogen und messbar gemacht (20.11.2026)

Aus den vier Befunden oben ist Code geworden: Eigentümer und Einheit in der Kandidatenzeile,
Eigentümer-Probe nach der Auswahl, mehrere Einheiten je Vermietung, Verlängerungen ohne Aufgabe,
Regel 3 des Prompts ersetzt (ein Kandidat nur in der Gemeinde ist eine schwache Spur, confidence
höchstens 0,5). Die Fälle stehen als Tests in `tests/newsletter_handler/test_eigentuemer.py`.

Die 129 Urteile sind der Prüfsatz: `scripts/radar_pruefsatz_2026-11-20.json` hält je Aufgabe fest,
welche Einheiten gemeint waren, welche nicht und welche offen blieben. Gemessen wird so:

1. Lese-Lauf über die alten Digests: Actions → Newsletter Handler → Run workflow mit
   `no_write=true`, `ignore_checkmark=true` und `scan_from_hours` so groß wie das Fenster. Der Lauf
   schreibt nichts (keine Aufgabe, keine Antwort, kein ✅), hat eine eigene Concurrency-Gruppe und
   ein längeres Zeitlimit und schreibt je Vermietung eine Zeile `AUSWERTUNG {…}` ins Protokoll.
   `ignore_checkmark` wirkt nur zusammen mit `no_write`.
2. `python scripts/radar_zuordnung_messen.py <protokoll.txt>` legt die Zeilen neben die Urteile.

Gewertet wird, was der Handler heute täte. Die gemeinten Einheiten sind inzwischen geschlossen;
richtig ist bei „erledigt“, „eintragen“ und „fremd“ also: keine Aufgabe.

Was die Probe nicht kann (trocken an den 22 Alt-Aufgaben mit widersprechendem Eigentümer geprüft,
ohne KI): Bei 48 der 129 Aufgaben fehlt der Eigentümer am Objekt – dort greift sie nicht. Und ein
veralteter Eigentümer (Entwickler hat an einen Investor verkauft) lässt eine echte Vermietung nur
durch, wenn Fläche oder Name stimmen (Wedel, Schwanewede, Mannheim blieben so stehen).


**Lese-Läufe vom 20./21.11.2026** (GitHub Actions, `no_write` + `ignore_checkmark`, Fenster ab 06.09.2026, nichts geschrieben):

| | Lauf 1 (Stand `292d6e3`) | Lauf 2 (Stand `551fea5`) |
|---|---|---|
| Digests | 72 von 72 | 36 von 72 – dann API-Limit erreicht (siehe unten) |
| Vermietungen | 186 | auf denselben 36 Digests: 135 (Lauf 1: 87) |
| Aufgaben nach Dublettenschutz | 33 | auf denselben 36 Digests: 20 (Lauf 1: 16) |
| davon unnötig laut Prüfsatz | 14 von 27 zugeordneten | auf denselben 36 Digests: 3 (Lauf 1: 6) |

- Lauf 1 zeigte zwei Rausch-Quellen: die zweite Wahl nach einer abgeschlossenen Einheit (8 Aufgaben, alle an einer
  freien Nachbar-Einheit) und ganze Parks, die teils schon vermietet waren (8). Beides ist in `551fea5` über die
  gemeldete Fläche abgestellt; in Lauf 2 sind Krefeld, Offenbach, Mülheim, Rheinau und Frankfurt (Oder) erledigt.
- Lauf 2 liest mehr Meldungen als Vermietung, weil „Neubau für einen genannten Nutzer“ jetzt zählt. Darunter sind
  prüfenswerte Treffer (Panattoni in Rohr und Eltmann, bauwo in Pocking) und neue Wiederholer (Triport an drei
  Tagen, Rheindocks mit 13 Einheiten). **Nicht entschieden, nicht im nächtlichen Lauf** – erst nach einem
  vollständigen Lauf.
- **Kosten:** Lauf 1 brauchte 422 KI-Aufrufe (Opus). Am 21.11.2026 um 00:35 UTC war mitten in Lauf 2 das
  Ausgabenlimit der Anthropic-Organisation erreicht („You will regain access on 2026-12-01“); danach liefen alle
  sechs Workflows mit KI rot. Ein Lese-Lauf über Wochen alter Digests ist kein Testlauf, sondern ein spürbarer Teil
  des Monatsbudgets – vorher Restbudget prüfen und freigeben lassen.

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
| `IGNORE_CHECKMARK` | nein | `false` | Nur mit `NO_WRITE=true`: auch Digests mit ✅ noch einmal lesen (Mess-Lauf über alte Digests) |
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
