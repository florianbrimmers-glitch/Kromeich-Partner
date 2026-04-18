# Kromeich Heroes

Rundenbasiertes, HoMM3-inspiriertes Handyspiel. Asynchroner Multiplayer
fuer Spiele mit Familie und Freunden ueber mehrere Tage.

**Phase**: Fundament (siehe Plan-Datei im Root-Ordner).

## Status dieser Session

Dieses Verzeichnis enthaelt das **Scaffold** und die Balance-Datenbasis.
Was laeuft:

- `data/*.json` — 4 Fraktionen, 28 Einheiten, 22 Spells, 20 Artefakte
  (davon 8 `game_changer`) und 2 Karten-Templates. Jede Zeile mit
  `balance_source`-Kommentar.
- `data/balance_notes.md` — Audit-Trail fuer jede Abweichung von HoMM3/HotA.
- `scripts/core/Battle.cs` + `DeterministicRng.cs` + `MapGen.cs` —
  deterministische, xorshift64-basierte Engine (C#, .NET 8).
- `scripts/net/SupabaseClient.cs` + `supabase_schema.sql` —
  Multiplayer-Schema (matches, moves, match_players) mit RLS + Client-Stub.
- `tools/balance_sim.py` — Monte-Carlo-Simulator mit Helden, Spells, Morale.
- `tools/map_gen.py` — Zonen-basierter Zufallskarten-Generator,
  ASCII-Render fuer Debug, exakt spiegelgleich zu MapGen.cs.
- `tools/play_battle.py` — CLI-Kampf mit Turn-Log.
- `tests/` — **19 pytest-Tests**, alle gruen.

Was **noch nicht** laeuft (geplant fuer Folge-Commits):

- Godot-Szenen: Main.tscn (Titel) und Battle.tscn (Auto-Replay-Kampf)
  sind da. Weltkarte, Stadt, Held-Screen folgen.
- Android-Build-Pipeline: Workflow ist eingerichtet (siehe unten),
  aber noch nicht ueber CI verifiziert.
- Supabase-Realtime-WebSocket-Client (bisher nur REST-Stub)
- C#-Test-Runner (bisher nur Python-Tests)
- Artefakt-Effekte in Battle.cs (Daten da, Python-Sim hat sie; C# noch nicht)

## Android-APK bauen (CI)

1. GitHub-UI → Actions → "Android APK Build" → "Run workflow".
2. `build_type` waehlen (`debug` zum Probieren, `release` erst wenn wir
   eine echte Signing-Keystore in Secrets hinterlegt haben).
3. Nach ~10-15 Minuten erscheint ein APK-Artefakt (`KromeichHeroes-debug-<sha>`).
4. Download -> auf Android-Handy installieren (Einstellungen ->
   "Installation aus unbekannten Quellen" einmalig erlauben).

**Wichtig:** Godot-4.2-C#-nach-Android gilt als experimentell. Erste
Builds scheitern meist an einem der folgenden Punkte; beide sind
dokumentiert/fixbar:
- Android-Build-Template nicht installiert -> Step
  `Install Android build template` im Workflow soll das machen.
- Debug-Keystore fehlt -> Workflow legt `~/.android/debug.keystore` an.
- Java-SDK-Pfad falsch -> Workflow zieht ihn aus `JAVA_HOME`.

Bei Failure zieht der Workflow `godot-logs-<sha>` als Artefakt;
dort stehen die naechsten Schritte drin.

## Setup

```bash
# Python-Simulator + Tests (benoetigt: python 3.11+, pytest)
pip install pytest
python -m pytest game/tests/ -v

# Balance-Simulator
python game/tools/balance_sim.py --runs 1000 --week 4 --seed 42

# Einen Kampf live anschauen
python game/tools/play_battle.py --a menschen --b totenreich --seed 42 --verbose

# Zufallskarte generieren und rendern
python game/tools/map_gen.py --template duell_klein --seed 42 --render

# Godot-Projekt (erst sinnvoll, wenn Scenes da sind)
# 1. Godot 4.2+ mit .NET/C# Unterstuetzung installieren
# 2. game/project.godot oeffnen

# Supabase (Multiplayer): scripts/net/supabase_schema.sql im SQL-Editor
# eines neuen Supabase-Projekts ausfuehren. SUPABASE_URL + ANON_KEY in
# Godot-Projekt-Settings als Autoload-Variable hinterlegen.
```

## Design-Philosophie

Kern-Leitlinie: **Chancengleichheit aller Fraktionen und Builds**, analog
zur Equilibris-Mod-Philosophie (HoMM4). Umgesetzt durch:

1. Datengetriebene Balance — alle Zahlen in `data/*.json`, nichts
   hart-codiert.
2. Simulator als Gatekeeper — Zielwert 45-55 Prozent Winrate pro Matchup.
3. 8+ game-changer-Artefakte ermoeglichen distinkte Builds (Archmage,
   Armageddon-Dragon-Slave, Nekro-Swarm, Siege, …).
4. RNG-lastige Auto-Win-Abilities (Blind, Bind, Curse) auf 10-20 Prozent
   Chance gedeckelt.
5. Keine Ubisoft-IP: alle Namen generisch, alle Assets werden eigen
   erstellt.

## Rechtliches

HoMM3 ist Ubisoft-IP. Dieses Projekt uebernimmt nur **Mechaniken** (nicht
schutzfaehig), keine Grafiken, Namen oder Texte. Fraktionen heissen
„Waldvolk", „Totenreich" usw. — nicht „Rampart", „Necropolis".

## Quellenverzeichnis fuer Balance-Entscheidungen

Siehe `data/balance_notes.md`.
