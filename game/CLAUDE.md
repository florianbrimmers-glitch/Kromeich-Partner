# Kromeich Heroes - Arbeits-Notizen

## Roadmap-Status (autonome /loop-Schleife "HoMM3-Endausbau")

Vollstaendige Roadmap + Architektur-Entscheidungen: Plan-Datei der
Session bzw. Git-History. Scope-Entscheidungen des Nutzers:
Singleplayer zuerst (kein MP in dieser Schleife), MEHR-Ressourcen-System
wie HoMM3, 7 Einheiten-Tiers (units.json migrieren!), CC0-Sound.

| Meilenstein | Status |
|---|---|
| M1 Save/Load + Autosave + CI-Gate | FERTIG (Iteration 1) |
| M2 Hauptmenue (Fortsetzen ist da; Fraktionswahl+Seed fehlen) | teilweise |
| M3 Ressourcen-System (Wallet, Minen-Typen, Haufen, Markt-Tausch) | offen - NAECHSTES |
| M4 Einheiten-Migration 7 Tiers (UnitType-Fassade ueber units.json) | offen |
| M5-M12 Parallel-Band (Objekte, Moral, Abilities, Belagerung, Sprites, Sound, Events) | offen |
| M7/M8 Heldenstats/Skills, Zauber | offen (nach M4) |
| M13 Mehrere Helden (vorher Struktur-Iteration!), M14 MP | zurueckgestellt |

Pro-Iteration-Vertrag: (1) git fetch+reset auf origin-Branch (Sandbox
resettet, Tracking-Ref luegt - ls-remote glauben, nicht git log!),
(2) EIN Meilenstein-Teil, (3) Logik nach core/ statt in den Monolithen,
(4) Test in tools/ + game-ci.yml, (5) Save-Fixture-Kompatibilitaet
(tools/fixtures/save_v*.json) pruefen, (6) nur gruen pushen (CI shippt
APK auf latest-mobile!), (7) diese Tabelle aktualisieren.

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
- Allgemein laeuft jedes `extends SceneTree`-Script in `tools/` headless.

Was nicht geht: WorldMapScreen rendern, Touch/Input testen, irgendwas
mit Display. Dafuer weiterhin Phone oder Desktop-Godot.
