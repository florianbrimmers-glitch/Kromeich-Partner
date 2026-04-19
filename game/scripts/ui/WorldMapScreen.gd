extends Control

# Weltkarten-Screen. Rendert eine deterministische Zufallskarte per
# _draw() und erlaubt den Helden per Tap zu bewegen. Dijkstra berechnet
# die Kosten aller erreichbaren Felder; unerreichbare werden abgedunkelt.

const MAP_WIDTH := 15
const MAP_HEIGHT := 22

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
	_set_status("STEP 3b: place_water")
	MapGen.place_water(tiles, MAP_WIDTH, MAP_HEIGHT, rng)
	_set_status("STEP 3c: place_mountains")
	MapGen.place_mountains(tiles, MAP_WIDTH, MAP_HEIGHT, rng)
	_set_status("STEP 3d: coat_with_sand")
	MapGen.coat_with_sand(tiles, MAP_WIDTH, MAP_HEIGHT)
	_set_status("STEP 3e: place_forests")
	MapGen.place_forests(tiles, MAP_WIDTH, MAP_HEIGHT, rng)
	_set_status("STEP 3f: find_spawn")
	var spawn := MapGen.find_spawn(tiles, MAP_WIDTH, MAP_HEIGHT)
	_map = {
		"width": MAP_WIDTH,
		"height": MAP_HEIGHT,
		"tiles": tiles,
		"hero_spawn": spawn,
	}
	_set_status("STEP 4: MapGen fertig, spawn %s" % str(spawn))
	_hero = Hero.new(spawn, 12)
	_set_status("STEP 5: Hero erstellt")
	_recompute_costs()
	_set_status("STEP 6: Costs berechnet (%d Felder)" % _costs.size())
	_on_map_resized()
	_update_labels()


func _recompute_costs() -> void:
	_costs = Pathfinder.compute_costs(_map, _hero.position)


func _on_map_resized() -> void:
	if _map.is_empty():
		return
	var size := _map_area.size
	var tw: float = size.x / float(MAP_WIDTH)
	var th: float = size.y / float(MAP_HEIGHT)
	_tile_size = min(tw, th)
	_map_area.queue_redraw()


func _update_labels() -> void:
	var sl := get_node_or_null(status_label_path) as Label
	if sl != null:
		sl.text = "Seed %d" % _seed
	var ml := get_node_or_null(mp_label_path) as Label
	if ml != null:
		ml.text = "MP %d/%d" % [_hero.mp, _hero.max_mp]


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
				col = col.darkened(0.45)
			_map_area.draw_rect(rect, col, true)

	# Held zeichnen
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


func _map_origin() -> Vector2:
	var used := Vector2(MAP_WIDTH * _tile_size, MAP_HEIGHT * _tile_size)
	var slack := _map_area.size - used
	return Vector2(slack.x * 0.5, slack.y * 0.5)


func _on_map_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton):
		return
	var mb := event as InputEventMouseButton
	if not mb.pressed or mb.button_index != MOUSE_BUTTON_LEFT:
		return
	var origin := _map_origin()
	var local := mb.position - origin
	if local.x < 0.0 or local.y < 0.0 or _tile_size <= 0.0:
		return
	var tx := int(local.x / _tile_size)
	var ty := int(local.y / _tile_size)
	if tx < 0 or tx >= MAP_WIDTH or ty < 0 or ty >= MAP_HEIGHT:
		return
	var target := Vector2i(tx, ty)
	if target == _hero.position:
		return
	if not _costs.has(target):
		return
	var cost: int = int(_costs[target])
	if cost > _hero.mp:
		return
	_hero.mp -= cost
	_hero.position = target
	_recompute_costs()
	_map_area.queue_redraw()
	_update_labels()


func _on_end_turn() -> void:
	_hero.end_turn()
	_recompute_costs()
	_map_area.queue_redraw()
	_update_labels()


func _on_reroll() -> void:
	_start(_seed + 1)


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/Main.tscn")
