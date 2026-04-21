extends Control

# Weltkarten-Screen. Rendert eine deterministische Zufallskarte per
# _draw() und erlaubt den Helden per Tap zu bewegen. Dijkstra berechnet
# die Kosten aller erreichbaren Felder; unerreichbare werden abgedunkelt.

const MAP_WIDTH := 18
const MAP_HEIGHT := 26

const CITY_COUNT := 8
const CITY_MIN_DIST := 7
const CITY_INCOME := 500
const OWNER_NEUTRAL := -1
const OWNER_HERO := 0
# Historischer Alias: OWNER_ENEMY == erste KI. Generisch wird eine KI
# ueber OWNER_AI_MIN..OWNER_AI_MAX adressiert. _is_ai_owner()/_ai_index
# kapseln die Abfrage, damit wir spaeter nicht Alle Vergleiche suchen.
const OWNER_ENEMY := 1
const OWNER_AI_MIN := 1
const OWNER_AI_MAX := 3

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

# Startgold: Spieler und Gegner beginnen mit diesem Betrag, damit der
# erste Zug nicht zwangslaeufig "Enter druecken und warten" ist - reicht
# genau fuer eine Kaserne (500 G).
const STARTING_GOLD := 500
const STARTING_UNIT := "sword"
const STARTING_UNIT_COUNT := 3

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

# Kriegsnebel: drei Stufen. HIDDEN = nie gesehen (schwarz), EXPLORED =
# schon einmal gesehen aber aktuell nicht in Sicht (gedimmt, Gelaende
# bleibt, bewegliche Einheiten nicht mehr), VISIBLE = aktuell in Sicht
# (volle Information). Sichtquellen sind Held, eigene Staedte und eigene
# Minen/Schatzfelder mit jeweils eigenem Radius (Manhattan). Der
# Ghost-Marker fuer gegnerische Helden verblasst ueber FOG_ROT_TURNS
# Zuege nach der letzten Sichtung ("Info rottet").
const FOG_HIDDEN := 0
const FOG_EXPLORED := 1
const FOG_VISIBLE := 2
const HERO_SIGHT := 6
const CITY_SIGHT := 4
const OBJECT_SIGHT := 2
const FOG_ROT_TURNS := 4

# Adaptive-KI-Parameter:
# AI_THREAT_RADIUS: Manhattan-Distanz eines feindlichen Helden zur
#   eigenen Stadt, unter der die KI defensiv umschaltet.
# AI_HUNT_SAFETY_PCT: prozentualer Armee-Vorsprung, den die KI haben
#   muss, bevor sie einen fremden Helden jagt (vermeidet Suizid-
#   Angriffe gegen sichtbar staerkere Gegner).
# AI_RAID_SAFETY_PCT: gleiche Logik fuer fixe Garnisonen/Objekt-Wachen.
const AI_THREAT_RADIUS := 5
const AI_HUNT_SAFETY_PCT := 10
const AI_RAID_SAFETY_PCT := 10

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
	{"id": "kaserne",  "name": "Kaserne",  "cost": 500, "effect": "Erlaubt Schwert"},
	{"id": "spaeher",  "name": "Spaeher",  "cost": 300, "effect": "+2 max Schritte/Zug"},
	{"id": "markt",    "name": "Markt",    "cost": 800, "effect": "+200 Gold/Zug"},
	{"id": "schmiede", "name": "Schmiede", "cost": 700, "effect": "+1 Armee/Zug, erlaubt Bogen", "requires": "kaserne"},
	{"id": "reiterei", "name": "Reiterei", "cost": 1000, "effect": "Erlaubt Reiter", "requires": "schmiede"},
	{"id": "wachturm", "name": "Wachturm", "cost": 400, "effect": "+1 Kampfkraft (dauerhaft)"},
	{"id": "kapelle",  "name": "Kapelle",  "cost": 500, "effect": "+10 XP/Zug"},
]

# Welche Einheit welches Gebaeude braucht. Kaserne ist Grundbedingung
# fuer alle, Bogen zusaetzlich Schmiede, Reiter zusaetzlich Reiterei.
const UNIT_BUILDING := {
	"sword": "kaserne",
	"bow":   "schmiede",
	"rider": "reiterei",
}

@export var status_label_path: NodePath    = ^"TopBar/StatusLabel"
@export var mp_label_path: NodePath        = ^"TopBar/MPLabel"
@export var end_turn_button_path: NodePath = ^"BottomBar/EndTurnBtn"
@export var reroll_button_path: NodePath   = ^"BottomBar/RerollBtn"
@export var back_button_path: NodePath     = ^"BottomBar/BackBtn"
@export var map_area_path: NodePath        = ^"MapArea"
@export var minimap_path: NodePath         = ^"Minimap"
@export var minimap_toggle_path: NodePath  = ^"TopBar/MinimapToggleBtn"

var _map: Dictionary
var _hero: Hero
var _seed: int = 42
var _costs: Dictionary = {}
var _tile_size: float = 64.0
var _map_area: Control
# Minimap: vollstaendig sichtbare Uebersichtskarte oben rechts. Zeichnet
# pro Kachel ein Farb-Pixel, das aktuelle Viewport-Rechteck und
# Helden-Positionen. Tap springt zum entsprechenden Feld.
var _minimap: Panel

# Scroll/Pan-State: die Karte ist potentiell groesser als _map_area.
# _view_offset ist die Pixel-Verschiebung des Karten-Origins relativ
# zu _map_area. Drag verschiebt den Offset, Tap (ohne Bewegung ueber
# DRAG_THRESHOLD) bewegt den Helden wie vorher.
const TILE_PX: float = 64.0
const DRAG_THRESHOLD: float = 12.0
var _view_offset: Vector2 = Vector2.ZERO
var _pan_active: bool = false
var _pan_start_pos: Vector2 = Vector2.ZERO
var _pan_start_offset: Vector2 = Vector2.ZERO
var _pan_moved: bool = false
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
# Gegner-KIs. Jede KI ist ein Dictionary mit:
#   "hero": Hero (null wenn im Kampf gefallen)
#   "owner_id": int (1..3) - wird in city/object["owner"] gespiegelt
#   "recruit_idx": int - Rotations-Index 0=sword,1=bow,2=rider
#   "fog": Array (MAP_WIDTH*MAP_HEIGHT) - eigene Sichtbarkeit
#   "player_last_seen_pos": Vector2i - wo diese KI den Spieler-Held
#       zuletzt gesehen hat (-1,-1 wenn nie)
#   "player_last_seen_turn": int
# Fuer Step 1 wird genau eine KI angelegt (owner_id = OWNER_ENEMY = 1),
# die Logik ist aber schon arrayfoermig - Schritt 3 aktiviert drei KIs.
var _enemies: Array = []
# Parallel zu _enemies: wo der SPIELER jede KI zuletzt gesichtet hat.
# {pos: Vector2i, turn: int}. pos.x < 0 = nie gesehen.
var _ai_seen_by_player: Array = []
# RNG bleibt nach _start() aktiv, damit Enemy-Turn deterministische
# Wuerfe fuer Garrison machen kann.
var _rng: DeterministicRng

# Kriegsnebel-Spielerseite. Je KI liegt ihr eigenes Fog-Array in
# _enemies[i]["fog"]. Werte aus FOG_HIDDEN/EXPLORED/VISIBLE.
# _turn_number zaehlt abgeschlossene Spielerzuege, damit der
# Ghost-Marker "Info rottet" linear verblassen kann.
var _fog_player: Array = []
var _turn_number: int = 0
# Snapshot der Spieler-Oekonomie-Werte dieser Runde, damit die Status-
# Zeile auch dann korrekt bleibt, wenn die KI-Phase durch ein
# Pflicht-Kampf-Overlay (KI greift Spieler an) suspendiert wird und
# erst nach Kampfabschluss weiterlaeuft.
var _turn_income: int = 0
var _turn_army_gain: int = 0
var _turn_xp_gain: int = 0
var _turn_owned: int = 0


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
	_minimap = get_node_or_null(minimap_path) as Panel
	if _minimap != null:
		_minimap.gui_input.connect(_on_minimap_input)
		_minimap.draw.connect(_draw_minimap)
	var mm_toggle := get_node_or_null(minimap_toggle_path) as Button
	if mm_toggle != null:
		mm_toggle.pressed.connect(_toggle_minimap)
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
	_enemies.clear()
	_ai_seen_by_player.clear()
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

	_set_status("STEP 3d2: place_swamps")
	# Sumpf: 2-3 Inland-Cluster plus zufaellige Umwandlung von Sandfeldern
	# zu Kuesten-Sumpf. Cluster laufen wie Wasser/Gebirge (BFS-Wachstum).
	var swamp_clusters: int = max(2, int(float(MAP_WIDTH * MAP_HEIGHT) / 120.0))
	for ci in range(swamp_clusters):
		var scx := rng.next_int(0, MAP_WIDTH - 1)
		var scy := rng.next_int(0, MAP_HEIGHT - 1)
		var s_target := rng.next_int(3, 8)
		var s_frontier: Array = [Vector2i(scx, scy)]
		var s_placed := 0
		var s_it := 0
		while s_placed < s_target and s_frontier.size() > 0 and s_it < 500:
			s_it += 1
			var sidx := rng.next_int(0, s_frontier.size() - 1)
			var scell: Vector2i = s_frontier[sidx]
			s_frontier.remove_at(sidx)
			if scell.x < 0 or scell.x >= MAP_WIDTH or scell.y < 0 or scell.y >= MAP_HEIGHT:
				continue
			var sti: int = scell.y * MAP_WIDTH + scell.x
			if int(tiles[sti]) != MapGen.TILE_GRASS:
				continue
			tiles[sti] = MapGen.TILE_SWAMP
			s_placed += 1
			s_frontier.append(Vector2i(scell.x + 1, scell.y))
			s_frontier.append(Vector2i(scell.x - 1, scell.y))
			s_frontier.append(Vector2i(scell.x, scell.y + 1))
			s_frontier.append(Vector2i(scell.x, scell.y - 1))
	for ti in range(tiles.size()):
		if int(tiles[ti]) == MapGen.TILE_SAND and rng.next_int(0, 99) < 22:
			tiles[ti] = MapGen.TILE_SWAMP

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
	_hero.gold = STARTING_GOLD
	_hero.add_units(STARTING_UNIT, STARTING_UNIT_COUNT)
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
			"faction": _cities.size() % FACTION_NAMES.size(),
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

	# Drei KIs: jede bekommt ihre eigene Start-Stadt. Pro KI wird die
	# Stadt gewaehlt, deren minimale Manhattan-Distanz zu allen bereits
	# vergebenen Start-Staedten (Spieler + schon gesetzte KIs) maximal
	# ist. So sitzen alle vier Fraktionen in moeglichst weit
	# auseinanderliegenden Ecken, der Rest bleibt neutral zum Erobern.
	if player_start_idx >= 0:
		var taken_idx: Array = [player_start_idx]
		var taken_pos: Array = [_cities[player_start_idx]["pos"]]
		var ai_slots: int = min(OWNER_AI_MAX - OWNER_AI_MIN + 1, _cities.size() - 1)
		for slot in range(ai_slots):
			var best_idx: int = -1
			var best_min_d: int = -1
			for i in range(_cities.size()):
				if taken_idx.has(i):
					continue
				var cp: Vector2i = _cities[i]["pos"]
				var min_d: int = -1
				for tp in taken_pos:
					var tpv: Vector2i = tp
					var d: int = abs(cp.x - tpv.x) + abs(cp.y - tpv.y)
					if min_d < 0 or d < min_d:
						min_d = d
				if min_d > best_min_d:
					best_min_d = min_d
					best_idx = i
			if best_idx < 0:
				break
			var owner_id: int = OWNER_AI_MIN + slot
			_cities[best_idx]["owner"] = owner_id
			_cities[best_idx]["garrison"] = 0
			var ai_hero := Hero.new(_cities[best_idx]["pos"], ENEMY_BASE_MP)
			ai_hero.gold = STARTING_GOLD
			ai_hero.add_units(STARTING_UNIT, STARTING_UNIT_COUNT)
			_enemies.append({
				"hero": ai_hero,
				"owner_id": owner_id,
				"recruit_idx": 0,
				"fog": [] as Array,
				"player_last_seen_pos": Vector2i(-1, -1),
				"player_last_seen_turn": -1,
				"rivals_seen": {} as Dictionary,
			})
			_ai_seen_by_player.append({"pos": Vector2i(-1, -1), "turn": -1})
			taken_idx.append(best_idx)
			taken_pos.append(_cities[best_idx]["pos"])

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

	_turn_number = 0
	_init_fog_arrays()
	_recompute_fog_player()
	for i in range(_enemies.size()):
		_recompute_fog_ai(i)

	_recompute_costs()
	_on_map_resized()
	_center_view_on(_hero.position)
	_update_labels()
	_set_combat("Kampf: noch keiner")
	_set_status("Seed %d  Reach %d  Tile %.1f" % [_seed, _costs.size(), _tile_size])


