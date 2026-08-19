# -*- coding: utf-8 -*-
"""Wendet die empirisch belegten API-Korrekturen auf den Skill propstack-expose-workflow an.

Warum dieses Skript existiert: die Skill-Dateien unter ~/.claude/skills/synced/ werden beim
Container-Neustart aus der Skill-Quelle neu geschrieben. Korrekturen, die dort von Hand
eingetragen werden, sind danach weg - am 19.08.2026 zweimal an einem Tag passiert. Statt die
ganze Skill-Kopie hier zu versionieren (sie enthaelt API-Keys im Klartext, die nicht ins Git
gehoeren), haelt dieses Repo nur die DIFFS und traegt sie nach jedem Reset wieder ein.
Der SessionStart-Hook ruft das Skript automatisch auf.

Das Skript ist idempotent und dokumentiert gleichzeitig, WELCHE Aussagen falsch waren und
wodurch sie ersetzt wurden. Die maßgebliche Fassung aller Funde ist die Notion-Seite
32d7b7e5627b810db8bfdfcb9f477ee2 ("Propstack API - Feld-Mapping"), Korrekturen 1-39.

Findet das Skript einen Anker nicht mehr, meldet es UNKLAR und beendet mit Code 2 - dann hat
sich die Skill-Quelle geaendert und die Korrektur muss neu formuliert werden.

Aufruf:
    python3 scripts/skill_korrekturen.py                 # anwenden
    python3 scripts/skill_korrekturen.py --pruefen       # nur berichten, nichts schreiben
    python3 scripts/skill_korrekturen.py --ziel <PFAD>   # anderes Skill-Verzeichnis
"""
import os, pathlib, sys

STANDARD = pathlib.Path(
    os.environ.get("SKILL_DIR")
    or (pathlib.Path.home() / ".claude/skills/synced/propstack-expose-workflow"))

def ziel_verzeichnis(argv):
    if "--ziel" in argv:
        return pathlib.Path(argv[argv.index("--ziel") + 1])
    return STANDARD

BASIS = ziel_verzeichnis(sys.argv)

