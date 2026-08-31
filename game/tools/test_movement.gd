extends SceneTree

# Headless-Tests fuer die Bewegungskosten und die Wegfindung (M7 Teil 2):
#
#   godot --headless --path game/ --script tools/test_movement.gd
#
# Abgedeckt:
#   1. Movement: Kostentabelle, Skalierung, Wegfindungs-Abschlag
#   2. Pathfinder: laeuft ueber dasselbe Modul (inklusive Sumpf - den
#      kannten die alten Literale dort NICHT)
#   3. Weltkarten-Dijkstra: Wegfindung macht Wald und Sumpf billiger und
#      erweitert die Reichweite, laesst flaches Gelaende aber unberuehrt
#   4. Save-Migration v3 -> v4: alte Punkte werden mitskaliert
#
# Jede Test-Funktion setzt am Ende eine Marke - ein Laufzeitfehler bricht
# in GDScript nur die Funktion ab, die Suite bliebe sonst gruen.

const Move := preload("res://scripts/core/Movement.gd")
const Skills := preload("res://scripts/core/HeroSkills.gd")
const SaveLib := preload("res://scripts/core/SaveManager.gd")

var _fails: int = 0
var _done: Array = []


func _init() -> void:
	_test_table()
	_test_pathfinder()
	await _test_worldmap()
	_test_migration()

	# Abschluss-Marken: die Soll-Liste kommt aus der Methodentabelle des
	# Skripts selbst (It. 31, vorher eine Liste von Hand). Damit faellt
	# zweierlei auf: eine Funktion, die mitten drin abbricht, UND eine neue
	# Testfunktion, die niemand aus _init aufruft.
	var missing: Array = []
	for m in get_method_list():
		var mn: String = String(m["name"])
		if mn.begins_with("_test") and not _done.has(mn):
			missing.append(mn)
	_check(missing.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)"
		% str(missing))

	print("")
	if _fails == 0:
		print("Bewegungs-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Bewegungs-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_table() -> void:
	print("== Movement: Kostentabelle ==")
	_check(Move.UNIT == 4, "ein flaches Feld kostet UNIT (%d)" % Move.UNIT)
	_check(Move.base_cost(0) == Move.UNIT and Move.base_cost(4) == Move.UNIT,
		"Gras und Sand sind flach")
	_check(Move.base_cost(1) == Move.UNIT * 2 and Move.base_cost(5) == Move.UNIT * 2,
		"Wald und Sumpf kosten doppelt")
	_check(Move.base_cost(2) < 0 and Move.base_cost(3) < 0,
		"Wasser und Berg sind unpassierbar")
	_check(not Move.is_passable(2) and Move.is_passable(5),
		"is_passable folgt der Tabelle (Sumpf ja, Wasser nein)")

	# Wegfindung greift NUR den Aufschlag ab.
	_check(Move.step_cost(1, 0) == 8, "Wald ohne Skill: 8")
	_check(Move.step_cost(1, 1) == 7, "Wegfindung I: 7 (ein Viertel des Aufschlags weg)")
	_check(Move.step_cost(1, 2) == 6, "Wegfindung II: 6")
	_check(Move.step_cost(1, 3) == 4, "Wegfindung III: wie flaches Gelaende")
	var flat_same := true
	for tier in range(4):
		if Move.step_cost(0, tier) != Move.UNIT:
			flat_same = false
	_check(flat_same, "flaches Gelaende wird durch den Skill NICHT billiger")
	_check(Move.step_cost(2, 3) < 0, "auch mit Stufe 3 bleibt Wasser unpassierbar")
	# Ueber die Stufe hinaus darf nichts kippen (clampi im Modul).
	_check(Move.step_cost(1, 99) == 4, "unsinnige Stufe wird gedeckelt")

	_check(Move.tiles_of(40) == 10, "40 Punkte sind 10 Felder")
	_check(Move.tiles_of(3) == 0, "Restpunkte unter einem Feld zaehlen nicht")

	# Die Tabelle im Skill-Modul muss zur Wirkung passen.
	_check(Skills.pathfinding_tier({"pathfinding": 2}) == 2,
		"HeroSkills liefert die Stufe, nicht den Prozentwert")
	_check(Skills.value_of("pathfinding", 3) == 100,
		"Stufe 3 steht in der Tabelle als 100 %")

	# MapGen spiegelt dieselbe Tabelle (eine Quelle, drei Nutzer).
	_check(MapGen.terrain_cost(1) == Move.step_cost(1, 0),
		"MapGen.terrain_cost kommt aus Movement")
	_check(MapGen.is_passable(5) and not MapGen.is_passable(3),
		"MapGen.is_passable ebenfalls")
	_done.append("_test_table")


# Kleine Handkarte: Zeile 0 ist Gras, Zeile 1 Wald, Zeile 2 Sumpf.
func _hand_map() -> Dictionary:
	var w: int = 6
	var h: int = 3
	var tiles: Array = []
	for y in range(h):
		for x in range(w):
			tiles.append(0 if y == 0 else (1 if y == 1 else 5))
	return {"width": w, "height": h, "tiles": tiles}


func _test_pathfinder() -> void:
	print("")
	print("== Pathfinder ueber dasselbe Modul ==")
	var m: Dictionary = _hand_map()
	var c0: Dictionary = Pathfinder.compute_costs(m, Vector2i(0, 0))
	_check(int(c0.get(Vector2i(0, 0), -1)) == 0, "Start kostet nichts")
	_check(int(c0.get(Vector2i(1, 0), -1)) == Move.UNIT,
		"ein Grasfeld kostet UNIT (ist %d)" % int(c0.get(Vector2i(1, 0), -1)))
	# Regression: die alten Literale in Pathfinder.gd kannten den Sumpf
	# nicht - Zeile 2 war damit komplett unerreichbar.
	_check(c0.has(Vector2i(0, 2)), "Sumpf ist erreichbar (frueher nicht)")
	_check(int(c0.get(Vector2i(0, 2), -1)) == Move.UNIT * 4,
		"Wald + Sumpf = 2 x 8 (ist %d)" % int(c0.get(Vector2i(0, 2), -1)))

	var c3: Dictionary = Pathfinder.compute_costs(m, Vector2i(0, 0), 3)
	_check(int(c3.get(Vector2i(0, 2), -1)) == Move.UNIT * 2,
		"mit Wegfindung III nur noch 2 x 4 (ist %d)" % int(c3.get(Vector2i(0, 2), -1)))
	_check(int(c3.get(Vector2i(1, 0), -1)) == Move.UNIT,
		"das Grasfeld bleibt gleich teuer")
	_done.append("_test_pathfinder")


func _test_worldmap() -> void:
	print("")
	print("== Weltkarte: Reichweite mit und ohne Wegfindung ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 4711, 1)
	await process_frame

	var hero = wm.get("_hero")
	_check(int(hero.max_mp) == int(wm.get("BASE_MAX_MP")),
		"Held startet mit BASE_MAX_MP (%d)" % int(hero.max_mp))
	_check(Move.tiles_of(int(hero.max_mp)) == 10,
		"das sind 10 flache Felder wie vor der Umstellung (sind %d)"
		% Move.tiles_of(int(hero.max_mp)))

	var start: Vector2i = hero.position
	var plain: Dictionary = wm.call("_dijkstra", start, true, 0)
	var skilled: Dictionary = wm.call("_dijkstra", start, true, 3)
	_check(plain.size() > 0 and skilled.size() > 0, "beide Laeufe liefern Felder")

	# Kein Feld darf mit Skill TEURER sein, und mindestens eines billiger -
	# sonst haette der Skill auf der echten Karte keine Wirkung.
	var worse: int = 0
	var better: int = 0
	for key in plain.keys():
		var a: int = int(plain[key])
		var b: int = int(skilled.get(key, 999999))
		if b > a:
			worse += 1
		elif b < a:
			better += 1
	_check(worse == 0, "kein Feld wird durch den Skill teurer (%d)" % worse)
	_check(better > 0, "%d Felder werden billiger" % better)

	# Reichweite: was mit den Punkten des Helden erreichbar ist.
	var reach_plain: int = 0
	var reach_skilled: int = 0
	for key in plain.keys():
		if int(plain[key]) <= int(hero.max_mp):
			reach_plain += 1
	for key in skilled.keys():
		if int(skilled[key]) <= int(hero.max_mp):
			reach_skilled += 1
	_check(reach_skilled > reach_plain,
		"Wegfindung III erweitert die Reichweite (%d -> %d Felder)"
		% [reach_plain, reach_skilled])

	# Der Screen zieht die Stufe aus den Skills des Helden - ohne das
	# waere das Modul verdrahtet, aber wirkungslos.
	hero.skills = {"pathfinding": 3}
	wm.call("_recompute_costs")
	var live: Dictionary = wm.get("_costs")
	var same := true
	for key in live.keys():
		if int(live[key]) != int(skilled.get(key, -1)):
			same = false
			break
	_check(same and live.size() == skilled.size(),
		"_recompute_costs benutzt die Helden-Stufe (%d Felder)" % live.size())
	hero.skills = {}

	wm.queue_free()
	await process_frame
	_done.append("_test_worldmap")


func _test_migration() -> void:
	print("")
	print("== Save-Migration v3 -> v4 -> v5 ==")
	var v3: Dictionary = {
		"save_version": 3,
		"hero": {"position": {"x": 2, "y": 3}, "mp": 7, "max_mp": 10, "army": {},
			"wallet": {"gold": 700, "wood": 3}},
		"enemies": [{"hero": {"mp": 4, "max_mp": 10, "army": {}}}, {"hero": null}],
		"cities": [],
	}
	var mig: Dictionary = SaveLib.migrate(v3)
	_check(int(mig["save_version"]) == SaveLib.SAVE_VERSION,
		"migrate hebt auf v%d" % SaveLib.SAVE_VERSION)
	# Seit v5 (M13a) liegt der Spieler-Held in "heroes[0]".
	var h: Dictionary = (mig["heroes"] as Array)[0] as Dictionary
	_check(int(h["mp"]) == 28 and int(h["max_mp"]) == 40,
		"Punkte des Helden skaliert (mp %d, max %d)" % [int(h["mp"]), int(h["max_mp"])])
	var eh: Dictionary = (mig["enemies"] as Array)[0]["hero"] as Dictionary
	_check(int(eh["mp"]) == 16, "KI-Held ebenfalls (ist %d)" % int(eh["mp"]))
	_check((mig["enemies"] as Array)[1]["hero"] == null,
		"gefallener KI-Held (null) toleriert")
	# v4 -> v5: der Beutel wandert aus dem Helden zum Spieler.
	_check(not mig.has("hero"), "alter Schluessel 'hero' ist weg")
	_check(int(mig.get("active_hero", -1)) == 0, "active_hero gesetzt")
	var purse: Dictionary = mig.get("purse", {}) as Dictionary
	_check(int(purse.get("gold", 0)) == 700 and int(purse.get("wood", 0)) == 3,
		"Beutel aus dem Helden gehoben (%s)" % str(purse))
	# Die KI behaelt ihren Beutel IM Helden - jede KI hat genau einen.
	_check(not mig.has("ai_purse"), "fuer die KI wird kein Beutel angelegt")

	# Ganze Kette ab v1: die Fixture aus M4-Zeiten muss durchlaufen.
	var f := FileAccess.open("res://tools/fixtures/save_v1.json", FileAccess.READ)
	_check(f != null, "Fixture save_v1.json vorhanden")
	if f != null:
		var raw: Variant = JSON.parse_string(f.get_as_text())
		_check(typeof(raw) == TYPE_DICTIONARY, "Fixture ist lesbar")
		if typeof(raw) == TYPE_DICTIONARY:
			var mp_before: int = int(((raw as Dictionary)["hero"] as Dictionary).get("mp", 0))
			var m2: Dictionary = SaveLib.migrate(raw as Dictionary)
			_check(int(m2["save_version"]) == SaveLib.SAVE_VERSION,
				"v1-Fixture landet auf v%d" % SaveLib.SAVE_VERSION)
			var h2: Dictionary = (m2["heroes"] as Array)[0] as Dictionary
			_check(int(h2["mp"]) == mp_before * SaveLib.MP_SCALE_3_TO_4,
				"und ihre Punkte sind mitskaliert (%d -> %d)"
				% [mp_before, int(h2["mp"])])
			_check((m2.get("purse", {}) as Dictionary).has("gold"),
				"und der Beutel ist angelegt (%s)" % str(m2.get("purse", {})))
			# Eine ZWEITE Migration darf nichts mehr aendern.
			var m3: Dictionary = SaveLib.migrate(m2)
			_check(int(((m3["heroes"] as Array)[0] as Dictionary)["mp"]) == int(h2["mp"]),
				"nochmal migrieren aendert nichts (idempotent)")
			_check((m3["heroes"] as Array).size() == 1,
				"und legt keinen zweiten Helden an")
	_done.append("_test_migration")
