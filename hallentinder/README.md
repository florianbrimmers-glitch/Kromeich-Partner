# Hallentinder (Web-App → Propstack)

Öffentlich erreichbare Swipe-App für Hallensuchende. Der Interessent beantwortet vier Fragen, swiped durch passende Hallen aus dem eigenen Propstack-Bestand und hinterlässt am Ende seine Kontaktdaten – daraus entstehen ein Propstack-Kontakt und je gelikter Halle ein **Deal**. Entrypoint `python -m hallentinder.main`, Standard-Port 8080.

Eigenständiges Paket – **kein Code-Sharing** mit `src/` oder den Slack-Handlern (bewusst gespiegelt, damit die produktiven Cron-Pipelines nicht an eine Web-App gekoppelt sind).

## Ablauf

1. **Onboarding:** Ort/PLZ, Flächenbedarf von–bis, Nutzung, Zeithorizont, Umkreis.
2. **Bestand:** `GET /v1/units` paginiert, im Prozess gecacht (Default 1 h). Vermietete Objekte (`rented`), reine Kaufobjekte (`marketing_type=BUY`), Wohnimmobilien (`object_type=LIVING` bzw. `rs_type=APARTMENT`) und Nicht-Hallen-Gewerbe (`rs_category` Büro/Laden/Gastro/Praxis) fliegen raus.
3. **Ranking:** harter Flächenfilter (Toleranz 0,6× bis 1,6× um den Wunschbereich) und Umkreisfilter über `lat/lng` (Haversine). Sortierung nach Entfernung plus Flächenabweichung, deterministisch. Bleiben unter 5 Treffer, wird der Radius stufenweise verdoppelt (max. 400 km), statt ein leeres Deck auszuliefern.
4. **Swipen:** Likes/Dislikes landen nur in der Server-Session (Token, TTL 2 h). **Kein** Propstack-Write beim Swipen.
5. **Absenden:** Dublettencheck per E-Mail → bestehenden Kontakt nutzen oder `POST /v1/contacts` → je gelikter Halle `POST /v1/client_properties` mit Notiz (Suchprofil + Objekt + Nachricht). Ein fehlgeschlagener Deal stoppt die übrigen nicht. Dislikes werden nie geschrieben.

## Suchmittelpunkt ohne Geodienst

`hallentinder/geo.py` enthält die Näherungs-Mittelpunkte der deutschen Leitregionen (erste zwei PLZ-Ziffern) – offline, ohne externen Dienst und ohne IP-Weitergabe. Gibt jemand einen Ortsnamen statt einer PLZ ein, wird der Mittelpunkt aus den Koordinaten der eigenen Objekte in diesem Ort gebildet. Passt beides nicht, läuft die Suche ohne Umkreisfilter und die App sagt das im Deck-Text.

## Betriebsmodi

| Modus | Propstack-Writes | Zweck |
|---|---|---|
| `NO_WRITE=true` (**Default**) | keine (Kontakt und Deals werden nur geloggt) | Testen mit echtem Bestand, beliebig wiederholbar |
| `NO_WRITE=false` | Kontakt + Deals | Echtbetrieb – muss im Deployment explizit gesetzt werden |

**Warum der sichere Default:** Deals lassen sich über die Propstack-API **nicht löschen** (`DELETE` liefert 404). Ein versehentlich angelegter Deal bleibt stehen, bis ihn jemand in Propstack von Hand entfernt. Deshalb ist `NO_WRITE=true` der Ausgangszustand – wie `DRY_RUN=true` bei den Slack-Handlern – und der Echtbetrieb setzt es bewusst auf `false`. Beim Start sagt das Log in beiden Richtungen deutlich, welcher Modus läuft; `/healthz` gibt ihn ebenfalls aus.

Der Bestand wird in beiden Modi live gelesen – `PROPSTACK_API_KEY` ist also immer nötig.

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `PROPSTACK_API_KEY` | ja | – | Propstack-v1-Key (units, contacts, client_properties) – dasselbe Secret wie die anderen Pipelines |
| `PROPSTACK_KEY_OBJEKTE` | nein | – | Optionaler Override: separater Key für units/deals |
| `NO_WRITE` | nein | `true` | Reiner Lese-/Loglauf; für den Echtbetrieb auf `false` setzen |
| `HALLENTINDER_HOST` | nein | `0.0.0.0` | Bind-Adresse |
| `HALLENTINDER_PORT` | nein | `8080` | Port |
| `HALLENTINDER_CACHE_TTL` | nein | `3600` | Bestands-Cache in Sekunden |
| `HALLENTINDER_RADIUS_KM` | nein | `50` | Default-Umkreis, wenn das Formular keinen sendet |
| `HALLENTINDER_ALLOWED_ORIGINS` | nein | leer | CORS-Whitelist (kommagetrennt); leer = keine Cross-Origin-Freigabe |
| `HALLENTINDER_STRICT_HALLE` | nein | `false` | `true` = nur Objekte mit erkennbarem Hallen-/Logistik-Merkmal ins Deck |
| `HALLENTINDER_RATE_LIMIT` | nein | `60` | Anfragen pro IP und Stunde auf `/api/session` und `/api/lead` (`0` = aus) |

