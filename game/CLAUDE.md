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