func _recompute_costs() -> void:
	_costs = _dijkstra(_hero.position, true)


func _init_fog_arrays() -> void:
	# Spieler-Fog + je ein Fog-Array pro KI auf HIDDEN setzen. Wird am
	# Start einer neuen Karte aufgerufen, danach nur noch per
	# _recompute_fog_player / _recompute_fog_ai gepflegt (setzt VISIBLE
	# zurueck auf EXPLORED und markiert neue Sichtfelder).
	var total: int = MAP_WIDTH * MAP_HEIGHT
	_fog_player.resize(total)
	for i in range(total):
		_fog_player[i] = FOG_HIDDEN
	for e in _enemies:
		var efog: Array = []
		efog.resize(total)
		for i in range(total):
			efog[i] = FOG_HIDDEN
		e["fog"] = efog


func _fog_mark(arr: Array, center: Vector2i, radius: int) -> void:
	# Manhattan-Scheibe um center auf VISIBLE. Randfelder (EXPLORED) bleiben
	# erst durch _recompute_fog erhalten, wenn diese Funktion vorher alles
	# VISIBLE -> EXPLORED demoted hat.
	for dy in range(-radius, radius + 1):
		var ay: int = center.y + dy
		if ay < 0 or ay >= MAP_HEIGHT:
			continue
		var remain: int = radius - abs(dy)
		for dx in range(-remain, remain + 1):
			var ax: int = center.x + dx
			if ax < 0 or ax >= MAP_WIDTH:
				continue
			arr[ay * MAP_WIDTH + ax] = FOG_VISIBLE


func _recompute_fog_player() -> void:
	# Wird nach Heldenbewegung und nach jedem KI-Zug aufgerufen. Setzt
	# erst VISIBLE zurueck auf EXPLORED, markiert dann alle aktuellen
	# Sichtquellen des Spielers (Held + eigene Staedte + eigene Minen/
	# Schatzfelder) und aktualisiert zum Schluss die Sichtungen der
	# KI-Helden (Ghost-Marker "Info rottet" im Draw).
	var arr: Array = _fog_player
	var total: int = MAP_WIDTH * MAP_HEIGHT
	for i in range(total):
		if int(arr[i]) == FOG_VISIBLE:
			arr[i] = FOG_EXPLORED
	if _hero != null:
		_fog_mark(arr, _hero.position, HERO_SIGHT)
	for city in _cities:
		if int(city["owner"]) == OWNER_HERO:
			_fog_mark(arr, Vector2i(city["pos"]), CITY_SIGHT)
	for obj in _objects:
		if int(obj.get("owner", OWNER_NEUTRAL)) == OWNER_HERO:
			_fog_mark(arr, Vector2i(obj["pos"]), OBJECT_SIGHT)
	for i in range(_enemies.size()):
		var eh: Hero = _enemies[i]["hero"] as Hero
		if eh == null:
			continue
		if _fog_get(arr, eh.position) == FOG_VISIBLE:
			_ai_seen_by_player[i]["pos"] = eh.position
			_ai_seen_by_player[i]["turn"] = _turn_number


func _recompute_fog_ai(idx: int) -> void:
	# Spiegel-Funktion zu _recompute_fog_player aus Sicht einer KI. Jede
	# KI pflegt ihr eigenes Fog-Array und ihre eigene Sichtung des
	# Spieler-Helden (relevant fuer Ziel-Auswahl "Hero jagen").
	if idx < 0 or idx >= _enemies.size():
		return
	var e: Dictionary = _enemies[idx]
	var arr: Array = e["fog"]
	var oid: int = int(e["owner_id"])
	var total: int = MAP_WIDTH * MAP_HEIGHT
	for j in range(total):
		if int(arr[j]) == FOG_VISIBLE:
			arr[j] = FOG_EXPLORED
	var eh: Hero = e["hero"] as Hero
	if eh != null:
		_fog_mark(arr, eh.position, HERO_SIGHT)
	for city in _cities:
		if int(city["owner"]) == oid:
			_fog_mark(arr, Vector2i(city["pos"]), CITY_SIGHT)
	for obj in _objects:
		if int(obj.get("owner", OWNER_NEUTRAL)) == oid:
			_fog_mark(arr, Vector2i(obj["pos"]), OBJECT_SIGHT)
	if _hero != null:
		if _fog_get(arr, _hero.position) == FOG_VISIBLE:
			e["player_last_seen_pos"] = _hero.position
			e["player_last_seen_turn"] = _turn_number
	# Rivalisierende KI-Helden: wenn aktuell im Sichtfeld, deren Position
	# und Runde merken. Target-Auswahl nutzt die Sichtungen genau wie
	# beim Spieler-Helden - damit greifen sich KIs im Free-for-All auch
	# untereinander an und bilden nicht automatisch eine 3v1-Front gegen
	# den Spieler.
	var rs: Dictionary = e.get("rivals_seen", {})
	for j in range(_enemies.size()):
		if j == idx:
			continue
		var rh: Hero = _enemies[j]["hero"] as Hero
		if rh == null:
			continue
		if _fog_get(arr, rh.position) == FOG_VISIBLE:
			var rid: int = int(_enemies[j]["owner_id"])
			rs[rid] = {"pos": rh.position, "turn": _turn_number}
	e["rivals_seen"] = rs


func _fog_get(arr: Array, p: Vector2i) -> int:
	if p.x < 0 or p.x >= MAP_WIDTH or p.y < 0 or p.y >= MAP_HEIGHT:
		return FOG_HIDDEN
	return int(arr[p.y * MAP_WIDTH + p.x])


func _is_ai_owner(owner: int) -> bool:
	return owner >= OWNER_AI_MIN and owner <= OWNER_AI_MAX


func _ai_index_for_owner(owner: int) -> int:
	for i in range(_enemies.size()):
		if int(_enemies[i]["owner_id"]) == owner:
			return i
	return -1


func _ai_index_at(pos: Vector2i) -> int:
	# Erste KI mit Held auf pos. Kollisionen koennen im Free-for-All
	# entstehen, wenn zwei KIs dasselbe Ziel nehmen - dann gewinnt die
	# mit niedrigerem Index (deterministisch).
	for i in range(_enemies.size()):
		var eh: Hero = _enemies[i]["hero"] as Hero
		if eh != null and eh.position == pos:
			return i
	return -1


func _ai_ring_color(owner_id: int) -> Color:
	# Ring-/Hero-Farbe pro KI-owner_id. Rot fuer die klassische "Gegner"-
	# Rolle (owner_id 1), violett und orange als Reserve fuer 2 und 3.
	match owner_id:
		1: return Color(0.85, 0.15, 0.15)
		2: return Color(0.70, 0.30, 0.85)
		3: return Color(0.95, 0.55, 0.15)
	return Color(0.85, 0.15, 0.15)


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
			# terrain_cost inline als Integer-Literale, weil Cross-File-
			# class_name-Aufrufe (MapGen.terrain_cost) im Android-Export
			# 0 liefern koennen - dann waere das ganze Grid unpassierbar
			# und Held wie KI stehen fest. Gleiches Muster wie Pathfinder.gd.
			# 0=Gras, 1=Wald, 2=Wasser, 3=Berg, 4=Sand, 5=Sumpf.
			var step: int = -1
			if t == 0 or t == 4:
				step = 1
			elif t == 1 or t == 5:
				step = 2
			if step <= 0:
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
	# Feste Kachelgroesse - Karte darf groesser als der Viewport sein und
	# muss dann gescrollt werden. Falls die Karte trotzdem reinpasst,
	# zentriert _clamp_view_offset sie im Viewport.
	_tile_size = TILE_PX
	_clamp_view_offset()
	_request_redraw()


func _clamp_view_offset() -> void:
	# _view_offset ist die Pixel-Verschiebung des Karten-Origins (oben
	# links, Feld (0,0)). Bei Karte groesser als Viewport muss er
	# zwischen (viewport - map) und 0 liegen. Bei kleinerer Karte
	# zentrieren wir fest.
	var area: Vector2 = _map_area.size
	var map_px: Vector2 = Vector2(MAP_WIDTH, MAP_HEIGHT) * _tile_size
	if map_px.x <= area.x:
		_view_offset.x = (area.x - map_px.x) * 0.5
	else:
		_view_offset.x = clamp(_view_offset.x, area.x - map_px.x, 0.0)
	if map_px.y <= area.y:
		_view_offset.y = (area.y - map_px.y) * 0.5
	else:
		_view_offset.y = clamp(_view_offset.y, area.y - map_px.y, 0.0)


