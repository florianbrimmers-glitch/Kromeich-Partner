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

# Gebaeude-Effekte
const BASE_MAX_MP := 12
const MP_BONUS_SPAEHER := 2     # pro Spaeher in eigener Stadt
const INCOME_MARKT := 200       # zusaetzlich pro Markt in eigener Stadt
const UNIT_COST := 150          # pro Einheit, benoetigt Kaserne

# Monster
const MONSTER_COUNT := 6
const MONSTER_MIN_DIST := 4
const MONSTER_VICTORY_GOLD := 120

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

# Gebaeude: id/Name/Kosten/effect-Text. Effect-Text wird im Stadt-Menue
# direkt unter dem Namen angezeigt, damit der Spieler weiss, was er kauft.
# Pro Stadt als Liste von ids in city["buildings"].
const BUILDINGS := [
	{"id": "kaserne",  "name": "Kaserne",  "cost": 500, "effect": "Erlaubt Rekrutierung"},
	{"id": "spaeher",  "name": "Spaeher",  "cost": 300, "effect": "+2 max Schritte/Zug"},
	{"id": "markt",    "name": "Markt",    "cost": 800, "effect": "+200 Gold/Zug"},
	{"id": "schmiede", "name": "Schmiede", "cost": 700, "effect": "+1 Armee/Zug"},
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
# Dauerhafte Kampf-Anzeige zwischen TopBar und MapArea. Wird NIE von
# Tap-Status ueberschrieben - bleibt stehen, bis ein neuer Kampf passiert.
var _combat_label: Label
var _victory_panel: Panel
var _game_won: bool = false


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
	if _victory_panel != null:
		_victory_panel.visible = false
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

	_recompute_costs()
	_on_map_resized()
	_update_labels()
	_set_combat("Kampf: noch keiner")
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
		# Monster blockieren Durchlaufen: Feld ist erreichbar (bereits in
		# costs eingetragen), aber wir expandieren die Nachbarn nicht.
		# Start hat nie ein Monster drauf.
		if cur != start and _monster_at(cur) >= 0:
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

	# Monster: grauer Kreis mit Staerke-Zahl. Zahl UND Ring sind farbig
	# nach Kampf-Prognose:
	#   gruen = kein Verlust (Kampfkraft-Bonus deckt Schaden)
	#   gelb  = Sieg mit Verlusten
	#   rot   = Niederlage (Kampfkraft < Monster-Staerke)
	# Ausserhalb MONSTER_VIEW_RANGE erscheint "?" mit grauem Ring.
	var cbonus: int = _combat_bonus()
	var eff: int = _hero.army + cbonus
	var mfont: Font = ThemeDB.fallback_font
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
		var btn := Button.new()
		btn.custom_minimum_size = Vector2(0, 140)
		btn.add_theme_font_size_override("font_size", 30)
		if built.has(bid):
			btn.text = bname + "  (Gebaut)\n" + effect
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
	var income: int = owned * CITY_INCOME + markt_count * INCOME_MARKT
	_hero.gold += income
	var army_gain: int = schmiede_count * SCHMIEDE_ARMY_PER_TURN
	_hero.army += army_gain
	var xp_gain: int = kapelle_count * KAPELLE_XP_PER_TURN
	if xp_gain > 0:
		_hero.xp += xp_gain
		if _check_level_up():
			_set_combat("Level-Up durch Kapelle! -> LEVEL %d" % _hero.level)
	_recompute_costs()
	_map_area.queue_redraw()
	_update_labels()
	_set_status("Zug beendet: +%d G, +%d A, +%d XP (%d Staedte)" % [income, army_gain, xp_gain, owned])


func _on_reroll() -> void:
	_start(_seed + 1)


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/Main.tscn")
