extends Control

# Weltkarten-Screen. Rendert eine deterministische Zufallskarte per
# _draw() und erlaubt den Helden per Tap zu bewegen. Dijkstra berechnet
# die Kosten aller erreichbaren Felder; unerreichbare werden abgedunkelt.

const MAP_WIDTH := 18
const MAP_HEIGHT := 26

const CITY_COUNT := 4
const CITY_MIN_DIST := 8
const CITY_INCOME := 500
const OWNER_NEUTRAL := -1
const OWNER_HERO := 0
const OWNER_ENEMY := 1

# Gegner-Held: Start-Werte, bewegt sich automatisch am Ende des Spielerzugs.
# Er startet mit Armee 0 und Gold 0, exakt wie der Spieler - keine
# Gratis-Resourcen. Sein Fortschritt haengt allein davon ab, was er in
# seinen Staedten baut (siehe _enemy_economy).
const ENEMY_BASE_MP := 10

# Gebaeude-Effekte
const BASE_MAX_MP := 10
const MP_BONUS_SPAEHER := 2     # pro Spaeher in eigener Stadt
const INCOME_MARKT := 200       # zusaetzlich pro Markt in eigener Stadt
const UNIT_COST := 150          # pro Einheit, benoetigt Kaserne

# Monster
const MONSTER_COUNT := 8
const MONSTER_MIN_DIST := 5
const MONSTER_VICTORY_GOLD := 120

# Karten-Objekte: Goldminen (dauerhaftes Einkommen) und Schatzkisten
# (Einmal-Belohnung). Beide haben eine Wache, die vor Einnahme besiegt
# werden muss (selbe Formel wie Stadt-Wache/Monster).
const OBJECT_MINE := 0
const OBJECT_TREASURE := 1
const MINE_COUNT := 4
const TREASURE_COUNT := 4
const MINE_GOLD_PER_TURN := 150
const TREASURE_GOLD_MIN := 300
const TREASURE_GOLD_MAX := 700
const OBJECT_GUARD_MIN := 2
const OBJECT_GUARD_MAX := 5
const OBJECT_MIN_DIST := 3

# Belohnung fuer Sieg ueber den Gegner-Helden (Auto-Resolve auf der Karte).
# Bewusst hoeher als ein Monster, weil er sich bewegt und zurueckschlaegt.
const ENEMY_DEFEAT_GOLD := 300
const ENEMY_DEFEAT_XP := 50

# Stadt-Wachen: jede neutrale Stadt hat eine zufaellige Wache. Sie muss
# vor der Einnahme besiegt werden (selbe Combat-Formel wie Monster).
# Die Start-Stadt des Helden hat Garrison 0.
const GARRISON_MIN := 2
const GARRISON_MAX := 5

# Held-Progression. XP_PER_STRENGTH * Monster-Staerke = XP pro Kill.
# LEVEL_THRESHOLDS[i] ist die XP-Schwelle, um von Level i auf i+1 zu
# springen (Level 1 = Startlevel, Index 0 ungenutzt zur Klarheit).
const XP_PER_STRENGTH := 15
const LEVEL_THRESHOLDS := [0, 50, 150, 350, 700, 1200, 2000]
const LEVEL_BONUS_ARMY := 1   # sofort +1 Armee bei Level-Up
const LEVEL_BONUS_MP := 1     # +1 max_mp pro Level-Up (additiv zur Basis)
# Kampfkraft-Bonus pro Level (level-1): zaehlt zur Armee im Kampf UND
# reduziert Verluste. Macht XP endlich nuetzlich: Level 3 mit 1 Armee
# schlaegt Staerke-3-Monster ohne einen einzigen Verlust.
const LEVEL_COMBAT_BONUS := 1

# Schmiede: pro eigener Stadt mit Schmiede +1 Armee/Zug (Ende-Zug).
const SCHMIEDE_ARMY_PER_TURN := 1
# Wachturm: pro eigener Stadt +1 Kampfkraft-Bonus (stapelt mit Level-Bonus).
const WACHTURM_COMBAT_BONUS := 1
# Kapelle: +XP pro Zug pro Stadt mit Kapelle.
const KAPELLE_XP_PER_TURN := 10

# Monster-Aufklaerung: exakte Staerke nur sichtbar, wenn der Held in
# Manhattan-Reichweite ist. Weiter weg erscheint "?" (Info-Vorteil fuer
# Erkundung).
const MONSTER_VIEW_RANGE := 5

# Fraktionen. Bewusst generische Namen (nicht HoMM3-IP), passt zur
# Plan-Phase 1 ("Waldvolk"/"Menschen"/"Totenreich"/"Orks").
const FACTION_NAMES := ["Waldvolk", "Menschen", "Totenreich", "Orks"]
const FACTION_COLORS := [
	Color(0.45, 0.85, 0.45),   # Waldvolk - gruen
	Color(0.95, 0.85, 0.35),   # Menschen - gold
	Color(0.70, 0.45, 0.90),   # Totenreich - violett
	Color(0.95, 0.35, 0.30),   # Orks - rot
]

# Gebaeude: id/Name/Kosten/effect-Text. Optional "requires" = id eines
# anderen Gebaeudes, das vorher gebaut sein muss (selbe Stadt). Schmiede
# z.B. braucht Kaserne, sonst war es zu leicht, ohne Kaserne zu spielen.
# Pro Stadt als Liste von ids in city["buildings"].
const BUILDINGS := [
	{"id": "kaserne",  "name": "Kaserne",  "cost": 500, "effect": "Erlaubt Rekrutierung"},
	{"id": "spaeher",  "name": "Spaeher",  "cost": 300, "effect": "+2 max Schritte/Zug"},
	{"id": "markt",    "name": "Markt",    "cost": 800, "effect": "+200 Gold/Zug"},
	{"id": "schmiede", "name": "Schmiede", "cost": 700, "effect": "+1 Armee/Zug", "requires": "kaserne"},
	{"id": "wachturm", "name": "Wachturm", "cost": 400, "effect": "+1 Kampfkraft (dauerhaft)"},
	{"id": "kapelle",  "name": "Kapelle",  "cost": 500, "effect": "+10 XP/Zug"},
]

@export var status_label_path: NodePath    = ^"TopBar/StatusLabel"
@export var mp_label_path: NodePath        = ^"TopBar/MPLabel"
@export var end_turn_button_path: NodePath = ^"BottomBar/EndTurnBtn"
@export var reroll_button_path: NodePath   = ^"BottomBar/RerollBtn"
@export var back_button_path: NodePath     = ^"BottomBar/BackBtn"
@export var map_area_path: NodePath        = ^"MapArea"

var _map: Dictionary
var _hero: Hero
var _seed: int = 42
var _costs: Dictionary = {}
var _tile_size: float = 64.0
var _map_area: Control
# Staedte: Array aus { "pos": Vector2i, "faction": int, "owner": int,
# "buildings": Array[String] }. Faction-ID indiziert FACTION_NAMES/_COLORS.
var _cities: Array = []
var _city_panel: Panel
var _city_title: Label
var _city_gold: Label
var _buildings_box: VBoxContainer
var _selected_city: int = -1
# Monster: Array aus { "pos": Vector2i, "strength": int }.
var _monsters: Array = []
# Karten-Objekte: Array aus { "pos": Vector2i, "kind": int, "owner": int,
# "guard": int, "gold": int }. kind=OBJECT_MINE gibt Gold/Zug solange im
# Besitz; kind=OBJECT_TREASURE gibt einmalig Gold und wird entfernt.
var _objects: Array = []
# Dauerhafte Kampf-Anzeige zwischen TopBar und MapArea. Wird NIE von
# Tap-Status ueberschrieben - bleibt stehen, bis ein neuer Kampf passiert.
var _combat_label: Label
var _victory_panel: Panel
var _victory_title: Label
var _game_won: bool = false
var _game_lost: bool = false
# Gegner-Held: Position, mp, army. Wird am Ende des Spielerzugs bewegt.
var _enemy: Hero
# RNG bleibt nach _start() aktiv, damit Enemy-Turn deterministische
# Wuerfe fuer Garrison machen kann.
var _rng: DeterministicRng


func _set_status(s: String) -> void:
	var lbl := get_node_or_null(status_label_path) as Label
	if lbl != null:
		lbl.text = s
	print("[WorldMap] " + s)


func _ready() -> void:
	_set_status("STEP 1: _ready")
	_map_area = get_node(map_area_path) as Control
	_map_area.gui_input.connect(_on_map_input)
	_map_area.draw.connect(_draw_map)
	_map_area.resized.connect(_on_map_resized)
	_build_combat_label()
	_build_city_panel()
	_build_victory_panel()

	(get_node(end_turn_button_path) as Button).pressed.connect(_on_end_turn)
	(get_node(reroll_button_path) as Button).pressed.connect(_on_reroll)
	(get_node(back_button_path) as Button).pressed.connect(_on_back)
	_set_status("STEP 2: Buttons verdrahtet")

	_start(_seed)