func _center_view_on(tile: Vector2i) -> void:
	# Viewport so verschieben, dass die Mitte der Kachel im Zentrum des
	# MapArea liegt. Danach clamp, damit wir nicht ins Leere scrollen.
	var area: Vector2 = _map_area.size
	var tile_center: Vector2 = Vector2(tile.x, tile.y) * _tile_size + Vector2(_tile_size, _tile_size) * 0.5
	_view_offset = area * 0.5 - tile_center
	_clamp_view_offset()
	_request_redraw()


func _update_labels() -> void:
	var ml := get_node_or_null(mp_label_path) as Label
	if ml != null:
		var mp: int = int(_hero.mp)
		var mmax: int = int(_hero.max_mp)
		var gold: int = int(_hero.gold)
		var lvl: int = int(_hero.level)
		var xp: int = int(_hero.xp)
		var bonus: int = _combat_bonus()
		var bonus_str: String = " (+" + str(bonus) + ")" if bonus > 0 else ""
		ml.text = "L%d  %d/%d  G%d  %s%s  XP%d" % [
			lvl, mp, mmax, gold, _hero.army_summary(), bonus_str, xp]


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
	var eff: int = _hero.total_count() + cbonus
	var mfont: Font = ThemeDB.fallback_font
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			var ti: int = int(tiles[y * MAP_WIDTH + x])
			var pos := origin + Vector2(x * _tile_size, y * _tile_size)
			var rect := Rect2(pos, Vector2(_tile_size - 1.0, _tile_size - 1.0))
			var key := Vector2i(x, y)
			var fog: int = _fog_get(_fog_player, key)
			if fog == FOG_HIDDEN:
				_map_area.draw_rect(rect, Color(0.04, 0.04, 0.06), true)
				continue
			var col := _terrain_color(ti)
			var reachable: bool = _costs.has(key) and int(_costs[key]) <= _hero.mp
			if fog == FOG_EXPLORED:
				# Einmal gesehen, aktuell ausser Sicht: fest gedimmt und
				# kein reachability-Highlight (man koennte zwar hinlaufen,
				# aber die Info ist veraltet). Wichtig: NICHT zusaetzlich
				# mit reachability-Darken kombinieren, sonst wirken eigene
				# Staedte und Minen heller als weit entfernte Sichtzonen.
				col = col.darkened(0.55)
			elif not reachable:
				# VISIBLE ausserhalb Bewegungsreichweite: nur leicht gedimmt,
				# damit Sichtbereich um eigene Burgen/Minen klar heller
				# bleibt als EXPLORED.
				col = col.darkened(0.3)
			_map_area.draw_rect(rect, col, true)
			if fog == FOG_VISIBLE and reachable and key != _hero.position:
				_map_area.draw_rect(rect, Color(1.0, 1.0, 1.0, 0.25), false, 2.0)

	# Staedte: farbiges Viereck pro Fraktion. Neutraler Rand dunkel,
	# eigene Stadt bekommt dicken goldenen Rand. Wache-Staerke in der
	# Mitte, farbig nach Kampf-Prognose wie bei Monstern.
	for city in _cities:
		var cp: Vector2i = city["pos"]
		var cfog: int = _fog_get(_fog_player, cp)
		if cfog == FOG_HIDDEN:
			continue
		var fid: int = int(city["faction"])
		var owner: int = int(city["owner"])
		var cpos := origin + Vector2(cp.x * _tile_size, cp.y * _tile_size)
		var inset: float = _tile_size * 0.18
		var crect := Rect2(
			cpos + Vector2(inset, inset),
			Vector2(_tile_size - 1.0 - 2.0 * inset, _tile_size - 1.0 - 2.0 * inset)
		)
		var fc: Color = FACTION_COLORS[fid] if fid >= 0 and fid < FACTION_COLORS.size() else Color.WHITE
		if cfog == FOG_EXPLORED:
			fc = fc.darkened(0.45)
		_map_area.draw_rect(crect, fc, true)
		if owner == OWNER_HERO:
			_map_area.draw_rect(crect, Color(1.0, 0.85, 0.2), false, 4.0)
		elif owner >= OWNER_AI_MIN:
			_map_area.draw_rect(crect, _ai_ring_color(owner), false, 4.0)
		else:
			_map_area.draw_rect(crect, Color(0.1, 0.1, 0.12), false, 2.0)
		var garrison: int = int(city.get("garrison", 0))
		if owner != OWNER_HERO and garrison > 0 and cfog == FOG_VISIBLE:
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
		var mfog: int = _fog_get(_fog_player, mp)
		if mfog == FOG_HIDDEN:
			continue
		var mstr: int = int(m["strength"])
		var mpx := origin + Vector2(mp.x * _tile_size + _tile_size * 0.5, mp.y * _tile_size + _tile_size * 0.5)
		var mrad := _tile_size * 0.36
		var dist: int = abs(mp.x - _hero.position.x) + abs(mp.y - _hero.position.y)
		var txt: String
		var tcol: Color
		# Staerke steht erst unter halber Held-Sichtweite fest (Nahaufklae-
		# rung). Darueber hinaus bleibt das Monster sichtbar, aber mit "?".
		if mfog == FOG_VISIBLE and dist <= (HERO_SIGHT / 2):
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
		var ofog: int = _fog_get(_fog_player, op)
		if ofog == FOG_HIDDEN:
			continue
		var okind: int = int(obj["kind"])
		var oowner: int = int(obj.get("owner", OWNER_NEUTRAL))
		var opos := origin + Vector2(op.x * _tile_size, op.y * _tile_size)
		var oinset: float = _tile_size * 0.28
		var orect := Rect2(
			opos + Vector2(oinset, oinset),
			Vector2(_tile_size - 1.0 - 2.0 * oinset, _tile_size - 1.0 - 2.0 * oinset)
		)
		var ofill: Color = Color(0.95, 0.80, 0.20) if okind == OBJECT_MINE else Color(0.85, 0.50, 0.20)
		if ofog == FOG_EXPLORED:
			ofill = ofill.darkened(0.45)
		_map_area.draw_rect(orect, ofill, true)
		# Symbol auf das Feld malen, damit Mine und Truhe auf einen Blick
		# unterscheidbar sind - nicht nur ueber die Farbe.
		var sym_col := Color(0.25, 0.15, 0.05)
		if okind == OBJECT_MINE:
			# Gekreuzte Spitzhacken-Striche (X) ueber das ganze Feld.
			var sw: float = max(2.0, _tile_size * 0.06)
			var sr1 := orect.position
			var sr2 := orect.position + orect.size
			_map_area.draw_line(sr1, sr2, sym_col, sw)
			_map_area.draw_line(Vector2(sr1.x, sr2.y), Vector2(sr2.x, sr1.y), sym_col, sw)
		else:
			# Truhe: waagerechter Deckel-Strich + Schloss-Punkt darunter.
			var lid_y: float = orect.position.y + orect.size.y * 0.38
			_map_area.draw_line(
				Vector2(orect.position.x, lid_y),
				Vector2(orect.position.x + orect.size.x, lid_y),
				sym_col,
				max(2.0, _tile_size * 0.05)
			)
			var lock_c := Vector2(
				orect.position.x + orect.size.x * 0.5,
				lid_y + orect.size.y * 0.18
			)
			_map_area.draw_circle(lock_c, max(2.0, _tile_size * 0.07), sym_col)
		if oowner == OWNER_HERO:
			_map_area.draw_rect(orect, Color(1.0, 0.85, 0.2), false, 4.0)
		elif oowner >= OWNER_AI_MIN:
			_map_area.draw_rect(orect, _ai_ring_color(oowner), false, 4.0)
		else:
			_map_area.draw_rect(orect, Color(0.1, 0.1, 0.12), false, 2.0)
		var ogd: int = int(obj.get("guard", 0))
		if ogd > 0 and ofog == FOG_VISIBLE:
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

	# KI-Helden: pro KI entweder voller Marker (in Sicht) oder Ghost an
	# zuletzt bekannter Position (Alpha ueber FOG_ROT_TURNS verblassend).
	# KIs tragen Ring-Farbe nach owner_id (1/2/3 -> rot/violett/orange),
	# damit man sie im Free-for-All unterscheiden kann.
	for i in range(_enemies.size()):
		var eh: Hero = _enemies[i]["hero"] as Hero
		var eoid: int = int(_enemies[i]["owner_id"])
		var efill: Color = _ai_ring_color(eoid)
		var ering: Color = efill.darkened(0.55)
		if eh != null:
			var ex := eh.position
			var efog: int = _fog_get(_fog_player, ex)
			if efog == FOG_VISIBLE:
				var epx := origin + Vector2(ex.x * _tile_size, ex.y * _tile_size)
				var ecenter := epx + Vector2(_tile_size * 0.5, _tile_size * 0.5)
				_map_area.draw_circle(ecenter, radius, efill)
				_map_area.draw_arc(ecenter, radius, 0.0, TAU, 24, ering, 2.0)
				var earmy: int = eh.total_count()
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
				continue
		# Held ist tot ODER aktuell nicht in Sicht: Ghost an letzter
		# Sichtungs-Position zeichnen, solange Info nicht verrottet ist.
		var seen: Dictionary = _ai_seen_by_player[i]
		var lpos: Vector2i = seen["pos"]
		if lpos.x < 0:
			continue
		var since: int = _turn_number - int(seen["turn"])
		if since >= FOG_ROT_TURNS:
			continue
		var alpha: float = 1.0 - float(since) / float(FOG_ROT_TURNS)
		var gpx := origin + Vector2(lpos.x * _tile_size, lpos.y * _tile_size)
		var gcenter := gpx + Vector2(_tile_size * 0.5, _tile_size * 0.5)
		_map_area.draw_circle(gcenter, radius, Color(efill.r, efill.g, efill.b, 0.35 * alpha))
		_map_area.draw_arc(gcenter, radius, 0.0, TAU, 24, Color(efill.r, efill.g, efill.b, alpha), 2.0)
		var qsize: int = int(_tile_size * 0.5)
		var qs := mfont.get_string_size("?", HORIZONTAL_ALIGNMENT_CENTER, -1, qsize)
		var qpos := gcenter + Vector2(-qs.x * 0.5, qs.y * 0.35)
		_map_area.draw_string(mfont, qpos, "?", HORIZONTAL_ALIGNMENT_CENTER, -1, qsize, Color(1.0, 0.6, 0.6, alpha))


