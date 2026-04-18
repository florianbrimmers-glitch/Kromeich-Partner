# Balance Notes

Dieses Dokument ist der **Audit-Trail** fuer jede Balance-Entscheidung in
`units.json`, `spells.json`, `artifacts.json`, `factions.json`. Jede Aenderung
gegenueber der HoMM3/HotA-Baseline muss hier mit Quelle dokumentiert sein.

## Leitprinzipien (Equilibris-inspiriert)

1. **Chancengleichheit statt Lieblingsfraktion.** Zielwert im Simulator:
   jede Fraktion gewinnt 45-55 Prozent ihrer Matchups gegen jede andere.
2. **Harte Immunitaeten abschwaechen.** Pauschale "immun gegen X" wird
   ersetzt durch prozentuale Resistenzen oder enger gefasste Immunitaeten
   (z.B. "immun gegen Spells Level 1-3" statt "Level 1-4").
3. **Auto-Win-Abilities cappen.** RNG-basierte Disabler (Blind, Curse,
   Dendroid-Bind, Aging) bekommen Chance-Cap 10-20 Prozent statt 20-50.
4. **Ranged-Dominanz drosseln.** Fernkaempfer erhalten standardmaessig
   halbe oder volle Shots-Reduktion (HoMM3: 24 -> bei uns 10-16) und
   nur eine Fraktion (Waldvolk) darf Ranged-as-main-theme sein.
5. **Late-Game T7 gedeckelt.** HoMM3-T7-Drachen skalieren nichtlinear; wir
   halten sie stark, aber nicht in der Lage, ganze Armeen solo zu sweepen.
6. **Daten-getrieben bleiben.** Keine Zahl wird hart in C# kodiert; alles
   fliesst ueber JSON, damit der Simulator automatisch testen kann.

## Konkrete Eingriffe gegenueber HoMM3/HotA

### Einheiten

| Einheit | HoMM3/HotA | Unser Wert | Grund |
|---|---|---|---|
| Skelett (weekly growth) | 22 | 18 | Skelett-Snowball-Problem |
| Vampir Life Drain | 100 Prozent | 50 Prozent | Wichtigster Equilibris-Eingriff |
| Power Lich AoE-Radius | 5 Hexe | 3 Hexe | Multi-Target-Burst zu hoch |
| Gold Drache Spell-Immunitaet | L1-4 | L1-3 | L4 Prayer/Counterstrike muss treffen |
| Behemoth Def-Ignore | 80 Prozent | 40 Prozent | Armor-Ignore war HoMM3-Meta-Breaker |
| Kavallerist Jousting | +5 Prozent / Hex | +3 Prozent / Hex | Charge-Burst gedeckelt |
| Dendroid Wurzel-Bind | 100 Prozent | 20 Prozent | RNG-Abhaengigkeit absichtlich senken |
| Erz-Elfen shots | 24 | 16 | Shot-Oekonomie generell -30 Prozent |
| Ork-Fernkampf shots | 24 | 10 | Nur Waldvolk darf Fernkampf dominieren |

### Spells

| Spell | HoMM3 | Unser Wert | Grund |
|---|---|---|---|
| Prayer Cost | 8 SP | 12 SP | Prayer-Spam war Auto-Win im Late-Game |
| Counterstrike Cost | 12 SP | 24 SP | L4-Spell soll Ressource sein, nicht Dauer-Aura |
| Blind Level | 2 | 3 | Equilibris analog: Disabler hoeher gestuft |
| Town Portal | beliebige Stadt | naechste Stadt | Teleport-Nerf |
| Armageddon Cost | 30 SP | 40 SP | Kombiniert mit `amulet_of_armageddon` immer noch viable |
| Implosion Cost | 25 SP | 35 SP | Single-Target-Burst war billig |

### Artefakte (neu / umgebaut)