## API

| Route | Zweck |
|---|---|
| `POST /api/session` | Suchprofil → Token, Trefferzahl, verwendeter Radius, erste Karten |
| `GET /api/cards?token=&offset=` | weitere Karten |
| `POST /api/swipe` | Like/Dislike merken (nur Session) |
| `GET /api/likes?token=` | aktuelle Auswahl |
| `POST /api/lead` | Kontakt + Deals in Propstack anlegen |
| `GET /healthz` | Status, Cache-Alter, Session-Zahl, `no_write` |

## Warum der Bestand gecacht wird

Der vollständige Abruf dauert live rund **zwei Minuten** (2205 Objekte, 23 Seiten à 100). Deshalb:

- Beim Start der App wird der Bestand in einem Hintergrund-Thread vorgeladen.
- Ist der Cache abgelaufen, bekommt der Besucher **sofort den alten Stand**; erneuert wird im Hintergrund, und nur ein Ladevorgang gleichzeitig.
- Blockierend ist nur der allererste Abruf, wenn noch gar kein Bestand da ist.

## Was der Bestand hergibt

Ermittelt mit `python -m hallentinder.diagnose` gegen die Live-API (Stand 23.08.2026, zwei Läufe mit identischem Ergebnis):

| | |
|---|---|
| Objekte gesamt | 2205 |
| davon vermietbare Hallen | 1458 |
| aussortiert | ~570 Wohnen, ~125 vermietet, ~50 Kauf, ~33 Büro/Laden |
| Koordinaten (Umkreissuche) | 1214 (83 %) |
| Fläche | 1244 (85 %) |
| Bild | 1101 (76 %) |
| Hallenhöhe | 44 % |
| Rampe | Boolean, bei ~120 Hallen gesetzt |
| Kranbahn | Boolean, im gesamten Bestand nirgends gesetzt |
| Exposé-Link | 100 % |

Objekte ohne Koordinaten lassen sich nicht in den Umkreis einordnen und rutschen ans Ende des Decks; Objekte ohne Fläche überstehen den Flächenfilter, werden aber nachrangig sortiert.

**Warum nach `id` sortiert wird:** Der Durchlauf zieht 23 Seiten über rund zwei Minuten. Ohne feste Sortierung wandern Objekte in dieser Zeit zwischen den Seiten – über mehrere Diagnoseläufe schwankte die Kategorieverteilung dadurch um bis zu 80 Objekte bei konstanter Gesamtzahl. Mit `sort_by=id` liefern aufeinanderfolgende Läufe identische Zahlen und null Duplikate. Die zusätzliche lokale Deduplizierung greift auch dann, wenn die API den Parameter einmal ignorieren sollte; verworfene Duplikate landen als Warnung im Log, weil sie bedeuten, dass ebenso viele andere Objekte fehlen.

## Datenschutz

- **Feld-Whitelist:** Die API gibt ausschließlich die Felder von `HallCard` heraus (`hallentinder/models.py`). Eigentümer, Makler, interne Notizen und alle übrigen Propstack-Rohfelder verlassen den Server nicht – dafür gibt es einen Test.
- **Einwilligung:** Ohne gesetzte Checkbox wird nichts geschrieben.
- **Keine externen Requests im Frontend:** keine Google Fonts, keine CDNs, kein Tracking. Die Schriften des Styleguides (Jomolhari, Poppins) werden genutzt, wenn sie lokal vorhanden sind, sonst greift ein System-Fallback.
- **Missbrauchsschutz:** IP-Rate-Limit, Honeypot-Feld, Längenlimits auf allen Eingaben.

## Interner Test

Für eine Testrunde im Team braucht es kein Hosting. Ein Rechner startet die App, die anderen öffnen sie im selben WLAN.

**Windows:** Doppelklick auf `Hallentinder starten.bat` im Projektordner. Das Skript prüft Python, installiert fehlende Abhängigkeiten, fragt den Propstack-Key ab (wird nicht gespeichert) und startet die App.

**macOS/Linux:**

```bash
pip install -r requirements.txt
PROPSTACK_API_KEY=xxx python -m hallentinder.main
```

Die App nennt beim Start selbst die Adresse für die Kollegen (`Für Kollegen im gleichen WLAN: http://…:8080`) – dort öffnen sie sie im Browser, auch am Handy. **Wichtig:** Der Bestand wird beim Start geladen, das dauert rund zwei Minuten. Bereit ist die App, sobald `Bestand im Cache: … vermietbare Hallen` im Log steht. Vorher zeigt sie „Der Objektbestand ist gerade nicht erreichbar".