func _terrain_color(t: int) -> Color:
	match t:
		MapGen.TILE_GRASS:    return Color(0.30, 0.55, 0.25)
		MapGen.TILE_FOREST:   return Color(0.15, 0.35, 0.18)
		MapGen.TILE_WATER:    return Color(0.18, 0.35, 0.65)
		MapGen.TILE_MOUNTAIN: return Color(0.45, 0.42, 0.40)
		MapGen.TILE_SAND:     return Color(0.85, 0.78, 0.48)
		MapGen.TILE_SWAMP:    return Color(0.35, 0.40, 0.22)
	return Color(0.5, 0.5, 0.5)


func _terrain_name(t: int) -> String:
	match t:
		MapGen.TILE_GRASS:    return "Gras"
		MapGen.TILE_FOREST:   return "Wald"
		MapGen.TILE_WATER:    return "Wasser"
		MapGen.TILE_MOUNTAIN: return "Gebirge"
		MapGen.TILE_SAND:     return "Sand"
		MapGen.TILE_SWAMP:    return "Sumpf"
	return "Unbekannt"


func _map_origin() -> Vector2:
	# _clamp_view_offset haelt _view_offset bereits in gueltigen Grenzen
	# (zentriert oder geklemmt an Kartenrand). Draw und Tap-Transform
	# nutzen ausschliesslich diesen Wert, damit beides konsistent bleibt.
	return _view_offset


func _request_redraw() -> void:
	# Haupt-Karte und Minimap zusammen neu zeichnen. Einmal an allen
	# Aenderungspunkten (Bewegung, Fog, Stadt einnehmen, Viewport-Pan)
	# aufrufen, statt beide manuell zu koordinieren.
	if _map_area != null:
		_map_area.queue_redraw()
	if _minimap != null:
		_minimap.queue_redraw()


func _toggle_minimap() -> void:
	# Die Minimap liegt als Overlay oben rechts auf der Karte und fing
	# vorher Taps auf Staedte/Helden in dieser Region ab - das Panel
	# landete dann beim Minimap-Handler (Viewport zentrieren), nicht beim
	# Map-Handler. Der Umschalter blendet sie aus, damit Spieler Objekte
	# in der rechten oberen Ecke erreichen, ohne vorher panen zu muessen.
	if _minimap == null:
		return
	_minimap.visible = not _minimap.visible


func _on_minimap_input(event: InputEvent) -> void:
	# Tap auf Minimap springt mit dem Viewport zum entsprechenden Feld.
	# Drag auf der Minimap wird (noch) nicht unterstuetzt - einfacher
	# Tap-to-Jump reicht fuer Navigation.
	var pos := Vector2.ZERO
	var pressed: bool = false
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
	if _minimap == null:
		return
	var size: Vector2 = _minimap.size
	if size.x <= 0.0 or size.y <= 0.0:
		return
	var cell_w: float = size.x / float(MAP_WIDTH)
	var cell_h: float = size.y / float(MAP_HEIGHT)
	var tx: int = clamp(int(pos.x / cell_w), 0, MAP_WIDTH - 1)
	var ty: int = clamp(int(pos.y / cell_h), 0, MAP_HEIGHT - 1)
	_center_view_on(Vector2i(tx, ty))


func _draw_minimap() -> void:
	# Mini-Uebersicht: pro Kachel ein Farb-Rechteck (Fog dimmt EXPLORED,
	# versteckt HIDDEN), Helden-Positionen als farbige Punkte, Viewport-
	# Rechteck als heller Rahmen. Staedte bekommen einen duennen
	# Owner-farbigen Ring, damit man Machtverhaeltnisse sofort sieht.
	if _minimap == null or _map.is_empty():
		return
	var size: Vector2 = _minimap.size
	if size.x <= 0.0 or size.y <= 0.0:
		return
	var cw: float = size.x / float(MAP_WIDTH)
	var ch: float = size.y / float(MAP_HEIGHT)
	_minimap.draw_rect(Rect2(Vector2.ZERO, size), Color(0.05, 0.06, 0.08), true)
	var tiles: Array = _map["tiles"]
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			var fog: int = _fog_get(_fog_player, Vector2i(x, y))
			if fog == FOG_HIDDEN:
				continue
			var t: int = int(tiles[y * MAP_WIDTH + x])
			var col: Color = _terrain_color(t)
			if fog == FOG_EXPLORED:
				col = col.darkened(0.45)
			_minimap.draw_rect(Rect2(Vector2(x * cw, y * ch), Vector2(cw + 0.5, ch + 0.5)), col, true)
	# Staedte als kleine farbige Quadrate nach Besitzer (bzw. Faktion
	# bei neutral), damit man Konsolidierung auf einen Blick sieht.
	for city in _cities:
		var cp: Vector2i = city["pos"]
		if _fog_get(_fog_player, cp) == FOG_HIDDEN:
			continue
		var owner: int = int(city["owner"])
		var ccol: Color
		if owner == OWNER_HERO:
			ccol = Color(1.0, 0.85, 0.2)
		elif owner >= OWNER_AI_MIN:
			ccol = _ai_ring_color(owner)
		else:
			var fid: int = int(city["faction"])
			ccol = FACTION_COLORS[fid] if fid >= 0 and fid < FACTION_COLORS.size() else Color(0.6, 0.6, 0.6)
		var crect := Rect2(Vector2(cp.x * cw, cp.y * ch), Vector2(cw, ch))
		_minimap.draw_rect(crect, ccol, false, max(1.0, cw * 0.3))
	# Held als heller Punkt.
	if _hero != null:
		var hp: Vector2i = _hero.position
		var hpx := Vector2(hp.x * cw + cw * 0.5, hp.y * ch + ch * 0.5)
		_minimap.draw_circle(hpx, max(1.5, min(cw, ch) * 0.45), Color(1.0, 0.95, 0.4))
	# KI-Helden nur, wenn aktuell sichtbar (sonst waere Minimap ein
	# Aimbot). Ghost-Marker waeren overkill auf der kleinen Flaeche.
	for i in range(_enemies.size()):
		var eh: Hero = _enemies[i]["hero"] as Hero
		if eh == null:
			continue
		if _fog_get(_fog_player, eh.position) != FOG_VISIBLE:
			continue
		var ep := Vector2(eh.position.x * cw + cw * 0.5, eh.position.y * ch + ch * 0.5)
		_minimap.draw_circle(ep, max(1.5, min(cw, ch) * 0.45), _ai_ring_color(int(_enemies[i]["owner_id"])))
	# Viewport-Rahmen: Ausschnitt, der aktuell in MapArea sichtbar ist.
	var area: Vector2 = _map_area.size
	var vx: float = -_view_offset.x / _tile_size
	var vy: float = -_view_offset.y / _tile_size
	var vw: float = area.x / _tile_size
	var vh: float = area.y / _tile_size
	var vr := Rect2(Vector2(vx * cw, vy * ch), Vector2(vw * cw, vh * ch))
	_minimap.draw_rect(vr, Color(1.0, 1.0, 1.0, 0.85), false, 2.0)


func _on_map_input(event: InputEvent) -> void:
	# Nur Mouse-Events verarbeiten. Auf Android erzeugt Godot per Default
	# aus jedem Touch zusaetzlich ein emuliertes MouseButton-Event
	# (emulate_mouse_from_touch=true) - wenn wir beide Pfade behandeln,
	# feuert jeder Tap doppelt und Kaempfe triggerten zweimal. Das
	# Projekt-Default bleibt bewusst an, damit Standard-Buttons im
	# Hauptmenue auf Touch reagieren; hier verwerfen wir den Touch-Pfad.
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index != MOUSE_BUTTON_LEFT:
			return
		if mb.pressed:
			_begin_pan(mb.position)
		else:
			_end_pan(mb.position)
		return
	if event is InputEventMouseMotion:
		var mm := event as InputEventMouseMotion
		if _pan_active:
			_update_pan(mm.position)
		return


func _begin_pan(pos: Vector2) -> void:
	_pan_active = true
	_pan_moved = false
	_pan_start_pos = pos
	_pan_start_offset = _view_offset


func _update_pan(pos: Vector2) -> void:
	if not _pan_active:
		return
	var delta: Vector2 = pos - _pan_start_pos
	if not _pan_moved and delta.length() > DRAG_THRESHOLD:
		_pan_moved = true
	if _pan_moved:
		_view_offset = _pan_start_offset + delta
		_clamp_view_offset()
		_request_redraw()


func _end_pan(pos: Vector2) -> void:
	var was_drag: bool = _pan_moved
	_pan_active = false
	_pan_moved = false
	if was_drag:
		return
	_handle_tap(pos)


