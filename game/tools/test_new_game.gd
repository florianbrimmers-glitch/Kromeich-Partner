extends SceneTree

# Headless-Test fuer M2 (Fraktionswahl + Seed):
#
#   godot --headless --path game/ --script tools/test_new_game.gd
#
# 4 Fraktionen x 3 Seeds: WorldMap starten mit Wunsch-Fraktion, pruefen
# dass _player_faction stimmt, die Startstadt der Fraktion gehoert und
# ein simulierter Tag ohne Fehler durchlaeuft. Zusaetzlich: Zufalls-
# Fraktion (-1) startet weiterhin, und derselbe Seed liefert dieselbe
# Karte unabhaengig von der Fraktionswahl (Determinismus-Invariante).

var _fails: int = 0


func _init() -> void:
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm := scene.instantiate()
	root.add_child(wm)
	await process_frame

	var owner_hero: int = wm.get("OWNER_HERO") if wm.get("OWNER_HERO") != null else 0

	for fid in range(4):
		for seed_val in [11, 4711, 987654]:
			wm.call("_start", seed_val, fid)
			var got_faction: int = wm.get("_player_faction")
			_check(got_faction == fid,
				"Fraktion %d/Seed %d: _player_faction == %d (ist %d)" % [fid, seed_val, fid, got_faction])
			var start_city_ok := false
			for c in (wm.get("_cities") as Array):
				if int(c["owner"]) == owner_hero:
					start_city_ok = int(c["faction"]) == fid
					break
			_check(start_city_ok, "Fraktion %d/Seed %d: Startstadt gehoert Fraktion" % [fid, seed_val])
			wm.call("_on_end_turn")
			await process_frame

	# Zufalls-Fraktion (-1): startet und hat irgendeine gueltige Fraktion.
	wm.call("_start", 11, -1)
	var f_rand: int = wm.get("_player_faction")
	_check(f_rand >= 0 and f_rand <= 3, "Zufalls-Fraktion liefert 0..3 (ist %d)" % f_rand)

	# Determinismus: gleicher Seed -> gleiche Stadt-Positionen, egal ob
	# Fraktion 0 oder 3 gewaehlt wurde.
	wm.call("_start", 2024, 0)
	var pos_a: Array = []
	for c in (wm.get("_cities") as Array):
		pos_a.append(c["pos"])
	wm.call("_start", 2024, 3)
	var pos_b: Array = []
	for c in (wm.get("_cities") as Array):
		pos_b.append(c["pos"])
	_check(str(pos_a) == str(pos_b), "Seed 2024: Stadt-Layout unabhaengig von Fraktionswahl")

	wm.queue_free()
	await process_frame

	print("")
	if _fails == 0:
		print("Neues-Spiel-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Neues-Spiel-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)
