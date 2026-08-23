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
| `NO_WRITE=true` | keine (Kontakt und Deals werden nur geloggt) | Testen mit echtem Bestand, beliebig wiederholbar |
| `NO_WRITE=false` (**Default**) | Kontakt + Deals | Normalbetrieb |

Der Bestand wird in beiden Modi live gelesen – `PROPSTACK_API_KEY` ist also immer nötig.

## Umgebungsvariablen

| Variable | Pflicht | Default | Bedeutung |
|---|---|---|---|
| `PROPSTACK_API_KEY` | ja | – | Propstack-v1-Key (units, contacts, client_properties) – dasselbe Secret wie die anderen Pipelines |
| `PROPSTACK_KEY_OBJEKTE` | nein | – | Optionaler Override: separater Key für units/deals |
| `NO_WRITE` | nein | `false` | Reiner Lese-/Loglauf |
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

Ermittelt mit `python -m hallentinder.diagnose` gegen die Live-API (Stand 23.08.2026):

| | |
|---|---|
| Objekte gesamt | 2205 |
| davon vermietbare Hallen | ~1450 |
| aussortiert | ~530 Wohnen, ~125 vermietet, 50 Kauf, ~40 Büro/Laden |
| Koordinaten (Umkreissuche) | 83 % |
| Fläche | 87 % |
| Bild | 75 % |
| Hallenhöhe | 43 % |
| Rampe / Kranbahn | Boolean – 140 Objekte mit Rampe, Kranbahn im ganzen Bestand nirgends gesetzt |
| Exposé-Link | 100 % |

Objekte ohne Koordinaten lassen sich nicht in den Umkreis einordnen und rutschen ans Ende des Decks; Objekte ohne Fläche überstehen den Flächenfilter, werden aber nachrangig sortiert.

## Datenschutz

- **Feld-Whitelist:** Die API gibt ausschließlich die Felder von `HallCard` heraus (`hallentinder/models.py`). Eigentümer, Makler, interne Notizen und alle übrigen Propstack-Rohfelder verlassen den Server nicht – dafür gibt es einen Test.
- **Einwilligung:** Ohne gesetzte Checkbox wird nichts geschrieben.
- **Keine externen Requests im Frontend:** keine Google Fonts, keine CDNs, kein Tracking. Die Schriften des Styleguides (Jomolhari, Poppins) werden genutzt, wenn sie lokal vorhanden sind, sonst greift ein System-Fallback.
- **Missbrauchsschutz:** IP-Rate-Limit, Honeypot-Feld, Längenlimits auf allen Eingaben.

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

**Erledigt** (Diagnoselauf vom 23.08.2026): Bestandsabruf ohne `q` paginiert korrekt über 23 Seiten, der Kontakt-Endpunkt ist lesend erreichbar, Bild-URLs kommen über `images`.

**Offen:** die **Deal-Anlage** `POST /client_properties` mit `{"client_property": {"client_id", "property_id", "note"}}` (`propstack.create_deal`). Das Payload-Schema ist die einzige verbliebene Annahme und lässt sich nur mit einem echten Schreibtest bestätigen – am besten mit einem Testkontakt, der danach wieder entfernt wird.

## Nicht enthalten

- **Hosting.** Die App ist lokal und als Container lauffähig, aber nirgends deployed; ohne öffentliche URL erreichen echte Interessenten sie nicht.
- Persistenz der Sessions (bewusst: ein Besuch ist unverbindlich, erst der Lead landet im CRM). Ein Neustart verwirft laufende Sitzungen.
- Benachrichtigung des Maklers per Slack/Aufgabe – der Deal in der Propstack-Pipeline ist das einzige Signal.