func _handle_tap(pos: Vector2) -> void:
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
	# Eigene Stadt:
	#   - Held steht drauf            -> Panel oeffnen
	#   - Stadt ausser MP-Reichweite  -> Panel oeffnen (Remote-Management)
	#   - Stadt in MP-Reichweite      -> unten normale Lauf-Logik
	# So blockiert das Panel nicht das Hinlaufen, wenn eine eigene Stadt
	# gerade erreichbar ist (HoMM3-Flow: erst hinlaufen, naechster Tap
	# oeffnet dann die Stadt).
	if target_city_idx >= 0 and int(_cities[target_city_idx]["owner"]) == OWNER_HERO:
		if target == _hero.position:
			_show_city(target_city_idx)
			return
		var reachable: bool = _costs.has(target) and int(_costs[target]) <= _hero.mp
		if not reachable:
			_show_city(target_city_idx)
			return
		# Reachable: Laufen lassen, nicht aufschnappen.
	if target == _hero.position:
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

	# Terrain-Id des Zielfelds bestimmt Obstacle-Generierung im Taktikkampf
	# (Wald -> Baumstamm/Busch, Berg -> Stein, Sumpf -> Sumpf, etc.).
	var battle_terrain: int = int((_map["tiles"] as Array)[target.y * MAP_WIDTH + target.x])

	# Monster auf Zielfeld: Taktik-Kampf-Overlay (Flucht erlaubt).
	var mon_idx: int = _monster_at(target)
	if mon_idx >= 0:
		var mstr_m: int = int(_monsters[mon_idx]["strength"])
		var mon_pos: Vector2i = _monsters[mon_idx]["pos"]
		_open_battle("Monster", mstr_m, true, battle_terrain, func(r: Dictionary) -> void:
			_on_monster_result(r, mon_pos, target, cost)
		)
		return

	# Gegner-Held auf Zielfeld: Pflichtkampf (keine Flucht), bevor wir
	# eine evtl. dort stehende Stadt einnehmen. Bei Sieg: Held tot, Stadt
	# wird im Callback direkt geclaimt (ohne zusaetzliche Garnison).
	var ai_at_target: int = _ai_index_at(target)
	if ai_at_target >= 0:
		var eh_t: Hero = _enemies[ai_at_target]["hero"] as Hero
		var ai_idx_cap: int = ai_at_target
		_open_battle("Gegner-Held", eh_t.total_count(), false, battle_terrain, func(r: Dictionary) -> void:
			_on_enemy_hero_result(r, target, cost, target_city_idx, ai_idx_cap)
		)
		return

	# Karten-Objekt auf Zielfeld: Wache (falls > 0) via Overlay, Einnahme
	# bzw. Einsammeln danach im Callback. Eigene Mine wird einfach betreten.
	var obj_idx: int = _object_at(target)
	if obj_idx >= 0:
		var obj: Dictionary = _objects[obj_idx]
		var okind: int = int(obj["kind"])
		var is_own_mine: bool = (okind == OBJECT_MINE and int(obj.get("owner", OWNER_NEUTRAL)) == OWNER_HERO)
		if not is_own_mine:
			var ogd: int = int(obj.get("guard", 0))
			if ogd > 0:
				var opos: Vector2i = target
				_open_battle("Wache", ogd, true, battle_terrain, func(r: Dictionary) -> void:
					_on_object_result(r, opos, target, cost)
				)
				return
			# guard == 0: direktes Betreten / Einsammeln (siehe unten)

	# Stadt-Wache: Overlay-Kampf. Bei Sieg claimt Callback die Stadt.
	if target_city_idx >= 0 and int(_cities[target_city_idx]["owner"]) != OWNER_HERO:
		var tc: Dictionary = _cities[target_city_idx]
		var garrison: int = int(tc.get("garrison", 0))
		if garrison > 0:
			var cidx: int = target_city_idx
			_open_battle("Stadtwache", garrison, true, battle_terrain, func(r: Dictionary) -> void:
				_on_city_result(r, cidx, target, cost)
			)
			return

	# Kein Kampf noetig: Mine/Schatz/Stadt ohne Wache oder leeres Feld.
	# Objekt-Einnahme bzw. Schatz einsammeln, falls vorhanden.
	if obj_idx >= 0:
		var obj2: Dictionary = _objects[obj_idx]
		var okind2: int = int(obj2["kind"])
		if okind2 == OBJECT_MINE and int(obj2.get("owner", OWNER_NEUTRAL)) != OWNER_HERO:
			obj2["owner"] = OWNER_HERO
		elif okind2 == OBJECT_TREASURE:
			var reward: int = int(obj2["gold"])
			_hero.gold += reward
			_objects.remove_at(obj_idx)
			_set_combat("Schatz gefunden: +%d G" % reward)

	_hero.mp -= cost
	_hero.position = target
	var claimed := false
	if target_city_idx >= 0 and int(_cities[target_city_idx]["owner"]) != OWNER_HERO:
		_cities[target_city_idx]["owner"] = OWNER_HERO
		claimed = true
	_recompute_fog_player()
	_recompute_costs()
	_request_redraw()
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


# Generisches Taktik-Kampf-Overlay. Host ruft _open_battle mit Gegner-
# Infos und einem Callback auf; der Callback bekommt das Ergebnis-
# Dictionary (outcome: "victory"/"defeat"/"flee", casualties: int) und
# ist fuer Belohnung und Bewegung verantwortlich. Der Level/Wachturm-
# Bonus fliesst in Att UND Def des Spieler-Stacks ein.
func _open_battle(opp_name: String, opp_army: int, allow_flee: bool, terrain_id: int, on_result: Callable) -> void:
	var bonus: int = _combat_bonus()
	var scene: PackedScene = load("res://scenes/TacticalBattle.tscn") as PackedScene
	if scene == null:
		push_error("TacticalBattle.tscn fehlt")
		return
	var overlay = scene.instantiate()
	add_child(overlay)
	if overlay.has_method("set_battle"):
		var p_stacks: Array = _army_to_stacks(_hero.army)
		var e_stacks: Array = _build_enemy_stacks(opp_name, opp_army)
		overlay.call("set_battle", {
			"player_name": "Held",
			"player_stacks": p_stacks,
			"player_bonus": bonus,
			"enemy_name": opp_name,
			"enemy_stacks": e_stacks,
			"allow_flee": allow_flee,
			"seed": _seed,
			"terrain_id": terrain_id,
		})
	overlay.connect("battle_finished", func(result: Dictionary) -> void:
		on_result.call(result)
		overlay.queue_free()
	)


# Zerlegt eine Gegner-Armee-Groesse in gemischte Stacks, abhaengig von
# der Quelle des Kampfes. Wachen bleiben reine Schwerter (einfache
# Verteidiger), Monster werden ab mittlerer Groesse gemischt (Bogen,
# Reiter), der Feind-Held erbt seine tatsaechliche Rekrutierungs-
# zusammensetzung. Keine RNG noetig - rein deterministisch aus der
# Gesamtzahl, damit zwei Spieler mit gleichem Seed das gleiche Matchup
# sehen.
func _build_enemy_stacks(opp_name: String, total: int) -> Array:
	if total <= 0:
		return [{"type": "sword", "count": 1}]
	# Der Feind-Held erbt seine tatsaechliche Rekrutierung direkt aus der
	# KI-Stadt. Alle anderen Gegner (Monster, Stadt-/Objektwachen) werden
	# nach Groesse gemischt - klein reine Schwert-Truppe, ab mittlerer
	# Groesse Bogen dazu, ab grosser Groesse auch Reiter.
	if opp_name == "Gegner-Held":
		# Spieler greift eine KI direkt an: Stacks aus deren Hero-Armee
		# ableiten. Finde die KI am Zielfeld - _enemies[i]["hero"].position
		# ist deterministisch; falls mehrere KIs kollidieren sollten,
		# nimmt _ai_index_at die erste.
		for e_i in _enemies:
			var he: Hero = e_i["hero"] as Hero
			if he != null and he.total_count() == total:
				return _army_to_stacks(he.army)
	if total <= 2:
		return [{"type": "sword", "count": total}]
	if total <= 5:
		var bows: int = max(1, int(round(float(total) * 0.4)))
		var swords: int = total - bows
		return [{"type": "sword", "count": swords}, {"type": "bow", "count": bows}]
	var riders: int = max(1, int(round(float(total) * 0.2)))
	var bows2: int = max(1, int(round(float(total) * 0.3)))
	var swords2: int = max(1, total - bows2 - riders)
	return [
		{"type": "sword", "count": swords2},
		{"type": "bow", "count": bows2},
		{"type": "rider", "count": riders},
	]


func _army_to_stacks(army: Dictionary) -> Array:
	var out: Array = []
	for uid in ["sword", "bow", "rider"]:
		var cnt: int = int(army.get(uid, 0))
		if cnt > 0:
			out.append({"type": uid, "count": cnt})
	if out.is_empty():
		out.append({"type": "sword", "count": 1})
	return out


func _apply_casualties(result: Dictionary) -> void:
	var cas = result.get("casualties", {})
	if cas is Dictionary:
		_hero.apply_casualties(cas)
	elif cas is int:
		_hero.apply_proportional_losses(int(cas))


func _count_casualties(result: Dictionary) -> int:
	var cas = result.get("casualties", {})
	if cas is Dictionary:
		var t := 0
		for v in (cas as Dictionary).values():
			t += int(v)
		return t
	return int(cas)


func _finish_move_to(target: Vector2i, cost: int) -> void:
	_hero.mp -= cost
	_hero.position = target
	_recompute_fog_player()
	_recompute_costs()
	_ensure_hero_in_view()
	_request_redraw()
	_update_labels()


func _ensure_hero_in_view() -> void:
	# Wenn der Held nach der Bewegung nicht mehr im Viewport ist (z.B.
	# weil der Spieler vorher frei gepannt hat), sanft nachfuehren. Ist
	# er noch sichtbar, wird der Pan-Zustand des Spielers respektiert.
	if _hero == null or _map_area == null:
		return
	var area: Vector2 = _map_area.size
	var hero_world: Vector2 = Vector2(_hero.position.x, _hero.position.y) * _tile_size + Vector2(_tile_size, _tile_size) * 0.5
	var on_screen: Vector2 = hero_world + _view_offset
	var margin: float = _tile_size
	var off: bool = (on_screen.x < margin or on_screen.x > area.x - margin
		or on_screen.y < margin or on_screen.y > area.y - margin)
	if off:
		_center_view_on(_hero.position)


func _on_battle_defeat() -> void:
	_game_lost = true
	_set_status("NIEDERLAGE")
	_set_combat("NIEDERLAGE: Held gefallen")
	_show_defeat_panel()


func _on_monster_result(result: Dictionary, mon_pos: Vector2i, target: Vector2i, cost: int) -> void:
	var outcome: String = String(result.get("outcome", "flee"))
	if outcome == "flee":
		_set_combat("Kampf abgebrochen (geflohen)")
		return
	if outcome == "defeat":
		_apply_casualties(result)
		_update_labels()
		_on_battle_defeat()
		return
	var mon_idx: int = _monster_at(mon_pos)
	if mon_idx < 0:
		return
	var mstr: int = int(_monsters[mon_idx]["strength"])
	var cas: int = _count_casualties(result)
	_apply_casualties(result)
	_hero.gold += MONSTER_VICTORY_GOLD
	var xp_gain: int = mstr * XP_PER_STRENGTH
	_hero.xp += xp_gain
	var leveled: bool = _check_level_up()
	_monsters.remove_at(mon_idx)
	_finish_move_to(target, cost)
	var msg_win: String
	if leveled:
		msg_win = "SIEG! -%d A  +%d G  +%d XP  -->  LEVEL %d!" % [cas, MONSTER_VICTORY_GOLD, xp_gain, _hero.level]
	else:
		msg_win = "SIEG! -%d A  +%d G  +%d XP" % [cas, MONSTER_VICTORY_GOLD, xp_gain]
	_set_status(msg_win)
	_set_combat(msg_win)


func _on_enemy_hero_result(result: Dictionary, target: Vector2i, cost: int, target_city_idx: int, ai_idx: int = 0) -> void:
	var outcome: String = String(result.get("outcome", "flee"))
	if outcome == "flee":
		# Gegner-Held-Kampf ist Pflicht; allow_flee=false. Fallback: keine Aktion.
		_set_combat("Kampf abgebrochen")
		return
	if outcome == "defeat":
		_apply_casualties(result)
		_update_labels()
		_on_battle_defeat()
		return
	var cas: int = _count_casualties(result)
	_apply_casualties(result)
	_hero.gold += ENEMY_DEFEAT_GOLD
	_hero.xp += ENEMY_DEFEAT_XP
	var leveled: bool = _check_level_up()
	if ai_idx >= 0 and ai_idx < _enemies.size():
		_enemies[ai_idx]["hero"] = null
	_finish_move_to(target, cost)
	# Stadt auf dem Zielfeld direkt einnehmen (Gegner-Held war der Verteidiger).
	var claimed: bool = false
	if target_city_idx >= 0 and int(_cities[target_city_idx]["owner"]) != OWNER_HERO:
		_cities[target_city_idx]["owner"] = OWNER_HERO
		_cities[target_city_idx]["garrison"] = 0
		claimed = true
	var msg_h_win: String
	if leveled:
		msg_h_win = "Gegner besiegt: -%d A +%d G +%d XP -> LEVEL %d!" % [cas, ENEMY_DEFEAT_GOLD, ENEMY_DEFEAT_XP, _hero.level]
	else:
		msg_h_win = "Gegner besiegt: -%d A +%d G +%d XP" % [cas, ENEMY_DEFEAT_GOLD, ENEMY_DEFEAT_XP]
	_set_status(msg_h_win)
	_set_combat(msg_h_win)
	if claimed:
		_check_victory()


