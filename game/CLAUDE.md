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
| M10 Kampf-Sprites | FERTIG (It. 13): 28 Token-SVGs in `assets/units/<fraktion>/<id>.svg`, erzeugt von `tools/gen_unit_sprites.py` (datengetrieben aus units.json - NICHT per Hand editieren, Generator anpassen und neu laufen lassen). Silhouette nach Rolle (Fernkampf/Flieger/Reiter/Riese/Nahkampf), Tier skaliert die Figur (0.74-1.04) und steht als Punktreihe am Sockel, ab T5 Hoerner, Erkennungszeichen aus den Abilities (Heiligenschein, Fangzaehne, Rippen, Todeswolke, Hammer, ...). Untote knochenfarben mit Fraktions-Aura. Wichtig: Token-Scheibe im Kampf ist DUNKEL (`fill.darkened(0.72)`), Seite steckt im Ring - Menschen-Gold auf goldener Scheibe war unsichtbar; Beschriftung deshalb hell mit Schlagschatten. Fallback auf die alten Kreise bleibt, wenn eine SVG fehlt. `tools/preview_unit_tokens.gd` (Kontaktbogen) + `tools/preview_battle.gd` (Gitter-Mock) rendern headless; der echte Screen laesst sich headless NICHT rendern. test_battle prueft die Abdeckung aller 28 Token. |
| M9 Belagerung | FERTIG (It. 14): neues `BattleObstacles.KIND_WALL` (blockt Bewegung+Schusslinie, `WALL_SEGMENT_HP`=2) + `siege_walls(cols, rows)` = Segmentreihe in Spalte `cols-4` mit Tor-Luecke in der Mittelreihe. Kampf-Screen: `ctx.siege`/`ctx.tower_dmg`, `_wall_hp` je Segment; Katapult trifft pro Runde das tor-naechste Segment (1 Schaden), zerstoertes Segment fliegt aus `_obstacles` UND `_ob_map` -> Feld sofort passierbar; Pfeilturm (SIEGE_TOWER_DMG 12 + 8 je Wachturm) trifft pro Runde den groessten Angreifer-Stack; Verteidiger +SIEGE_DEF_BONUS (2) solange ein Segment steht; `attack_wall`-Einheiten (Zyklop) schlagen per Tap selbst Segmente ein. **Falle:** `_dijkstra_for` prueft Hindernis-Arten als Literale - neue Kinds dort NACHTRAGEN (die Mauer blockte zuerst nicht). Ausserdem: Stadt-Wachen bestehen jetzt aus Einheiten der Stadt-Fraktion (`_faction_guard_stacks`), und die Auto-Abrechnung bei KI-Angriffen rechnet die eigene Mauer mit `SIEGE_AUTO_DEF_FACTOR` (1.25) ein. 8. Suite `tools/test_siege.gd`. |
| Echte Garnisonen (M9b) | FERTIG (It. 15). Vorher hielt jede Stadt nur `garrison: int` (Phantom-Truppen wurden beim Angriff synthetisiert) und die Spielerstadt startete mit 0 - die Mauer aus M9 schuetzte niemanden. Jetzt: `city["garrison_army"]` ist ein `{uid: count}`-Dict wie `Hero.army`, neues `core/Garrison.gd` (synth/total/add/remove/to_stacks/from_stacks/summary). **SAVE_VERSION=3** + `_migrate_2_to_3` (alte Zahl -> echte Einheiten der Stadt-Fraktion). Rekrutieren OHNE Held vor Ort fuellt die Garnison (Fernverwaltung existierte schon); CityScreen hat einen Garnison-Button mit Verschiebe-Panel (Held <-> Stadt, 1/alle, respektiert MAX_ARMY_SLOTS). Kampf nutzt die gespeicherten Einheiten; `battle_finished` liefert jetzt `player_remaining` + `enemy_remaining`, damit eine gescheiterte Belagerung die Garnison geschwaecht zuruecklaesst. KI-Angriff auf eigene Stadt = **spielbarer Verteidigungskampf** (gleiches Muster wie der Pflicht-Kampf gegen den Helden: Overlay auf, `return false`, Callback `_on_city_defense_result` setzt die KI-Phase fort); Verteidiger = Garnison + Held falls anwesend. `SIEGE_AUTO_DEF_FACTOR` entfallen. 9. Suite `tools/test_garrison.gd`. |
| M5-M12 Parallel-Band (Objekte, Sound, Events) | offen |
| M7/M8 Heldenstats/Skills, Zauber | offen (nach M4) |
| M13 Mehrere Helden (vorher Struktur-Iteration!), M14 MP | zurueckgestellt |

Pro-Iteration-Vertrag: (1) git fetch+reset auf origin-Branch (Sandbox
resettet, Tracking-Ref luegt - ls-remote glauben, nicht git log!),
(2) EIN Meilenstein-Teil, (3) Logik nach core/ statt in den Monolithen,
(4) Test in tools/ + game-ci.yml, (5) Save-Fixture-Kompatibilitaet
(tools/fixtures/save_v*.json) pruefen, (6) nur gruen pushen (CI shippt
APK auf latest-mobile!), (7) diese Tabelle aktualisieren.

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
- Art-Pipeline: Stadt-Hintergruende (menschen/bg.png + bg_walled.png)
  sind KI-generiert via Canva MCP (generate-design -> create-design-
  from-candidate -> export-design als PNG -> curl -> Repo). Gebaeude-
  Sprites sind handgebaute SVGs; gemalte Alpha-Sprites stehen aus.
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