func _start(seed_value: int) -> void:
	_set_status("STEP 3: generiere seed=%d" % seed_value)
	_seed = seed_value
	_game_won = false
	_game_lost = false
	_enemy = null
	if _victory_panel != null:
		_victory_panel.visible = false
	_rng = DeterministicRng.new(seed_value)
	var rng := _rng
	_set_status("STEP 3a1: Array init")
	var tiles: Array = []
	_set_status("STEP 3a2: resize %d" % (MAP_WIDTH * MAP_HEIGHT))
	tiles.resize(MAP_WIDTH * MAP_HEIGHT)
	_set_status("STEP 3a3: fill grass")
	for i in range(tiles.size()):
		tiles[i] = MapGen.TILE_GRASS
	var water_clusters: int = max(2, int(float(MAP_WIDTH * MAP_HEIGHT) / 80.0))
	_set_status("STEP 3b: place_water (%d Cluster)" % water_clusters)
	for ci in range(water_clusters):
		_set_status("STEP 3b.%d.a: cx/cy" % (ci + 1))
		var cx := rng.next_int(0, MAP_WIDTH - 1)
		var cy := rng.next_int(0, MAP_HEIGHT - 1)
		_set_status("STEP 3b.%d.b: target_size" % (ci + 1))
		var target_size := rng.next_int(8, 18)
		_set_status("STEP 3b.%d.c: loop start (%d,%d) tgt=%d" % [ci + 1, cx, cy, target_size])
		var frontier: Array = [Vector2i(cx, cy)]
		var placed := 0
		var it := 0
		while placed < target_size and frontier.size() > 0 and it < 500:
			it += 1
			var idx := rng.next_int(0, frontier.size() - 1)
			var cell: Vector2i = frontier[idx]
			frontier.remove_at(idx)
			if cell.x < 0 or cell.x >= MAP_WIDTH or cell.y < 0 or cell.y >= MAP_HEIGHT:
				continue
			var ti: int = cell.y * MAP_WIDTH + cell.x
			if int(tiles[ti]) != MapGen.TILE_GRASS:
				continue
			tiles[ti] = MapGen.TILE_WATER
			placed += 1
			frontier.append(Vector2i(cell.x + 1, cell.y))
			frontier.append(Vector2i(cell.x - 1, cell.y))
			frontier.append(Vector2i(cell.x, cell.y + 1))
			frontier.append(Vector2i(cell.x, cell.y - 1))
		_set_status("STEP 3b.%d.d: loop done it=%d placed=%d" % [ci + 1, it, placed])
	var mountain_clusters: int = max(3, int(float(MAP_WIDTH * MAP_HEIGHT) / 50.0))
	_set_status("STEP 3c: place_mountains (%d Cluster)" % mountain_clusters)
	for ci in range(mountain_clusters):
		var cx := rng.next_int(0, MAP_WIDTH - 1)
		var cy := rng.next_int(0, MAP_HEIGHT - 1)
		var target_size := rng.next_int(4, 10)
		var frontier: Array = [Vector2i(cx, cy)]
		var placed := 0
		var it := 0
		while placed < target_size and frontier.size() > 0 and it < 500:
			it += 1
			var idx := rng.next_int(0, frontier.size() - 1)
			var cell: Vector2i = frontier[idx]
			frontier.remove_at(idx)
			if cell.x < 0 or cell.x >= MAP_WIDTH or cell.y < 0 or cell.y >= MAP_HEIGHT:
				continue
			var ti: int = cell.y * MAP_WIDTH + cell.x
			if int(tiles[ti]) != MapGen.TILE_GRASS:
				continue
			tiles[ti] = MapGen.TILE_MOUNTAIN
			placed += 1
			frontier.append(Vector2i(cell.x + 1, cell.y))
			frontier.append(Vector2i(cell.x - 1, cell.y))
			frontier.append(Vector2i(cell.x, cell.y + 1))
			frontier.append(Vector2i(cell.x, cell.y - 1))
	_set_status("STEP 3d: coat_with_sand")
	var sand_changes: Array = []
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			var ti := y * MAP_WIDTH + x
			if int(tiles[ti]) != MapGen.TILE_GRASS:
				continue
			var has_water := false
			if x + 1 < MAP_WIDTH and int(tiles[y * MAP_WIDTH + x + 1]) == MapGen.TILE_WATER:
				has_water = true
			elif x - 1 >= 0 and int(tiles[y * MAP_WIDTH + x - 1]) == MapGen.TILE_WATER:
				has_water = true
			elif y + 1 < MAP_HEIGHT and int(tiles[(y + 1) * MAP_WIDTH + x]) == MapGen.TILE_WATER:
				has_water = true
			elif y - 1 >= 0 and int(tiles[(y - 1) * MAP_WIDTH + x]) == MapGen.TILE_WATER:
				has_water = true
			if has_water:
				sand_changes.append(ti)
	for ti in sand_changes:
		tiles[ti] = MapGen.TILE_SAND

	_set_status("STEP 3e: place_forests")
	for i in range(tiles.size()):
		if int(tiles[i]) == MapGen.TILE_GRASS and rng.next_int(0, 99) < 20:
			tiles[i] = MapGen.TILE_FOREST

	_set_status("STEP 3f: find_spawn")
	var spawn := Vector2i(int(MAP_WIDTH / 2), int(MAP_HEIGHT / 2))
	var found := false
	var max_r: int = max(MAP_WIDTH, MAP_HEIGHT)
	for r in range(max_r):
		if found:
			break
		for dy in range(-r, r + 1):
			if found:
				break
			for dx in range(-r, r + 1):
				var sx: int = int(MAP_WIDTH / 2) + dx
				var sy: int = int(MAP_HEIGHT / 2) + dy
				if sx < 0 or sx >= MAP_WIDTH or sy < 0 or sy >= MAP_HEIGHT:
					continue
				if int(tiles[sy * MAP_WIDTH + sx]) == MapGen.TILE_GRASS:
					spawn = Vector2i(sx, sy)
					found = true
					break
	_map = {
		"width": MAP_WIDTH,
		"height": MAP_HEIGHT,
		"tiles": tiles,
		"hero_spawn": spawn,
	}
	_set_status("STEP 4: MapGen fertig, spawn %s" % str(spawn))
	_hero = Hero.new(spawn, BASE_MAX_MP)
	_set_status("STEP 5: Hero erstellt")

	# Staedte platzieren: deterministisch, nur Gras-Felder, Mindestabstand
	# untereinander. Spawn-Abstand wird NICHT geprueft, weil eine der
	# Staedte selbst zum Start-Ort des Helden wird.
	_set_status("STEP 5a: Staedte platzieren")
	_cities.clear()
	var city_attempts := 0
	while _cities.size() < CITY_COUNT and city_attempts < 400:
		city_attempts += 1
		var cx: int = rng.next_int(0, MAP_WIDTH - 1)
		var cy: int = rng.next_int(0, MAP_HEIGHT - 1)
		if int(tiles[cy * MAP_WIDTH + cx]) != 0:  # 0 = GRASS
			continue
		var candidate := Vector2i(cx, cy)
		var too_close := false
		for existing in _cities:
			var ep: Vector2i = existing["pos"]
			if abs(candidate.x - ep.x) + abs(candidate.y - ep.y) < CITY_MIN_DIST:
				too_close = true
				break
		if too_close:
			continue
		_cities.append({
			"pos": candidate,
			"faction": _cities.size(),
			"owner": OWNER_NEUTRAL,
			"buildings": [],
			"garrison": rng.next_int(GARRISON_MIN, GARRISON_MAX),
		})

	# Start-Stadt waehlen: eine der platzierten Staedte wird dem Helden
	# zugewiesen, Garrison auf 0, Spawn-Position = Stadt-Position. So
	# sieht man vom ersten Zug an seine eigene Stadt auf der Karte.
	# _hero wurde oben schon mit Mitten-Spawn erzeugt - Position hier
	# ueberschreiben.
	var player_start_idx: int = -1
	if _cities.size() > 0:
		player_start_idx = rng.next_int(0, _cities.size() - 1)
		_cities[player_start_idx]["owner"] = OWNER_HERO
		_cities[player_start_idx]["garrison"] = 0
		spawn = _cities[player_start_idx]["pos"]
		_map["hero_spawn"] = spawn
		_hero.position = spawn

	# Gegner-Held: Start in der Stadt, die am weitesten von der Spieler-
	# Stadt ist. So startet die Partie mit garantierter Distanz zwischen
	# den beiden Helden.
	if _cities.size() > 1 and player_start_idx >= 0:
		var enemy_idx: int = -1
		var best_d: int = -1
		var ps: Vector2i = _cities[player_start_idx]["pos"]
		for i in range(_cities.size()):
			if i == player_start_idx:
				continue
			var cp: Vector2i = _cities[i]["pos"]
			var d: int = abs(cp.x - ps.x) + abs(cp.y - ps.y)
			if d > best_d:
				best_d = d
				enemy_idx = i
		if enemy_idx >= 0:
			_cities[enemy_idx]["owner"] = OWNER_ENEMY
			_cities[enemy_idx]["garrison"] = 0
			_enemy = Hero.new(_cities[enemy_idx]["pos"], ENEMY_BASE_MP)

	# Monster platzieren: nur Gras/Wald, Mindestabstand zu Held, Staedten
	# und anderen Monstern, Staerke 1-3.
	_set_status("STEP 5b: Monster platzieren")
	_monsters.clear()
	var m_attempts := 0
	while _monsters.size() < MONSTER_COUNT and m_attempts < 600:
		m_attempts += 1
		var mx: int = rng.next_int(0, MAP_WIDTH - 1)
		var my: int = rng.next_int(0, MAP_HEIGHT - 1)
		var tt: int = int(tiles[my * MAP_WIDTH + mx])
		if tt != 0 and tt != 1:  # 0 GRASS, 1 FOREST
			continue
		var mpos := Vector2i(mx, my)
		if abs(mpos.x - spawn.x) + abs(mpos.y - spawn.y) < MONSTER_MIN_DIST:
			continue
		var blocked := false
		for c in _cities:
			if c["pos"] == mpos:
				blocked = true
				break
		if blocked:
			continue
		for m in _monsters:
			if abs((m["pos"] as Vector2i).x - mpos.x) + abs((m["pos"] as Vector2i).y - mpos.y) < 2:
				blocked = true
				break
		if blocked:
			continue
		_monsters.append({ "pos": mpos, "strength": rng.next_int(1, 3) })

	# Karten-Objekte platzieren: erst Minen, dann Schatzkisten. Gras/Wald
	# wie Monster, Mindestabstand zu Spawn/Staedten/Monstern/anderen
	# Objekten. Jedes Objekt hat eine zufaellige Wache (OBJECT_GUARD_*).
	_set_status("STEP 5c: Objekte platzieren")
	_objects.clear()
	var o_attempts: int = 0
	var o_target: int = MINE_COUNT + TREASURE_COUNT
	while _objects.size() < o_target and o_attempts < 800:
		o_attempts += 1
		var ox: int = rng.next_int(0, MAP_WIDTH - 1)
		var oy: int = rng.next_int(0, MAP_HEIGHT - 1)
		var ot: int = int(tiles[oy * MAP_WIDTH + ox])
		if ot != 0 and ot != 1:
			continue
		var opos := Vector2i(ox, oy)
		if abs(opos.x - spawn.x) + abs(opos.y - spawn.y) < OBJECT_MIN_DIST:
			continue
		var oblocked: bool = false
		for c in _cities:
			var cpp: Vector2i = c["pos"]
			if abs(cpp.x - opos.x) + abs(cpp.y - opos.y) < OBJECT_MIN_DIST:
				oblocked = true
				break
		if oblocked:
			continue
		for m in _monsters:
			if (m["pos"] as Vector2i) == opos:
				oblocked = true
				break
		if oblocked:
			continue
		for eo in _objects:
			if abs((eo["pos"] as Vector2i).x - opos.x) + abs((eo["pos"] as Vector2i).y - opos.y) < 2:
				oblocked = true
				break
		if oblocked:
			continue
		var kind: int = OBJECT_MINE if _objects.size() < MINE_COUNT else OBJECT_TREASURE
		var gold_amt: int = MINE_GOLD_PER_TURN
		if kind == OBJECT_TREASURE:
			gold_amt = rng.next_int(TREASURE_GOLD_MIN, TREASURE_GOLD_MAX)
		_objects.append({
			"pos": opos,
			"kind": kind,
			"owner": OWNER_NEUTRAL,
			"guard": rng.next_int(OBJECT_GUARD_MIN, OBJECT_GUARD_MAX),
			"gold": gold_amt,
		})

	_recompute_costs()
	_on_map_resized()
	_update_labels()
	_set_combat("Kampf: noch keiner")
	_set_status("Seed %d  Reach %d  Tile %.1f" % [_seed, _costs.size(), _tile_size])


