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
- Branch: `claude/heroes-mobile-game-yJ31W`

### Godot im Sandbox installieren

Godot ist nicht vorinstalliert, laesst sich aber on-demand reinholen
(/tmp ueberlebt nicht zwangslaeufig zwischen Sessions):

```
cd /tmp && curl -sL -o godot.zip \
  https://github.com/godotengine/godot/releases/download/4.5-stable/Godot_v4.5-stable_linux.x86_64.zip \
  && unzip -o godot.zip && chmod +x Godot_v4.5-stable_linux.x86_64
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
