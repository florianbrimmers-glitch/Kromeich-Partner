extends SceneTree

# KI-Langzeit-Smoke-Test (ab M3 in CI):
#
#   godot --headless --path game/ --script tools/test_ai_smoke.gd
#
# WorldMap headless, 30 Tage durchspielen. Erwartung: kein Crash, die
# Oekonomie laeuft (irgendeine KI hat Gold verdient oder Gebaeude
# gebaut), Kalender stimmt. Faengt Regressionen, bei denen eine
# Oekonomie-/Einheiten-Aenderung die KI-Pfade vergisst.

var _fails: int = 0


# KEINE Abschluss-Marken in dieser Suite: sie ist vollstaendig linear, es
# gibt keine _test*-Funktionen. Ein Abbruch in _init selbst erreicht `quit()`
# nicht und laesst den CI-Schritt in den Timeout laufen - unschoen, aber
# sichtbar. Eine Marke waere hier ein Check, der immer gruen ist (It. 31).
func _init() -> void:
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm := scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 999, 2)

	var days: int = 30
	for i in range(days):
		wm.call("_on_end_turn")
		await process_frame

	var turn: int = wm.get("_turn_number")
	# Nicht auf ==30 pruefen: greift eine KI den Spieler an, oeffnet ein
	# Pflicht-Kampf-Overlay und suspendiert die Runde bis zum (headless
	# nie kommenden) Spieler-Input. 10+ Tage reichen als Oekonomie-Smoke.
	_check(turn >= 10, "mind. 10 Tage simuliert (turn=%d)" % turn)

	# Mindestens eine KI lebt noch ODER das Spiel ist entschieden.
	var enemies: Array = wm.get("_enemies")
	var alive: int = 0
	var built_total: int = 0
	for e in enemies:
		if e["hero"] != null:
			alive += 1
	var owner_ai_min: int = wm.get("OWNER_AI_MIN")
	for c in (wm.get("_cities") as Array):
		if int(c["owner"]) >= owner_ai_min:
			built_total += (c["buildings"] as Array).size()
	var game_over: bool = bool(wm.get("_game_won")) or bool(wm.get("_game_lost"))
	_check(alive > 0 or game_over, "KIs leben (%d) oder Spiel entschieden" % alive)
	_check(built_total > 0 or game_over, "KI-Staedte haben gebaut (%d Gebaeude)" % built_total)

	# Autosave existiert nach 30 Tagen (Trigger in _finalize_turn).
	var save_ok: bool = FileAccess.file_exists("user://saves/autosave.json") or game_over
	_check(save_ok, "Autosave nach Simulation vorhanden")

	wm.queue_free()
	await process_frame

	print("")
	if _fails == 0:
		print("KI-Smoke-Test: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("KI-Smoke-Test: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)