func _recompute_costs() -> void:
	_costs = _dijkstra(_hero.position, true)


func _dijkstra(start: Vector2i, monsters_block: bool) -> Dictionary:
	# Dijkstra inline: static-Calls auf class_name Pathfinder liefern
	# im Android-Export leere Dicts zurueck (gleiches Problem wie bei
	# MapGen). Also hier direkt gerechnet.
	# monsters_block: wenn true (Spielerheld), blockieren Monster das
	# Durchlaufen. Fuer die Gegner-KI lassen wir das weg, damit der
	# Gegner nicht von Monstern eingekesselt wird (vereinfachtes AI).
	var tiles: Array = _map["tiles"]
	var costs: Dictionary = {}
	costs[start] = 0
	# 4 Richtungen als feste Vector2i-Variablen (statt Array-Literal
	# im for-Loop), damit GDScript keine Variant-Konvertierung braucht.
	var dir_e := Vector2i(1, 0)
	var dir_w := Vector2i(-1, 0)
	var dir_s := Vector2i(0, 1)
	var dir_n := Vector2i(0, -1)
	var open: Array = [start]
	var guard := 0
	var cap: int = MAP_WIDTH * MAP_HEIGHT * 4 + 10
	while open.size() > 0 and guard < cap:
		guard += 1
		var best_idx := 0
		var best_cost: int = int(costs[open[0]])
		for i in range(1, open.size()):
			var c: int = int(costs[open[i]])
			if c < best_cost:
				best_cost = c
				best_idx = i
		var cur: Vector2i = open[best_idx]
		open.remove_at(best_idx)
		var cur_cost: int = int(costs[cur])
		# Monster blockieren Durchlaufen: Feld ist erreichbar (bereits in
		# costs eingetragen), aber wir expandieren die Nachbarn nicht.
		# Start hat nie ein Monster drauf. Gegner-KI ignoriert Monster,
		# damit sie nicht eingekesselt wird.
		if monsters_block and cur != start and _monster_at(cur) >= 0:
			continue
		for di in range(4):
			var d: Vector2i = dir_e
			if di == 1: d = dir_w
			elif di == 2: d = dir_s
			elif di == 3: d = dir_n
			var nx: int = cur.x + d.x
			var ny: int = cur.y + d.y
			if nx < 0 or nx >= MAP_WIDTH or ny < 0 or ny >= MAP_HEIGHT:
				continue
			var t: int = int(tiles[ny * MAP_WIDTH + nx])
			var step := -1
			if t == 0 or t == 4:
				step = 1
			elif t == 1:
				step = 2
			if step < 0:
				continue
			var next_cost: int = cur_cost + step
			var key := Vector2i(nx, ny)
			if not costs.has(key) or next_cost < int(costs[key]):
				costs[key] = next_cost
				open.append(key)
	return costs


func _on_map_resized() -> void:
	if _map.is_empty():
		return
	var size := _map_area.size
	var tw: float = size.x / float(MAP_WIDTH)
	var th: float = size.y / float(MAP_HEIGHT)
	_tile_size = min(tw, th)
	_map_area.queue_redraw()


func _update_labels() -> void:
	var ml := get_node_or_null(mp_label_path) as Label
	if ml != null:
		var mp: int = int(_hero.mp)
		var mmax: int = int(_hero.max_mp)
		var gold: int = int(_hero.gold)
		var army: int = int(_hero.army)
		var lvl: int = int(_hero.level)
		var xp: int = int(_hero.xp)
		var bonus: int = _combat_bonus()
		var bonus_str: String = ""
		if bonus > 0:
			bonus_str = "(+" + str(bonus) + ")"
		# "Schritte" statt "MP", damit klar ist, was das ist.
		# A 1 (+2) bedeutet: 1 Armee + 2 Kampfkraft-Bonus (Level + Wachturm).
		ml.text = "L " + str(lvl) + "  Schritte " + str(mp) + "/" + str(mmax) + "  G " + str(gold) + "  A " + str(army) + bonus_str + "  XP " + str(xp)


func _build_combat_label() -> void:
	var lbl := Label.new()
	# Zwischen TopBar (y=32..96) und MapArea (y=120..). Volle Breite,
	# zentriert, damit die Sieg-Meldung nicht uebersehen wird.
	lbl.anchor_left = 0.0
	lbl.anchor_right = 1.0
	lbl.anchor_top = 0.0
	lbl.anchor_bottom = 0.0
	lbl.offset_left = 24
	lbl.offset_top = 100
	lbl.offset_right = -24
	lbl.offset_bottom = 170
	lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	lbl.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	lbl.add_theme_font_size_override("font_size", 34)
	lbl.add_theme_color_override("font_color", Color(1.0, 0.85, 0.35))
	lbl.mouse_filter = Control.MOUSE_FILTER_IGNORE
	lbl.text = "Kampf: noch keiner"
	add_child(lbl)
	_combat_label = lbl


func _set_combat(msg: String) -> void:
	if _combat_label != null:
		_combat_label.text = msg