func _on_object_result(result: Dictionary, obj_pos: Vector2i, target: Vector2i, cost: int) -> void:
	var outcome: String = String(result.get("outcome", "flee"))
	if outcome == "flee":
		_set_combat("Kampf abgebrochen (geflohen)")
		return
	if outcome == "defeat":
		_apply_casualties(result)
		_update_labels()
		_on_battle_defeat()
		return
	var obj_idx: int = _object_at(obj_pos)
	if obj_idx < 0:
		return
	var obj: Dictionary = _objects[obj_idx]
	var okind: int = int(obj["kind"])
	var ogd: int = int(obj.get("guard", 0))
	var cas: int = _count_casualties(result)
	_apply_casualties(result)
	var xp_o: int = ogd * XP_PER_STRENGTH
	_hero.xp += xp_o
	var lvl_o: bool = _check_level_up()
	obj["guard"] = 0
	var msg_og: String
	if lvl_o:
		msg_og = "Wache besiegt: -%d A +%d XP -> LEVEL %d!" % [cas, xp_o, _hero.level]
	else:
		msg_og = "Wache besiegt: -%d A +%d XP" % [cas, xp_o]
	_set_combat(msg_og)
	if okind == OBJECT_MINE:
		obj["owner"] = OWNER_HERO
	elif okind == OBJECT_TREASURE:
		var reward: int = int(obj["gold"])
		_hero.gold += reward
		_objects.remove_at(obj_idx)
		_set_combat("Schatz gefunden: +%d G (Wache -%d A)" % [reward, cas])
	_finish_move_to(target, cost)


func _on_city_result(result: Dictionary, city_idx: int, target: Vector2i, cost: int) -> void:
	var outcome: String = String(result.get("outcome", "flee"))
	if outcome == "flee":
		_set_combat("Kampf abgebrochen (geflohen)")
		return
	if outcome == "defeat":
		_apply_casualties(result)
		_update_labels()
		_on_battle_defeat()
		return
	if city_idx < 0 or city_idx >= _cities.size():
		return
	var tc: Dictionary = _cities[city_idx]
	var garrison: int = int(tc.get("garrison", 0))
	var cas: int = _count_casualties(result)
	_apply_casualties(result)
	var xp_c: int = garrison * XP_PER_STRENGTH
	_hero.xp += xp_c
	var leveled_c: bool = _check_level_up()
	tc["garrison"] = 0
	tc["owner"] = OWNER_HERO
	_finish_move_to(target, cost)
	var fid: int = int(tc["faction"])
	var msg_c: String
	if leveled_c:
		msg_c = "Stadt %s: Wache besiegt (-%d A, +%d XP) -> LEVEL %d" % [FACTION_NAMES[fid], cas, xp_c, _hero.level]
	else:
		msg_c = "Stadt %s: Wache besiegt (-%d A, +%d XP)" % [FACTION_NAMES[fid], cas, xp_c]
	_set_status(msg_c)
	_set_combat(msg_c)
	_check_victory()


func _object_at(p: Vector2i) -> int:
	for i in range(_objects.size()):
		if (_objects[i]["pos"] as Vector2i) == p:
			return i
	return -1


func _check_victory() -> void:
	# Free-for-All-Sieg: alle anderen Fraktionen sind eliminiert - d.h.
	# keine KI besitzt mehr eine Stadt, und keine KI hat noch einen
	# lebenden Helden. Neutrale Staedte/Minen zaehlen nicht als Gegner;
	# der Spieler muss sie nicht einnehmen, um zu gewinnen.
	if _cities.size() == 0:
		return
	for c in _cities:
		var ow: int = int(c["owner"])
		if _is_ai_owner(ow):
			return
	for e in _enemies:
		var eh: Hero = e["hero"] as Hero
		if eh != null:
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
			stats.text = "Level " + str(_hero.level) + "   XP " + str(_hero.xp) + "\nGold " + str(_hero.gold) + "   Armee " + str(_hero.total_count())
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
		_hero.add_units("sword", LEVEL_BONUS_ARMY)
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

	# Rekrutieren: drei Buttons (je Einheit-Typ). Jeder braucht ein anderes
	# Gebaeude: Schwert -> Kaserne, Bogen -> Schmiede, Reiter -> Reiterei.
	# Fehlt das Gebaeude, ist der Button deaktiviert mit Hinweis, welches.
	# Rekrutierung braucht den Helden vor Ort - ansonsten wuerden frisch
	# gekaufte Einheiten in die Armee teleportiert, egal wo der Held steht.
	var hero_here: bool = _hero != null and _hero.position == Vector2i(city["pos"])
	for uid in UnitType.all_ids():
		var cost: int = UnitType.cost_of(uid)
		var req: String = String(UNIT_BUILDING.get(uid, "kaserne"))
		var rbtn := Button.new()
		rbtn.custom_minimum_size = Vector2(0, 110)
		rbtn.add_theme_font_size_override("font_size", 30)
		if not built.has(req):
			rbtn.text = "%s rekrutieren  -  benoetigt %s" % [UnitType.name_of(uid), req.capitalize()]
			rbtn.disabled = true
		elif not hero_here:
			rbtn.text = "%s rekrutieren  -  Held nicht vor Ort" % UnitType.name_of(uid)
			rbtn.disabled = true
		else:
			rbtn.text = "%s rekrutieren  -  %d G  (+1)" % [UnitType.name_of(uid), cost]
			if _hero.gold < cost:
				rbtn.disabled = true
		rbtn.pressed.connect(_recruit_unit.bind(city_idx, uid))
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


func _recruit_unit(city_idx: int, unit_id: String) -> void:
	var cost: int = UnitType.cost_of(unit_id)
	if _hero.gold < cost:
		return
	var city: Dictionary = _cities[city_idx]
	var built: Array = city["buildings"]
	var req: String = String(UNIT_BUILDING.get(unit_id, "kaserne"))
	if not built.has(req):
		return
	# Held muss in der Stadt stehen, sonst wuerden gekaufte Einheiten in
	# die Heldenarmee teleportieren. Mirror zur Button-Logik in _show_city.
	if _hero.position != Vector2i(city["pos"]):
		return
	_hero.gold -= cost
	_hero.add_units(unit_id, 1)
	_update_labels()
	_set_status("Rekrutiert: +1 %s" % UnitType.name_of(unit_id))
	_show_city(city_idx)


func _enemy_unlocked_units_for(idx: int) -> Array:
	var out: Array = []
	if idx < 0 or idx >= _enemies.size():
		return out
	var oid: int = int(_enemies[idx]["owner_id"])
	for uid in UnitType.ORDER:
		var req: String = String(UNIT_BUILDING.get(uid, "kaserne"))
		for c in _cities:
			if int(c["owner"]) == oid and (c["buildings"] as Array).has(req):
				out.append(uid)
				break
	return out


func _enemy_next_unit_id_for(idx: int, allowed: Array = []) -> String:
	# Waehlt den naechsten Einheiten-Typ in strikter Rotation pro KI.
	# Wird eine Positivliste "allowed" uebergeben, werden gesperrte Slots
	# uebersprungen - der Rotations-Index rueckt trotzdem weiter, damit
	# die Mischung nicht monoton wird.
	if idx < 0 or idx >= _enemies.size():
		return ""
	var e: Dictionary = _enemies[idx]
	var ri: int = int(e["recruit_idx"])
	if allowed.is_empty():
		var uid: String = UnitType.ORDER[ri % UnitType.ORDER.size()]
		e["recruit_idx"] = (ri + 1) % UnitType.ORDER.size()
		return uid
	for _step in range(UnitType.ORDER.size()):
		var uid: String = UnitType.ORDER[ri % UnitType.ORDER.size()]
		ri = (ri + 1) % UnitType.ORDER.size()
		e["recruit_idx"] = ri
		if uid in allowed:
			return uid
	return ""


func _building_by_id(bid: String) -> Dictionary:
	for b in BUILDINGS:
		if String(b["id"]) == bid:
			return b
	return {}


