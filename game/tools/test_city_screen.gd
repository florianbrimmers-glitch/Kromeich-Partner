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

	# Kosten als Dictionaries wie in den echten BUILDINGS (int-Kosten
	# lassen _plot_subline/_plot_sub_color am Typ-Check scheitern).
	var buildings: Array = [
		{"id": "kaserne",  "name": "Kaserne",  "cost": {"gold": 500}, "effect": "x"},
		{"id": "spaeher",  "name": "Spaeher",  "cost": {"gold": 300}, "effect": "x"},
		{"id": "markt",    "name": "Markt",    "cost": {"gold": 800}, "effect": "x"},
		{"id": "schmiede", "name": "Schmiede", "cost": {"gold": 700}, "effect": "x", "requires": "kaserne"},
		{"id": "reiterei", "name": "Reiterei", "cost": {"gold": 1000}, "effect": "x", "requires": "schmiede"},
		{"id": "wachturm", "name": "Wachturm", "cost": {"gold": 400}, "effect": "x"},
		{"id": "kapelle",  "name": "Kapelle",  "cost": {"gold": 500}, "effect": "x"},
		{"id": "zitadelle", "name": "Zitadelle", "cost": {"gold": 2500}, "effect": "x", "requires": ["reiterei", "mauer"]},
	]
	var hero := Hero.new(Vector2i(0, 0))
	hero.gold = 1000
	var city: Dictionary = {
		"faction": 1, "pos": Vector2i(0, 0),
		"buildings": ["kaserne"], "pools": {"men_spearman": 3},
	}
	var ctx: Dictionary = {
		"city": city, "hero": hero, "buildings": buildings,
		"faction_names": ["Waldvolk", "Menschen", "Totenreich", "Orks"],
		"faction_colors": [Color.GREEN, Color.GOLD, Color.PURPLE, Color.RED],
		"calendar": "T1 W1 M1 J1", "hero_here": true,
	}
	cs.open(ctx)

	# 1) Layout geladen?
	# Layout enthaelt alle Gebaeude-Hotspots inkl. mauer+zitadelle -> 9.
	ok = _check(cs._layout.size() == 9, "Layout hat 9 Eintraege (ist %d)" % cs._layout.size()) and ok

	# 2) Hotspots berechnet?
	var plots: Array = cs._compute_plots(cs._stage_rect())
	cs._plots = plots
	ok = _check(plots.size() == 8, "8 Hotspots berechnet (ist %d)" % plots.size()) and ok

	# 3) Tap auf gebaute Kaserne -> Rekrut-Panel mit T1+T2 der Menschen,
	#    Zeilen-Button emittiert recruit_requested.
	var kaserne: Dictionary = _find(plots, "kaserne")
	ok = _check(not kaserne.is_empty(), "Kaserne-Plot existiert") and ok
	if not kaserne.is_empty():
		cs._handle_tap(kaserne["center"])
		ok = _check(cs._recruit_panel != null and cs._recruit_panel.visible,
			"Tap Kaserne oeffnet Rekrut-Panel") and ok
		ok = _check(cs._recruit_buttons.size() == 2
			and cs._recruit_buttons.has("men_spearman")
			and cs._recruit_buttons.has("men_archer"),
			"Panel zeigt 2 Einheiten (Speertraeger+Armbruster)") and ok
		if cs._recruit_buttons.has("men_spearman"):
			(cs._recruit_buttons["men_spearman"] as Button).pressed.emit()
			ok = _check(_got_recruit == "men_spearman",
				"Panel-Button -> recruit 'men_spearman' (war '%s')" % _got_recruit) and ok
		if cs._recruit_panel != null:
			cs._recruit_panel.visible = false

	# 3b) Zitadelle: ungebaut -> build_requested; Subline nennt BEIDE
	#     fehlenden Voraussetzungen (requires darf Array sein).
	var zit: Dictionary = _find(plots, "zitadelle")
	ok = _check(not zit.is_empty(), "Zitadelle-Plot existiert") and ok
	if not zit.is_empty():
		cs._handle_tap(zit["center"])
		ok = _check(_got_build == "zitadelle",
			"Tap Zitadelle -> build 'zitadelle' (war '%s')" % _got_build) and ok
	var zit_sub: String = cs._plot_subline(buildings[7], false, 1)
	ok = _check(zit_sub.contains("Reiterei") and zit_sub.contains("Mauer"),
		"Zitadelle-Subline nennt Reiterei+Mauer (war '%s')" % zit_sub) and ok

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

	# 7) Layout-Wahl + Beschriftungen kollidieren nicht (Iteration 16).
	#    Die Test-Stadt ist Fraktion 1 (Menschen). Ob deren gemalter
	#    Hintergrund im Build liegt, entscheidet welches Layout gilt -
	#    geprueft wird deshalb die Konsistenz, nicht ein fixes Layout.
	var painted: bool = cs._has_painted_bg()
	var expected: Dictionary = cs._layout if painted else cs._layout_plain
	ok = _check(cs._active_layout() == expected,
		"Layout passt zum Hintergrund (gemalt=%s)" % str(painted)) and ok
	ok = _check(not cs._layout_plain.is_empty(),
		"Plain-Layout aus city_layout.json geladen (%d Plots)" % cs._layout_plain.size()) and ok

	# Beschriftungs-Boxen: zwei Zeilen ab center + hh + 18, Breite = hw*1.9.
	# Ueberlappen sich zwei Boxen, laufen die Texte im Spiel ineinander -
	# genau der Fehler aus dem Nutzer-Screenshot.
	var boxes: Array = []
	for p2 in plots:
		var c2: Vector2 = p2["center"]
		var hw2: float = float(p2["hw"])
		var hh2: float = float(p2["hh"])
		boxes.append({
			"id": String(p2["id"]),
			"rect": Rect2(Vector2(c2.x - hw2 * 0.95, c2.y + hh2 + 18.0),
				Vector2(hw2 * 1.9, CityScreen.LABEL_BLOCK_H)),
		})
	var clashes: Array = []
	for i in range(boxes.size()):
		for j in range(i + 1, boxes.size()):
			if (boxes[i]["rect"] as Rect2).intersects(boxes[j]["rect"] as Rect2):
				clashes.append("%s/%s" % [boxes[i]["id"], boxes[j]["id"]])
	ok = _check(clashes.is_empty(),
		"keine Text-Kollisionen im aktiven Layout (%s)" % str(clashes)) and ok

	# Dasselbe fuer das jeweils ANDERE Layout - beide muessen sauber sein,
	# je nachdem ob eine Fraktion einen gemalten Hintergrund hat.
	var other: Dictionary = cs._layout_plain if painted else cs._layout
	var saved: Dictionary = cs._layout
	cs._layout = other
	cs._layout_plain = other
	var plots2: Array = cs._compute_plots(cs._stage_rect())
	var clashes2: Array = []
	for i2 in range(plots2.size()):
		for j2 in range(i2 + 1, plots2.size()):
			var a2: Dictionary = plots2[i2]
			var b2: Dictionary = plots2[j2]
			var ra := Rect2(Vector2(a2["center"].x - float(a2["hw"]) * 0.95,
				a2["center"].y + float(a2["hh"]) + 18.0),
				Vector2(float(a2["hw"]) * 1.9, CityScreen.LABEL_BLOCK_H))
			var rb := Rect2(Vector2(b2["center"].x - float(b2["hw"]) * 0.95,
				b2["center"].y + float(b2["hh"]) + 18.0),
				Vector2(float(b2["hw"]) * 1.9, CityScreen.LABEL_BLOCK_H))
			if ra.intersects(rb):
				clashes2.append("%s/%s" % [String(a2["id"]), String(b2["id"])])
	cs._layout = saved
	ok = _check(clashes2.is_empty(),
		"keine Text-Kollisionen im zweiten Layout (%s)" % str(clashes2)) and ok

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