func _draw_map() -> void:
	var tiles: Array = _map["tiles"]
	var origin := _map_origin()
	# Kampf-Prognose-Werte einmal vor den Schleifen, damit Staedte UND
	# Monster die gleiche Bonus-Logik fuer ihre Zahlen verwenden.
	var cbonus: int = _combat_bonus()
	var eff: int = _hero.army + cbonus
	var mfont: Font = ThemeDB.fallback_font
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			var ti: int = int(tiles[y * MAP_WIDTH + x])
			var pos := origin + Vector2(x * _tile_size, y * _tile_size)
			var rect := Rect2(pos, Vector2(_tile_size - 1.0, _tile_size - 1.0))
			var col := _terrain_color(ti)
			var key := Vector2i(x, y)
			var reachable: bool = _costs.has(key) and int(_costs[key]) <= _hero.mp
			if not reachable:
				col = col.darkened(0.7)
			_map_area.draw_rect(rect, col, true)
			if reachable and key != _hero.position:
				_map_area.draw_rect(rect, Color(1.0, 1.0, 1.0, 0.25), false, 2.0)

	# Staedte: farbiges Viereck pro Fraktion. Neutraler Rand dunkel,
	# eigene Stadt bekommt dicken goldenen Rand. Wache-Staerke in der
	# Mitte, farbig nach Kampf-Prognose wie bei Monstern.
	for city in _cities:
		var cp: Vector2i = city["pos"]
		var fid: int = int(city["faction"])
		var owner: int = int(city["owner"])
		var cpos := origin + Vector2(cp.x * _tile_size, cp.y * _tile_size)
		var inset: float = _tile_size * 0.18
		var crect := Rect2(
			cpos + Vector2(inset, inset),
			Vector2(_tile_size - 1.0 - 2.0 * inset, _tile_size - 1.0 - 2.0 * inset)
		)
		var fc: Color = FACTION_COLORS[fid] if fid >= 0 and fid < FACTION_COLORS.size() else Color.WHITE
		_map_area.draw_rect(crect, fc, true)
		if owner == OWNER_HERO:
			_map_area.draw_rect(crect, Color(1.0, 0.85, 0.2), false, 4.0)
		elif owner == OWNER_ENEMY:
			_map_area.draw_rect(crect, Color(0.85, 0.15, 0.15), false, 4.0)
		else:
			_map_area.draw_rect(crect, Color(0.1, 0.1, 0.12), false, 2.0)
		var garrison: int = int(city.get("garrison", 0))
		if owner != OWNER_HERO and garrison > 0:
			var cdist: int = abs(cp.x - _hero.position.x) + abs(cp.y - _hero.position.y)
			var gtxt: String
			var gcol: Color
			if cdist <= MONSTER_VIEW_RANGE:
				gtxt = str(garrison)
				if eff < garrison:
					gcol = Color(1.0, 0.35, 0.35)
				elif garrison - cbonus <= 0:
					gcol = Color(0.45, 1.0, 0.45)
				else:
					gcol = Color(1.0, 0.92, 0.35)
			else:
				gtxt = "?"
				gcol = Color(0.75, 0.75, 0.75)
			var gsize: int = int(_tile_size * 0.45)
			var gs := mfont.get_string_size(gtxt, HORIZONTAL_ALIGNMENT_CENTER, -1, gsize)
			var gcenter := cpos + Vector2(_tile_size * 0.5, _tile_size * 0.5)
			var gp := gcenter + Vector2(-gs.x * 0.5, gs.y * 0.3)
			# Dunkler Schatten fuer Lesbarkeit auf bunten Fraktions-Farben.
			_map_area.draw_string(mfont, gp + Vector2(2, 2), gtxt, HORIZONTAL_ALIGNMENT_CENTER, -1, gsize, Color(0, 0, 0, 0.8))
			_map_area.draw_string(mfont, gp, gtxt, HORIZONTAL_ALIGNMENT_CENTER, -1, gsize, gcol)

	# Monster: grauer Kreis mit Staerke-Zahl. Zahl UND Ring sind farbig
	# nach Kampf-Prognose:
	#   gruen = kein Verlust (Kampfkraft-Bonus deckt Schaden)
	#   gelb  = Sieg mit Verlusten
	#   rot   = Niederlage (Kampfkraft < Monster-Staerke)
	# Ausserhalb MONSTER_VIEW_RANGE erscheint "?" mit grauem Ring.
	var mfsize: int = int(_tile_size * 0.55)
	for m in _monsters:
		var mp: Vector2i = m["pos"]
		var mstr: int = int(m["strength"])
		var mpx := origin + Vector2(mp.x * _tile_size + _tile_size * 0.5, mp.y * _tile_size + _tile_size * 0.5)
		var mrad := _tile_size * 0.36
		var dist: int = abs(mp.x - _hero.position.x) + abs(mp.y - _hero.position.y)
		var txt: String
		var tcol: Color
		if dist <= MONSTER_VIEW_RANGE:
			txt = str(mstr)
			if eff < mstr:
				tcol = Color(1.0, 0.35, 0.35)       # rot: kannst nicht schlagen
			elif mstr - cbonus <= 0:
				tcol = Color(0.45, 1.0, 0.45)       # gruen: ohne Verluste
			else:
				tcol = Color(1.0, 0.92, 0.35)       # gelb: Sieg mit Verlusten
		else:
			txt = "?"
			tcol = Color(0.75, 0.75, 0.75)
		_map_area.draw_circle(mpx, mrad, Color(0.20, 0.20, 0.22))
		_map_area.draw_arc(mpx, mrad, 0.0, TAU, 20, tcol, 4.0)
		var ts := mfont.get_string_size(txt, HORIZONTAL_ALIGNMENT_CENTER, -1, mfsize)
		var tp := mpx + Vector2(-ts.x * 0.5, ts.y * 0.35)
		_map_area.draw_string(mfont, tp, txt, HORIZONTAL_ALIGNMENT_CENTER, -1, mfsize, tcol)

	# Karten-Objekte: Goldmine (gold gefuelltes Quadrat) und Schatzkiste
	# (oranges Quadrat). Besitz wird ueber Rand-Farbe markiert: neutral
	# dunkel, HERO goldener Rand, ENEMY roter Rand. Wache-Zahl in der
	# Mitte mit Kampf-Prognose-Farbe (nur sichtbar in MONSTER_VIEW_RANGE).
	for obj in _objects:
		var op: Vector2i = obj["pos"]
		var okind: int = int(obj["kind"])
		var oowner: int = int(obj.get("owner", OWNER_NEUTRAL))
		var opos := origin + Vector2(op.x * _tile_size, op.y * _tile_size)
		var oinset: float = _tile_size * 0.28
		var orect := Rect2(
			opos + Vector2(oinset, oinset),
			Vector2(_tile_size - 1.0 - 2.0 * oinset, _tile_size - 1.0 - 2.0 * oinset)
		)
		var ofill: Color = Color(0.95, 0.80, 0.20) if okind == OBJECT_MINE else Color(0.85, 0.50, 0.20)
		_map_area.draw_rect(orect, ofill, true)
		if oowner == OWNER_HERO:
			_map_area.draw_rect(orect, Color(1.0, 0.85, 0.2), false, 4.0)
		elif oowner == OWNER_ENEMY:
			_map_area.draw_rect(orect, Color(0.85, 0.15, 0.15), false, 4.0)
		else:
			_map_area.draw_rect(orect, Color(0.1, 0.1, 0.12), false, 2.0)
		var ogd: int = int(obj.get("guard", 0))
		if ogd > 0:
			var odist: int = abs(op.x - _hero.position.x) + abs(op.y - _hero.position.y)
			var otxt: String
			var ocol: Color
			if odist <= MONSTER_VIEW_RANGE:
				otxt = str(ogd)
				if eff < ogd:
					ocol = Color(1.0, 0.35, 0.35)
				elif ogd - cbonus <= 0:
					ocol = Color(0.45, 1.0, 0.45)
				else:
					ocol = Color(1.0, 0.92, 0.35)
			else:
				otxt = "?"
				ocol = Color(0.75, 0.75, 0.75)
			var osize: int = int(_tile_size * 0.4)
			var oss := mfont.get_string_size(otxt, HORIZONTAL_ALIGNMENT_CENTER, -1, osize)
			var ocenter := opos + Vector2(_tile_size * 0.5, _tile_size * 0.5)
			var op2 := ocenter + Vector2(-oss.x * 0.5, oss.y * 0.3)
			_map_area.draw_string(mfont, op2 + Vector2(2, 2), otxt, HORIZONTAL_ALIGNMENT_CENTER, -1, osize, Color(0, 0, 0, 0.8))
			_map_area.draw_string(mfont, op2, otxt, HORIZONTAL_ALIGNMENT_CENTER, -1, osize, ocol)

	var hero_px := origin + Vector2(_hero.position.x * _tile_size, _hero.position.y * _tile_size)
	var center := hero_px + Vector2(_tile_size * 0.5, _tile_size * 0.5)
	var radius := _tile_size * 0.35
	_map_area.draw_circle(center, radius, Color(1.0, 0.85, 0.2))
	_map_area.draw_arc(center, radius, 0.0, TAU, 24, Color(0.2, 0.15, 0.05), 2.0)

	# Gegner-Held: roter Kreis mit dunklem Ring. Gleiche Groesse wie
	# Spieler-Held, damit klar ist, dass es ein gleichwertiger Akteur ist.
	# Darueber die Armee-Zahl mit Kampf-Prognose-Farbe (rot/gelb/gruen)
	# - so kann man entscheiden, ob man angreifen will.
	if _enemy != null:
		var ex := _enemy.position
		var epx := origin + Vector2(ex.x * _tile_size, ex.y * _tile_size)
		var ecenter := epx + Vector2(_tile_size * 0.5, _tile_size * 0.5)
		_map_area.draw_circle(ecenter, radius, Color(0.85, 0.15, 0.15))
		_map_area.draw_arc(ecenter, radius, 0.0, TAU, 24, Color(0.15, 0.02, 0.02), 2.0)
		var earmy: int = int(_enemy.army)
		var etxt: String = str(earmy)
		var ecol: Color
		if eff < earmy:
			ecol = Color(1.0, 0.35, 0.35)
		elif earmy - cbonus <= 0:
			ecol = Color(0.45, 1.0, 0.45)
		else:
			ecol = Color(1.0, 0.92, 0.35)
		var esize: int = int(_tile_size * 0.5)
		var es := mfont.get_string_size(etxt, HORIZONTAL_ALIGNMENT_CENTER, -1, esize)
		var epos := ecenter + Vector2(-es.x * 0.5, es.y * 0.35)
		_map_area.draw_string(mfont, epos + Vector2(2, 2), etxt, HORIZONTAL_ALIGNMENT_CENTER, -1, esize, Color(0, 0, 0, 0.8))
		_map_area.draw_string(mfont, epos, etxt, HORIZONTAL_ALIGNMENT_CENTER, -1, esize, ecol)