func _enemy_economy_for(idx: int) -> void:
	# Gegner spielt nach den gleichen Regeln wie der Spieler: Einkommen pro
	# eigener Stadt (+Markt), Armee-Wachstum nur mit Schmiede, max_mp nur
	# mit Spaeher. Danach Ausgaben nach Prioritaet: Kaserne -> Schmiede ->
	# Markt -> Spaeher. Sobald keine Prioritaets-Gebaeude mehr affordable
	# sind und Kaserne steht, wird Ueberschuss in Rekruten gesteckt.
	# Wachturm/Kapelle bringen dem Gegner (noch) nichts, daher ignoriert.
	if idx < 0 or idx >= _enemies.size():
		return
	var e: Dictionary = _enemies[idx]
	var eh: Hero = e["hero"] as Hero
	if eh == null:
		return
	var oid: int = int(e["owner_id"])
	var owned: int = 0
	var markt: int = 0
	var schmiede: int = 0
	var spaeher: int = 0
	for c in _cities:
		if int(c["owner"]) != oid:
			continue
		owned += 1
		var bl: Array = c["buildings"]
		if bl.has("markt"):
			markt += 1
		if bl.has("schmiede"):
			schmiede += 1
		if bl.has("spaeher"):
			spaeher += 1
	eh.max_mp = ENEMY_BASE_MP + MP_BONUS_SPAEHER * spaeher
	var e_mine_income: int = 0
	for obj in _objects:
		if int(obj["kind"]) == OBJECT_MINE and int(obj.get("owner", OWNER_NEUTRAL)) == oid:
			e_mine_income += int(obj["gold"])
	eh.gold += owned * CITY_INCOME + markt * INCOME_MARKT + e_mine_income
	# Schmiede-Bonus wird auch rotierend verteilt, damit sich das Muster
	# "Gegner hat nur Schwerter" nicht ueber die frei geschenkten Einheiten
	# einschleicht. Einheiten-Typen, deren Gebaeude noch fehlen, werden
	# uebersprungen - sonst haette der Gegner Reiter ohne Reiterei.
	var smithy_gifts: int = schmiede * SCHMIEDE_ARMY_PER_TURN
	var unlocked: Array = _enemy_unlocked_units_for(idx)
	for _i in range(smithy_gifts):
		if unlocked.is_empty():
			break
		var gift_uid: String = _enemy_next_unit_id_for(idx, unlocked)
		if gift_uid != "":
			eh.add_units(gift_uid, 1)
	# Symmetrie zum Spieler: Gebaeude bauen und Rekruten kaufen nur,
	# wenn der KI-Held aktuell auf einer eigenen Stadt steht. Sonst
	# waechst die Armee auf der Jagd um +10 pro Zug und der Spieler
	# hat keine Chance. Gold stapelt sich und wird bei der Rueckkehr
	# in die Stadt ausgegeben - genau wie beim Spieler.
	var in_own_city: bool = false
	for c in _cities:
		if int(c["owner"]) == oid and Vector2i(c["pos"]) == eh.position:
			in_own_city = true
			break
	if not in_own_city:
		return
	var priority: Array = ["kaserne", "schmiede", "reiterei", "markt", "spaeher"]
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
			if eh.gold < bcost:
				continue
			var req: String = String(bdef["requires"]) if bdef.has("requires") else ""
			for c in _cities:
				if int(c["owner"]) != oid:
					continue
				var bl: Array = c["buildings"]
				if bl.has(bid):
					continue
				if req != "" and not bl.has(req):
					continue
				bl.append(bid)
				eh.gold -= bcost
				spent = true
				break
			if spent:
				break
		if spent:
			continue
		# Keine Prioritaets-Gebaeude mehr affordable: Ueberschuss in Rekruten
		# stecken. Rotations-Slot S -> B -> R muss _gleichzeitig_ Gold und
		# das noetige Gebaeude (Kaserne/Schmiede/Reiterei) haben. Ist der
		# aktuelle Slot blockiert, bleibt der Rotations-Index stehen und die
		# KI kauft diese Runde nichts - so holt sie den Slot automatisch
		# nach, sobald das fehlende Gebaeude steht.
		var ri: int = int(e["recruit_idx"])
		var next_uid: String = UnitType.ORDER[ri % UnitType.ORDER.size()]
		var next_cost: int = UnitType.cost_of(next_uid)
		var next_req: String = String(UNIT_BUILDING.get(next_uid, "kaserne"))
		if eh.gold < next_cost:
			continue
		var has_req: bool = false
		for c in _cities:
			if int(c["owner"]) == oid and (c["buildings"] as Array).has(next_req):
				has_req = true
				break
		if has_req:
			eh.gold -= next_cost
			eh.add_units(next_uid, 1)
			e["recruit_idx"] = (ri + 1) % UnitType.ORDER.size()
			spent = true


func _run_enemy_turn_for(idx: int) -> bool:
	# Einfache Gegner-KI: waehlt die naechstgelegene Nicht-eigene-Stadt
	# (neutral, Spieler oder andere KI) per Dijkstra, laeuft mit
	# Gradienten-Abstieg so weit wie MP reichen. Monster werden ignoriert
	# (monsters_block=false), damit die KI nicht eingekesselt wird.
	# Rueckgabe: true wenn der Zug abgeschlossen ist, false wenn ein
	# Pflicht-Kampf-Overlay geoeffnet wurde und die AI-Phase suspendiert
	# auf den Callback wartet.
	if idx < 0 or idx >= _enemies.size():
		return true
	var e: Dictionary = _enemies[idx]
	var eh: Hero = e["hero"] as Hero
	if eh == null:
		return true
	var oid: int = int(e["owner_id"])
	var fog_e: Array = e["fog"]
	var pls_pos: Vector2i = e["player_last_seen_pos"]
	var pls_turn: int = int(e["player_last_seen_turn"])
	eh.end_turn()
	# Vor der Zielauswahl Fog aktualisieren, damit die KI ihre eigene Sicht
	# kennt (sonst wuerde sie mit stale Fog aus der letzten Runde arbeiten).
	_recompute_fog_ai(idx)
	fog_e = e["fog"]
	pls_pos = e["player_last_seen_pos"]
	pls_turn = int(e["player_last_seen_turn"])
	var ecosts: Dictionary = _dijkstra(eh.position, false)
	# Ziel-Auswahl: naechste nicht-eigene Stadt, fremde/neutrale Goldmine
	# oder Schatzkiste - aber nur, wenn die KI das Feld schonmal gesehen
	# hat (Fog-Symmetrie). Spieler-Held-Ziel ist moeglich, solange die
	# letzte Sichtung noch nicht "verrottet" ist (FOG_ROT_TURNS).
	var target_kind: String = ""
	var target_idx: int = -1
	var target_cost: int = -1
	var target_pos: Vector2i = eh.position
	# Nur Ziele anpeilen, die die KI auch nehmen kann. Sonst sitzt sie
	# endlos auf einer zu starken Wache und das Heimweg-Fallback greift
	# nie, weil target_cost immer 0 bleibt. Armee ist der einzige Wert,
	# der Kaempfe entscheidet (KI hat keinen Kampfkraft-Bonus).
	var army: int = eh.total_count()
	for i in range(_cities.size()):
		if int(_cities[i]["owner"]) == oid:
			continue
		var cp: Vector2i = _cities[i]["pos"]
		if _fog_get(fog_e, cp) == FOG_HIDDEN:
			continue
		if not ecosts.has(cp):
			continue
		var garrison_c: int = int(_cities[i].get("garrison", 0))
		# Safety-Margin: KI greift nicht mit knapper Armee an, sondern
		# braucht AI_RAID_SAFETY_PCT Prozent mehr. Verhindert 1:1-Pyrrhus-
		# Eroberungen, bei denen die KI nach Sieg handlungsunfaehig ist.
		if garrison_c > 0 and army * 100 < garrison_c * (100 + AI_RAID_SAFETY_PCT):
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
		if okind == OBJECT_MINE and int(obj.get("owner", OWNER_NEUTRAL)) == oid:
			continue
		var op: Vector2i = obj["pos"]
		if _fog_get(fog_e, op) == FOG_HIDDEN:
			continue
		if not ecosts.has(op):
			continue
		var guard_o: int = int(obj.get("guard", 0))
		if guard_o > 0 and army * 100 < guard_o * (100 + AI_RAID_SAFETY_PCT):
			continue
		var c2: int = int(ecosts[op])
		if target_cost < 0 or c2 < target_cost:
			target_kind = "mine" if okind == OBJECT_MINE else "treasure"
			target_idx = i
			target_cost = c2
			target_pos = op
	# Helden-Jagd: sowohl der Spieler als auch rivalisierende KIs sind
	# Kandidaten, solange die letzte Sichtung nicht verrottet ist. Pro
	# Kandidat AI_HUNT_SAFETY_PCT Prozent Armee-Vorsprung verlangen,
	# sonst verzichtet die KI auf den Angriff (Suizid-Vermeidung). Ohne
	# Filter joggt die KI stur auf jeden gesehenen Helden zu, egal wie
	# stark der ist - und verliert alles in einem Kampf.
	var hunt_candidates: Array = []
	if _hero != null and pls_pos.x >= 0 and (_turn_number - pls_turn) < FOG_ROT_TURNS:
		hunt_candidates.append({"pos": pls_pos, "strength": _hero.total_count()})
	var rs_hunt: Dictionary = e.get("rivals_seen", {})
	for rid_key in rs_hunt.keys():
		var entry: Dictionary = rs_hunt[rid_key]
		var rturn: int = int(entry["turn"])
		if (_turn_number - rturn) >= FOG_ROT_TURNS:
			continue
		# Rival muss noch leben, um ueberhaupt angreifbar zu sein.
		var rh_live: Hero = null
		for oi in range(_enemies.size()):
			if int(_enemies[oi]["owner_id"]) == int(rid_key):
				rh_live = _enemies[oi]["hero"] as Hero
				break
		if rh_live == null:
			continue
		hunt_candidates.append({"pos": Vector2i(entry["pos"]), "strength": rh_live.total_count()})
	for hc_entry in hunt_candidates:
		var hp: Vector2i = hc_entry["pos"]
		var hstr: int = int(hc_entry["strength"])
		if not ecosts.has(hp):
			continue
		if army * 100 < hstr * (100 + AI_HUNT_SAFETY_PCT):
			continue
		var hc: int = int(ecosts[hp])
		if target_cost < 0 or hc <= target_cost:
			target_kind = "hero"
			target_idx = -1
			target_cost = hc
			target_pos = hp
	# Heimweg: wenn die KI genug Gold fuer eine billige Ausgabe hat, aber
	# nicht auf einer eigenen Stadt steht, ist die naechste eigene Stadt ein
	# valides Ziel. Grund: _enemy_economy_for gibt nur aus, wenn der Held
	# auf einer eigenen Stadt steht (gleiche Regel wie beim Spieler). Ohne
	# diesen Anker wuerde sich Gold endlos stapeln. Hero-Jagd hat Vorrang,
	# sonst gewinnt das naeher gelegene Ziel (home vs. Loot).
	var cheapest_spend: int = 300 # Spaeher ist das billigste Gebaeude
	for uid in UnitType.ORDER:
		var uc: int = UnitType.cost_of(uid)
		if uc < cheapest_spend:
			cheapest_spend = uc
	if eh.gold >= cheapest_spend and target_kind != "hero":
		var on_own_city: bool = false
		for i in range(_cities.size()):
			if int(_cities[i]["owner"]) == oid and Vector2i(_cities[i]["pos"]) == eh.position:
				on_own_city = true
				break
		if not on_own_city:
			var best_home_i: int = -1
			var best_home_cost: int = -1
			var best_home_pos: Vector2i = eh.position
			for i in range(_cities.size()):
				if int(_cities[i]["owner"]) != oid:
					continue
				var cp2: Vector2i = _cities[i]["pos"]
				if not ecosts.has(cp2):
					continue
				var cc: int = int(ecosts[cp2])
				if best_home_cost < 0 or cc < best_home_cost:
					best_home_i = i
					best_home_cost = cc
					best_home_pos = cp2
			if best_home_i >= 0 and (target_cost < 0 or best_home_cost < target_cost):
				target_kind = "home"
				target_idx = best_home_i
				target_cost = best_home_cost
				target_pos = best_home_pos
	# Defensives Override: jede eigene Stadt in Manhattan-Reichweite
	# AI_THREAT_RADIUS eines aktuell sichtbaren feindlichen Helden
	# (Spieler oder rivalisierende KI) zaehlt als bedroht. Reagiert die
	# KI, laeuft ihr Held zur naechstgelegenen bedrohten Stadt, statt
	# weiter zu looten. Hat Vorrang vor Raid, Hunt und Home - defensive
	# Entscheidungen sind im Free-for-All die teuersten Fehler (Stadt
	# verloren = oft Spielentscheidung).
	var defend_i: int = -1
	var defend_cost: int = -1
	var defend_pos: Vector2i = eh.position
	for i in range(_cities.size()):
		if int(_cities[i]["owner"]) != oid:
			continue
		var cp_d: Vector2i = _cities[i]["pos"]
		if not ecosts.has(cp_d):
			continue
		var is_threatened: bool = false
		if _hero != null and _fog_get(fog_e, _hero.position) == FOG_VISIBLE:
			var dph: int = abs(_hero.position.x - cp_d.x) + abs(_hero.position.y - cp_d.y)
			if dph <= AI_THREAT_RADIUS:
				is_threatened = true
		if not is_threatened:
			for oi in range(_enemies.size()):
				if oi == idx:
					continue
				var ohd: Hero = _enemies[oi]["hero"] as Hero
				if ohd == null:
					continue
				if _fog_get(fog_e, ohd.position) != FOG_VISIBLE:
					continue
				var dpo: int = abs(ohd.position.x - cp_d.x) + abs(ohd.position.y - cp_d.y)
				if dpo <= AI_THREAT_RADIUS:
					is_threatened = true
					break
		if not is_threatened:
			continue
		var cd: int = int(ecosts[cp_d])
		if defend_cost < 0 or cd < defend_cost:
			defend_i = i
			defend_cost = cd
			defend_pos = cp_d
	if defend_i >= 0:
		target_kind = "defend"
		target_idx = defend_i
		target_cost = defend_cost
		target_pos = defend_pos
	# Fallback-Exploration: nichts bekannt -> naechstgelegenes Hidden-Feld
	# ansteuern, damit die KI aktiv erkundet und nicht passiv in der
	# Startzone bleibt.
	if target_cost < 0:
		var best_ex: int = -1
		var best_ep: Vector2i = eh.position
		for p in ecosts.keys():
			var pv: Vector2i = p
			if _fog_get(fog_e, pv) != FOG_HIDDEN:
				continue
			var pc: int = int(ecosts[pv])
			if best_ex < 0 or pc < best_ex:
				best_ex = pc
				best_ep = pv
		if best_ex < 0:
			return true
		target_kind = "explore"
		target_idx = -1
		target_cost = best_ex
		target_pos = best_ep
	if target_cost < 0:
		return true
	# Zweite Dijkstra vom Ziel aus, um Schritt-fuer-Schritt den Gradienten
	# absteigen zu koennen. Einfacher als Pfad-Rekonstruktion.
	var tcosts: Dictionary = _dijkstra(target_pos, false)
	if not tcosts.has(eh.position):
		return true
	var tiles: Array = _map["tiles"]
	var guard: int = 0
	var cap: int = MAP_WIDTH + MAP_HEIGHT + 10
	while eh.mp > 0 and eh.position != target_pos and guard < cap:
		guard += 1
		var cur_val: int = int(tcosts[eh.position])
		var best_next: Vector2i = eh.position
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
			var np: Vector2i = eh.position + d
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
			if step_cost > eh.mp:
				continue
			if v < best_val:
				best_val = v
				best_next = np
				best_step = step_cost
		if best_step < 0:
			break
		# Spieler-Held auf dem naechsten Schritt: Pflicht-Kampf via
		# Taktik-Overlay. Der Aufruf oeffnet ein modales Overlay, das der
		# Spieler selbst ausspielt. Wir suspendieren die KI-Phase bis
		# zum Callback (return false -> _advance_ai_phase legt eine
		# Pause ein und wird von _on_ai_attack_result fortgesetzt).
		if _hero != null and best_next == _hero.position:
			var battle_terrain: int = int(tiles[best_next.y * MAP_WIDTH + best_next.x])
			var ai_total: int = eh.total_count()
			var next_idx: int = idx + 1
			_open_battle("Gegner-Held", ai_total, false, battle_terrain, func(r: Dictionary) -> void:
				_on_ai_attack_result(r, idx, next_idx)
			)
			return false
		# Gegner-Held einer anderen KI auf dem naechsten Schritt: Auto-
		# Resolve-Kampf (kein Overlay, Spieler ist nicht beteiligt).
		# Sieger = hoehere Gesamtarmee; Sieger nimmt proportionale
		# Verluste in Hoehe der Verliererarmee hin, Verlierer ist weg.
		# Gleichstand: Angreifer (diese KI) verliert (deterministischer
		# Tiebreaker, damit der Verteidiger einen Vorteil hat).
		var other_idx: int = -1
		for oi in range(_enemies.size()):
			if oi == idx:
				continue
			var oh: Hero = _enemies[oi]["hero"] as Hero
			if oh != null and oh.position == best_next:
				other_idx = oi
				break
		if other_idx >= 0:
			var other_hero: Hero = _enemies[other_idx]["hero"] as Hero
			var att_total: int = eh.total_count()
			var def_total: int = other_hero.total_count()
			if att_total > def_total:
				eh.apply_proportional_losses(def_total)
				_enemies[other_idx]["hero"] = null
				eh.position = best_next
				eh.mp -= best_step
			else:
				other_hero.apply_proportional_losses(att_total)
				e["hero"] = null
				return true
			continue
		eh.position = best_next
		eh.mp -= best_step
	# Ziel erreicht? Einnehmen/Einsammeln je nach Ziel-Art. KI hat keinen
	# Kampfkraft-Bonus, nur ihre Armee zaehlt. Wenn die Wache zu stark ist,
	# bleibt die KI einfach stehen und versucht es spaeter nochmal.
	if eh.position == target_pos:
		if target_kind == "city":
			var tc: Dictionary = _cities[target_idx]
			var garrison: int = int(tc.get("garrison", 0))
			if garrison > 0:
				if eh.total_count() < garrison:
					return true
				eh.apply_proportional_losses(garrison)
			tc["owner"] = oid
			tc["garrison"] = 0
		elif target_kind == "mine":
			var obj: Dictionary = _objects[target_idx]
			var g: int = int(obj.get("guard", 0))
			if g > 0:
				if eh.total_count() < g:
					return true
				eh.apply_proportional_losses(g)
				obj["guard"] = 0
			obj["owner"] = oid
		elif target_kind == "treasure":
			var obj2: Dictionary = _objects[target_idx]
			var g2: int = int(obj2.get("guard", 0))
			if g2 > 0:
				if eh.total_count() < g2:
					return true
				eh.apply_proportional_losses(g2)
			eh.gold += int(obj2["gold"])
			_objects.remove_at(target_idx)
	return true