# (Datei, alter Text, neuer Text, Kurzname) - alter Text darf fehlen, wenn schon korrigiert
KORREKTUREN = [
 ("SKILL.md",
  "- **`mezzanineflache`** direkt setzen wirkungslos → `mezzanineflache_verfugbar` verwenden.",
  '- **Zwei Felder heißen „Mezzaninefläche": eines in der Sektion Preise, eines in der Sektion '
  'Flächen.** Die Quadratmeter gehören in die Flächen-Sektion (`mezzanineflache_gesamt` / '
  '`mezzanineflache_verfugbar`, Einheit `sqm`), die Miete in die Preise-Sektion. '
  '**`mezzanineflache` ist das Feld der Preise-Sektion** (`unit: "euro"`) — eine Fläche darin '
  'wird als „10.150 €" angezeigt. Am 13.08.2026 sind so 664 Einheiten verdorben worden, '
  'korrigiert am 17.08.2026. Früher stand hier „direkt setzen wirkungslos, '
  '`mezzanineflache_verfugbar` befüllt es automatisch" — beides falsch: das Feld ist '
  'schreibbar, und es wird nicht automatisch befüllt (677 Einheiten mit `_gesamt`, aber nur '
  '16 mit `mezzanineflache`).\n'
  '- **Vor dem ersten Schreibzugriff auf ein Custom Field seine Einheit prüfen.** '
  '`GET /custom_field_groups` liefert je Feld `field_type` **und** `unit`. „Schreibbar" heißt '
  'nicht „richtiges Feld", und der Feldname sagt nichts über die Einheit. Gegenprobe über '
  '`pretty_value` im `expand=1`-Kanal: dort steht „812 m²" oder „3,50 €".\n'
  '- **Tore: zwei Felder, der API-Name des zweiten ist irreführend.** Die Maske zeigt '
  '„Rampentore" und „Ebenerdige Tore". In der API sind das `ramepntore` (String) und '
  '**`anzahl_rampentore_2`** (Number) — dessen `pretty_name` lautet „Anzahl Rampentore 2", '
  'trägt aber die **ebenerdigen** Tore (an 7 Datensätzen gegen die Klartexte belegt, '
  'bestandsweit 1.123 Einheiten). In `ramepntore` nur die Rampenzahl als nackte Zahl. '
  '**Alles was keine Rampe ist — Hallentore, Sektionaltore, Rolltore, ebenerdige Zufahrten — '
  'ist ein ebenerdiges Tor.** Zusatzdetails („davon 3 Jumbotore") in ein '
  '`zusatzausstattung*`-Feld, Vorbehalte in `bemerkung`. Separat genannte Rampenarten werden '
  'addiert (25 + 3 = 28), eine mit **„davon"** eingeleitete Menge ist eine Teilmenge und wird '
  '**nicht** addiert.\n'
  '- **Zahlen, die nur für das Gesamtobjekt vorliegen, nicht auf jede Einheit kopieren.** '
  'Sonst behauptet jede Einheit den Wert des ganzen Standorts (gefunden: 9 Einheiten mit je '
  '„108 Rampentore" für einen Park mit 61.009 m²). Verteilungsregel: **1 Rampe pro 1.000 m² '
  'Hallenfläche, 1 ebenerdiges Tor pro Einheit** — oder aus Luftbild und Lageplan auszählen. '
  'Gerechnete Werte in `bemerkung` als abgeleitet kennzeichnen. **Vorlegen statt rechnen**, '
  'wenn Einheiten- und Gesamtwert zusammen im Feld stehen, zwei Bauteile gemischt sind oder '
  'gar keine Zahl dasteht („ja", „vorhanden").\n'
  '- **UI-Beschriftungen weichen von `pretty_name` ab**, weil der Shop Felder umbenennen kann: '
  '`lagerflache` heißt in der Maske „Hallenfläche". Ein Feld über die Maskenbeschriftung in '
  'der Registry zu suchen kann fehlschlagen — die Zuordnung über die Werte belegen.',
  "Mezzanin- und Torfelder"),

 ("SKILL.md",
  "- **Flächen-Custom-Fields doppelt setzen:** die Exposé-Flächensektion liest `lagerflache` / "
  "`buroflache` / `mezzanineflache`, daneben existieren `*_verfugbar`, `*_gesamt`, "
  "`*_teilbar_ab`. Immer alle Varianten.",
  "- **Flächen-Custom-Fields doppelt setzen:** die Exposé-Flächensektion liest `lagerflache` / "
  "`buroflache`, daneben existieren `*_verfugbar`, `*_gesamt`, `*_teilbar_ab`. Alle Varianten "
  "setzen — **außer `mezzanineflache`**, siehe oben.",
  "Flächenvarianten ohne mezzanineflache"),

 ("SKILL.md",
  """`GET /v1/units/:id` gibt `rs_category`, `total_floor_space`, `industrial_area`, `hall_height`, `floor_load` **top-level als `null` zurück, auch wenn sie gesetzt sind.** Die echten Werte stehen in `required_fields` / `optional_fields`:

```bash
curl -s "https://api.propstack.de/v1/units/<ID>?api_key=<OBJ_KEY>" | python3 -c "
import json,sys; d=json.load(sys.stdin)
for f in d['required_fields']+d['optional_fields']: print(f['name'],'=',f['value'])
print('Typ:', d.get('rs_type'), d.get('object_type'))"
```

`usable_floor_space` wird dagegen top-level gespiegelt — die Inkonsistenz ist nicht systematisch. **Ein `200 ok` ist kein Beweis. Immer zurücklesen.**""",
  """`GET /v1/units/:id` liefert `rs_category`, `total_floor_space`, `industrial_area`, `hall_height`, `floor_load`, `plot_area`, `price_on_inquiry`, `broker_id`, `property_status_id` **überhaupt nicht** — die Keys fehlen, sie sind nicht `null`. `required_fields` / `optional_fields` enthalten nur anzeigeformatierte Texte („Gesamtfläche ca." = „3.206 m²") und taugen **nicht** als Read-Back.

Belastbar ist der Listenkanal mit `expand=1` — **immer mit `per`**, sonst liefert er trotz ID-Filter nur 20 Datensätze (HTTP 200, kein Hinweis; gemessen: 30 angefragt → 20 zurück, 60 → 20, 100 → 20):

```bash
GET /v1/units?expand=1&per=100&property_ids[]=<ID>&property_ids[]=<ID>…
```

Dort stehen 296 Felder inklusive echter `rs_category`, `rs_type` und aller Custom Fields mit `value` **und** `pretty_value`. Nur per Einzelabfrage belastbar: `property_status_id` (über `status.id`), `lat`/`lng`, Eigentümer (über die paginierte Liste `GET /v1/relationships`).

**Zwei Pflichten bei jeder Batch-Prüfung:** die Menge der zurückgelieferten IDs gegen die angefragten vergleichen und bei Differenz laut abbrechen — eine Lücke sieht sonst aus wie „keine Abweichung"; und Lesefehler **pro Einheit** abfangen, nicht pro Block (ein 404 auf eine verwaiste ID darf nicht den ganzen Block verschlucken).

`page`/`per`-Vollscans sind während eines Schreiblaufs **nicht stabil** (Sortierung nach `updated_at`): derselbe Scan lieferte 2.059, 2.185 und 2.042 Einheiten, Datensätze fallen zwischen zwei Seiten durch und kommen doppelt vor. Für Kampagnen erst alle IDs sammeln (mehrere Durchläufe, Vereinigungsmenge) und dann per `property_ids[]` arbeiten — oder bis zum Fixpunkt iterieren.

**Ein `200 ok` ist kein Beweis, und „n geschrieben, 0 Fehler" belegt nur die Vollständigkeit gegenüber der eigenen Arbeitsliste, nicht gegenüber dem Bestand.**""",
  "Read-Back-Kanal und Paginierung"),

 ("SKILL.md",
  """## Schritt 3: Existenzprüfung

```bash
curl -s "https://api.propstack.de/v1/projects?api_key=<OBJ_KEY>&q=<ORT>"
curl -s "https://api.propstack.de/v1/units?api_key=<OBJ_KEY>&q=<ORT>"
```
""",
  """## Schritt 3: Existenzprüfung

⚠️ **`q=` durchsucht `name`, NICHT `title`.** Am 19.08.2026 hat `q=Westside` das Projekt
„Gewerbepark in (65) Frankfurt am Main" mit dem Titel „FRANKFURT WESTSIDE" **nicht**
gefunden — Ergebnis waren 8 Dubletten. Der Marketingname des Eigentümers steht im `title`,
gesucht wird im `name`, und der folgt dem Hausschema `<Objektart> in (XX) Ort`.
**Der belastbare Schlüssel ist PLZ + Straße:**

```bash
# Pflicht: über Adresse suchen
curl -s "https://api.propstack.de/v1/projects?api_key=<OBJ_KEY>&q=<PLZ>"
curl -s "https://api.propstack.de/v1/units?api_key=<OBJ_KEY>&q=<STRASSE>"
# Ergänzend: über Ort, Eigentümer und Marketingnamen
curl -s "https://api.propstack.de/v1/projects?api_key=<OBJ_KEY>&q=<ORT>"
curl -s "https://api.propstack.de/v1/units?api_key=<OBJ_KEY>&q=<ORT>"
```

Wer neu anlegt, ohne über PLZ **und** Straße geprüft zu haben, erzeugt Dubletten.
""",
  "Existenzprüfung über PLZ und Straße"),

 ("references/api-fields.md",
  "| Rampentore | `ramepntore` | string/number | 7 |",
  "| Rampentore (nur Rampen, nackte Zahl) | `ramepntore` | string | 7 |\n"
  "| **Ebenerdige Tore** (so in der Maske; `pretty_name` sagt „Anzahl Rampentore 2\") "
  "| `anzahl_rampentore_2` | number | 3 |",
  "Torfelder in der Haupttabelle"),

 ("references/api-fields.md",
  "| Mezzaninefläche (Flächen-Sektion) | `mezzanineflache` | number | 310 |",
  "| ~~Mezzaninefläche (Flächen-Sektion)~~ | `mezzanineflache` | number, **unit euro** "
  "| **nicht befüllen** — Feld der Preise-Sektion |",
  "mezzanineflache als Preisfeld markiert"),

 ("references/api-fields.md",
  "⚠️ **WICHTIG:** `mezzanineflache` direkt setzen funktioniert NICHT! Immer "
  "`mezzanineflache_verfugbar` verwenden – das befüllt `mezzanineflache` automatisch.",
  "⚠️ **KORRIGIERT 17.08.2026.** Hier stand: „`mezzanineflache` direkt setzen funktioniert "
  "NICHT! Immer `mezzanineflache_verfugbar` verwenden – das befüllt `mezzanineflache` "
  "automatisch.\" Beide Hälften sind falsch. Das Feld **ist** schreibbar (getestet an Einheit "
  "4934596), und es wird **nicht** automatisch befüllt — 677 Einheiten hatten `_gesamt` "
  "gefüllt, aber nur 16 das obere Feld. Trotzdem tabu: es trägt die Einheit `euro` und steht "
  "in der Maske in der Sektion **Preise**. Eine Fläche darin erscheint als Geldbetrag. "
  "Mezzaninfläche gehört in `mezzanineflache_gesamt` / `_verfugbar`, die Miete in "
  "`intern_mietpreis_mezzanine`.",
  "api-fields: Mezzanin-Warnung korrigiert"),
]