func _terrain_color(t: int) -> Color:
	match t:
		MapGen.TILE_GRASS:    return Color(0.30, 0.55, 0.25)
		MapGen.TILE_FOREST:   return Color(0.15, 0.35, 0.18)
		MapGen.TILE_WATER:    return Color(0.18, 0.35, 0.65)
		MapGen.TILE_MOUNTAIN: return Color(0.45, 0.42, 0.40)
		MapGen.TILE_SAND:     return Color(0.85, 0.78, 0.48)
	return Color(0.5, 0.5, 0.5)


func _terrain_name(t: int) -> String:
	match t:
		MapGen.TILE_GRASS:    return "Gras"
		MapGen.TILE_FOREST:   return "Wald"
		MapGen.TILE_WATER:    return "Wasser"
		MapGen.TILE_MOUNTAIN: return "Gebirge"
		MapGen.TILE_SAND:     return "Sand"
	return "Unbekannt"


func _map_origin() -> Vector2:
	var used := Vector2(MAP_WIDTH * _tile_size, MAP_HEIGHT * _tile_size)
	var slack := _map_area.size - used
	return Vector2(slack.x * 0.5, slack.y * 0.5)


func _on_map_input(event: InputEvent) -> void:
	var pos := Vector2.ZERO
	var pressed := false
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index != MOUSE_BUTTON_LEFT:
			return
		pressed = mb.pressed
		pos = mb.position
	elif event is InputEventScreenTouch:
		var st := event as InputEventScreenTouch
		pressed = st.pressed
		pos = st.position
	else:
		return
	if not pressed:
		return
	var origin := _map_origin()
	var local := pos - origin
	if _tile_size <= 0.0:
		_set_status("Tap ignoriert: tile_size=0")
		return
	var tx := int(local.x / _tile_size)
	var ty := int(local.y / _tile_size)
	if tx < 0 or tx >= MAP_WIDTH or ty < 0 or ty >= MAP_HEIGHT:
		_set_status("Tap ausserhalb (%d,%d)" % [tx, ty])
		return
	var target := Vector2i(tx, ty)
	var target_city_idx: int = _city_at(target)
	if target == _hero.position:
		if target_city_idx >= 0 and int(_cities[target_city_idx]["owner"]) == OWNER_HERO:
			_show_city(target_city_idx)
		else:
			_set_status("Tap auf Held (%d,%d)" % [tx, ty])
		return
	if not _costs.has(target):
		if target_city_idx >= 0:
			var fid0: int = int(_cities[target_city_idx]["faction"])
			_set_status("Stadt %s (%d,%d)" % [FACTION_NAMES[fid0], tx, ty])
		else:
			var tiles: Array = _map["tiles"]
			var tt: int = int(tiles[ty * MAP_WIDTH + tx])
			_set_status("Tap %s (%d,%d)" % [_terrain_name(tt), tx, ty])
		return
	var cost: int = int(_costs[target])
	if cost > _hero.mp:
		_set_status("Tap zu teuer: %d > %d MP" % [cost, _hero.mp])
		return

	# Monster auf Zielfeld: vor Bewegung auto-resolve. Armee >= Staerke
	# gewinnt (verliert aber Einheiten), sonst Angriff verweigert und
	# weder MP noch Armee sinken - Spieler kann ausweichen.
	var mon_idx: int = _monster_at(target)
	if mon_idx >= 0:
		var mstr: int = int(_monsters[mon_idx]["strength"])
		# Kampfkraft = Armee + Level-Bonus + Wachturm-Bonus.
		# Bonus reduziert auch Verluste.
		var combat_bonus: int = _combat_bonus()
		var eff_strength: int = _hero.army + combat_bonus
		if eff_strength < mstr:
			var msg_fail: String = "NIEDERLAGE: Kampfkraft %d < Monster %d" % [eff_strength, mstr]
			_set_status(msg_fail)
			_set_combat(msg_fail)
			return
		var army_loss: int = max(0, mstr - combat_bonus)
		_hero.army -= army_loss
		_hero.gold += MONSTER_VICTORY_GOLD
		var xp_gain: int = mstr * XP_PER_STRENGTH
		_hero.xp += xp_gain
		var leveled: bool = _check_level_up()
		_monsters.remove_at(mon_idx)
		_hero.mp -= cost
		_hero.position = target
		_recompute_costs()
		_map_area.queue_redraw()
		_update_labels()
		var msg_win: String
		if leveled:
			msg_win = "SIEG! -%d A  +%d G  +%d XP  -->  LEVEL %d!" % [army_loss, MONSTER_VICTORY_GOLD, xp_gain, _hero.level]
		else:
			msg_win = "SIEG! -%d A  +%d G  +%d XP" % [army_loss, MONSTER_VICTORY_GOLD, xp_gain]
		_set_status(msg_win)
		_set_combat(msg_win)
		return

	# Gegner-Held auf Zielfeld: direkter Kampf, bevor wir eine evtl. dort
	# stehende Stadt beruehren. Kampfkraft = Armee + Level/Wachturm-Bonus,
	# Gegner hat nur seine Armee. Verlust = max(0, Gegner-Armee - Bonus).
	# Sieg toetet den Gegner-Helden (raus von der Karte), Oekonomie laeuft
	# weiter - seine Staedte werden nur nicht mehr verteidigt.
	if _enemy != null and target == _enemy.position:
		var cbonus_h: int = _combat_bonus()
		var eff_h: int = _hero.army + cbonus_h
		var eff_e: int = _enemy.army
		if eff_h < eff_e:
			var msg_eh_fail: String = "NIEDERLAGE: Gegner-Armee %d > Kampfkraft %d" % [eff_e, eff_h]
			_set_status(msg_eh_fail)
			_set_combat(msg_eh_fail)
			return
		var army_loss_h: int = max(0, eff_e - cbonus_h)
		_hero.army -= army_loss_h
		_hero.gold += ENEMY_DEFEAT_GOLD
		_hero.xp += ENEMY_DEFEAT_XP
		var leveled_h: bool = _check_level_up()
		_enemy = null
		var msg_h_win: String
		if leveled_h:
			msg_h_win = "Gegner besiegt: -%d A +%d G +%d XP -> LEVEL %d!" % [army_loss_h, ENEMY_DEFEAT_GOLD, ENEMY_DEFEAT_XP, _hero.level]
		else:
			msg_h_win = "Gegner besiegt: -%d A +%d G +%d XP" % [army_loss_h, ENEMY_DEFEAT_GOLD, ENEMY_DEFEAT_XP]
		_set_combat(msg_h_win)

	# Karten-Objekt auf Zielfeld: Wache-Kampf falls Wache > 0, danach
	# Einnahme (Mine) bzw. Einsammeln (Schatz). Eigene Mine wird einfach
	# betreten, ohne Kampf. Niederlage blockiert Bewegung.
	var obj_idx: int = _object_at(target)
	if obj_idx >= 0:
		var obj: Dictionary = _objects[obj_idx]
		var okind: int = int(obj["kind"])
		var is_own_mine: bool = (okind == OBJECT_MINE and int(obj.get("owner", OWNER_NEUTRAL)) == OWNER_HERO)
		if not is_own_mine:
			var ogd: int = int(obj.get("guard", 0))
			if ogd > 0:
				var cb_o: int = _combat_bonus()
				var eff_o: int = _hero.army + cb_o
				if eff_o < ogd:
					var msg_o_fail: String = "NIEDERLAGE: Wache %d > Kampfkraft %d" % [ogd, eff_o]
					_set_status(msg_o_fail)
					_set_combat(msg_o_fail)
					return
				var loss_o: int = max(0, ogd - cb_o)
				_hero.army -= loss_o
				var xp_o: int = ogd * XP_PER_STRENGTH
				_hero.xp += xp_o
				var lvl_o: bool = _check_level_up()
				obj["guard"] = 0
				var msg_og: String
				if lvl_o:
					msg_og = "Wache besiegt: -%d A +%d XP -> LEVEL %d!" % [loss_o, xp_o, _hero.level]
				else:
					msg_og = "Wache besiegt: -%d A +%d XP" % [loss_o, xp_o]
				_set_combat(msg_og)
			if okind == OBJECT_MINE:
				obj["owner"] = OWNER_HERO
			elif okind == OBJECT_TREASURE:
				var reward: int = int(obj["gold"])
				_hero.gold += reward
				_objects.remove_at(obj_idx)
				_set_combat("Schatz gefunden: +%d G" % reward)

	# Stadt-Wache-Kampf: wenn Zielfeld eine neutrale Stadt mit Garrison > 0
	# ist, vor Einnahme der Wache-Kampf. Niederlage blockiert Bewegung,
	# damit man nicht versehentlich in die eigene Vernichtung laeuft.
	if target_city_idx >= 0 and int(_cities[target_city_idx]["owner"]) != OWNER_HERO:
		var tc: Dictionary = _cities[target_city_idx]
		var garrison: int = int(tc.get("garrison", 0))
		if garrison > 0:
			var cbonus_c: int = _combat_bonus()
			var eff_c: int = _hero.army + cbonus_c
			if eff_c < garrison:
				var msg_fail_c: String = "NIEDERLAGE: Stadt-Wache %d > Kampfkraft %d" % [garrison, eff_c]
				_set_status(msg_fail_c)
				_set_combat(msg_fail_c)
				return
			var army_loss_c: int = max(0, garrison - cbonus_c)
			_hero.army -= army_loss_c
			var xp_c: int = garrison * XP_PER_STRENGTH
			_hero.xp += xp_c
			var leveled_c: bool = _check_level_up()
			tc["garrison"] = 0
			var msg_c: String
			if leveled_c:
				msg_c = "Wache besiegt: -%d A +%d XP  -->  LEVEL %d!" % [army_loss_c, xp_c, _hero.level]
			else:
				msg_c = "Wache besiegt: -%d A +%d XP" % [army_loss_c, xp_c]
			_set_combat(msg_c)

	_hero.mp -= cost
	_hero.position = target
	var claimed := false
	if target_city_idx >= 0 and int(_cities[target_city_idx]["owner"]) != OWNER_HERO:
		_cities[target_city_idx]["owner"] = OWNER_HERO
		claimed = true
	_recompute_costs()
	_map_area.queue_redraw()
	_update_labels()
	if claimed:
		var fid1: int = int(_cities[target_city_idx]["faction"])
		_set_status("Stadt %s eingenommen (%d MP)" % [FACTION_NAMES[fid1], cost])
		_check_victory()
	elif target_city_idx >= 0:
		var fid2: int = int(_cities[target_city_idx]["faction"])
		_set_status("Stadt %s (%d MP)" % [FACTION_NAMES[fid2], cost])
	else:
		_set_status("Zug -> (%d,%d) fuer %d MP" % [tx, ty, cost])