func _check_defeat() -> void:
	# Niederlage: Spieler hat keine Stadt mehr, es gibt aber noch mind.
	# eine KI-Stadt. In Step 1 reicht das als Signal - die feinere
	# Free-for-All-Siegbedingung kommt in Schritt 5.
	if _cities.size() == 0:
		return
	var player_cities: int = 0
	var ai_cities: int = 0
	for c in _cities:
		var ow: int = int(c["owner"])
		if ow == OWNER_HERO:
			player_cities += 1
		elif ow >= OWNER_AI_MIN:
			ai_cities += 1
	if player_cities == 0 and ai_cities > 0:
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
			stats.text = "Level " + str(_hero.level) + "   XP " + str(_hero.xp) + "\nGold " + str(_hero.gold) + "   Armee " + str(_hero.total_count())
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
	_hero.add_units("sword", army_gain)
	var xp_gain: int = kapelle_count * KAPELLE_XP_PER_TURN
	if xp_gain > 0:
		_hero.xp += xp_gain
		if _check_level_up():
			_set_combat("Level-Up durch Kapelle! -> LEVEL %d" % _hero.level)
	# Oekonomie-Snapshot fuer die Status-Zeile, falls die KI-Phase durch
	# einen Pflicht-Kampf suspendiert und erst im Callback finalisiert wird.
	_turn_income = income
	_turn_army_gain = army_gain
	_turn_xp_gain = xp_gain
	_turn_owned = owned
	# Gegner-Zuege: pro KI erst Oekonomie (Einkommen, Gebaeude, Rekruten),
	# dann Bewegung. Reihenfolge entspricht dem Spieler-Flow. Die KIs
	# spielen in Reihenfolge ihrer Indizes, damit die Runden-Logik
	# deterministisch ist. Greift eine KI den Spieler an, suspendiert
	# _advance_ai_phase und wird vom Overlay-Callback fortgesetzt.
	_advance_ai_phase(0)


func _advance_ai_phase(start_idx: int) -> void:
	for ai_idx in range(start_idx, _enemies.size()):
		_enemy_economy_for(ai_idx)
		var done: bool = _run_enemy_turn_for(ai_idx)
		if not done:
			return
		if _game_lost:
			break
	_finalize_turn()


func _finalize_turn() -> void:
	_turn_number += 1
	_recompute_fog_player()
	for i in range(_enemies.size()):
		_recompute_fog_ai(i)
	_recompute_costs()
	_request_redraw()
	_update_labels()
	_set_status("Zug beendet: +%d G, +%d A, +%d XP (%d Staedte)" % [_turn_income, _turn_army_gain, _turn_xp_gain, _turn_owned])
	_check_defeat()
	# Nach der kompletten KI-Phase pruefen, ob die KIs sich gegenseitig
	# ausradiert haben und der Spieler dadurch schon gewonnen hat. Ohne
	# diesen Aufruf wird der Sieg nur getriggert, wenn der Spieler selbst
	# eine Stadt einnimmt oder einen KI-Held besiegt.
	_check_victory()


func _on_ai_attack_result(result: Dictionary, ai_idx: int, next_idx: int) -> void:
	# Callback nach Pflicht-Kampf KI-greift-Spieler-an.
	# outcome == "defeat": Spieler gefallen, Spiel verloren.
	# outcome == "victory": Spieler gewinnt, die angreifende KI ist weg.
	# "flee" ist hier nicht moeglich (allow_flee=false).
	var outcome: String = String(result.get("outcome", "flee"))
	if outcome == "defeat":
		_apply_casualties(result)
		_update_labels()
		_on_battle_defeat()
		return
	# Sieg: Spieler nimmt Verluste hin, angreifende KI ist vernichtet.
	_apply_casualties(result)
	if ai_idx >= 0 and ai_idx < _enemies.size():
		_enemies[ai_idx]["hero"] = null
	_set_combat("Gegner-Held hat dich angegriffen und verloren")
	_update_labels()
	# Restliche KIs noch abarbeiten, dann normale Rundenfinalisierung.
	_advance_ai_phase(next_idx)


func _on_reroll() -> void:
	_start(_seed + 1)


func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/Main.tscn")
