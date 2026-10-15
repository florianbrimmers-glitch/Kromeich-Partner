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

### Artefakte (It. 51, kleine Fassung)

Das hier frueher beschriebene Schema (slot/tier/effects/game_changer, IDs wie
`crown_of_elements` oder `chalice_of_necromancy`) ist NICHT umgesetzt worden -
der Nutzer hat sich fuer die kleine Fassung entschieden. `artifacts.json`
kennt nur `bonus` (auf die vier Primaerwerte, benannt wie in skills.json) und
`rarity`; `Artifacts.gd` liest nichts anderes. Ein Eintrag nach dem alten
Schema haette leeren Bonus und Gewicht 1 - `test_artifacts` meldet ihn.

| Artefakt | Bonus | rarity |
|---|---|---|
| schwert_der_wacht | +2 Angriff | 30 |
| schild_des_bergvolks | +2 Verteidigung | 30 |
| helm_der_klarheit | +2 Wissen | 25 |
| stab_der_kraft | +2 Zauberkraft | 25 |
| umhang_des_spaehers | +1 Angriff, +1 Verteidigung | 35 |
| krone_der_weisen | +1 Zauberkraft, +2 Wissen | 15 |
| panzer_des_riesen | +3 Verteidigung | 10 |
| klinge_des_zorns | +3 Angriff, -1 Verteidigung | 12 |

Balance-Anker: auf Stufe 12 hat ein Held rund 11 Primaerpunkte aus
Aufstiegen; drei Plaetze geben hoechstens +6 auf einen Wert. Kein Relikt,
also keine Stufe-5-Zauber.

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