func _city_at(p: Vector2i) -> int:
	# Liefert Index in _cities oder -1.
	for i in range(_cities.size()):
		if _cities[i]["pos"] == p:
			return i
	return -1


func _monster_at(p: Vector2i) -> int:
	for i in range(_monsters.size()):
		if (_monsters[i]["pos"] as Vector2i) == p:
			return i
	return -1


func _object_at(p: Vector2i) -> int:
	for i in range(_objects.size()):
		if (_objects[i]["pos"] as Vector2i) == p:
			return i
	return -1


func _check_victory() -> void:
	# Sieg-Bedingung: alle Staedte dem Helden gehoeren.
	if _cities.size() == 0:
		return
	for c in _cities:
		if int(c["owner"]) != OWNER_HERO:
			return
	_game_won = true
	_show_victory_panel()


func _show_victory_panel() -> void:
	if _victory_panel == null:
		return
	if _victory_title != null:
		_victory_title.text = "GEWONNEN!"
		_victory_title.add_theme_color_override("font_color", Color(1.0, 0.85, 0.25))
	var vb := _victory_panel.get_node_or_null("VB") as VBoxContainer
	if vb != null:
		var stats := vb.get_node_or_null("Stats") as Label
		if stats != null:
			stats.text = "Level " + str(_hero.level) + "   XP " + str(_hero.xp) + "\nGold " + str(_hero.gold) + "   Armee " + str(_hero.army)
	_victory_panel.visible = true


func _combat_bonus() -> int:
	# Kampfkraft-Bonus: Level-Bonus plus Wachturm-Bonus pro eigener Stadt.
	var b: int = LEVEL_COMBAT_BONUS * max(0, _hero.level - 1)
	for c in _cities:
		if int(c["owner"]) == OWNER_HERO and (c["buildings"] as Array).has("wachturm"):
			b += WACHTURM_COMBAT_BONUS
	return b


func _check_level_up() -> bool:
	# Schleife, falls sehr viele XP auf einmal (z.B. spaeter aus Quests).
	# Jeder Level-Up gibt sofort Armee und hebt max_mp um LEVEL_BONUS_MP
	# (wirksam beim naechsten Ende-Zug, wenn max_mp neu berechnet wird).
	var leveled := false
	while _hero.level < LEVEL_THRESHOLDS.size() and _hero.xp >= int(LEVEL_THRESHOLDS[_hero.level]):
		_hero.level += 1
		_hero.army += LEVEL_BONUS_ARMY
		leveled = true
	return leveled


func _build_city_panel() -> void:
	var panel := Panel.new()
	panel.visible = false
	panel.anchor_left = 0.5
	panel.anchor_top = 0.5
	panel.anchor_right = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -480
	panel.offset_top = -700
	panel.offset_right = 480
	panel.offset_bottom = 700
	add_child(panel)
	_city_panel = panel

	# Opaker Hintergrund - default Panel-Theme ist halbtransparent und
	# auf der Weltkarte unleserlich.
	var bg := ColorRect.new()
	bg.color = Color(0.10, 0.11, 0.14, 1.0)
	bg.anchor_right = 1.0
	bg.anchor_bottom = 1.0
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(bg)

	var vb := VBoxContainer.new()
	vb.anchor_right = 1.0
	vb.anchor_bottom = 1.0
	vb.offset_left = 40
	vb.offset_top = 40
	vb.offset_right = -40
	vb.offset_bottom = -40
	vb.add_theme_constant_override("separation", 28)
	panel.add_child(vb)

	_city_title = Label.new()
	_city_title.text = "Stadt"
	_city_title.add_theme_font_size_override("font_size", 48)
	vb.add_child(_city_title)

	_city_gold = Label.new()
	_city_gold.text = "Gold: 0"
	_city_gold.add_theme_font_size_override("font_size", 32)
	vb.add_child(_city_gold)

	_buildings_box = VBoxContainer.new()
	_buildings_box.add_theme_constant_override("separation", 16)
	vb.add_child(_buildings_box)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(spacer)

	var close_btn := Button.new()
	close_btn.text = "Schliessen"
	close_btn.custom_minimum_size = Vector2(0, 120)
	close_btn.add_theme_font_size_override("font_size", 32)
	close_btn.pressed.connect(_hide_city)
	vb.add_child(close_btn)


