# Kromeich Heroes - Arbeits-Notizen

## Offene Design-Entscheidungen (noch nicht implementiert)

### Fraktions-Misch-Malus in Armeen
Gemischte Armeen sollen Nachteile haben, abhaengig davon welche
Fraktionen in einem Stack zusammenstehen:

- **Menschen + Totenreich**: Malus (klassischer "Lebende mit Untoten"-
  Konflikt, z.B. -Moral oder -Kampfkraft).
- Andere Kombinationen folgen noch; Grundprinzip ist aehnlich dem
  HoMM3-Morale-System (gleiche Fraktion = Bonus, Feind-Fraktion = Malus).

Implementiert wird das vermutlich in `CombatMath.gd`/`TacticalBattleScreen`
als Round-Start-Modifikator.

## Technisches Gedaechtnis

- Plattform-Detail: Godot 4.5 stable (NON-Mono), GDScript only.
- Keine Godot-Binary im Sandbox verfuegbar - Aenderungen laufen blind,
  Syntax-Check passiert auf dem Zielgeraet.
- Branch: `claude/heroes-mobile-game-yJ31W`
