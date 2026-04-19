extends Control

# Weltkarten-Screen. Rendert eine deterministische Zufallskarte per
# _draw() und erlaubt den Helden per Tap zu bewegen. Dijkstra berechnet
# die Kosten aller erreichbaren Felder; unerreichbare werden abgedunkelt.

const MAP_WIDTH := 15
const MAP_HEIGHT := 22

const CITY_COUNT := 4
const CITY_MIN_DIST := 6
const CITY_INCOME := 500
const OWNER_NEUTRAL := -1
const OWNER_HERO := 0

# Fraktionen. Bewusst generische Namen (nicht HoMM3-IP), passt zur
# Plan-Phase 1 ("Waldvolk"/"Menschen"/"Totenreich"/"Orks").
const FACTION_NAMES := ["Waldvolk", "Menschen", "Totenreich", "Orks"]
const FACTION_COLORS := [
	Color(0.45, 0.85, 0.45),   # Waldvolk - gruen
	Color(0.95, 0.85, 0.35),   # Menschen - gold
	Color(0.70, 0.45, 0.90),   # Totenreich - violett
	Color(0.95, 0.35, 0.30),   # Orks - rot
]

# Gebaeude: id/Name/Kosten. Pro Stadt als Liste von ids in city["buildings"].
const BUILDINGS := [
	{"id": "kaserne", "name": "Kaserne", "cost": 500},
	{"id": "spaeher", "name": "Spaeher", "cost": 300},
	{"id": "markt", "name": "Markt", "cost": 800},
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
	_build_city_panel()

	(get_node(end_turn_button_path) as Button).pressed.connect(_on_end_turn)
	(get_node(reroll_button_path) as Button).pressed.connect(_on_reroll)
	(get_node(back_button_path) as Button).pressed.connect(_on_back)
	_set_status("STEP 2: Buttons verdrahtet")

	_start(_seed)


func _start(seed_value: int) -> void:
	_set_status("STEP 3: generiere seed=%d" % seed_value)
	_seed = seed_value
	var rng := DeterministicRng.new(seed_value)
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
	_hero = Hero.new(spawn, 12)
	_set_status("STEP 5: Hero erstellt")

	# Staedte platzieren: deterministisch, nur Gras-Felder, Mindestabstand
	# zu Held und untereinander. Bis zu 400 Versuche, danach wird
	# aufgegeben und einfach weniger Staedte platziert.
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
		var dx0: int = abs(candidate.x - spawn.x)
		var dy0: int = abs(candidate.y - spawn.y)
		if dx0 + dy0 < CITY_MIN_DIST:
			continue
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
		})

	_recompute_costs()
	_on_map_resized()
	_update_labels()
	_set_status("Seed %d  Reach %d  Tile %.1f" % [_seed, _costs.size(), _tile_size])


func _recompute_costs() -> void:
	# Dijkstra inline: static-Calls auf class_name Pathfinder liefern
	# im Android-Export leere Dicts zurueck (gleiches Problem wie bei
	# MapGen). Also hier direkt gerechnet.
	var tiles: Array = _map["tiles"]
	var start: Vector2i = _hero.position
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
	_costs = costs


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
		ml.text = "MP " + str(mp) + "/" + str(mmax) + "  G " + str(gold)


func _draw_map() -> void:
	var tiles: Array = _map["tiles"]
	var origin := _map_origin()
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
	# eigene Stadt bekommt dicken goldenen Rand.
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
		else:
			_map_area.draw_rect(crect, Color(0.1, 0.1, 0.12), false, 2.0)

	var hero_px := origin + Vector2(_hero.position.x * _tile_size, _hero.position.y * _tile_size)
	var center := hero_px + Vector2(_tile_size * 0.5, _tile_size * 0.5)
	var radius := _tile_size * 0.35
	_map_area.draw_circle(center, radius, Color(1.0, 0.85, 0.2))
	_map_area.draw_arc(center, radius, 0.0, TAU, 24, Color(0.2, 0.15, 0.05), 2.0)


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


func _build_city_panel() -> void:
	var panel := Panel.new()
	panel.visible = false
	panel.anchor_left = 0.5
	panel.anchor_top = 0.5
	panel.anchor_right = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -440
	panel.offset_top = -600
	panel.offset_right = 440
	panel.offset_bottom = 600
	add_child(panel)
	_city_panel = panel

	var vb := VBoxContainer.new()
	vb.anchor_right = 1.0
	vb.anchor_bottom = 1.0
	vb.offset_left = 32
	vb.offset_top = 32
	vb.offset_right = -32
	vb.offset_bottom = -32
	vb.add_theme_constant_override("separation", 24)
	panel.add_child(vb)

	_city_title = Label.new()
	_city_title.text = "Stadt"
	vb.add_child(_city_title)

	_city_gold = Label.new()
	_city_gold.text = "Gold: 0"
	vb.add_child(_city_gold)

	_buildings_box = VBoxContainer.new()
	_buildings_box.add_theme_constant_override("separation", 12)
	vb.add_child(_buildings_box)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(spacer)

	var close_btn := Button.new()
	close_btn.text = "Schliessen"
	close_btn.custom_minimum_size = Vector2(0, 96)
	close_btn.pressed.connect(_hide_city)
	vb.add_child(close_btn)


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
		var btn := Button.new()
		btn.custom_minimum_size = Vector2(0, 96)
		if built.has(bid):
			btn.text = bname + "  (Gebaut)"
			btn.disabled = true
		else:
			btn.text = bname + "  -  " + str(cost) + " G"
			if _hero.gold < cost:
				btn.disabled = true
			btn.pressed.connect(_buy_building.bind(city_idx, i))
		_buildings_box.add_child(btn)
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
	built.append(bid)
	_hero.gold -= cost
	_update_labels()
	_set_status("Gebaut: " + str(b["name"]))
	_show_city(city_idx)


func _on_end_turn() -> void:
	_hero.end_turn()
	var owned := 0
	for city in _cities:
		if int(city["owner"]) == OWNER_HERO:
			owned += 1
	var income: int = owned * CITY_INCOME
	_hero.gold += income
	_recompute_costs()
	_map_area.queue_redraw()
	_update_labels()
	_set_status("Zug beendet: +%d Gold (%d Staedte)" % [income, owned])


func _on_reroll() -> void:
	_start(_seed + 1)


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/Main.tscn")