def main():
    pruefen = "--pruefen" in sys.argv
    print("Skill-Verzeichnis: %s" % BASIS)
    if not BASIS.is_dir():
        print("  Verzeichnis existiert nicht - nichts zu tun.")
        return 0
    offen, gesetzt, fehlend = [], [], []
    for datei, alt, neu, name in KORREKTUREN:
        p = BASIS / datei
        if not p.exists():
            fehlend.append("%s (Datei fehlt: %s)" % (name, datei)); continue
        s = p.read_text(encoding="utf-8")
        if neu in s:
            gesetzt.append(name)
        elif alt in s:
            offen.append((p, alt, neu, name))
        else:
            fehlend.append("%s (weder alter noch neuer Text gefunden)" % name)

    for name in gesetzt:
        print("  ok      %s" % name)
    for _, _, _, name in offen:
        print("  %s %s" % ("FEHLT   " if pruefen else "gesetzt ", name))
    for name in fehlend:
        print("  UNKLAR  %s" % name)

    if not pruefen:
        for p, alt, neu, name in offen:
            p.write_text(p.read_text(encoding="utf-8").replace(alt, neu, 1), encoding="utf-8")

    print("\n%d von %d Korrekturen vorhanden%s"
          % (len(gesetzt) + (0 if pruefen else len(offen)), len(KORREKTUREN),
             ", %d offen" % len(offen) if pruefen and offen else ""))
    if fehlend:
        print("ACHTUNG: %d Korrektur(en) nicht zuordenbar - Skill-Datei hat sich geaendert."
              % len(fehlend))
        return 2
    return 1 if (pruefen and offen) else 0

if __name__ == "__main__":
    sys.exit(main())