func _build_victory_panel() -> void:
	# Vollbild-Overlay. Wird sichtbar, sobald alle Staedte dem Helden
	# gehoeren. "Neue Karte" startet per _on_reroll einen neuen Seed.
	var panel := Panel.new()
	panel.visible = false
	panel.anchor_right = 1.0
	panel.anchor_bottom = 1.0
	add_child(panel)
	_victory_panel = panel

	var bg := ColorRect.new()
	bg.color = Color(0.06, 0.08, 0.05, 0.96)
	bg.anchor_right = 1.0
	bg.anchor_bottom = 1.0
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(bg)

	var vb := VBoxContainer.new()
	vb.name = "VB"
	vb.anchor_right = 1.0
	vb.anchor_bottom = 1.0
	vb.offset_left = 60
	vb.offset_top = 400
	vb.offset_right = -60
	vb.offset_bottom = -400
	vb.add_theme_constant_override("separation", 40)
	vb.alignment = BoxContainer.ALIGNMENT_CENTER
	panel.add_child(vb)

	var title := Label.new()
	title.text = "GEWONNEN!"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 96)
	title.add_theme_color_override("font_color", Color(1.0, 0.85, 0.25))
	vb.add_child(title)
	_victory_title = title

	var sub := Label.new()
	sub.text = "Alle Staedte erobert"
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sub.add_theme_font_size_override("font_size", 40)
	vb.add_child(sub)

	var stats := Label.new()
	stats.name = "Stats"
	stats.text = ""
	stats.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	stats.add_theme_font_size_override("font_size", 36)
	vb.add_child(stats)

	var new_btn := Button.new()
	new_btn.text = "Neue Karte"
	new_btn.custom_minimum_size = Vector2(0, 140)
	new_btn.add_theme_font_size_override("font_size", 40)
	new_btn.pressed.connect(_on_victory_new_map)
	vb.add_child(new_btn)

	var back_btn := Button.new()
	back_btn.text = "Zurueck zum Menue"
	back_btn.custom_minimum_size = Vector2(0, 140)
	back_btn.add_theme_font_size_override("font_size", 40)
	back_btn.pressed.connect(_on_back)
	vb.add_child(back_btn)


func _on_victory_new_map() -> void:
	_victory_panel.visible = false
	_game_won = false
	_start(_seed + 1)


func _show_city(city_idx: int) -> void:
	_selected_city = city_idx
	var city: Dictionary = _cities[city_idx]
	var fid: int = int(city["faction"])
	_city_title.text = "Stadt " + FACTION_NAMES[fid]
	_city_gold.text = "Gold: " + str(_hero.gold)
	for c in _buildings_box.get_children():
		c.queue_free()
	var built: Array = city["buildings"]
	for i in range(BUILDINGS.size()):
		var b: Dictionary = BUILDINGS[i]
		var bid: String = b["id"]
		var bname: String = b["name"]
		var cost: int = int(b["cost"])
		var effect: String = String(b["effect"]) if b.has("effect") else ""
		var requires: String = String(b["requires"]) if b.has("requires") else ""
		var btn := Button.new()
		btn.custom_minimum_size = Vector2(0, 140)
		btn.add_theme_font_size_override("font_size", 30)
		if built.has(bid):
			btn.text = bname + "  (Gebaut)\n" + effect
			btn.disabled = true
		elif requires != "" and not built.has(requires):
			# Voraussetzung fehlt: Hinweis statt Effekt-Text, Button aus.
			btn.text = bname + "  -  " + str(cost) + " G\nBenoetigt: " + requires.capitalize()
			btn.disabled = true
		else:
			btn.text = bname + "  -  " + str(cost) + " G\n" + effect
			if _hero.gold < cost:
				btn.disabled = true
			btn.pressed.connect(_buy_building.bind(city_idx, i))
		_buildings_box.add_child(btn)

	# Rekrutieren: nur wenn Kaserne gebaut. Gibt +1 zum Hero-Armee-Zaehler.
	if built.has("kaserne"):
		var rbtn := Button.new()
		rbtn.custom_minimum_size = Vector2(0, 120)
		rbtn.add_theme_font_size_override("font_size", 32)
		rbtn.text = "Rekrutieren  -  " + str(UNIT_COST) + " G  (+1 Armee)"
		if _hero.gold < UNIT_COST:
			rbtn.disabled = true
		rbtn.pressed.connect(_recruit_unit.bind(city_idx))
		_buildings_box.add_child(rbtn)

	_city_panel.visible = true


func _hide_city() -> void:
	_city_panel.visible = false
	_selected_city = -1


func _buy_building(city_idx: int, bld_idx: int) -> void:
	var b: Dictionary = BUILDINGS[bld_idx]
	var bid: String = b["id"]
	var cost: int = int(b["cost"])
	if _hero.gold < cost:
		return
	var city: Dictionary = _cities[city_idx]
	var built: Array = city["buildings"]
	if built.has(bid):
		return
	# Voraussetzung pruefen (z.B. Schmiede benoetigt Kaserne).
	if b.has("requires") and not built.has(String(b["requires"])):
		return
	built.append(bid)
	_hero.gold -= cost
	_update_labels()
	_set_status("Gebaut: " + str(b["name"]))
	_show_city(city_idx)


func _recruit_unit(city_idx: int) -> void:
	if _hero.gold < UNIT_COST:
		return
	var city: Dictionary = _cities[city_idx]
	var built: Array = city["buildings"]
	if not built.has("kaserne"):
		return
	_hero.gold -= UNIT_COST
	_hero.army += 1
	_update_labels()
	_set_status("Einheit rekrutiert (+1 Armee)")
	_show_city(city_idx)


func _building_by_id(bid: String) -> Dictionary:
	for b in BUILDINGS:
		if String(b["id"]) == bid:
			return b
	return {}


func _enemy_economy() -> void:
	# Gegner spielt nach den gleichen Regeln wie der Spieler: Einkommen pro
	# eigener Stadt (+Markt), Armee-Wachstum nur mit Schmiede, max_mp nur
	# mit Spaeher. Danach Ausgaben nach Prioritaet: Kaserne -> Schmiede ->
	# Markt -> Spaeher. Sobald keine Prioritaets-Gebaeude mehr affordable
	# sind und Kaserne steht, wird Ueberschuss in Rekruten gesteckt.
	# Wachturm/Kapelle bringen dem Gegner (noch) nichts, daher ignoriert.
	if _enemy == null:
		return
	var owned: int = 0
	var markt: int = 0
	var schmiede: int = 0
	var spaeher: int = 0
	for c in _cities:
		if int(c["owner"]) != OWNER_ENEMY:
			continue
		owned += 1
		var bl: Array = c["buildings"]
		if bl.has("markt"):
			markt += 1
		if bl.has("schmiede"):
			schmiede += 1
		if bl.has("spaeher"):
			spaeher += 1
	_enemy.max_mp = ENEMY_BASE_MP + MP_BONUS_SPAEHER * spaeher
	var e_mine_income: int = 0
	for obj in _objects:
		if int(obj["kind"]) == OBJECT_MINE and int(obj.get("owner", OWNER_NEUTRAL)) == OWNER_ENEMY:
			e_mine_income += int(obj["gold"])
	_enemy.gold += owned * CITY_INCOME + markt * INCOME_MARKT + e_mine_income
	_enemy.army += schmiede * SCHMIEDE_ARMY_PER_TURN
	var priority: Array = ["kaserne", "schmiede", "markt", "spaeher"]
	var guard: int = 0
	var spent: bool = true
	while spent and guard < 24:
		guard += 1
		spent = false
		for bid in priority:
			var bdef: Dictionary = _building_by_id(bid)
			if bdef.is_empty():
				continue
			var bcost: int = int(bdef["cost"])
			if _enemy.gold < bcost:
				continue
			var req: String = String(bdef["requires"]) if bdef.has("requires") else ""
			for c in _cities:
				if int(c["owner"]) != OWNER_ENEMY:
					continue
				var bl: Array = c["buildings"]
				if bl.has(bid):
					continue
				if req != "" and not bl.has(req):
					continue
				bl.append(bid)
				_enemy.gold -= bcost
				spent = true
				break
			if spent:
				break
		if spent:
			continue
		# Keine Prioritaets-Gebaeude mehr affordable: Ueberschuss in Rekruten
		# stecken, solange Kaserne vorhanden und Gold reicht.
		if _enemy.gold < UNIT_COST:
			continue
		var has_kaserne: bool = false
		for c in _cities:
			if int(c["owner"]) == OWNER_ENEMY and (c["buildings"] as Array).has("kaserne"):
				has_kaserne = true
				break
		if has_kaserne:
			_enemy.gold -= UNIT_COST
			_enemy.army += 1
			spent = true


