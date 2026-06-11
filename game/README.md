# Kromeich Heroes

Rundenbasiertes, HoMM3-inspiriertes Handyspiel in **Godot 4.6** (reines
GDScript). Ziel: asynchroner Multiplayer fuer Spiele mit Familie und
Freunden ueber mehrere Tage.

## Was laeuft (spielbar)

- **Weltkarte** (`scripts/ui/WorldMapScreen.gd`): deterministische
  Zufallskarte (Seed), 6 Terrain-Typen, Fog of War, Dijkstra-Bewegung,
  Staedte/Goldminen/Schaetze/Monster, KI-Gegner mit eigener Oekonomie.
- **Kalender**: 1 Zug = 1 Tag, 7 Tage = Woche, 4 Wochen = Monat,
  12 Monate = Jahr (`scripts/core/GameCalendar.gd`).
- **4 Fraktionen** (Waldvolk/Menschen/Totenreich/Orks) mit je 3 Einheiten
  (`scripts/core/UnitType.gd`), taegliches Pool-Wachstum pro Stadt
  (Bresenham-verteilt, stapelt sich, verfaellt nicht).
- **Stadt-Screen** (`scripts/ui/CityScreen.gd`): isometrische Ansicht mit
  Gebaeude-Hotspots (aktuell Platzhalter-Grafik; KI-Sprite-Pipeline siehe
  `assets/city/ART_SPEC.md`).
- **Taktischer Kampf** (`scripts/ui/TacticalBattleScreen.gd`): Grid-Kampf
  mit Initiative, Fernkampf, Gegenschlag, Obstacles.
- **Held** (`scripts/core/Hero.gd`): Level, XP, Armee mit max 6 Stacks.

## Tests & CI

Headless-Tests laufen ohne Display, lokal wie in der CI
(`.github/workflows/game-ci.yml`):

```bash
godot --headless --path game/ --import          # einmal (Class-Cache)
godot --headless --path game/ --script tools/test_core_logic.gd
godot --headless --path game/ --script tools/test_city_screen.gd
godot --headless --path game/ --script tools/balance_sim.gd -- --runs=500
```

## Test-Loop auf dem Handy

- **Schnell (empfohlen)**: One-Click-Deploy aus dem Godot-Editor uebers
  WLAN aufs Phone — Setup in `SETUP_WIRELESS_DEPLOY.md`.
- **APK aus CI** (zum Verteilen an Mitspieler): jeder Push baut via
  `.github/workflows/game-android-build.yml` ein APK-Artefakt
  (GitHub -> Actions -> Run -> "Artifacts", Login noetig, 14 Tage gueltig).

## Verzeichnis

- `scripts/core/` — Spiellogik, headless-testbar, kein Rendering
- `scripts/ui/` — Screens (Control-basiert, programmatisch aufgebaut)
- `tools/` — Headless-Skripte: Tests + Balance-Simulator
- `data/` — JSON-Datenbasis; Stand teils noch Planungs-Phase
  (28-Einheiten-Roster etc.), Migration in die Engine offen.
  `data/balance_notes.md` = Audit-Trail fuer Balance-Entscheidungen.
- `assets/` — Grafik (minimal; Art-Pipeline: `assets/city/ART_SPEC.md`)
- `scripts/net/supabase_schema.sql` — geplantes Multiplayer-Schema
  (matches/moves/match_players mit RLS), noch nicht angebunden.

Hinweis: Der urspruengliche C#/.NET- und Python-Prototyp wurde komplett
nach GDScript portiert und entfernt; die Git-History hat die Altdateien.

## Design-Philosophie

Kern-Leitlinie: **Chancengleichheit aller Fraktionen und Builds**, analog
zur Equilibris-Mod-Philosophie (HoMM4):

1. Balance-Zahlen sollen langfristig datengetrieben sein (`data/*.json`).
2. Simulator als Gatekeeper — Zielkorridor 40-60 Prozent Winrate pro
   Matchup (`tools/balance_sim.gd`; aktuell bekannt ausserhalb, Tuning
   steht aus).
3. Game-changer-Artefakte fuer distinkte Builds (geplant).
4. RNG-lastige Auto-Win-Abilities gedeckelt (geplant).
5. Keine Ubisoft-IP: alle Namen generisch, alle Assets eigen erstellt.

## Rechtliches

HoMM3 ist Ubisoft-IP. Dieses Projekt uebernimmt nur **Mechaniken** (nicht
schutzfaehig), keine Grafiken, Namen oder Texte. Fraktionen heissen
„Waldvolk", „Totenreich" usw. — nicht „Rampart", „Necropolis".

## Offene Design-Notizen

Siehe `CLAUDE.md` (Fraktions-Misch-Malus, Sandbox-Godot-Setup) und
`data/balance_notes.md`.
