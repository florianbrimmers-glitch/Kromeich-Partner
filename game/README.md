# Kromeich Heroes

Rundenbasiertes, HoMM3-inspiriertes Handyspiel. Asynchroner Multiplayer
fuer Spiele mit Familie und Freunden ueber mehrere Tage.

**Phase**: Fundament (siehe Plan-Datei im Root-Ordner).

## Status dieser Session

Dieses Verzeichnis enthaelt das **Scaffold** und die Balance-Datenbasis.
Was laeuft:

- `data/*.json` — 4 Fraktionen, 28 Einheiten, 22 Spells, 20 Artefakte
  (davon 8 `game_changer`). Jede Zeile mit `balance_source`-Kommentar.
- `data/balance_notes.md` — Audit-Trail fuer jede Abweichung von HoMM3/HotA
  mit Equilibris-Begruendung.
- `scripts/core/Battle.cs` + `DeterministicRng.cs` — deterministische,
  xorshift64-basierte Kampfengine (C#, .NET 8).
- `tools/balance_sim.py` — Monte-Carlo-Simulator fuer Fraktion-vs-Fraktion;
  spiegelt die Kampfformel aus Battle.cs.
- `tests/` — pytest-Suite (8 Tests, alle gruen).

Was **noch nicht** laeuft (geplant fuer Folge-Commits):

- Godot-Szenen (Weltkarte, Stadt, Kampf-UI)
- Zufallskarten-Generator (`scripts/core/MapGen.cs`)
- Supabase-Multiplayer-Client
- Android-Build-Pipeline
- C#-Test-Runner (bisher nur Python-Tests)

## Setup

```bash
# Python-Simulator + Tests (benoetigt: python 3.11+, pytest)
pip install pytest
python -m pytest game/tests/ -v

# Balance-Simulator
python game/tools/balance_sim.py --runs 1000 --week 4 --seed 42

# Godot-Projekt (erst sinnvoll, wenn Scenes da sind)
# 1. Godot 4.2+ mit .NET/C# Unterstuetzung installieren
# 2. game/project.godot oeffnen
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
