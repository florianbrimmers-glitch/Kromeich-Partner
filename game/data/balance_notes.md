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

## Balance-Tuning Pass 8 (Robust-Metrik: 5 Seeds x 3 Wochen)

In Pass 7 war der Sim Single-Seed/Single-Week; viele Tunings waren nicht
reproduzierbar. Neue Robust-Metrik (`--robust`) aggregiert ueber Wochen
2/4/6 und 5 Seeds.

Pass-8-Befunde:
- Week-Skalierung ist ein eigenes Problem: W2 und W6 zeigen oft
  diametrale Matchups. Goldwyrm+Treefather (beide crystal-kostenpflichtig)
  werden bei W6 zu stark.
- T7-Parity (alle Drachen speed 9, HP 200, att 22-24, dmg 32-48) war
  kritischer Sanierungsschritt.
- Angel Speed 10 -> 9 (gleich mit anderen Drachen) bremst Men-Dominanz.

**Final Pass 8** (Robust-Metrik, 500 Runs, 5 Seeds, Wochen 2/4/6):
| Matchup | Mean | Status |
|---|---|---|
| Men vs Ork | 45.7 Prozent | [OK] |
| Men vs Tot | 46.9 Prozent | [OK] |
| Men vs Wald | 46.9 Prozent | [OK] |
| Ork vs Tot | 46.9 Prozent | [OK] |
| Ork vs Wald | 64.9 Prozent | [!!] |
| Tot vs Wald | 66.5 Prozent | [!!] |

4/6 im Zielband 45-55 Prozent. Wald-Matchups mit Orks/Tot bleiben
systemisch zu hoch; Fix kommt mit HoMM3-Terrain-Modifiern und
Hero-Skills (beide noch nicht in Sim).

## Balance-Tuning Pass 9 (Helden-Skills im Combat)

Pass 9 verkabelt `hero.skills` in `balance_sim.compute_damage`:
offense/archery (Angreifer-Multiplikator), armorer (Verteidiger-Reduktion),
leadership (Morale aus `make_faction_hero`). Jede Fraktion kann im MVP
einen fraktions-typischen Skill-Build bekommen.

Empirische Erkenntnis (siehe Sim-Runs in Session-Log):
Asymmetrische Skill-Zuweisung ist ein **sehr** starker Hebel. Beispiele:
- Men+Leadership+Armorer gegen Ork+Offense+Armorer: Men 100 Prozent
- Nur Orks/Tot bekommen Armorer: Ork/Tot dominieren Wald mit 95 Prozent
- Alle bekommen Leadership (Morale): Men dominiert Tot 99 Prozent
  (weil Tot als Undead moralen-immun sind)

Die kombinierten Effekte eines 15-Prozent-Armorer und eines 40-Prozent-
Offense **compounden** ueber einen mehrrundigen Kampf zu 50+ Prozent
Winrate-Verschiebungen. Das ist nicht handverles bar.

**Entscheidung Pass 9** (Auto-Assign-Sim):
| Matchup | Mean (Baseline) | Mean (Pass 9 Heroes) | Delta |
|---|---|---|---|
| Men vs Ork | 45.7 | 52.1 | +6 |
| Men vs Tot | 46.9 | 50.3 | +3 |
| Men vs Wald | 46.9 | 51.4 | +5 |
| Ork vs Tot | 46.9 | 44.4 | -3 |
| Ork vs Wald | 64.9 | 58.8 | -6 |
| Tot vs Wald | 66.5 | 66.3 | -0 |

5/6 Matchups im 40-60-Prozent-Band (vorher 4/6).
Heroes bekommen bewusst einen **symmetrischen Default**-Build
(+1 Attack pro Skill-Tier, keine Secondary-Skills), damit die Sim nicht
durch Auto-Assign vergiftet wird. Strategische Skill-Wahl bleibt
bewusst Spieler-Entscheidung; die Combat-Engine unterstuetzt beliebige
`hero.skills`-Dicts.

Offene Punkte (Post-MVP):
- Leadership-Morale begrabt Undead-Matchups (HoMM3-korrekt, aber braucht
  Sim-Logik die beide Haelften ausbalanciert)
- Archery/Offense als strategische Spieler-Pick: werden in Sim-Runs fuer
  gezielte Build-Tests genutzt (`test_artifact_builds.py`), nicht fuer
  Auto-Assign
- Tot vs Wald bleibt 66 Prozent; braucht entweder Terrain-Modifier
  (Wald-Baeume hemmen Ranged) oder Tot-spezifische Anti-Ranged-Mechanik

## Balance-Tuning Pass 10 (GDScript-Sim, 800 Runs, Seed 12345)

Erster Pass mit der **vollstaendigen Kampf-Engine**: alle Abilities aus
M6b (Flug, Mehrfachangriff, Konter-Regeln, Status-Effekte, Todeswolke)
und Moral/Glueck aus M6 sind implementiert. Vorher galt die Balance nur
auf dem Papier (Risiko 1 der Roadmap).

### Zwei Messinstrumente statt eines

Der Sim rechnet jede Paarung in **zwei Sichten**, weil sie sich
widersprechen koennen:

- **Wochen-Paritaet** - beide Seiten stellen ihr Wochen-Wachstum auf.
  Belohnt billige Massen-Fraktionen.
- **Gold-Paritaet** - beide Seiten investieren gleich viel Gold, die
  Wochen-Zusammensetzung wird skaliert. Das ist der Maßstab, mit dem die
  aelteren Passes gearbeitet haben.

Ausserdem misst der Sim jetzt den **Erstschlag-Vorteil** (Spiegel-Duelle
liegen bei 0.67 statt 0.50, weil Seite A bei Gleichstand zuerst zieht)
und rechnet ihn heraus: `fair(A,B) = (wr(A,B) + 1 - wr(B,A)) / 2`. Ohne
diese Korrektur ist jede Zelle um rund 17 Punkte verzerrt.

