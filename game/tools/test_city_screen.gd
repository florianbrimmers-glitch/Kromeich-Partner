extends SceneTree

# Headless-Smoke-Test fuer CityScreen (die View-Logik, nicht das Rendering).
#
#   godot --headless --path game/ --script tools/test_city_screen.gd
#
# Prueft: Layout laedt, Hotspots werden berechnet, Tap auf gebautes
# Militaergebaeude -> recruit_requested, Tap auf ungebautes -> build_requested.
# _draw selbst laeuft headless nicht, daher wird _plots wie im echten Frame
# manuell aus _compute_plots gefuellt.

var _got_recruit: String = ""
var _got_build: String = ""
var _got_plaza: String = ""


func _init() -> void:
	var ok: bool = true

	var cs := CityScreen.new()
	cs.size = Vector2(1080, 1920)
	root.add_child(cs)   # loest _ready aus (Layout + HUD)

	cs.recruit_requested.connect(func(uid: String) -> void: _got_recruit = uid)
	cs.build_requested.connect(func(bid: String) -> void: _got_build = bid)
	cs.plaza_tapped.connect(func(stats: String) -> void: _got_plaza = stats)

	var buildings: Array = [
		{"id": "kaserne",  "name": "Kaserne",  "cost": 500, "effect": "x"},
		{"id": "spaeher",  "name": "Spaeher",  "cost": 300, "effect": "x"},
		{"id": "markt",    "name": "Markt",    "cost": 800, "effect": "x"},
		{"id": "schmiede", "name": "Schmiede", "cost": 700, "effect": "x", "requires": "kaserne"},
		{"id": "reiterei", "name": "Reiterei", "cost": 1000, "effect": "x", "requires": "schmiede"},
		{"id": "wachturm", "name": "Wachturm", "cost": 400, "effect": "x"},
		{"id": "kapelle",  "name": "Kapelle",  "cost": 500, "effect": "x"},
	]
	var hero := Hero.new(Vector2i(0, 0))
	hero.gold = 1000
	var city: Dictionary = {
		"faction": 1, "pos": Vector2i(0, 0),
		"buildings": ["kaserne"], "pools": {"sword": 3},
	}
	var ctx: Dictionary = {
		"city": city, "hero": hero, "buildings": buildings,
		"faction_names": ["Waldvolk", "Menschen", "Totenreich", "Orks"],
		"faction_colors": [Color.GREEN, Color.GOLD, Color.PURPLE, Color.RED],
		"weekly_growth": {"kaserne": 8, "schmiede": 4, "reiterei": 2},
		"calendar": "T1 W1 M1 J1", "hero_here": true,
	}
	cs.open(ctx)

	# 1) Layout geladen?
	ok = _check(cs._layout.size() == 7, "Layout hat 7 Eintraege (ist %d)" % cs._layout.size()) and ok

	# 2) Hotspots berechnet?
	var plots: Array = cs._compute_plots(cs._stage_rect())
	cs._plots = plots
	ok = _check(plots.size() == 7, "7 Hotspots berechnet (ist %d)" % plots.size()) and ok

	# 3) Tap auf gebaute Kaserne -> recruit "sword"
	var kaserne: Dictionary = _find(plots, "kaserne")
	ok = _check(not kaserne.is_empty(), "Kaserne-Plot existiert") and ok
	if not kaserne.is_empty():
		cs._handle_tap(kaserne["center"])
		ok = _check(_got_recruit == "sword",
			"Tap Kaserne -> recruit 'sword' (war '%s')" % _got_recruit) and ok

	# 4) Tap auf ungebauten Markt -> build "markt"
	var markt: Dictionary = _find(plots, "markt")
	if not markt.is_empty():
		cs._handle_tap(markt["center"])
		ok = _check(_got_build == "markt",
			"Tap Markt -> build 'markt' (war '%s')" % _got_build) and ok

	# 5) Treffer-Test ausserhalb aller Rauten -> nichts
	_got_build = ""
	_got_recruit = ""
	cs._handle_tap(Vector2(5, 5))
	ok = _check(_got_build == "" and _got_recruit == "",
		"Tap ins Leere loest nichts aus") and ok

	# 6) Plaza-Tap: emittiert plaza_tapped mit Stadt-Statistik
	var stage := cs._stage_rect()
	var plaza_pos := stage.position + Vector2(
		CityScreen.PLAZA_NORM_X * stage.size.x,
		CityScreen.PLAZA_NORM_Y * stage.size.y)
	_got_build = ""
	_got_recruit = ""
	_got_plaza = ""
	cs._handle_tap(plaza_pos)
	ok = _check(_got_build == "" and _got_recruit == "",
		"Plaza-Tap loest weder build noch recruit aus") and ok
	ok = _check(_got_plaza.contains("Menschen") and _got_plaza.contains("gebaut"),
		"Plaza-Tap emittiert Stadt-Statistik (war '%s')" % _got_plaza) and ok

	print("")
	if ok:
		print("CityScreen-Smoke-Test: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("CityScreen-Smoke-Test: FEHLGESCHLAGEN")
		quit(1)


func _check(cond: bool, msg: String) -> bool:
	print(("[OK]   " if cond else "[FAIL] ") + msg)
	return cond


func _find(plots: Array, bid: String) -> Dictionary:
	for p in plots:
		if String(p["id"]) == bid:
			return p
	return {}