`NO_WRITE` ist per Default `true`, es entsteht also nichts in Propstack; im Log stehen die Anfragen, die im Echtbetrieb entstanden wären. **Für eine Vorführung nicht auf `false` stellen** – angelegte Deals lassen sich per API nicht mehr löschen.

Fehlt der Key, bricht der Start mit einer Meldung ab, die sagt, wo er zu finden ist.

Worauf beim Testen zu achten ist – das sind die Punkte, die der Diagnoselauf als schwach gepflegt gemeldet hat:

- **Reihenfolge des Decks:** Kommen die naheliegenden, passenden Hallen zuerst? 17 % der Hallen haben keine Koordinaten und landen deshalb am Ende, 15 % keine Flächenangabe.
- **Suchorte ohne Bestand:** Ein Ort, an dem nichts vorhanden ist – wird der Umkreis sinnvoll erweitert, oder kommen unpassende Treffer?
- **Karteninhalt:** Reichen Bild, Ort, Fläche und die Merkmale für eine Ja/Nein-Entscheidung? Ein Viertel der Hallen hat kein Bild.
- **Ortsnamen statt PLZ:** „Osnabrück" wird über den eigenen Bestand aufgelöst, nicht über einen Geodienst – bei Orten ohne eigene Objekte greift kein Umkreisfilter.

## Diagnose gegen die Live-API

```bash
PROPSTACK_API_KEY=xxx NO_WRITE=true python -m hallentinder.diagnose
```

Read-only. Prüft Bestandsabruf und Duplikate, Wirkung des Filters, Pflegegrad der Felder, meldet Kategorien, die weder ausgeschlossen noch als Halle bekannt sind, fährt das Ranking gegen echte Daten und simuliert einen Lead. Läuft auch als GitHub-Action `Hallentinder Diagnose` (manuell startbar), Bericht als Artefakt.

## Lokale Ausführung

```bash
pip install -r requirements.txt
PROPSTACK_API_KEY=xxx NO_WRITE=true python -m hallentinder.main
# → http://localhost:8080
```

Tests (ohne Netz/Credentials):

```bash
pip install -r requirements-dev.txt
pytest tests/hallentinder/ -v
```

Docker:

```bash
docker build -t hallentinder .
docker run -p 8080:8080 -e PROPSTACK_API_KEY=xxx -e NO_WRITE=true hallentinder
```

## Vor dem Scharfschalten prüfen

Zwei Punkte lassen sich nur gegen die Live-API klären und sind gekapselt, damit eine Korrektur lokal bleibt:

**Erledigt** (Diagnoseläufe vom 23.08.2026): Bestandsabruf ohne `q` paginiert korrekt über 23 Seiten und ist mit `sort_by=id` stabil, der Kontakt-Endpunkt ist lesend erreichbar, Bild-URLs kommen über `images`, `ramp`/`crane_runway` sind Booleans, und der Kategoriefilter ist gegen die tatsächlich vorkommenden Enums geprüft.

**Ebenfalls erledigt:** die **Deal-Anlage**. Ein Schreibtest gegen die Live-API (`python -m hallentinder.schreibtest`) hat bestätigt: `POST /client_properties` mit `{"client_property": {"client_id", "property_id", "note"}}` antwortet mit **HTTP 201** und `{"id": …, "ok": true}` – genau das, was `propstack.create_deal` sendet.

⚠️ **Deals lassen sich per API nicht löschen.** `DELETE /client_properties/{id}` und `DELETE /deals/{id}` liefern beide 404. Beim Löschen des zugehörigen Kontakts verschwinden Deals teilweise mit, aber nicht zuverlässig – im Schreibtest blieb einer von zweien stehen. Das ist beim Testen mit echten Objekten zu bedenken: **jeder angelegte Deal bleibt, bis ihn jemand in Propstack von Hand entfernt.** Für die App selbst ist das unkritisch (sie legt Deals nur bei echten Anfragen an), für Testläufe aber der Grund, `NO_WRITE=true` zu nutzen.

Es bleibt damit keine unverifizierte Annahme mehr im Code.

## Nicht enthalten

- **Hosting.** Die App ist lokal und als Container lauffähig, aber nirgends deployed; ohne öffentliche URL erreichen echte Interessenten sie nicht.
- Persistenz der Sessions (bewusst: ein Besuch ist unverbindlich, erst der Lead landet im CRM). Ein Neustart verwirft laufende Sitzungen.
- Benachrichtigung des Maklers per Slack/Aufgabe – der Deal in der Propstack-Pipeline ist das einzige Signal.