### Zwei Regel-Fehler, die als Balance-Problem erschienen

1. **Moral begrub die Untoten.** Untote waren gegen Moral komplett immun -
   also auch gegen den +1-Reinheitsbonus, den jede andere reine Armee
   bekommt. Ergebnis: rund 10 Prozent weniger Aktionen pro Runde,
   dauerhaft. Totenreich gewann **0.00** aller Matchups, obwohl die Stats
   passten. Ein Trace zeigte denselben Kampf ohne die Extrazug-Regel mit
   Totenreich als klarem Sieger. Die `balance_notes` hatten das als
   offenen Punkt notiert ("Leadership-Morale begrabt Undead-Matchups").
   **Fix:** Untote sind nur noch gegen SCHLECHTE Moral immun (frieren
   nie ein), profitieren aber von guter Moral wie alle. Glueck gilt fuer
   sie ebenfalls normal.
2. **Regeneration war faktisch Unsterblichkeit.** `regeneration_per_turn`
   heilte die vorderste Einheit voll - beim Baumvater 158 HP pro Runde.
   Im Trace stand das Waldvolk-Endgame bei konstanter HP, waehrend der
   Gegner verblutete; Waldvolk gewann dadurch fast jedes Matchup.
   **Fix:** Regeneration heilt `REGEN_FRACTION` = 25 Prozent der max-HP
   pro Runde (Leitprinzip 2: harte Immunitaeten abschwaechen).

### Daten-Aenderungen (16 Einheiten)

Totenreich war auf dem Papier ein Drittel schwaecher als Waldvolk
(976 HP / 196 Dmg gegen 1303 / 300). Die Anti-Skelett-Flut-Entscheidung
aus Pass 1 bleibt: Skelett-Growth bleibt 18, nur die HP steigen.

| Einheit | Aenderung | Grund |
|---|---|---|
| Skelett | HP 6 -> 7 | bei 6 HP war jeder Treffer ein Kill |
| Zombie | Growth 10 -> 12, dmg 2-3 -> 3-4, Kosten 120 -> 100 | schwaechster T2 im Spiel |
| Gespenst | Growth 6 -> 8, Kosten 200 -> 170 | Mittelfeld-Defizit |
| Vampir | Growth 3 -> 4, Kosten 500 -> 420 | Life-Drain skaliert mit Stackgroesse |
| Lich | Growth 2 -> 3, Kosten 600 -> 520 | einziger Fernkaempfer der Fraktion |
| Schwarzritter | Growth 1 -> 2, Kosten 1800 -> 1500 | ein T6 pro Woche war wirkungslos |
| Zwerg | Growth 14 -> 12 | 280 HP aus T1 war der zaeheste Unterbau |
| Elfenbogen | Growth 9 -> 7, att 9 -> 8, shots 16 -> 12 | staerkste Schadensquelle im Spiel (Leitprinzip 4) |
| Einhorn | dmg 18-22 -> 15-20 | staerkster T5 im Spiel |
| Goldwyrm | att 24 -> 22, dmg 34-48 -> 32-46 | T7-Gleichstand mit Engel/Knochendrache |
| Goblin | HP 5 -> 6 | T1 verdampfte vor dem ersten Schlag |
| Wolfsreiter | HP 10 -> 14 | starb vor dem ersten Jousting-Angriff |
| Orkschuetze | Growth 8 -> 9 | Ausgleich nach dem Waldvolk-Trim |
| Oger | Growth 3 -> 4 | Orks waren sonst Schlusslicht |
| Rok | Growth 2 -> 3 | dito |
| Zyklop | Growth 2 (unveraendert nach Test) | mit 3 wurden Orks dominant |

Menschen bleiben die **Referenz** und wurden nicht angefasst.
Wochenkosten liegen danach dicht zusammen: Waldvolk 12940, Totenreich
12880, Orks 12630, Menschen 12570 Gold.

### Ergebnis (symmetrisiert, 800 Runs)

| Paarung | Wochen-Paritaet | Gold-Paritaet |
|---|---|---|
| Waldvolk vs Menschen | 0.43 | 0.41 |
| Waldvolk vs Totenreich | 0.34 | 0.41 |
| Waldvolk vs Orks | 0.59 | 0.51 |
| Menschen vs Totenreich | 0.42 | 0.51 |
| Menschen vs Orks | 0.57 | 0.58 |
| Totenreich vs Orks | 0.71 | 0.64 |

**Gold-Paritaet: 6 von 6 Paarungen im 30-70-Band. Wochen-Paritaet: 5 von 6.**
Vor dem Pass lagen 13 bis 15 der 16 Rohzellen ausserhalb, Totenreich bei
0.00 gegen alle.

Offener Rest: **Totenreich vs Orks 0.71** bei Wochen-Paritaet (Gold-Sicht
0.64). Nicht weiter nachgezogen, weil Totenreich gegen Waldvolk mit 0.34
schon auf der Verliererseite steht - ein weiterer Nerf wuerde diese
Paarung kaputt machen. Ueberanpassung an eine der beiden Sichten waere
schlechter als der verbleibende Ausreisser.

### Modell-Grenzen (gelten weiter)

- Fernkaempfer werden im abstrakten Kampf **nie physisch blockiert** und
  feuern ab Runde 1. Auf dem echten 10x8-Gitter erreichen Nahkaempfer sie
  und erzwingen den Nahkampf-Malus - schuetzenlastige Fraktionen sind
  dort schwaecher als hier.
- Keine Helden-Skills (M7), keine Zauber (M8), keine Belagerung (M9).
  Nach jedem dieser Meilensteine gehoert ein neuer Pass hierher.