func _run_enemy_turn() -> void:
	# Einfache Gegner-KI: waehlt die naechstgelegene Nicht-Gegner-Stadt
	# (neutral oder Spieler) per Dijkstra, laeuft mit Gradienten-Abstieg so
	# weit wie MP reichen. Am Ziel wird besetzt (ggf. mit Wache-Kampf, wenn
	# Spieler-Stadt sollte es keine haben, neutrale Staedte haben eine).
	# Monster werden ignoriert (monsters_block=false), damit der Gegner
	# nicht eingekesselt wird.
	if _enemy == null:
		return
	_enemy.end_turn()
	var ecosts: Dictionary = _dijkstra(_enemy.position, false)
	# Ziel-Auswahl: naechste Nicht-Gegner-Stadt, fremde/neutrale Goldmine
	# oder Schatzkiste. Schatzkisten sind One-Shot, aber interessantes
	# Goldziel. Minen gibt es dauerhaft, aber nur solange unbewacht einer
	# anderen Fraktion.
	var target_kind: String = ""
	var target_idx: int = -1
	var target_cost: int = -1
	var target_pos: Vector2i = _enemy.position
	for i in range(_cities.size()):
		if int(_cities[i]["owner"]) == OWNER_ENEMY:
			continue
		var cp: Vector2i = _cities[i]["pos"]
		if not ecosts.has(cp):
			continue
		var c: int = int(ecosts[cp])
		if target_cost < 0 or c < target_cost:
			target_kind = "city"
			target_idx = i
			target_cost = c
			target_pos = cp
	for i in range(_objects.size()):
		var obj: Dictionary = _objects[i]
		var okind: int = int(obj["kind"])
		if okind == OBJECT_MINE and int(obj.get("owner", OWNER_NEUTRAL)) == OWNER_ENEMY:
			continue
		var op: Vector2i = obj["pos"]
		if not ecosts.has(op):
			continue
		var c2: int = int(ecosts[op])
		if target_cost < 0 or c2 < target_cost:
			target_kind = "mine" if okind == OBJECT_MINE else "treasure"
			target_idx = i
			target_cost = c2
			target_pos = op
	if target_cost < 0:
		return
	# Zweite Dijkstra vom Ziel aus, um Schritt-fuer-Schritt den Gradienten
	# absteigen zu koennen. Einfacher als Pfad-Rekonstruktion.
	var tcosts: Dictionary = _dijkstra(target_pos, false)
	if not tcosts.has(_enemy.position):
		return
	var tiles: Array = _map["tiles"]
	var guard: int = 0
	var cap: int = MAP_WIDTH + MAP_HEIGHT + 10
	while _enemy.mp > 0 and _enemy.position != target_pos and guard < cap:
		guard += 1
		var cur_val: int = int(tcosts[_enemy.position])
		var best_next: Vector2i = _enemy.position
		var best_val: int = cur_val
		var best_step: int = -1
		var d_e := Vector2i(1, 0)
		var d_w := Vector2i(-1, 0)
		var d_s := Vector2i(0, 1)
		var d_n := Vector2i(0, -1)
		for di in range(4):
			var d: Vector2i = d_e
			if di == 1: d = d_w
			elif di == 2: d = d_s
			elif di == 3: d = d_n
			var np: Vector2i = _enemy.position + d
			if not tcosts.has(np):
				continue
			var v: int = int(tcosts[np])
			if v >= cur_val:
				continue
			if np.x < 0 or np.x >= MAP_WIDTH or np.y < 0 or np.y >= MAP_HEIGHT:
				continue
			var t: int = int(tiles[np.y * MAP_WIDTH + np.x])
			var step_cost: int = 1
			if t == 1:
				step_cost = 2
			if step_cost > _enemy.mp:
				continue
			if v < best_val:
				best_val = v
				best_next = np
				best_step = step_cost
		if best_step < 0:
			break
		# Spieler-Held auf dem naechsten Schritt: Hero-vs-Hero-Kampf
		# aufloesen. Gewinnt der Gegner (reine Armee vs. Kampfkraft mit
		# Bonus), ist das Spiel verloren. Gewinnt der Spieler, ist der
		# Gegner weg und die KI bricht den Zug ab.
		if best_next == _hero.position:
			var eff_hp: int = _hero.army + _combat_bonus()
			var eff_ep: int = _enemy.army
			if eff_ep > eff_hp:
				_set_combat("NIEDERLAGE: Gegner-Held hat dich besiegt")
				_game_lost = true
				_show_defeat_panel()
				return
			_set_combat("Gegner-Held hat dich angegriffen und verloren")
			_enemy = null
			return
		_enemy.position = best_next
		_enemy.mp -= best_step
	# Ziel erreicht? Einnehmen/Einsammeln je nach Ziel-Art. Gegner hat
	# keinen Kampfkraft-Bonus, nur seine Armee zaehlt. Wenn die Wache zu
	# stark ist, bleibt der Gegner einfach stehen und versucht es spaeter
	# nochmal (oder Spieler nimmt inzwischen).
	if _enemy.position == target_pos:
		if target_kind == "city":
			var tc: Dictionary = _cities[target_idx]
			var garrison: int = int(tc.get("garrison", 0))
			if garrison > 0:
				if _enemy.army < garrison:
					return
				_enemy.army -= garrison
			tc["owner"] = OWNER_ENEMY
			tc["garrison"] = 0
		elif target_kind == "mine":
			var obj: Dictionary = _objects[target_idx]
			var g: int = int(obj.get("guard", 0))
			if g > 0:
				if _enemy.army < g:
					return
				_enemy.army -= g
				obj["guard"] = 0
			obj["owner"] = OWNER_ENEMY
		elif target_kind == "treasure":
			var obj2: Dictionary = _objects[target_idx]
			var g2: int = int(obj2.get("guard", 0))
			if g2 > 0:
				if _enemy.army < g2:
					return
				_enemy.army -= g2
			_enemy.gold += int(obj2["gold"])
			_objects.remove_at(target_idx)


func _check_defeat() -> void:
	# Niederlage: alle Staedte dem Gegner. Spiegelbild zu _check_victory.
	if _cities.size() == 0 or _enemy == null:
		return
	for c in _cities:
		if int(c["owner"]) != OWNER_ENEMY:
			return
	_game_lost = true
	_show_defeat_panel()


func _show_defeat_panel() -> void:
	if _victory_panel == null:
		return
	if _victory_title != null:
		_victory_title.text = "NIEDERLAGE"
		_victory_title.add_theme_color_override("font_color", Color(1.0, 0.4, 0.35))
	var vb := _victory_panel.get_node_or_null("VB") as VBoxContainer
	if vb != null:
		var stats := vb.get_node_or_null("Stats") as Label
		if stats != null:
			stats.text = "Level " + str(_hero.level) + "   XP " + str(_hero.xp) + "\nGold " + str(_hero.gold) + "   Armee " + str(_hero.army)
	_victory_panel.visible = true


func _on_end_turn() -> void:
	# Gebaeude-Effekte pro eigener Stadt:
	#   Spaeher  -> max_mp hoch
	#   Markt    -> Gold-Einkommen hoch
	#   Schmiede -> pro Zug +1 Armee
	#   Wachturm -> +1 Kampfkraft (via _combat_bonus() dauerhaft)
	#   Kapelle  -> +10 XP pro Zug, kann Level-Up ausloesen
	# Level-Up-Bonus: pro Level (ueber 1) zusaetzlich +1 max_mp.
	var owned := 0
	var spaeher_count := 0
	var markt_count := 0
	var schmiede_count := 0
	var kapelle_count := 0
	for city in _cities:
		if int(city["owner"]) == OWNER_HERO:
			owned += 1
			var bl: Array = city["buildings"]
			if bl.has("spaeher"):
				spaeher_count += 1
			if bl.has("markt"):
				markt_count += 1
			if bl.has("schmiede"):
				schmiede_count += 1
			if bl.has("kapelle"):
				kapelle_count += 1
	var level_bonus_mp: int = LEVEL_BONUS_MP * max(0, _hero.level - 1)
	_hero.max_mp = BASE_MAX_MP + MP_BONUS_SPAEHER * spaeher_count + level_bonus_mp
	_hero.end_turn()
	# Goldminen im Besitz: +MINE_GOLD_PER_TURN pro Mine (bereits als
	# obj["gold"] hinterlegt, damit spaeter Minen unterschiedlichen
	# Ertrag haben koennen, ohne dass sich die Rechnung aendert).
	var mine_income: int = 0
	for obj in _objects:
		if int(obj["kind"]) == OBJECT_MINE and int(obj.get("owner", OWNER_NEUTRAL)) == OWNER_HERO:
			mine_income += int(obj["gold"])
	var income: int = owned * CITY_INCOME + markt_count * INCOME_MARKT + mine_income
	_hero.gold += income
	var army_gain: int = schmiede_count * SCHMIEDE_ARMY_PER_TURN
	_hero.army += army_gain
	var xp_gain: int = kapelle_count * KAPELLE_XP_PER_TURN
	if xp_gain > 0:
		_hero.xp += xp_gain
		if _check_level_up():
			_set_combat("Level-Up durch Kapelle! -> LEVEL %d" % _hero.level)
	# Gegner-Zug: erst Oekonomie (Einkommen, Gebaeude, Rekruten), dann
	# Bewegung. Reihenfolge entspricht dem Spieler-Flow - zuerst kommt das
	# Einkommen aus den eigenen Staedten, dann wird ausgegeben, dann
	# bewegt sich der Held mit moeglicherweise groesserer Armee.
	_enemy_economy()
	_run_enemy_turn()
	_recompute_costs()
	_map_area.queue_redraw()
	_update_labels()
	_set_status("Zug beendet: +%d G, +%d A, +%d XP (%d Staedte)" % [income, army_gain, xp_gain, owned])
	_check_defeat()


func _on_reroll() -> void:
	_start(_seed + 1)


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/Main.tscn")
