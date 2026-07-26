extends SceneTree

# Headless-Tests fuer Save/Load (M1):
#
#   godot --headless --path game/ --script tools/test_save_load.gd
#
# Drei Ebenen:
#   1. SaveCodec-Roundtrips (inkl. Float-Inputs, wie JSON sie liefert)
#   2. SaveManager Datei-Roundtrip in user:// + Korrupt-Datei-Verhalten
#   3. Szenen-Roundtrip: WorldMap starten, 2 Tage simulieren,
#      capture -> restore -> capture, JSON-Vergleich
#
# WICHTIG: laeuft OHNE Autoloads (SceneTree-Script) - deshalb werden alle
# SaveManager-Funktionen statisch ueber preload aufgerufen. Genau das ist
# auch der Grund, warum das Spiel selbst SaveLib-preloads nutzt.

const SaveLib := preload("res://scripts/core/SaveManager.gd")

var _fails: int = 0


func _init() -> void:
	_test_codec()
	_test_file_roundtrip()
	await _test_scene_roundtrip()

	print("")
	if _fails == 0:
		print("Save/Load-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Save/Load-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_codec() -> void:
	print("== SaveCodec ==")
	_check(SaveCodec.v2i(Vector2i(3, -7)) == [3, -7], "v2i -> [3,-7]")
	_check(SaveCodec.to_v2i([3.0, -7.0]) == Vector2i(3, -7), "to_v2i mit Floats (JSON)")
	_check(SaveCodec.to_v2i(null) == SaveCodec.V2I_NONE, "to_v2i(null) -> V2I_NONE")
	_check(SaveCodec.to_v2i([1]) == SaveCodec.V2I_NONE, "to_v2i(kaputt) -> V2I_NONE")
	var ia := SaveCodec.int_array([1.0, 2.0, 3.0])
	_check(ia == [1, 2, 3] and ia[0] is int, "int_array castet Floats")
	var idd := SaveCodec.int_dict({"sword": 5.0})
	_check(idd["sword"] == 5 and idd["sword"] is int, "int_dict castet Werte")

	print("== Hero to_dict/from_dict ==")
	var h := Hero.new(Vector2i(4, 9), 14)
	h.gold = 321
	h.add_units("men_spearman", 5)
	h.add_units("men_archer", 2)
	h.xp = 77
	h.level = 3
	h.mp = 6
	var d := h.to_dict()
	# JSON-Zyklus simulieren (Floats!)
	var d2: Dictionary = JSON.parse_string(JSON.stringify(d))
	var h2 := Hero.from_dict(d2)
	_check(JSON.stringify(h2.to_dict()) == JSON.stringify(d),
		"Hero-Roundtrip ueber JSON identisch")
	var h3 := Hero.from_dict({})
	_check(h3.level == 1 and h3.gold == 0, "Hero.from_dict({}) -> Defaults")

	# Save-v2: Alt-Unit-IDs werden nicht mehr pro Lookup kanonisiert,
	# sondern EINMAL beim Laden migriert (v1 -> v2).
	print("== SaveManager migrate v1 -> v2 ==")
	var old_save: Dictionary = {
		"save_version": 1, "seed": 1,
		"hero": {"army": {"sword": 3, "men_spearman": 2}},
		"cities": [{"pools": {"skelett": 4}}],
		"enemies": [{"hero": null}, {"hero": {"army": {"oger": 2}}}],
	}
	var mig: Dictionary = SaveLib.migrate(old_save)
	_check(int(mig["save_version"]) == SaveLib.SAVE_VERSION,
		"migrate hebt auf v%d" % SaveLib.SAVE_VERSION)
	var ma: Dictionary = (mig["hero"] as Dictionary)["army"]
	_check(int(ma.get("men_spearman", 0)) == 5 and not ma.has("sword"),
		"migrate merged Alt- und Neu-Keys (sword -> men_spearman)")
	var mpools: Dictionary = ((mig["cities"] as Array)[0] as Dictionary)["pools"]
	_check(int(mpools.get("nec_skeleton", 0)) == 4,
		"migrate mappt Stadt-Pools (skelett -> nec_skeleton)")
	var meh: Dictionary = ((mig["enemies"] as Array)[1] as Dictionary)["hero"]
	_check(int((meh["army"] as Dictionary).get("ork_orc", 0)) == 2,
		"migrate mappt KI-Armeen (oger -> ork_orc), null-Held toleriert")

	print("== DeterministicRng State ==")
	var r := DeterministicRng.new(42)
	r.next_int(0, 100)
	var s := r.get_state_string()
	var a1 := r.next_int(0, 1000000)
	var r2 := DeterministicRng.new(1)
	r2.set_state_string(s)
	var a2 := r2.next_int(0, 1000000)
	_check(a1 == a2, "RNG-State-String stellt Sequenz wieder her")


func _test_file_roundtrip() -> void:
	print("== SaveManager Datei ==")
	var state := {"seed": 1337, "hero": {"gold": 5}, "fog_player": [1, 2]}
	var err := SaveLib.write_save(state)
	_check(err == OK, "write_save OK (err=%d)" % err)
	_check(SaveLib.has_autosave(), "has_autosave nach write")
	var back := SaveLib.read_save()
	_check(int(back.get("seed", 0)) == 1337, "seed ueberlebt Roundtrip")
	_check(int(back.get("save_version", 0)) == SaveLib.SAVE_VERSION, "save_version gesetzt")
	# Korrupte Datei -> {} statt Crash
	var f := FileAccess.open(SaveLib.AUTOSAVE_PATH, FileAccess.WRITE)
	f.store_string("{kaputt")
	f.close()
	_check(SaveLib.read_save().is_empty(), "korruptes Save -> {}")
	SaveLib.delete_autosave()
	_check(not SaveLib.has_autosave(), "delete_autosave entfernt Datei")


func _test_scene_roundtrip() -> void:
	print("== Szenen-Roundtrip ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm := scene.instantiate()
	root.add_child(wm)
	await process_frame
	# Deterministisch neu starten und 2 Tage simulieren.
	wm.call("_start", 1337)
	wm.call("_on_end_turn")
	await process_frame
	wm.call("_on_end_turn")
	await process_frame
	var s1: Dictionary = wm.call("_capture_state")
	# JSON-Zyklus (so kommt es von der Platte zurueck).
	var s1_json: Dictionary = JSON.parse_string(JSON.stringify(s1))
	var ok_restore: bool = wm.call("_restore_state", s1_json)
	_check(ok_restore, "_restore_state akzeptiert eigenen Snapshot")
	var s2: Dictionary = wm.call("_capture_state")
	var j1 := JSON.stringify(s1)
	var j2 := JSON.stringify(s2)
	_check(j1 == j2, "capture -> restore -> capture identisch (%d vs %d Zeichen)" % [j1.length(), j2.length()])
	# Negativ: leeres Dict wird abgelehnt.
	_check(not wm.call("_restore_state", {}), "_restore_state({}) -> false")

	# Eingechecktes Version-Fixture: jede spaetere Format-Aenderung MUSS
	# alte Saves weiter laden (tolerante Defaults oder migrate()-Schritt).
	# Bricht dieser Check, stirbt ein echtes Handy-Save da draussen.
	print("== Fixture-Kompatibilitaet ==")
	var ff := FileAccess.open("res://tools/fixtures/save_v1.json", FileAccess.READ)
	_check(ff != null, "fixtures/save_v1.json vorhanden")
	if ff != null:
		var fixture: Variant = JSON.parse_string(ff.get_as_text())
		_check(typeof(fixture) == TYPE_DICTIONARY, "Fixture ist gueltiges JSON")
		var migrated: Dictionary = SaveLib.migrate(fixture as Dictionary)
		_check(wm.call("_restore_state", migrated), "Fixture v1 laedt nach migrate()")
	wm.queue_free()
	await process_frame