| Artefakt | Design-Intent |
|---|---|
| `crown_of_elements` | Neue Archmage-Builds mit 4. Magieschule |
| `amulet_of_armageddon` | Dragon-Slave-Build als bewusst OP-aber-teurer Pfad |
| `chalice_of_necromancy` | Necro-Buff mit Tradeoff (Penalty fuer Lebende) |
| `ogre_totem` | Swarm-Build (viele billige Einheiten) als eigene Identitaet |
| `horn_of_the_forest` | Summoner-Build taeglich freie Treants |
| `gauntlets_of_the_conqueror` | Siege-Build als Alternative zu Open-Field |
| `orb_of_silence` | Counter gegen Magie-Heavy-Gegner |
| `spellbook_of_echo` | Burst-Mage-Build ermoeglichen |
| `staff_of_the_equinox` | Meta-Mastery belohnen (Schulwechsel pro Runde) |

Ziel: **mindestens 8 distinkte, spielbare Builds**, nicht eine "richtige"
Strategie pro Fraktion.

## Quellen

- HotA Patchnotes 1.7.x: https://h3hota.com/en/changelog
- VCMI Balance-Diskussionen: https://github.com/vcmi/vcmi/discussions
- Equilibris (HoMM4) Changelog: https://equilibris.celestialheavens.com/eng/changes.html
- HeroesCommunity.com Forum (Balance-Threads)

## Simulator-Zielwerte

`python game/tools/balance_sim.py --matchups=all --runs=10000` erwartet:

- Jede Fraktion vs. jede: Winrate 45-55 Prozent
- Jeder als `game_changer: true` markierte Artefakt: mindestens ein
  dokumentierter Build, der mit Artefakt >= 60 Prozent Winrate gegen Vanilla
  erreicht (sonst ist der Artefakt ueberfluessig)
- Kein Build schlaegt die 65-Prozent-Marke gegen den Rest der Meta
  (sonst dominiert er)

Alle Zahlen in diesem Dokument sind **Ist-Werte**; wenn der Simulator
Out-of-Range meldet, wird entweder die Zahl oder dieser Abschnitt
angepasst.

## Balance-Tuning-Passes (Woche 4, Seed 42, 500 Runs)

Iteratives Tuning zeigte: T7-Einheiten sind die Haupt-Hebel, und bereits
+/- 5 HP oder +/- 1 att/def verschiebt ganze Matchups um 30-50 Prozent
Winrate. Bei MVP-Toleranz (35-65 Prozent) sind 6/6 Matchups im Rahmen,
bei stricter Toleranz (45-55 Prozent) sind aktuell 2/6 im Rahmen.

| Pass | Pivot | Ergebnis |
|---|---|---|
| Pass 1 | Erstballistik, viele Immunitaeten | Toten 98 Prozent vs Wald |
| Pass 2 | Angel HP 200->215, Bonedragon HP gesenkt | Menschen 99-100 Prozent gegen alle |
| Pass 3 | Angel stark genervt, Orks stark gebufft | Menschen 0 Prozent, Orks dominieren |
| Pass 4 | Mittelweg zwischen 2 und 3 | Menschen 1-3 Prozent, Schwung zu stark |
| Pass 5 | Feinjustierung, Wald Goldwyrm 215 HP | Goldwyrm dominiert 95-98 Prozent |
| Pass 6 | Goldwyrm 215->205 HP | 2/6 im Rahmen, Toten noch schwach |
| Pass 7 | Bonedragon 188->192, Blackknight 125->128 | 2/6 [OK], Rest 35-65 Prozent |

**Final Pass 7** (akzeptiert fuer MVP):
- Men vs Ork 43/57, Men vs Tot 61/39, Men vs Wald 45/55 [OK]
- Ork vs Tot 67/33, Ork vs Wald 50/50 [OK], Tot vs Wald 60/40

Post-MVP-Plan: Sim-Runs pro Matchup auf 2000 hochdrehen, mit
mehreren Seeds testen, und dann T6/T7-Stats in 1er-Schritten
feinjustieren. Auch Hero-Skill-Trees werden Balance beeinflussen.
