# Kromeich Heroes - Arbeits-Notizen

## Roadmap-Status (autonome /loop-Schleife "HoMM3-Endausbau")

Vollstaendige Roadmap + Architektur-Entscheidungen: Plan-Datei der
Session bzw. Git-History. Scope-Entscheidungen des Nutzers:
Singleplayer zuerst (kein MP in dieser Schleife), MEHR-Ressourcen-System
wie HoMM3, 7 Einheiten-Tiers (units.json migrieren!), CC0-Sound.

| Meilenstein | Status |
|---|---|
| M1 Save/Load + Autosave + CI-Gate | FERTIG (Iteration 1) |
| M2 Hauptmenue (Fortsetzen, Fraktionswahl, Seed-Eingabe) | FERTIG (Iteration 2) |
| M3 Ressourcen-System (Wallet, Minen, Haufen, Markt-Tausch, Mehrkosten) | FERTIG (It. 3+4) |
| M4 Einheiten-Migration | KOMPLETT (It. 5-8). It. 7: begrenzte Schuesse + Nahkampf-Malus-Flags (Standard x0.5, melee_penalty_half x0.75, no_melee_penalty x1.0 - dokumentierte Interpretation). It. 8: Alt-IDs komplett raus - SAVE_VERSION=2, Mapping einmalig in SaveManager._migrate_1_to_2 (hero.army, KI-Armeen, Stadt-Pools; LEGACY_UNIT_IDS dort), UnitType.canonical() geloescht, Fixture v1 beweist die migrate-Kette. NAECHSTES (It. 9): M6b Battle-Abilities Rest (flying, double_attack, unlimited_retaliations, ...) - erst damit gilt die units.json-Balance |
| M6b Battle-Abilities | KOMPLETT (It. 9+10). Teil 2 (It. 10): neu `core/StatusFx.gd` - Status mit Dauer im Stack-Dict (`status: {name: runden}`): verwurzelt (1 Rd, keine Bewegung), geblendet/betaeubt (1 Rd, Zug + Konter verloren; Nahkampf-Treffer weckt Blendung), krank (3 Rd, -2 Att/-2 Def), verflucht (2 Rd, -25 % Schaden), gealtert (2 Rd, +25 % erlittener Schaden); Lich-Todeswolke trifft Nachbar-Stacks mit halbem Schaden; Marker (W/B/S/K/F/A) im Kampf-Gitter. CombatMath liest die Status direkt aus den Stacks. Nur noch `undead` offen -> gehoert zu M6 Moral. |
| M6b Teil 1 (It. 9, Details) | neu `core/Abilities.gd` (reine statische Regeln ueber den units.json-Flags, per preload eingebunden). Umgesetzt: flying (Dijkstra ignoriert Stein/Baum+Gelaende), double_attack/double_shot, unlimited_retaliations/no_retaliation (Konter-Zaehler statt Bool), defense_ignore_25pct, jousting_bonus(_light) ueber `tiles_moved`, polearm_bonus_vs_cavalry (Kavallerie = Jousting-Traeger), life_drain_50pct + regeneration (neu `CombatMath.heal`, Cap bei count_start). CombatMath.damage hat einen optionalen 7. `opts`-Parameter. balance_sim spiegelt alle Regeln und weist Unentschieden getrennt aus (Elfen-Spiegelduell endet durch Baumvater-Regeneration remis). |
| M6 Moral + Glueck + Fraktions-Mix | FERTIG (It. 11): neu `core/Morale.gd`. Moral je Seite aus der Armee (HoMM3-streng, Nutzer-Entscheidung): 1 Fraktion +1, 2 = 0, 3 = -1, 4 = -2, Lebende+Untote zusaetzlich -1, Engel-Aura +1, Clamp +-3. Wirkung 10 % je Punkt: negativ = Zugverlust, positiv = zweite Aktion (max 1/Runde/Stack, `morale_extra_used`). `undead` = immun gegen Moral UND Glueck. Glueck (x2/x0.5, 10 % je Punkt) kommt aus Kapellen: +1 je Kapelle, max +3 (`WorldMapScreen._player_luck`, ueber `player_luck` im Battle-Kontext). Erzfeind-Bonus `hates:necro_tier7` = +50 % (Engel vs. Knochendrache) in `Abilities.hate_bonus_pct`. Kopfzeile zeigt "Moral +1 Glueck +2". Damit sind ALLE kampfrelevanten units.json-Flags ausgewertet; offen nur die 4 Magie-Flags (M8) und `attack_wall` (M9). |
| Balance-Pass 10 | FERTIG (It. 12), dokumentiert in `data/balance_notes.md`. Zwei Regel-Fehler gefunden und behoben: (1) Untote waren gegen JEDE Moral immun und verloren dadurch die +1-Reinheitsmoral, die jede andere Armee bekommt -> Totenreich gewann 0.00 aller Matchups; jetzt nur noch gegen schlechte Moral immun, Glueck gilt normal. (2) `regeneration_per_turn` heilte voll -> Baumvater (158 HP) war unsterblich, Waldvolk gewann fast alles; jetzt `Abilities.REGEN_FRACTION` = 25 % der max-HP. Dazu 16 Einheiten getunt (Totenreich billiger+zahlreicher, Waldvolk getrimmt, Orks leicht rauf, Menschen unveraendert als Referenz). Sim kann jetzt Wochen- UND Gold-Paritaet, rechnet den Erstschlag-Vorteil heraus (Spiegel-Duelle lagen bei 0.67!) und hat `--trace=A,B` fuer Runde-fuer-Runde-Diagnose. Ergebnis: Gold-Paritaet 6/6 Paarungen im 30-70-Band, Wochen-Paritaet 5/6 (vorher 13-15 von 16 Rohzellen ausserhalb). |
| M10 Kampf-Sprites | FERTIG (It. 13): 28 Token-SVGs in `assets/units/<fraktion>/<id>.svg`, erzeugt von `tools/gen_unit_sprites.py` (datengetrieben aus units.json - NICHT per Hand editieren, Generator anpassen und neu laufen lassen). Silhouette nach Rolle (Fernkampf/Flieger/Reiter/Riese/Nahkampf), Tier skaliert die Figur (0.74-1.04) und steht als Punktreihe am Sockel, ab T5 Hoerner, Erkennungszeichen aus den Abilities (Heiligenschein, Fangzaehne, Rippen, Todeswolke, Hammer, ...). Untote knochenfarben mit Fraktions-Aura. Wichtig: Token-Scheibe im Kampf ist DUNKEL (`fill.darkened(0.72)`), Seite steckt im Ring - Menschen-Gold auf goldener Scheibe war unsichtbar; Beschriftung deshalb hell mit Schlagschatten. Fallback auf die alten Kreise bleibt, wenn eine SVG fehlt. `tools/preview_unit_tokens.gd` (Kontaktbogen) + `tools/preview_battle_full.gd` (Gitter in Geraetegroesse) rendern headless; der echte Screen laesst sich headless NICHT rendern. test_battle prueft die Abdeckung aller 28 Token. |
| M9 Belagerung | FERTIG (It. 14): neues `BattleObstacles.KIND_WALL` (blockt Bewegung+Schusslinie, `WALL_SEGMENT_HP`=2) + `siege_walls(cols, rows)` = Segmentreihe in Spalte `cols-4` mit Tor-Luecke in der Mittelreihe. Kampf-Screen: `ctx.siege`/`ctx.tower_dmg`, `_wall_hp` je Segment; Katapult trifft pro Runde das tor-naechste Segment (1 Schaden), zerstoertes Segment fliegt aus `_obstacles` UND `_ob_map` -> Feld sofort passierbar; Pfeilturm (SIEGE_TOWER_DMG 12 + 8 je Wachturm) trifft pro Runde den groessten Angreifer-Stack; Verteidiger +SIEGE_DEF_BONUS (2) solange ein Segment steht; `attack_wall`-Einheiten (Zyklop) schlagen per Tap selbst Segmente ein. **Falle:** `_dijkstra_for` prueft Hindernis-Arten als Literale - neue Kinds dort NACHTRAGEN (die Mauer blockte zuerst nicht). Ausserdem: Stadt-Wachen bestehen jetzt aus Einheiten der Stadt-Fraktion (`_faction_guard_stacks`), und die Auto-Abrechnung bei KI-Angriffen rechnet die eigene Mauer mit `SIEGE_AUTO_DEF_FACTOR` (1.25) ein. 8. Suite `tools/test_siege.gd`. |
| Echte Garnisonen (M9b) | FERTIG (It. 15). Vorher hielt jede Stadt nur `garrison: int` (Phantom-Truppen wurden beim Angriff synthetisiert) und die Spielerstadt startete mit 0 - die Mauer aus M9 schuetzte niemanden. Jetzt: `city["garrison_army"]` ist ein `{uid: count}`-Dict wie `Hero.army`, neues `core/Garrison.gd` (synth/total/add/remove/to_stacks/from_stacks/summary). **SAVE_VERSION=3** + `_migrate_2_to_3` (alte Zahl -> echte Einheiten der Stadt-Fraktion). Rekrutieren OHNE Held vor Ort fuellt die Garnison (Fernverwaltung existierte schon); CityScreen hat einen Garnison-Button mit Verschiebe-Panel (Held <-> Stadt, 1/alle, respektiert MAX_ARMY_SLOTS). Kampf nutzt die gespeicherten Einheiten; `battle_finished` liefert jetzt `player_remaining` + `enemy_remaining`, damit eine gescheiterte Belagerung die Garnison geschwaecht zuruecklaesst. KI-Angriff auf eigene Stadt = **spielbarer Verteidigungskampf** (gleiches Muster wie der Pflicht-Kampf gegen den Helden: Overlay auf, `return false`, Callback `_on_city_defense_result` setzt die KI-Phase fort); Verteidiger = Garnison + Held falls anwesend. `SIEGE_AUTO_DEF_FACTOR` entfallen. 9. Suite `tools/test_garrison.gd`. |
| Grafik-Politur (It. 16) | FERTIG. Stadt: Effekt-Text von der Buehne runter (er lief in den Nachbar-Plot; steht jetzt beim Tap in der Statuszeile), Beschriftung auf 2 Zeilen mit Breiten-Begrenzung (`_centered_text(..., max_w)`), Kapelle/Zitadelle im gemalten Layout auf x 0.33/0.67 auseinandergerueckt, `HUD_TOP` 150->250 (Garnison-Button ragte in die Kopfzeile). NEU `buildings_plain` in city_layout.json: Fraktionen OHNE gemalten Hintergrund verteilen dieselben 9 Plots ueber y 0.14-0.86 (`_active_layout()` waehlt anhand `_has_painted_bg()`), dazu ein Platzhalter-Verlauf statt Volltonflaeche - **kein Asset**, wird von gemalten bg.png ersetzt. Kampf: Kopfzeile 330->125 px, Log unter das Gitter (3 statt 5 Zeilen), Gitterflaeche 1485 statt 1357 px, Terrain-Boden je `terrain_id` (TERRAIN_GROUND) mit Schachbrett-Nuance + Verlauf statt Schwarz, Beschriftung auf cell*0.52 UNTER das Token (lag vorher auf dem Sprite). **Test-Falle:** das Kampf-Log ist als Test-Quelle unbrauchbar (3 Zeilen, Zug-Kette laeuft synchron weiter) - dafuer gibt es `_skips_status`/`_skips_moral` als Zaehler; Einzelwert-Marker reichen nicht, weil die naechste Aktion sie ueberschreibt. |
| Kampf-Effekte (It. 17) | FERTIG. Neu `core/BattleVfx.gd` (preload-Alias `Vfx`, weil `Fx` schon StatusFx ist): reine DATEN-Schicht, Effekte sind Dictionaries in einer Array-Queue, `advance()` laesst die Zeit laufen. Arten: Ausfallschritt, Projektil (Parabel), Einschlag (Ring + Splitter), Schadenszahl, Zerfall, Shake, Heilung, Wort-Einblendung, Mauerbruch, Gleiten. **Zwei Trichter statt zwanzig Aufrufstellen:** `_apply_dmg` erzeugt Treffer+Zahl+Zerfall (dort laufen Nahkampf, Konter, Schuss, Todeswolke und Pfeilturm ALLE durch), `_melee_exchange` den Ausfallschritt. Staffelung ueber `cfg["delay"]` (t startet negativ, `Vfx.pending()` = noch nicht zeichnen) - sonst blitzt der Treffer, waehrend der Pfeil fliegt; `Vfx.time_left_of(q, MOVE)` schiebt den Nahkampf hinter einen laufenden Anmarsch. Einschlag-Geometrie (`impact_radius`/`impact_spoke`) steht IM MODUL, weil `tools/preview_battle_fx.gd` dieselben Werte zeichnet. 10. Suite `tools/test_battle_vfx.gd`. |
| Stadt komplett (It. 18) | FERTIG. Der Nutzer hat Screenshots vom Geraet geschickt: auf dem Kaserne-Platz stand ein violetter Iso-Quader. Ursache war `_draw_plot` -> `_draw_iso_block` als Fallback fuer ein GEBAUTES Gebaeude ohne Sprite; **28 von 36 Sprites fehlten** (Waldvolk/Totenreich/Orks komplett, Menschen die Zitadelle). Jetzt zwei Generatoren: `tools/gen_city_bg.py` (4 Hintergruende + 4 bg_walled-Varianten mit Mauerring; ersetzt das gemalte Canva-PNG der Menschen) und `tools/gen_city_buildings.py` (36 Gebaeude + 9 Baustellen aus einer Teile-Bibliothek: Iso-Koerper, 5 Dachformen, Zierteile, 9 Rezepte, 4 Paletten). **Bild-Grenzen-Pruefung** `check_bounds()` im Generator - die Zitadelle war zuerst oben abgeschnitten und im Sprite-Blatt fiel es kaum auf. Fallback-Quader bleibt als Notausgang, aber entsaettigt. |
| Weltkarte lesbar (It. 19) | FERTIG. Drei Befunde aus den Geraete-Screenshots. (1) Je Gelaendeart lag EINE Kachel - `grass.svg` hatte seine Bluete auf Pixel (52,20), also stand auf jeder Wiese dieselbe Bluete an derselben Stelle: Tapetenmuster. Jetzt `tools/gen_world_tiles.py` mit SECHS Varianten je Gelaendeart, Auswahl deterministisch aus Feldkoordinate + Seed (`_tile_variant`). (2) Gelaendearten stiessen kerzengerade aneinander - jetzt weiche Uebergangs-Fransen (`fringe_<seite>.svg`, weiss, wird mit der Nachbarfarbe moduliert; vier Dateien decken alle Kombinationen). (3) Unerforscht war Volltonschwarz mit Gitterlinien - jetzt gewolkte Nebelkacheln. Dazu die HUD-Zeile aufgebrochen: statt "T4 W1 M1 J1 L2 0/10 G872 H15 E5 K3 1 Sk / 2 Zo ... XP140" in EINEM Label jetzt zwei gruppierte Zeilen mit `GameCalendar.calendar_long()`; die Armee ist raus (steht im Helden-Panel). **Falle:** der erste `_tile_variant`-Hash koppelte die Paritaet an x - waagerechte Nachbarn bekamen NIE dieselbe Variante (0 % statt 1/6), ein verstecktes Schachbrett. Zwei Shift-Multiply-Runden loesen das; der Test prueft jetzt BEIDE Schranken, eine Obergrenze allein haette den Fehler durchgelassen. |
| 28 Kreaturen (It. 20) | FERTIG. Der Kontaktbogen in echter Kampfgroesse (86 px) zeigte: `gen_unit_sprites.py` baute alle 28 Token aus FUENF Rollen-Koerpern, also teilten sich sieben Stufen je Fraktion fuenf Formen - Skelett, Zombie, Wicht und Vampir waren derselbe Klumpen, Greif und Pegasus dieselbe Fluegelform. Generator komplett neu: **eine Rezeptzeile je Einheit** (Silhouette, Kopf, Waffe, optional Fluegel) aus einer Teile-Bibliothek, wie bei den Gebaeuden. 12 Silhouetten-Klassen (humanoid/squat/brute/robed/skeletal/spectre/quadruped/mounted/bird/dragon/tree), 20 Koepfe, 18 Waffen, 4 Fluegelarten. ViewBox 64 -> 128 (Godot rastert in ViewBox-Groesse, aus 64 auf 86 px wurde alles weich), KONTUR auf jeder Silhouette (ohne sie verschwamm die Figur mit der dunklen Token-Scheibe), Kopf heller als der Rumpf. **Zwei Selbstpruefungen brechen den Lauf ab:** Bildgrenzen und Rezept-Eindeutigkeit (kein Paar Silhouette/Kopf/Waffe zweimal). |
| Schlachtfeld-Kulisse (It. 21) | FERTIG - damit ist das Grafik-Programm durch. Vorher: Volltonfarbe je Gelaende mit Schachbrett-Nuance, Hindernisse im Code als Rauten/Ovale/Punktwolken, und ueber/unter dem Gitter zusammen rund 40 % leere Flaeche (das Gitter ist breitenbegrenzt bei 10 Spalten, die Flaeche auf dem Handy viel hoeher als breit). Neu `tools/gen_battle_art.py`: 6 Gelaende x 4 Boden-Kacheln, je eine **Kulisse** (Ferne oberhalb des Gitters: Baumsaum, Bergkette, Wasserband, Felsnadeln, Sumpf) und ein **Vordergrund** (gefuelltes Band unterhalb), plus 6 Hindernis-Sprites inkl. gerissener Mauer bei hp<=1. Boden-Variante aus `_ground_variant` (gleicher gemischter Hash wie die Weltkarte). Fehlt eine Datei, greift ueberall der alte Weg. **Falle:** das Zeichnen darf `_rng` NICHT anfassen - das wuerde die Kampfwuerfel verschieben; deshalb `_art_seed` als eigene Kopie. |
| M5 Karten-Objekte (It. 24) | FERTIG. Vorher gab es drei Objekt-Arten (Mine, Truhe, Haufen) - alles Ressourcen. Neu sieben Bonus-Arten, unbewacht: vier **Stat-Schreine** (Soeldnerlager/Wehrturm/Sternwarte/Garten -> je +1 Angriff/Verteidigung/Zauberkraft/Wissen, EINMALIG), **Brunnen** (Mana auf Maximum, 1x/Tag), **Lehrmeister** (+120 XP einmalig, kann eine Stufe ausloesen), **Windmuehle** (Zufalls-Ressource, 1x/Woche, deterministisch aus Seed+Feld+Woche). Sie fuettern genau die Werte, die M7/M8 eingefuehrt haben. Zustand steckt im Objekt-Dictionary (`used`, `used_turn`, `used_week`) und wird ohne Migration mitgespeichert. Verbrauchte Objekte bleiben sichtbar, aber entsaettigt. `_place_objects` laeuft jetzt ueber eine **Plan-Liste** statt Index-Arithmetik - die alte Form (`if idx >= MINE_COUNT + TREASURE_COUNT`) trug sieben zusaetzliche Arten nicht. Sprites aus `tools/gen_map_objects.py`; die drei alten SVGs bleiben handgeschrieben, sie sind bei 64 px in Ordnung. 13. Suite `tools/test_map_objects.gd`. |
| M12 Wochenereignisse (It. 25) | FERTIG. Der Kalender zaehlte nur - Tag, Woche, Monat standen in der Kopfzeile, aber keine Einheit hatte eine Wirkung. Neu `core/WeekEvents.gd`: vier Arten, gewichtet (ruhig 8, Einheiten-Woche 6, Ernte 3, Seuche 2). "Woche des X" verdoppelt das Wachstum genau dieser Einheit in ALLEN Staedten, die Seuche halbiert alles (nie unter 1), die Ernte zahlt einmalig 250 Gold je eigener Stadt. Faktoren als BRUCH (Zaehler/Nenner), weil die Pool-Rechnung ueber Bresenham auf ganzen Zahlen laeuft. Angriffspunkt ist `_pool_cap_for` - EIN Ort, damit Tages-Tick und Catch-up beim Neubau automatisch dasselbe rechnen. **Nichts wird gespeichert:** das Ereignis leitet sich aus Seed und Wochennummer ab; der Test prueft, dass es nach Save/Load identisch ist und NICHT im Save steht. Anzeige in Kopfzeile (nur wenn nicht ruhig), Statuszeile beim Wochenwechsel und im Stadtbildschirm - dort wird rekrutiert. 14. Suite `tools/test_week_events.gd`. |
| M11 Geraeusche (It. 26) | FERTIG. Das Spiel war voellig stumm. 20 WAVs aus `tools/gen_sfx.py` - **selbst synthetisiert**, nicht CC0 geladen: die Scope-Notiz sagte CC0, aber selbst erzeugt ist noch freier (keine Attribution, keine Lizenzdatei, kein Netz; ein frueher Download-Versuch scheiterte an einer toten URL). 22050 Hz mono 16 Bit, 289 KB gesamt. **Hoeren kann ich nichts**, deshalb misst der Generator jede Datei (Dauer, Spitze, RMS, Gleichspannung, Nulldurchgaenge) und bricht ab - das Gegenstueck zum "immer ansehen" bei der Grafik. Godot-Seite: Autoload `Sfx` mit Player-POOL (ein einzelner Player schneidet sich im Kampf selbst ab), Stumm-Knopf in der Kopfzeile. 15. Suite `tools/test_sfx.gd`. |
| M7 Teil 1 Heldenstats + Skills (It. 22) | FERTIG. `data/skills.json` lag seit It. 5 im Repo und wurde von KEINER Zeile Code gelesen; der Held hatte weder Angriff noch Verteidigung, ein Aufstieg gab stumpf +1 Einheit ohne Entscheidung. Neu `core/HeroSkills.gd` (preload, kein class_name): rechnet Skill-Stufen in ZAHLEN um - der Kampf-Screen sieht nie einen Skill, nur Prozentwerte im Kontext. Held bekommt `att`/`def`/`spell_power`/`knowledge` + `skills: {id: stufe}`; **kein SAVE_VERSION-Bump**, reine Feld-Ergaenzung mit toleranten Defaults. Aufstieg: +1 Primaerwert fraktionsgewichtet (eigener RNG aus Seed+Stufe, `_rng` bleibt unberuehrt) plus Wahl aus ZWEI Skills in einem Overlay; mehrere Aufstiege laufen ueber `_skill_queue` und `call_deferred`. Umgesetzt: Fuehrung (Moral), Logistik (Bewegung), Aufklaeren (Sicht), Bogenkampf/Offensive/Ruestungskunde (Schadensprozente), Verwaltung (Tagesgold). **Angebots-Filter `NOT_YET_IMPLEMENTED`**: Weisheit, Mystizismus, Wegfindung, Taktik und Totenerweckung werden NICHT angeboten - ein Skill ohne Wirkung waere ein toter Zug. Ebenso zieht der Primaerwert nur aus Angriff/Verteidigung; Zauberkraft und Wissen wirken erst mit M8. 11. Suite `tools/test_hero_skills.gd`. |
| M8 Teil 1 Zauber (It. 23) | FERTIG. `data/spells.json` (21 Zauber, 5 Schulen) war die zweite ungenutzte Datendatei, und `spell_power`/`knowledge` im Helden waren Felder ohne Wirkung. Neu `core/HeroSpells.gd` (preload, kein class_name): loest die Formeln der JSON ("dmg=15+15*power") in Zahlen auf - der Kampf-Screen fragt nur nach Schaden bzw. Status und parst nie einen Effekt-String. **Mana** = 10 + 10 x Wissen, Regeneration 1/Tag plus Mystizismus, Restmana kommt ueber `mana_left` aus dem Kampf zurueck (EIN Ort im `battle_finished`-Handler, nicht in jedem der fuenf Callbacks). **Zauberbuch** im Kampf: Knopf zwischen Warten und Fliehen, Liste der wirkbaren Zauber, danach Ziel antippen (`_pending_spell` faengt den Tap VOR Angriff und Bewegung ab); ein Zauber pro Runde, Zaubern kostet keinen Zug. Umgesetzt sind 10 von 21: Heilen, Eile, Verlangsamen, Steinhaut, Magischer Pfeil, Feuerblitz, Feuerball (Flaeche wie die Lich-Todeswolke), Schwaeche, Fluch, Blenden. StatusFx bekam vier Zauber-Status und `spd_mod` (Eile/Verlangsamen heben sich auf, Reichweite mindestens 1). Weisheit und Mystizismus sind damit umgesetzt und raus aus `NOT_YET_IMPLEMENTED`; der Primaerwert-Topf umfasst jetzt alle VIER Werte, weil Wissen und Zauberkraft endlich etwas tun. **Vereinfachung, dokumentiert:** es gibt keine Magiergilde, der Held kennt alle umgesetzten Zauber seiner `affinity_schools` bis zur Weisheits-Stufe. Stufe 5 (Implosion, Armageddon) bleibt unerreichbar, weil laut skills.json ein Relikt fehlt. 12. Suite `tools/test_spells.gd`. |
| M8 Teil 2 Zauber (It. 27) | FERTIG. Fuenf weitere Zauber, damit sind **15 von 21** umgesetzt: Segen (immer Hoechstschaden), Schild (-15 % NAHKAMPF-Schaden), Gebet (+2 Angriff/Verteidigung/Geschwindigkeit auf die GANZE eigene Seite, ohne Ziel-Tippen), Konterschlag (+1 Konter pro Runde), Untote erwecken (hebt `count` wieder an, nur auf untote Stacks). StatusFx bekam vier Status; `taken_factor(stack, melee)` unterscheidet jetzt Nahkampf und Fernkampf (der Schild wirkt nur gegen Nahkampf), `damage_bias` verschiebt den Wurf, `extra_retaliations` speist `Abilities.retaliation_allowed(..., extra)`. `CombatMath.heal(stack, hp, allow_revive)` trennt Heilen von Wiederbeleben - Heilen deckelt bei der AKTUELLEN Stackgroesse, nur Wiederbeleben hebt `count`. **Der Segen wuerfelt trotzdem** und ueberschreibt nur das Ergebnis: sonst haetten gesegnete und ungesegnete Kaempfe unterschiedlich lange RNG-Ketten und der Balance-Simulator waere nicht mehr vergleichbar (Gold-Paritaet bleibt 6/6). Der Fluch bleibt bewusst ein Faktor statt "immer Mindestschaden", weil derselbe Status aus der Schwarzritter-Faehigkeit kommt und ein Wechsel Balance-Pass 10 verschoben haette. Offen bleiben 6: `protection_fire` (kein Schadenstyp Feuer), `resurrect`/`implosion`/`armageddon` (Stufe 5, Relikt fehlt), `summon_boat`/`town_gate` (Abenteuer-Zauber, keine Boote). |
| M7 Teil 2 (It. 28) | FERTIG - damit hat JEDER Skill aus skills.json eine Wirkung, `NOT_YET_IMPLEMENTED` ist leer. **Wegfindung:** neu `core/Movement.gd`. Die Kostenzahlen standen DREIMAL im Baum (MapGen.terrain_cost, Pathfinder.compute_costs, Integer-Literale in WorldMapScreen._dijkstra) - jetzt einmal. Dabei fiel auf, dass die Literale in Pathfinder.gd den Sumpf nicht kannten: Sumpffelder galten dort als unpassierbar. **Feinere Einheit:** ein flaches Feld kostet `Movement.UNIT` = 4 Punkte, ein raues 8 - ein Prozent-Abschlag auf einen Aufschlag von 1 waere in ganzen Zahlen entweder nichts oder alles gewesen. Helden-Punkte mitskaliert (BASE_MAX_MP 10 -> 40), Reichweite also unveraendert 10 Felder; **SAVE_VERSION=4** + `_migrate_3_to_4` skaliert `mp`/`max_mp` von Held und KI-Helden (ohne das haette ein alter Spielstand einen Helden mit 7 von 40 Punkten geladen). Kopfzeile zeigt FELDER (`Move.tiles_of`), nicht Punkte. **Taktik:** Aufstellungsphase vor Runde 1 im Kampf-Screen (`_tactics_phase`), Stack antippen -> Zielfeld antippen, erlaubt sind Spalte 1 bis 1+Stufe, "Kampf beginnen" beendet sie; ohne Skill gibt es die Phase gar nicht. **Totenerweckung:** ein Teil der gefallenen Gegner steigt als Skelett in die Heldenarmee - gerechnet ueber die gefallenen TREFFERPUNKTE (`enemy_killed_hp` im Kampf-Ergebnis), nicht ueber Koepfe, sonst brachte ein Feld Goblins mehr als ein Knochendrache (die Notiz in skills.json sagt "Equilibris-Stil"). Angriffspunkt ist der EINE `battle_finished`-Trichter, und zwar NACH `on_result.call` - der Verteidigungskampf setzt `_hero.army` dort komplett neu. 16. Suite `tools/test_movement.gd`, dazu Taktik und Totenerweckung in `test_hero_skills.gd`. |
| Kreaturen in der Oberflaeche (It. 29) | FERTIG. Die 28 Kreatur-Sprites waren an genau EINER Stelle sichtbar (Kampfgitter). Neu `core/UnitArt.gd`: Unit-ID -> SVG plus Cache plus `stat_line()` - der Kampf-Screen delegiert jetzt dorthin, statt seine eigene Verzeichnis-Liste zu halten. **Rekrutier-Panel** zeigt Bild und Kampfwerte (vorher kaufte man eine Einheit, ohne zu sehen, was sie kann), **Garnisons-Panel** Bild je Zeile. **NEU: Heldenblatt** (Knopf "Held" in der Kopfzeile, `_open_hero_panel`): Werte, Skills und die Armee mit Bildern, nach Tier sortiert. Das schliesst eine Luecke, die It. 19 aufgerissen hat - die Kopfzeile gab damals die Armee-Liste ab mit der Begruendung "steht schon im Helden-Panel", und dieses Panel gab es nicht: die eigene Armee war auf der Weltkarte NIRGENDS zu sehen. 17. Suite `tools/test_unit_art.gd` (prueft auch, dass der Knopf in WorldMap.tscn liegt - Code allein reicht nicht). |
| Silhouetten-Reparatur (It. 30) | FERTIG mit Vorbehalt. Der Kontaktbogen fuer It. 29 zeigte bei 96 px auf FLACHEM Grund, was It. 20 falsch abgehakt hatte: rund ein Drittel der Kreaturen war unlesbar. Vierbeiner hatten Vogelkoepfe auf Ellipsen-Rumpfen mit Strichbeinen (Greif = Kavalier), die "Drachen" waren Enten, die Orks rote Klumpen, Wicht/Pegasus/Einhorn formlos. Neu gezeichnet: `animal_leg` (Gelenkknick, Huf/Tatze/Fang statt Rechteck), `_body_path` (Brust tiefer als Kruppe, getrennte Vorderkante -> Bison-Umriss fuer den Behemoth), `_neck` (gefuellt und verjuengt statt Strich konstanter Breite), `sil_mounted` (Reiter sitzt IM Sattel, mit Bein am Rumpf), `sil_bird` (aufrecht mit Schwanzfedern und Standbeinen), `sil_brute` (Schulterhoecker, zwei Arme), `sil_spectre` (tief eingeschnittener Fetzensaum, Klauenarme), alle vier Fluegelarten, und die Tier-Punkte sind kleiner und ohne Kontur (sieben weisse Scheiben mit Rand zogen mehr Blick als die Kreatur). **Der Vorbehalt:** die beiden Drachen sind nach SECHS Anlaeufen "gefluegeltes Wesen", aber nicht zweifelsfrei "Drache" - Ente, dann Huhn, dann diagonaler Streifen, dann Papierfluegel. Was geholfen hat: langer Schweif am Boden, flach liegender Rumpf, Fluegel im PROFIL und nicht groesser als der Rumpf. Auch der Kreuzritter bleibt ein Kasten. |
| **Beurteilungs-Falle (It. 30, teuer):** ein Kontaktbogen AUF DER TOKEN-SCHEIBE beweist nichts ueber die Silhouette. Ring, dunkle Scheibe und Beschriftung haben in It. 20 die halbe Arbeit getan; auf flachem Panel-Grund fiel dieselbe Figur auseinander. Kreaturen ab jetzt immer BEIDES pruefen: 96 px auf flachem Panel-Grund UND 86 px auf der Scheibe. Und `check_unique` im Generator prueft nur, dass kein Paar (Silhouette, Kopf, Waffe) doppelt vorkommt - NICHT, ob das Ergebnis wie das aussieht, was draufsteht. | |
| Drachen (It. 32) | FERTIG. Der offene Punkt aus It. 30. Was endlich funktioniert hat, ist eine andere TECHNIK statt weiterer Formen: `tapered(mittellinie, breiten, ...)` rechnet den Umriss aus einer Mittellinie plus Breitenprofil (Normalen numerisch, links und rechts um die halbe Breite versetzt). Damit gibt es keine Nahtstellen mehr - vier Anlaeufe mit gestapelten Massen (Ellipse+Hals+Schweif) sind genau daran gescheitert und wurden jedes Mal zum Vogel. `spine_spikes` benutzt dieselbe Mittellinie und setzt die Zacken auf den UMRISS (halbe Breite nach aussen), nicht in die Flaeche - vorher lasen sie sich als aufgemalte Pfeilspitzen. Dazu: Drachenfluegel liegen komplett OBERHALB der Rueckenlinie (sonst ist die Zackenkante hinter dem Rumpf und damit unsichtbar), beim Knochendrachen dunkle Membran auf hellem Koerper statt hellgrau auf hellgrau, und der `draconic`-Kopf ist eine keilfoermige Schnauze mit Kieferlinie und zwei nach hinten gelegten Hoernern statt eines weichen Keils, der als Kapuze las. **Verworfen und im Code dokumentiert:** Schulterstuecke am breiten Rumpf - sie standen als freischwebende Platten neben dem Torso und machten den Kreuzritter zum Roboter. Der Kreuzritter bleibt damit ein Kasten; das ist der letzte offene Punkt an den Kreaturen. |
| Stadt-Komposition (It. 33) | FERTIG. In der KOMPONIERTEN Ansicht bei Geraetegroesse (`tools/preview_city_full.gd`) fiel auf, was das Sprite-Blatt nie zeigt: alle neun Bauplaetze lagen im Band y 0.475-0.80, also im oberen Drittel des Hofs - darunter blieb ein Drittel der Mauerflaeche leer, und zwei Paare lagen nur 0.06 auseinander und ueberdeckten sich. Jetzt drei Tiefenreihen ueber y 0.47-0.875 mit unregelmaessigem x und `"s"` je Plot als Groessenfaktor (hinten 0.84-1.05, vorn bis 1.10); die Zitadelle ist der GROESSTE Bau, obwohl sie hinten steht - vorher stand das Spitzengebaeude kleiner da als die Kaserne. **Drei Duplikate zusammengelegt:** `tools/gen_city_bg.py` LIEST jetzt `data/city_layout.json` (vorher eine zweite Kopie der Koordinaten - Wege und Platz waeren nach dem Umbau mitten durch die Gebaeude gelaufen), die Wege-Luecken werden aus den Reihen GERECHNET statt als feste Liste gepflegt, und der Platz steht als `"plaza"` im Layout, aus dem ihn sowohl der Generator zeichnet als auch CityScreen antippbar macht (vorher vier Konstanten hier, Koordinaten dort). **Neuer Pruefer `check_layout()` im Generator** meldet Ueberdeckungen, Plaetze ausserhalb des Mauerrings und einen Platz unter einem Gebaeude - er hat meine handgesetzten Werte dreimal widerlegt, bevor das Layout stand. Dazu Ork-Hof um 15 % abgedunkelt: mittelbraune Haeuser auf mittelbraunem Boden waren im Sprite-Blatt unsichtbar als Problem, in der Szene der auffaelligste Mangel. `test_city_screen` prueft zusaetzlich, dass der Platz unter keinem Bauplatz liegt. |
| Weltkarte komponiert (It. 34) | FERTIG. Neu `tools/preview_world_full.gd`: komponiert Gelaende, Fransen, Nebel, Objekte, Staedte, Monster und Helden aus einem ECHTEN WorldMapScreen (`_start()` laeuft headless; Positionen und `_tile_variant`/`_fog_get` kommen aus dem Screen selbst, nicht aus einer Nachbildung) und speichert die ganze Karte plus den Ausschnitt, den das Handy zeigt. Drei Befunde, alle nur in dieser Ansicht sichtbar: **(1)** Staedte durften am Kartenrand liegen - und eine Stadt IST der Startpunkt des Helden. In 3 von 6 Seeds begann das Spiel in der Kartenecke, der erste Bildschirm war zu ~85 % Nebel und die halbe Sichtweite lag ausserhalb der Karte. Jetzt `CITY_BORDER_MARGIN = 2`, getestet ueber 6 Seeds (die Gegenprobe mit ausgebautem Rand-Abstand meldet 25 Randstaedte). **(2)** Die Wiesen-Deko war zu fein und zu bunt: vier reine Gelbpunkte je Kachel lasen sich als orange UI-Funken, drei gespreizte 1.3-px-Halme als Schriftzeichen ("w"). Jetzt zwei duenne blasse Halme, gedeckte Blumen, und Blumen nur auf 2 von 6 Varianten (Deko-Anzahl darf jetzt eine LISTE je Variante sein). **(3)** `FRINGE_ALPHA` 0.40 x 0.30/0.52 in der Datei = effektiv 0.12/0.21: die Uebergangs-Fransen aus It. 19 waren praktisch unsichtbar, Gelaendegrenzen blieben Treppen. Jetzt 0.62. Dazu Wald deutlich abgedunkelt (#2c5220 statt #3d6b2c) mit dichterem Kronendach - sein Grundton lag vorher auf dem dunklen Ende der Wiese, und Wald kostet doppelte Bewegung, den MUSS man erkennen. |
| Monster und Wachen (It. 35) | FERTIG. Ein wanderndes Monster war "Staerke 1-3" und im Kampf 1-3 MENSCHLICHE Speertraeger - auf der Karte ein grauer Kreis mit Zahl. Dasselbe galt fuer jede Objekt-Wache: eine Truhe im Orkgebiet wurde von drei Menschen gehuetet. Jetzt hat jedes Monster und jede Wache eine echte Kreatur aus `MONSTER_POOL`, deren Sprite auf der Karte steht und die im Kampf antritt (Weg dafuer gab es schon: `enemy_army` im Battle-Kontext, aus M9). **Kraft-Neutralitaet ist die tragende Regel:** die Staerke wird als TREFFERPUNKT-Budget gelesen (`Staerke x MONSTER_HP_PER_STRENGTH`, 10 = HP eines Speertraegers), die Stackgroesse folgt aus den HP der Kreatur, und nur Kreaturen, die einzeln ins Budget passen (`MONSTER_HP_TOLERANCE` 1.45), kommen in Frage - ein Oger kann deshalb nie ein Staerke-1-Monster sein. Der Test prueft genau diese Schranke, sonst waere aus der Kosmetik still eine Schwierigkeits-Aenderung geworden. **Kein SAVE_VERSION-Bump:** fehlt `unit` bzw. `guard_unit` (alter Spielstand), wird die Kreatur deterministisch aus Position und Staerke abgeleitet und bleibt ueber Aufrufe stabil - ein wechselndes Monsterbild bei jedem Neuzeichnen waere der offensichtliche Fehler dabei. Die Bit-Mischung aus `_tile_variant` ist dafuer als `_mix_hash()` herausgezogen (zweiter Nutzer). |
| Kampfschirm komponiert (It. 36) | FERTIG. Neu `tools/preview_battle_full.gd`, und `preview_battle.gd` ist DAFUER GELOESCHT: das alte Werkzeug war ein Nachbau mit eigenen Kopien von CELL, PAD_TOP, PAD_BOTTOM, TERRAIN_GROUND und GROUND_VARIANTS - genau die Sorte Kopie, die in It. 33/34 auseinandergelaufen ist. Das neue holt alles aus einem echten Screen: Bildschirmgroesse aus den Projekt-Einstellungen, Lage des Gitterfeldes aus den Offsets des `_grid_area`-Knotens, Zellgroesse aus `bs._geom()`, Stacks und Hindernisse aus `set_battle()`. **Die harte Zahl:** Zelle 104 px, Gitter 1040x832, Kulissen-Baender 653 px = 44 % der Gitterflaeche. Befunde: **(1)** Die Kreaturen waren verloren - Scheibe 0.40 der Zelle, Sprite 0.92, und weil die Figur im SVG nur 85 % der Bildhoehe fuellt, kam eine 45-px-Figur auf einer 104-px-Zelle heraus. Jetzt `TOKEN_DISC_FRAC` 0.44 / `TOKEN_SPRITE_FRAC` 1.14 / `TOKEN_SPRITE_LIFT` 0.10 (als Konstanten, weil die Vorschau sie AUSLIEST). **(2)** Der Kulissen-Inhalt lag komplett in den unteren 80 von 200 Einheiten des Bandes - oben blieben auf dem Geraet rund 200 px leer. Jetzt Himmelsbaender plus zwei ferne Kammlinien (`_far_horizon`) und ein hoeher angesetzter, tieferer Baumsaum. **(3)** Das Sumpf-Hindernis hatte ein Vollflaechen-Rechteck als Untergrund und stand als hartes 104-px-Quadrat im Feld - das einzige rechtwinklige Element im Bild. **(4)** Boden-Varianten 4 -> 6 und Bueschel nur in zwei davon: bei 80 Zellen kam jede Variante 20 Mal vor, die Deko las sich als Raster. **Das Werkzeug hat zuerst SICH SELBST widerlegt:** es zeichnete die Beschriftung mit `cell*0.52` als Schriftgroesse - das ist im Screen der ABSTAND, die Groesse ist `cell*0.30`. Ich hielt die Beschriftung fuer zu gross, bis ich im Screen nachgelesen habe. |
| Effekt-Vorschau und Pfeil (It. 37) | FERTIG. Letztes Vorschau-Werkzeug mit eigenen Zahlen: `preview_battle_fx.gd` rechnete mit `CELL = 64`, auf dem Geraet sind es 104 - und ALLE Effektradien sind relativ zur Zelle. Jetzt kommen Gitter und Token-Faktoren aus `TacticalBattleScreen` (`GRID_COLS`, `TOKEN_DISC_FRAC`, `TOKEN_SPRITE_FRAC`, `TOKEN_SPRITE_LIFT`) und der Sprite-Pfad aus `UnitArt` - die dritte `FACTION_DIRS`-Kopie im Baum ist weg. In echter Groesse zeigte sich: das Geschoss war ein PUNKT, also flog bei 104 px eine Murmel durchs Bild, deren Richtung man nur am Schweif erraten konnte. Jetzt ein ausgerichteter Pfeil (Schaft, Dreiecksspitze, Federn), Richtung aus der BAHN und nicht aus der Luftlinie - auf einer Parabel zeigt die Luftlinie in die falsche Richtung. **Zwei Selbstwiderlegungen des Werkzeugs in einer Iteration:** es zeichnete die Spitze als Kugel (`_dot`), waehrend der Screen ein Dreieck zeichnet - also brauchte die Vorschau ein gefuelltes Dreieck (`_tri`, baryzentrisch, weil Image kein `draw_colored_polygon` kennt), sonst haette ich einen Pfeil beurteilt, den es im Spiel nicht gibt. |
| Durchspiel-Test (It. 38) | FERTIG - und die ergiebigste Iteration seit dem Grafik-Programm. Es gab 17 Suiten und KEINE hat das Spiel gespielt: `test_ai_smoke` druckt 30 Mal "Tag beenden", der Spieler tut dabei nichts. Jeder Teil war einzeln geprueft, die KETTE Weltkarte -> Kampf-Overlay -> Callback -> Weltkarte nie. Neu `tools/test_playthrough.gd` (18. Suite): baut, rekrutiert, laeuft zum naechsten Ziel, spielt Kaempfe im Overlay aus, beendet den Tag - zwei Seeds, je bis 40 Zuege, rund 5 Sekunden. **Drei echte Fehler in einem Lauf:** (1) **Das Spiel konnte einfrieren.** `_open_battle` verband `battle_finished` NACH `set_battle` - ein Kampf, der schon in `set_battle` entschieden wird (die schnellere Gegnerseite zieht in `_step()` und faellt dabei der einzige Verteidiger, feuert das Signal sofort), verlor sein Signal ins Leere: das Overlay blieb fuer immer im Baum und der Callback lief nie. Bei einem Verteidigungskampf setzt genau dieser Callback die KI-Phase fort, die KI war also ab da eingefroren - ohne Absturz, ohne Meldung. Der Test fand ab Zug 3 vierzehn Mal dasselbe tote Overlay. Fix: erst verbinden, dann `set_battle`. (2) **Die Kampf-Prognose log.** Sie verglich die ANZAHL eigener Einheiten mit der Monster-Staerke; seit It. 35 entspricht eine Staerke aber keiner vergleichbaren Einheit mehr. Der Test-Spieler verlor in Zug 1 seine ganze Armee an einen Kampf, den die Karte gelb (= Sieg mit Verlusten) anzeigte. Jetzt EIN `_threat_color(own_gold, threat_gold)` fuer Monster, Objekt-Wachen UND Garnisonen - vorher stand die Dreifach-Abfrage dreimal im Zeichencode. (3) **Das HP-Budget aus It. 35 war das falsche Mass.** 30 HP als ein Greif (Tier 3, Angriff 8, fliegend) schlagen 30 HP als drei Speertraeger muehelos - HP sind ueber Tiers hinweg nicht vergleichbar, GOLD ist es (darauf ist Balance-Pass 10 getunt). Jetzt `MONSTER_GOLD_PER_STRENGTH` = 60, Toleranz 1.0 (die Kreatur muss EINZELN ins Budget passen) und ABRUNDEN statt runden - mit `round()` ergaben 60 Gold Budget zwei 40-Gold-Goblins. **Dazu die fehlende HoMM3-Regel:** der Verlust der letzten Stadt war sofortiges Spielende, auch mit lebendem Helden und voller Armee. Jetzt `LOSS_GRACE_DAYS` = 7 mit Anzeige in der Kopfzeile ("OHNE STADT: 5 Tage") und `_no_city_since` im Save (tolerantes Feld, kein Versions-Bump). |
| Zugkette auf EINE Uhr (It. 39) | FERTIG. Der breite Durchspiel-Lauf (6 Seeds x 60 Zuege statt 2 x 40) meldete acht Mal "Kampf nach 400 Schritten offen". Diagnose: Runde 10, Gegner am Zug, kein laufender Effekt, kein toter Eintrag in der Reihenfolge - die Kette stand einfach. Ursache: `_wait_for_fx` haengte an `get_tree().create_timer()`, einer ZWEITEN Uhr neben der Effekt-Queue. Zwei Folgen: (a) headless laeuft keine Echtzeit, der Timer feuerte nie und der Kampf stand fuer immer; (b) die KI-Pause haette bei einem "schnellen Kampf" (fx_speed > 1) nicht mitskaliert. Jetzt gibt es die Effekt-Art `Vfx.PAUSE` (unsichtbar, blockierend) und ein `_pending_fn`, das `_process` aufruft, sobald die Queue frei ist - eine Uhr fuer alles. Bei `fx_speed <= 0` laeuft die Kette wirklich synchron durch, wie der Kommentar es seit It. 17 versprach (fuer `extra` lag dort trotzdem ein 0.3-s-Timer). **Folgefehler im Test, aufschlussreich:** `test_battle` prueft den Lebensentzug des Vampirs nach `_try_attack_enemy` - und weil die Kette jetzt wirklich durchlaeuft, schlaegt die Gegenseite sofort zurueck, bevor der Test die HP liest (130 -> 71 statt Heilung). Der Test hatte sich darauf verlassen, dass der Timer headless NIE feuert. Jetzt prueft er die Mechanik direkt ueber `_melee_exchange`. Dazu im Durchspiel-Test: der Test-Spieler weicht ueberlegenen KI-Helden aus (vorher lief er mit drei Einheiten zur Gegnerstadt und wurde unterwegs gestellt), `_deadlocks` wird pro Seed geleert, und "es wurde gekaempft" steht in den Summen statt pro Seed - sonst haengt die Pruefung an der Kartenverteilung. |
| M13a Helden-Struktur (It. 40) | FERTIG - Struktur ohne neues Gameplay, vom Nutzer freigegebener Plan. Vorher war `_hero` ein Einzelobjekt und der Geldbeutel hing am Helden (`_hero.wallet`); mit zwei Helden waere "welcher Held haelt das Gold" sofort ein Fehler. Jetzt `_heroes: Array` + `_active_hero`, und **`_hero` ist ein GETTER** auf den aktiven Helden. Das war der Befund, der den Umbau tragbar machte: `_hero` kommt 160 Mal in der Datei vor, aber es gab nur ZWEI Schreibzugriffe auf die Variable selbst - alle rund 90 Lesestellen (position, mp, army, xp, skills, mana) blieben unveraendert. Der Beutel liegt als `_purse: Wallet` im Screen (27 Stellen umgestellt); `Hero.wallet` bleibt fuer die KI, die je genau einen Helden hat. `CityScreen` bekommt `"wallet"` im Kontext und liest ihn ueber `_wallet()` mit Rueckfall auf `hero.wallet`. **SAVE_VERSION=5** + `_migrate_4_to_5` (`hero` -> `heroes[0]`, `hero.wallet` -> `purse`, `active_hero`). Tageswechsel, Mana-Regeneration und `_recalc_max_mp` laufen ueber ALLE Helden; die Karte zeichnet alle eigenen Helden, der aktive mit gelbem Ring; ein Tap auf einen anderen eigenen Helden wechselt ihn (`_switch_hero`, rechnet die Reichweite neu). 19. Suite `tools/test_multi_hero.gd`. **Zwei Befunde beim Umbau:** (1) `_recompute_fog_player` deckte nur um EINEN Helden auf - gefunden hat es der Save-Roundtrip im neuen Test (capture -> restore -> capture war nicht identisch, weil der Nebel je nach aktivem Helden anders aussah). Jetzt deckt jeder Held mit seiner eigenen Sichtweite auf (`_hero_sight_of`). (2) SECHS bestehende Suiten mussten angepasst werden, alle aus demselben Grund: sie lasen Gold und Ressourcen aus `hero.wallet`. Das ist die gewollte Folge des Umbaus, keine Regression - der Rest lief unveraendert durch, und der breite Durchspiel-Lauf (6 Seeds x 60 Zuege) liefert Zahl fuer Zahl dasselbe Ergebnis wie davor. |
| M13b Mehrere Helden, Gameplay (It. 41) | FERTIG. Drei Regeln sind neu. **(1) Anwerben:** Knopf im Stadtschirm (`hire_hero_requested` -> `_on_hire_hero`), `MAX_HEROES` = 3, `HERO_HIRE_COST` = 2500 Gold, `HERO_HIRE_UNITS` = 2 Einheiten in der Fraktion DER STADT - nicht in der des Spielers, damit eine erobere Ork-Stadt Orks anwirbt und die Moral-Regel aus M6 eine echte Entscheidung bleibt. **Dokumentierte Vereinfachung: keine Taverne als GEBAEUDE.** Ein zehnter Bauplatz passt nur mit Verrenkungen in den Mauerring (`check_layout()` in gen_city_bg.py meldet die Schmiede als zu nah), und 4 Fraktions-Sprites + Baustelle + Layout-Slot waeren eine Art-Iteration ohne Gameplay-Gewinn - wie "keine Magiergilde" in M8. **(2) Niederlage erst wenn alle gefallen sind:** `_on_battle_defeat(fallen_idx := -1)` entfernt GENAU den gefallenen Helden. **Die Invariante, die dabei stehenbleiben MUSS: `_hero` ist niemals null.** Der letzte Held bleibt als Objekt in `_heroes` stehen und es wird nur `_game_lost` gesetzt - ein Weltzustand ohne Helden hat vor M13b nie existiert, und `test_playthrough`/`test_garrison` haben sofort drei Nil-Zugriffe gemeldet (`_hero.level`, `_hero.skills`, Zuweisung auf `army`), als ich die Liste wirklich leer laufen liess. `_check_defeat` prueft `_heroes.is_empty()`. **(3) Jeder Held in der Stadt verteidigt sie:** der Verteidigungskampf nimmt `_hero_index_at(target_pos)` statt nur den AKTIVEN zu pruefen - vorher haette ein zweiter Held in derselben Stadt tatenlos zugesehen und waere beim Verlust der Stadt trotzdem verschont geblieben. Der Index wandert durch `_on_city_defense_result(..., def_hero_idx)`. **Falle, die dabei zugeschlagen hat:** das letzte Argument war vorher ein `bool hero_joined`, und `test_garrison` gab weiter `false` mit - in GDScript wird das zu `0`, und 0 ist ein GUELTIGER Held-Index. Der Test war rot mit "Held war nicht beteiligt"; die Lehre steht als Kommentar an beiden Aufrufstellen. |
| Durchspiel-Test spielt mit drei Helden (It. 41) | FERTIG, und wieder der ergiebigste Teil. `test_playthrough` hatte immer nur EINEN Helden - der ganze M13b-Code lief damit nie durch die echte Zugkette. Jetzt wirbt der Test-Spieler an, wenn Gold und Platz da sind, rotiert pro Zug ueber ALLE Helden (`_switch_hero`), und die eigene Stadt wird zum Bewegungsziel, sobald ein Held bezahlbar ist ("Heimweg") - ohne diese Regel lief er nie wieder nach Hause und der Anwerbe-Pfad kam nicht vor. Der Unterschied ist gross: Seed 90210 spielte vorher 10 Zuege bis zur Niederlage, jetzt alle 60 mit 3 Helden, 4 Staedten und 16 gewonnenen Kaempfen. **Drei Anpassungen, die der Umbau erzwungen hat:** (a) XP und Armee werden ueber alle Helden SUMMIERT und jedes Mal frisch aus `wm` gelesen - ein am Anfang gemerktes Hero-Objekt waere nach dessen Tod eine Leiche, deren Zahlen der Test vergleicht; (b) die Helden-Schleife prueft die Listengroesse in JEDEM Durchlauf neu, weil ein Held mitten in der Runde fallen kann; (c) Zielfelder mit einem anderen eigenen Helden werden ausgelassen - dort wechselt ein Tap den Helden statt zu laufen, der Zug waere verpufft. **Befund, der offen bleibt (naechste Iteration):** in 3 von 6 Seeds ist das Spiel in Woche 1-2 vorbei, immer im gleichen Muster - ein KI-Held stellt den Startheld mit drei Einheiten, der Pflichtkampf ist nicht ausschlagbar, und weil noch kein zweiter Held angeworben war, hilft die neue Regel nicht. HoMM3 hat dafuer Flucht und Kapitulation, wir nicht. |
| HUD-Geometrie gemessen (It. 41) | FERTIG. Der Anwerbe-Knopf ist der vierte Eintrag in der rechten Knopfspalte des Stadtschirms, alle mit festen Offsets - also gemessen statt geschaut: `_test_hud_geometry` in `test_city_screen.gd` prueft, dass sich keine zwei Knoepfe ueberdecken, keiner auf einem Bauplatz liegt (er wuerde den Tap fressen) und jeder ganz auf dem Schirm liegt. **Dabei kamen zwei Fallen heraus, die die Suite seit It. 18 stumm gemacht haben** - siehe unten bei den Fallen. |
| Flucht und Kapitulation (It. 42) | FERTIG - die HoMM3-Tuer aus einem Kampf, den man nicht gewinnen kann. Vorher war der Kampf gegen einen Gegner-Helden PFLICHT (`allow_flee=false` an beiden Aufrufstellen), und "Fliehen" bei Monstern war ein KOSTENLOSER Abbruch - also gleichzeitig zu hart und zu weich. Jetzt: **Flucht** kostet die GANZE Armee, der Held taucht in der naechsten eigenen Stadt auf, `mp = 0`. **Kapitulation** kostet Gold in Hoehe des Armeewerts (`SURRENDER_COST_FACTOR` 1.0, Mindestpreis 250), dafuer behaelt der Held seine UEBERLEBENDEN Truppen. Beides braucht eine eigene Stadt als Ziel - ohne die ist es die letzte Schlacht, und die Knoepfe sind unsichtbar. Aus der eigenen Mauer flieht man nicht (HoMM3-Regel): der Verteidigungskampf laesst `allow_flee=false`, und `_on_city_defense_result` hat zusaetzlich einen Riegel, weil ein durchgereichtes "flee" sonst in den else-Zweig gelaufen waere und die Stadt gekostet haette. Ausgefuehrt wird der Rueckzug an EINEM Ort (`_apply_retreat` im `battle_finished`-Trichter), der Callback laeuft danach TROTZDEM - er muss die KI-Phase fortsetzen (die Falle aus It. 38). **Wirkung, gemessen am breiten Durchspiel-Lauf:** vorher liefen 3 von 6 Seeds die vollen 60 Zuege, jetzt 5 von 6. |
| Knopfreihe im Kampf, gemessen (It. 42) | FERTIG. Der vierte Knopf brauchte Platz - und beim Messen kam heraus, dass die Reihe schon vorher kaputt war: "Zauber" lag bei x 500-624, "Fliehen" bei 600-1030, also **24 Pixel Ueberdeckung**, in der der spaeter eingehaengte Fliehen-Knopf den Tap gefressen hat. Jeder der vier Knoepfe hatte eigene Pixel-Offsets. Jetzt vier gleiche Plaetze ueber `_place_btn(btn, slot)` mit BRUCH-Ankern (`anchor_left = slot / BTN_SLOTS`) - die Reihe haengt damit an keiner Bildschirmzahl und teilt sich auf jedem Geraet gleich auf. `_test_button_row` in test_battle.gd prueft: keine Ueberdeckung, alles auf dem Schirm, kein Knopf auf dem Gitter (er wuerde den Tap auf ein Feld fressen), jede Beschriftung passt in ihren Knopf. |
| Ein unbesiegbarer Einzelgaenger (It. 42) | FERTIG, und der lehrreichste Befund der Iteration. Der Durchspiel-Test verlor in Seed 4711 die ganze Armee an einen Kampf, den die Karte GRUEN gefaerbt hatte: **3 Speertraeger + Goblin + Wolfreiter (320 Gold) gegen EIN Gespenst (170 Gold)**. Nachgemessen mit einem Wegwerf-Werkzeug: 0 von 4 Siegen gegen 320 Gold, 4 von 4 gegen 480 Gold - der Umschlagpunkt liegt bei etwa 2,4. Ursache: `Abilities.regen_hp` heilt einen Anteil der max-HP der OBERSTEN EINHEIT. Ein einzelnes Gespenst holt 7 von 25 HP pro Runde zurueck (28 %), und wer weniger Schaden pro Runde macht als das, kann es GAR NICHT toeten - der Kampf ist nicht schwer, er ist unmoeglich. Zwei Aenderungen: **(1)** `MONSTER_MIN_COUNT` = 3 fuer REGENERIERER (nicht fuer alle - der erste Anlauf legte die Untergrenze auf jede Kreatur, und prompt kostete das schwaechste Monster drei Goblins bei 60 Gold Budget, doppeltes Budget, test_new_game zu Recht rot). **(2)** Neu `_threat_gold(army)` als EIN Trichter fuer alle drei Bedrohungsanzeigen (Monster, Objektwache, Garnison) mit einem Zuschlag `1 + THREAT_REGEN_BONUS / count` - bei Stackgroesse 1 also 2,5, bei 10 nur 1,15. **Der Zuschlag MUSS mit der Stackgroesse fallen**, weil dieselbe Heilung sich auf mehr HP verteilt. Beide Zahlen haelt test_new_game fest, inklusive des konkreten Kampfes: 320 Gold gegen ein Gespenst darf nicht gruen sein. |
| Der Durchspiel-Test hatte eine eigene Kopie der Nachbarschaft (It. 42) | FERTIG. Der breite Lauf meldete zwei Mal "Kampf nach 400 Schritten offen" - Diagnose erst moeglich, nachdem die Meldung RUNDE und ARMEEN mitgab: Runde 1, beide Armeen vollzaehlig. Ursache: `_player_acts` pruefte Nachbarschaft als `abs(dx) <= 1 and abs(dy) <= 1` (mit Diagonalen), `_adj` im Kampf-Screen rechnet aber orthogonal (`|dx| + |dy| == 1`). Bei einem diagonal stehenden Gegner sagte der Test "angreifen", der Screen "Ausser Reichweite" - **und verbrauchte den Zug nicht** (fuer einen Menschen richtig, fuer eine Schleife toedlich). Jetzt fragt der Test `bs._adj` selbst, und die Schleife hat einen Fortschritts-Riegel: aendern sich Slot, Runde und Position nicht, wird gewartet. Dritte Fehlerart dieser Sorte nach den Vorschau-Werkzeugen (It. 36/37) - **eine Regel, die im Test nachgebaut wird, laeuft irgendwann auseinander.** |
| M14 MP | offen. Armee-Tausch wenn zwei eigene Helden sich treffen (heute ist die Stadt-Garnison die Umschlagstelle), Wechsel-Knopf in der Kopfzeile als Alternative zum Tap. **Jeder "Held dazu"-Pfad MUSS `_recompute_fog_player` und `_recompute_costs` rufen** - siehe `_add_hero` in test_multi_hero.gd und `_on_hire_hero`. |

**Falle: `--quit` findet Parse-Fehler in WorldMapScreen.gd NICHT.** Der
Parse-Check laedt nur die Hauptszene; `scenes/WorldMap.tscn` haengt nicht
daran. In It. 40 ist so ein echter Fehler durchgerutscht (eine Variable war
durch einen neuen Schleifenkopf lokal geworden, ein spaeterer Block las sie
weiter) - `--quit` meldete nichts, die Suiten fielen sofort um. Nach jeder
Aenderung an einem UI-Skript deshalb mindestens EINE Suite laufen lassen,
die die Szene instanziiert (`test_new_game` ist die schnellste).

**Falle: `_ready` laeuft in einem headless `--script`-Werkzeug NICHT
synchron beim `add_child`, sondern erst im naechsten Frame.** Gefunden in
It. 41: `test_city_screen` hat den Stadtschirm seit It. 18 OHNE HUD
geprueft - `_build_hud` war nie gelaufen, und die Suite war gruen, weil
`open()` das Layout selbst nachlaedt und `_update_hud` jedes Feld mit
`if _x != null` abschirmt. Wer einen Screen im Werkzeug baut: nach
`root.add_child(...)` ein `await process_frame`.

**Falle: rechts/unten verankerte Knoepfe messen sich headless gegen die
FENSTERgroesse, nicht gegen das Handy.** `_ready` setzt in den Screens
`anchor_right/bottom = 1.0`; der Screen deckt damit das Testfenster, und
ein mit `offset_left = -320` verankerter Knopf landete bei x = 2760 statt
760. Fuer eine Messung in Geraetegroesse erst
`set_anchors_preset(Control.PRESET_TOP_LEFT)`, dann `size` setzen, dann
einen Frame warten (`_test_hud_geometry` in test_city_screen.gd).

**Falle: eine Aktion, die der Kampf-Screen ABLEHNT, verbraucht keinen
Zug.** `_try_attack_enemy` meldet "Ausser Reichweite" und kehrt zurueck,
ohne `_end_player_turn` zu rufen - fuer einen Menschen richtig (er tippt
etwas anderes), fuer jede Schleife eine Endlosschleife. Wer den Kampf
automatisch spielt, braucht einen Fortschritts-Riegel: aendern sich Slot,
Runde und Position nicht, `_on_wait` rufen.

**Falle: keine Regel des Spiels im Test NACHBAUEN.** In It. 42 hatte
`test_playthrough` eine eigene Nachbarschafts-Definition mit Diagonalen,
`_adj` im Kampf rechnet orthogonal - der Test forderte 400 Mal einen
Angriff, den der Screen ablehnte. Dritter Fall dieser Sorte nach den
Vorschau-Werkzeugen (It. 36/37). Immer die Funktion des Spiels aufrufen.

**Falle: `_hero` ist niemals null - auch nicht nach der Niederlage.**
`_on_battle_defeat` laesst den LETZTEN Helden als Objekt in `_heroes`
stehen und setzt nur `_game_lost`. Der ganze Screen verlaesst sich darauf
(It. 41: drei Nil-Zugriffe innerhalb einer Minute, als die Liste wirklich
leer lief). Ein echter helden-loser Zustand waere eine eigene Iteration -
er braucht `_hero == null` als legalen Fall in `_hero_stats_text`,
`_update_labels`, `_recompute_costs` UND im Zeichencode.

**Falle: `bool` als Argument, wo ein INDEX erwartet wird.** GDScript macht
aus `false` eine `0`, und `0` ist ein gueltiger Held-Index. In It. 41 hat
genau das `test_garrison` rot gemacht, nachdem `hero_joined: bool` zu
`def_hero_idx: int` wurde. "Nicht beteiligt" heisst `-1`, nie `false`.

**Falle: `_hero` ist seit It. 40 ein GETTER** auf `_heroes[_active_hero]`.
Zuweisen geht nicht mehr - der Held wird in `_heroes` gesetzt. Und in
Kampf-Callbacks (die Lambdas in `_open_battle`) NICHT `_hero` lesen, sondern
den beim Oeffnen gemerkten Helden: der aktive Held kann zwischen
Kampfbeginn und Callback wechseln.

**Falle: Bewegungspunkte sind seit It. 28 KEINE Felder.** `Movement.UNIT`
(4) Punkte = ein flaches Feld. Wer eine Zahl in Feldern braucht (Anzeige,
Test), nimmt `Move.tiles_of(punkte)`; wer eine Konstante in Punkten
schreibt, denkt an den Faktor 4 (`MP_BONUS_SPAEHER` = 8 sind zwei Felder).
Neue Gelaende-Art? Kosten NUR in `core/Movement.gd` eintragen - MapGen,
Pathfinder und der Weltkarten-Dijkstra lesen alle von dort.

**Falle: AUTOLOADS EXISTIEREN NICHT bei `godot --script tools/x.gd`.**
Weder `SaveManager` noch `Sfx` liegen dort im Baum. Ein direkter Aufruf
(`Sfx.play(...)`) scheitert zur Laufzeit, bricht die Testfunktion ab - und
weil ein Abbruch die Suite nicht rot macht, haengt sie bis zum Timeout,
ohne dass etwas fehlschlaegt. Genau so verhielten sich in It. 26 zwei
Suiten: still, nicht rot. Deshalb geht JEDER Geraeusch-Aufruf ueber die
statische Fassade `core/SfxBus.gd`, die den Autoload nachschlaegt und ohne
ihn ein No-op ist.

**Falle: `GameCalendar.week_total` ist EINS-BASIERT** - Zug 0 ist Woche 1,
Zug 7 ist Woche 2. In It. 25 stand die "erste Woche ist ruhig"-Sperre auf
Woche 0 und griff damit im Spiel NIE. Der eigene Test hat es zunaechst
nicht gezeigt, weil er genau diesen nicht existierenden Fall (Woche 0)
geprueft hat. Zugnummer aus Woche: `turn = (week - 1) * 7`.

**Test-Falle: ein Laufzeitfehler in einer Test-Funktion faellt NICHT auf.**
GDScript bricht nur die betroffene Funktion ab; die Suite laeuft weiter und
meldet gruen. In It. 24 hat ein geratener Funktionsname (`collect_state`
statt `_capture_state`) so einen halben Test verschluckt.

Seit It. 31 haben ALLE 17 Suiten die Gegenmassnahme: jede `_test*`-Funktion
setzt als letzte Zeile `_done.append("<name>")`, und ein Abschluss-Check
vergleicht das mit `get_method_list()` - die Soll-Liste kommt also aus dem
Skript selbst. Damit faellt zweierlei auf: eine Funktion, die mitten drin
abbricht, UND eine neue Testfunktion, die niemand aus `_init` aufruft.
Beides gegengeprueft mit absichtlich kaputten Kopien (Aufruf entfernt bzw.
nil-Zugriff in einer awaited Funktion) - in beiden Faellen wird die Suite
rot und nennt die Funktion. **Wer eine Testfunktion hinzufuegt, braucht die
Marke**, sonst ist die Suite rot; das ist Absicht.

**Test-Falle: GDScript-Lambdas fangen lokale Variablen als KOPIE.** Ein
`signal.connect(func(r): got = r)` auf eine LOKALE Variable schreibt ins
Nichts - das Ergebnis muss in ein Feld. Hat in It. 23 einen halben Testlauf
gekostet.

**Test-Falle (ZWEIMAL passiert): `_next_round()` laesst die KI ziehen.** Wer im Test mehrere
Runden anstoesst, um an einen spaeteren Zustand zu kommen, riskiert dass
der eigene Stack stirbt und `_finished` gesetzt wird - danach prallt jede
weitere Aktion ab. Fuer einen bestimmten Zustand einen FRISCHEN Screen
aufsetzen, nicht durch Runden laufen. In It. 27 wieder zugeschlagen: drei
`_next_round()`-Aufrufe nur um `_casts_left` zurueckzusetzen - die KI hat
dabei den Spieler-Stack von 4 auf 1 gehauen und der Heil-Test schlug fehl.
Fuer "ein Zauber pro Runde" genuegt `bs._casts_left = 1`.

**Getrennte Helden-Boni (It. 22):** `CombatMath.damage` nahm `att_bonus`
und `def_bonus` schon immer entgegen, aber beide wurden aus demselben
`_player_bonus` gefuellt - ein Angriffsbonus machte den Helden also auch
zaeher. Jetzt `player_att`/`player_def` im Kontext, mit `player_bonus` als
Rueckfall fuer Alt-Aufrufer. `_dmg` hat einen vierten Parameter
`shooting`, weil `melee_penalty` dafuer NICHT taugt (das ist der
Nahkampf-Malus fuer Fernkaempfer, nicht die Frage ob geschossen wird).

**Test-Falle It. 17 (`fx_speed`):** Der Kampf-Screen wartet mit der
Zugkette auf ablaufende Effekte. Jeder Test, der einen Kampf treibt, MUSS
`bs.fx_speed = 0.0` direkt nach `TBS.new()` setzen - sonst wartet er auf
Animationen, die headless nie ankommen, und laeuft in den Timeout.
`test_battle.gd` (6 Instanzen) und `test_siege.gd` (1) tun das.

Pro-Iteration-Vertrag: (1) git fetch+reset auf origin-Branch (Sandbox
resettet, Tracking-Ref luegt - ls-remote glauben, nicht git log!),
(2) EIN Meilenstein-Teil, (3) Logik nach core/ statt in den Monolithen,
(4) Test in tools/ + game-ci.yml, (5) Save-Fixture-Kompatibilitaet
(tools/fixtures/save_v*.json) pruefen, (6) nur gruen pushen (CI shippt
APK auf latest-mobile!), (7) diese Tabelle aktualisieren.

## Grafik-Programm (Nutzer-Entscheidung, It. 17 ff.)

Der Nutzer hat die Grafik komplett verworfen ("nur der Hintergrund ist
fertig"). Entschieden:

- **Stil-Messlatte** sind die drei SVG-Stadt-Hintergruende (Waldvolk,
  Totenreich, Orks), erzeugt von einem Python-Generator.
- **Pipeline: SVG-Generatoren, alles aus einer Hand.** KEIN Bildgenerator.
  Claude Design ist nur die Begutachtungs-Leinwand, kein Erzeuger - das war
  ein Missverstaendnis des Nutzers und ist ausgeraeumt.
- `assets/city/menschen/bg.png` (Canva-generiert, gemalt) **wird ersetzt**,
  damit alle vier Staedte zusammenpassen.
- Kampf: **gemalte Kreatur direkt im Gitter**, nicht Token + Detail-Panel.
  Bei ~86 px Zellgroesse heisst das: grobe, kontrastreiche Silhouetten.
- Reihenfolge: 17 Effekte -> 18 Stadt komplett -> 19 Weltkarte lesbar ->
  20 Kreaturen -> 21 Schlachtfeld-Kulisse. **Alle fuenf sind fertig.**
- **Karten-Objekte brauchen nichts.** Truhe, Mine, Haufen, die vier
  Stadt-Icons und Held/Feind wurden bei 64 px geprueft: klar lesbar,
  konsistent, deutliche Silhouetten. Zwei vermeintliche Defekte dort waren
  Fehler im Vorschau-Skript, nicht im Spiel - der Fraktionsname aus
  units.json (`orkstaemme`) ist NICHT der Verzeichnisname (`orks`), und ein
  Regex auf `width="..."` trifft das erste innere `<rect>`, weil die
  `<svg>`-Tags dort keine Groesse tragen.

### Verbindliche Asset-Konventionen

- **Stadt-Layout:** `data/city_layout.json` ist die EINZIGE Quelle fuer
  Bauplaetze und Platz. `tools/gen_city_bg.py` liest sie (Wege und Platz
  weichen den Plots aus), `CityScreen` liest sie, `tools/preview_city_full.gd`
  spiegelt die Skalierung. Wer eine Position aendert, laesst
  `python3 tools/gen_city_bg.py` laufen - `check_layout()` meldet
  Ueberdeckungen und Plaetze ausserhalb des Mauerrings. Der Ring ist unten
  ENG: bei y 0.875 darf ein Plot mit s=1.0 nur zwischen x 0.34 und 0.66
  stehen.
- **Gebaeude-Sprites:** ViewBox 512x512, Bodenraute-Mitte bei **y=288**.
  `CityScreen._draw_sprite_at` verankert auf `SPRITE_GROUND_FRAC = 0.56`
  (0.56 * 512 = 287). Weicht der Anker ab, schweben die Gebaeude ueber
  ihrer Raute oder versinken darin.
- **Nie von Hand editieren.** Generator anpassen und neu laufen lassen:
  `python3 tools/gen_city_bg.py`, `python3 tools/gen_city_buildings.py`,
  `python3 tools/gen_unit_sprites.py`.
- **Asset-Vollstaendigkeit** ist getestet: `tools/test_city_screen.gd`
  iteriert alle Gebaeude-IDs aus `data/city_layout.json` x alle vier
  `FACTION_DIRS` und verlangt fuer jede Kombination ein Sprite, dazu bg,
  bg_walled und je eine Baustelle. Ein neues Gebaeude ohne Grafik macht die
  Suite rot, statt still einen Quader zu zeichnen.
- `ART_EXTENSIONS` ist `[".svg", ".png"]` - eine neue .svg gewinnt ohne
  Code-Change gegen eine bestehende .png.
- **EINE Uhr fuer die Zugkette.** Wartezeiten im Kampf laufen ueber die
  Effekt-Queue (`Vfx.PAUSE` + `_pending_fn`, geleert in `_process`), NICHT
  ueber `get_tree().create_timer()`. Ein Timer ist eine zweite Uhr: er
  ignoriert `fx_speed` und laeuft headless gar nicht (keine Echtzeit) - der
  Kampf steht dann still, mit dem Gegner am Zug und ohne sichtbaren Grund
  (It. 39). Wer eine neue Wartezeit braucht: Pause in die Queue legen.

**Signal ZUERST verbinden, dann den Zustand setzen.** `_open_battle` hat
  `set_battle` vor dem `connect` aufgerufen - und ein Kampf kann in
  `set_battle` schon entschieden sein. Das Signal ging ins Leere, das
  Overlay blieb stehen, die KI-Phase war eingefroren. Wer eine Szene
  einhaengt, die IN der Initialisierung fertig werden kann, verbindet
  vorher (It. 38).

**Vorschau-Werkzeuge duerfen NICHTS eigenes wissen.** Vier Iterationen
  (33-37) haben denselben Fehler in vier Werkzeugen gefunden: eine Kopie
  einer Zahl aus dem Screen. Reihenfolge der Funde: Bauplatz-Koordinaten,
  Fransen-Deckkraft, Schriftgroesse der Token-Beschriftung
  (`cell*0.52` ist der ABSTAND, nicht die Groesse), Zellgroesse 64 statt
  104 - und zuletzt eine Kugel als Pfeilspitze, wo der Screen ein Dreieck
  zeichnet. Wer ein Vorschau-Werkzeug anfasst: jede Zahl, die auch im
  Screen steht, MUSS von dort gelesen werden. Notfalls die Zahl im Screen
  zur Konstante machen (so entstanden `TOKEN_DISC_FRAC` und Co.).

**Immer KOMPONIERT ansehen, nicht als Kachel- oder Sprite-Blatt.** Drei
  Iterationen hintereinander (30, 33, 34) haben denselben Fehler gefunden:
  Einzelteile nebeneinander sehen gut aus, im Zusammenhang bei
  Geraetegroesse fallen sie auseinander. Werkzeuge dafuer:
  `tools/preview_city_full.gd` (Stadt), `tools/preview_world_full.gd`
  (Weltkarte inkl. Handy-Ausschnitt), `tools/preview_battle_full.gd` +
  `preview_battle_fx.gd` (Kampf), Kontaktbogen per headless Chromium fuer
  Kreaturen - dort auf FLACHEM Grund UND auf der Token-Scheibe.
- **Weltkarten-Kacheln:** 64x64, FLACHE Grundfarbe (ein senkrechter Verlauf
  je Kachel ergibt im Feld Querstreifen alle 64 px - ein Verlauf kann nicht
  kacheln), Deko mit Abstand zum Rand (`INSET`), damit die Kacheln seitlich
  passen. Sechs Varianten je Art; vier waren bei ~30 Kacheln im Blick noch
  als Muster erkennbar.
- **Einheiten-Token:** ViewBox 128x128, Standlinie y=114, Figur fuellt rund
  85 % der Hoehe, jede Silhouette mit Kontur. Sie erscheinen an genau EINER
  Stelle (`TacticalBattleScreen._unit_texture` -> `_draw_token`) in genau
  EINER Groesse (`cell * 0.92`, rund 86 px) - alles ist darauf hin
  entschieden.
- **Schlachtfeld:** Boden-Kacheln 64x64 (flach, Deko mit `INSET`),
  Kulissen-Baender 540 breit und im Screen auf die Flaechenbreite gezogen.
  Deko-Deckkraft niedrig halten: bei 0.3+ und zwei gleich grossen Flecken je
  Kachel ergaben 96-px-Zellen ein regelmaessiges Fleckenraster, und feine
  Drei-Strich-Bueschel lasen sich hochskaliert wie Schriftzeichen.
- **SVG-Fallen im Generator**, drei teuer bezahlt: (1) In eine
  Formatzeichenkette KEIN festes Minuszeichen vor einen bereits
  vorzeichenbehafteten Wert schreiben - aus `"-%.1f" % (s*25.3)` wurde bei
  s=-1 ein `--25.3` und damit ungueltiges SVG. (2) Der Grenzen-Pruefer muss
  bei Boegen (`A`) nur die letzten zwei der sieben Zahlen als Koordinaten
  lesen UND bei Kleinbuchstaben den Cursor mitfuehren - sonst meldet er
  ueberall Fehlalarm und ist damit wertlos. (3) Lange Formatzeichenketten
  mit abwechselnd x- und y-Werten sind fehleranfaellig - bei den
  Sand-Felsnadeln waren x und y vertauscht und die Punkte lagen weit unter
  dem Band. Punkt-TUPEL nehmen (`poly_pts`), nicht Zahlenketten.
- Silhouette ist das Unterscheidungsmerkmal, nicht die Farbe: die Sprites
  sind auf dem Handy ~150 px breit. Reiterei/Kaserne/Mauer sahen im ersten
  Anlauf identisch aus (Kasten mit Dach) - die Mauer hat jetzt einen eigenen
  Koerper (`wall_piece`) und der Spaeher einen (`scout_tower`).

**Nachtrag zum Layout:** Seit alle vier Fraktionen einen Hintergrund haben,
liefert `_has_painted_bg()` ueberall true - alle benutzen das enge
`buildings`-Band (y 0.475-0.80). `buildings_plain` bleibt als Fallback im
Code und ist weiter getestet.

## Entschiedene Design-Fragen (implementiert)

### Fraktions-Misch-Malus in Armeen (It. 11, `core/Morale.gd`)
Nutzer-Entscheidung: **HoMM3-streng**, jede zusaetzliche Fraktion kostet.

| Armee | Moral |
|---|---|
| 1 Fraktion (rein) | +1 |
| 2 Fraktionen | 0 |
| 3 Fraktionen | -1 |
| 4 Fraktionen | -2 |
| Lebende + Untote zusammen | zusaetzlich -1 |
| Engel dabei (`morale_aura`) | +1 |

Ergebnis auf +-3 begrenzt; Untote (`undead`) sind komplett immun. Der
klassische Fall "Menschen + Totenreich" landet damit bei -1.

### Glueck (It. 11)
Quelle ist die Kapelle: +1 je Kapelle in eigenen Staedten, max +3.
Wirkung 10 % je Punkt auf den einzelnen Schlag (Volltreffer x2,
Pechschlag x0.5). Helden-Skills als weitere Quelle kommen mit M7.

## Technisches Gedaechtnis

- Plattform-Detail: Godot 4.6 stable (NON-Mono), GDScript only.
  CI ist auf 4.6 gepinnt (`game-android-build.yml: GODOT_VERSION`),
  lokaler Editor sollte deshalb auch 4.6 sein.
- Branch: `claude/heroes-mobile-game-yJ31W`
- APK-Auslieferung: GitHub-Release-Tag `latest-mobile` (wird von
  game-android-build.yml bei jedem Push ueberschrieben). Artifacts
  waren wegen Storage-Quota (GitHub Free) unzuverlaessig.
- Art-Pipeline: ALLES aus Python-Generatoren in `tools/gen_*.py`, Ausgabe
  SVG (Godot importiert SVG direkt). Kein Bildgenerator mehr - die
  Canva-PNGs der Menschen sind seit It. 18 entfernt. Zum Beurteilen:
  Kontaktbogen per headless Chromium
  (`/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell
  --headless --screenshot=... file://...`) auf eine HTML-Seite mit den
  inline eingebetteten SVGs, oder `tools/preview_city_full.gd` fuer die
  komponierte Buehne aller vier Fraktionen. **Immer ansehen, nicht nur
  save_err=0 glauben** - so wurden der abgeschnittene Zitadellen-Turm, die
  Zinnen-"Perlenkette" neben dem Mauerring und die als Kratzer lesbaren
  Totenreich-Knochen gefunden.
- Claude Design MCP ist als Projekt-Config eingetragen (.mcp.json im
  Repo-Root, Endpoint api.anthropic.com/v1/design/mcp). Tools sollten
  ab Session-Start als mcp__claude-design__* auftauchen - beim ersten
  Mal pruefen, ggf. braucht es eine OAuth-Freigabe durch den Nutzer.

### Godot im Sandbox installieren

Godot ist nicht vorinstalliert, laesst sich aber on-demand reinholen
(/tmp ueberlebt nicht zwangslaeufig zwischen Sessions):

```
cd /tmp && curl -sL -o godot.zip \
  https://github.com/godotengine/godot/releases/download/4.6-stable/Godot_v4.6-stable_linux.x86_64.zip \
  && unzip -o godot.zip && chmod +x Godot_v4.6-stable_linux.x86_64
```

Damit gehen:

- **Parse-Check des ganzen Projekts** (alle `class_name`-Refs aufgeloest):
  einmal `--headless --path game/ --import`, danach
  `--headless --path game/ --quit 2>&1 | grep -iE "error|warning"`.
- **Balance-Sim**:
  `--headless --path game/ --script tools/balance_sim.gd -- --runs=500`.
  Seit M4 Teil 1 nur informativ: BASELINE_IDS sind Alt-Aliase, die auf
  Einheiten verschiedener Tiers aufloesen - Werte verzerrt, Umbau auf
  4x4-Fraktions-Matrix kommt in M4 Teil 2/3.
- Allgemein laeuft jedes `extends SceneTree`-Script in `tools/` headless.

Was nicht geht: WorldMapScreen rendern, Touch/Input testen, irgendwas
mit Display. Dafuer weiterhin Phone oder Desktop-Godot.
