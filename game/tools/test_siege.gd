extends SceneTree

# Headless-Tests fuer die Belagerung (M9):
#
#   godot --headless --path game/ --script tools/test_siege.gd
#
# Abgedeckt:
#   1. Mauer-Kind in BattleObstacles (blockt Bewegung + Schusslinie)
#   2. Segment-Reihe mit Tor-Luecke an der erwarteten Stelle
#   3. Pathing: Fussvolk kommt nicht durch, Flieger schon
#   4. Katapult schlaegt nach zwei Runden eine Bresche, Feld wird frei
#   5. Verteidiger-Bonus wirkt nur solange ein Segment steht
#   6. Pfeilturm macht Schaden, Zyklop kann ein Segment einschlagen
#   7. Stadt-Wache besteht aus Einheiten der Stadt-Fraktion

const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")
const Obst := preload("res://scripts/core/BattleObstacles.gd")

var _fails: int = 0
var _done: Array = []


func _init() -> void:
	_test_wall_kind()
	_test_wall_layout()
	await _test_pathing_and_breach()
	await _test_defender_bonus_and_tower()
	await _test_faction_guards()

	# Abschluss-Marken (It. 31): jede _test*-Funktion setzt am Ende eine
	# Marke. Ein Laufzeitfehler bricht in GDScript nur die betroffene
	# Funktion ab - die Suite laeuft weiter und meldet gruen. Genau so hat
	# It. 24 einen halben Test verschluckt (geratener Funktionsname). Die
	# Liste kommt aus der Methodentabelle des Skripts selbst, damit auch
	# eine NEUE Testfunktion auffaellt, die niemand aufruft.
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
		print("Belagerungs-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Belagerungs-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_wall_kind() -> void:
	print("== BattleObstacles: Mauer-Kind ==")
	_check(Obst.blocks_move(Obst.KIND_WALL), "Mauer blockt Bewegung")
	_check(Obst.blocks_los(Obst.KIND_WALL), "Mauer blockt Schusslinie")
	_check(not Obst.halves_damage(Obst.KIND_WALL), "Mauer halbiert nicht (sie blockt ganz)")
	_check(Obst.display_name(Obst.KIND_WALL) == "Mauer", "Anzeigename")
	_check(Obst.WALL_SEGMENT_HP == 2, "Segment haelt 2 Katapult-Treffer")
	_done.append("_test_wall_kind")


func _test_wall_layout() -> void:
	print("== Mauer-Reihe mit Tor ==")
	var walls: Array = Obst.siege_walls(10, 8)
	_check(walls.size() == 7, "8 Reihen minus Tor = 7 Segmente (ist %d)" % walls.size())
	var col: int = Obst.wall_col(10)
	var gate: int = Obst.gate_row(8)
	var same_col: bool = true
	var gate_free: bool = true
	for w in walls:
		var p: Vector2i = Vector2i(w["pos"])
		if p.x != col:
			same_col = false
		if p.y == gate:
			gate_free = false
		if int(w["hp"]) != Obst.WALL_SEGMENT_HP:
			_check(false, "Segment ohne Start-HP")
	_check(same_col, "alle Segmente in Spalte %d" % col)
	_check(gate_free, "Tor-Reihe %d bleibt frei" % gate)
	# Die Mauer muss VOR der Verteidiger-Startreihe (cols-2) liegen.
	_check(col < 10 - 2, "Mauer liegt vor der Verteidiger-Reihe")
	_done.append("_test_wall_layout")


func _siege_screen(player: Array, enemy: Array, tower: int = 0):
	var bs = TBS.new()
	# Effekte aus (It. 17): mit fx_speed > 0 wartet die Zugkette auf
	# Animationen, die headless nie ankommen -> Test haengt.
	bs.fx_speed = 0.0
	bs.size = Vector2(1080, 1920)
	root.add_child(bs)
	bs.set_battle({
		"player_stacks": player, "enemy_stacks": enemy,
		"seed": 99, "allow_flee": true, "siege": true, "tower_dmg": tower,
	})
	return bs


func _test_pathing_and_breach() -> void:
	print("== Pathing + Bresche ==")
	var bs = _siege_screen(
		[{"type": "men_spearman", "count": 10}, {"type": "men_griffin", "count": 5}],
		[{"type": "nec_skeleton", "count": 10}])
	await process_frame
	var col: int = Obst.wall_col(bs.GRID_COLS)
	var gate: int = Obst.gate_row(bs.GRID_ROWS)
	_check(bs._wall_hp.size() == bs.GRID_ROWS - 1,
		"Screen kennt %d Segmente (ist %d)" % [bs.GRID_ROWS - 1, bs._wall_hp.size()])
	_check(bs._siege and bs._walls_standing(), "Belagerungs-Modus aktiv")

	# Ein Feld hinter der Mauer, NICHT in der Tor-Reihe: Fussvolk muesste
	# aussen herum, Flieger fliegt direkt drueber.
	var behind := Vector2i(col + 1, gate + 2)
	var walk: Dictionary = bs._dijkstra_for(Vector2i(1, gate + 2), [], false)
	var fly: Dictionary = bs._dijkstra_for(Vector2i(1, gate + 2), [], true)
	_check(int(fly.get(behind, 999)) <= 8, "Flieger erreicht das Feld hinter der Mauer")
	_check(int(walk.get(behind, 999)) > int(fly.get(behind, 999)),
		"Fussvolk braucht den Umweg durchs Tor (%d vs %d Schritte)" % [
			int(walk.get(behind, 999)), int(fly.get(behind, 999))])

	# Schusslinie: quer durch die Mauer blockiert.
	var mod: Dictionary = Obst.line_modifier(bs._obstacles,
		Vector2i(1, gate + 2), Vector2i(col + 3, gate + 2))
	_check(bool(mod["blocked"]), "Mauer blockiert die Schusslinie")

	# Katapult: zwei Treffer auf dasselbe (tor-naechste) Segment. Welches
	# das ist, entscheidet der Screen - der Test vergleicht deshalb die
	# Schluesselmengen statt eine Position anzunehmen.
	var keys_before: Array = bs._wall_hp.keys().duplicate()
	var before: int = keys_before.size()
	bs._catapult_shot()
	_check(bs._wall_hp.size() == before, "erster Treffer beschaedigt nur")
	bs._catapult_shot()
	_check(bs._wall_hp.size() == before - 1,
		"zweiter Treffer schlaegt die Bresche (%d Segmente)" % bs._wall_hp.size())
	var breach := Vector2i(-1, -1)
	for k in keys_before:
		if not bs._wall_hp.has(k):
			breach = k
			break
	_check(breach.x >= 0, "Bresche gefunden (%s)" % str(breach))
	_check(abs(breach.y - gate) <= 1, "Bresche liegt am Tor (Reihe %d, Tor %d)" % [breach.y, gate])
	_check(not bs._ob_map.has(breach), "Bresche-Feld ist aus der Hindernis-Karte verschwunden")
	var after_breach: Dictionary = bs._dijkstra_for(Vector2i(1, breach.y), [], false)
	_check(after_breach.has(breach), "Fussvolk kann durch die Bresche laufen")
	bs.queue_free()
	await process_frame
	_done.append("_test_pathing_and_breach")


func _test_defender_bonus_and_tower() -> void:
	print("== Verteidiger-Bonus + Pfeilturm + Zyklop ==")
	var bs = _siege_screen(
		[{"type": "ork_cyclops", "count": 4}],
		[{"type": "nec_skeleton", "count": 20}], 12)
	await process_frame
	var atk: Dictionary = bs._p_stacks[0]
	var def_stack: Dictionary = bs._e_stacks[0]
	# Gleicher Seed vor jedem Wurf: mit stehender Mauer muss der Schaden
	# gegen den Verteidiger kleiner sein als ohne.
	bs._rng.seed = 7
	var with_wall: int = bs._dmg(atk, def_stack, false)
	bs._wall_hp.clear()
	bs._rng.seed = 7
	var without_wall: int = bs._dmg(atk, def_stack, false)
	_check(with_wall < without_wall,
		"Mauer schuetzt den Verteidiger (%d statt %d Schaden)" % [with_wall, without_wall])

	# Turm feuert nur mit stehender Mauer.
	var hp_before: int = _stack_hp(atk)
	bs._tower_shot()
	_check(_stack_hp(atk) == hp_before, "ohne Mauer schweigt der Turm")
	bs = _siege_screen([{"type": "men_spearman", "count": 20}],
		[{"type": "nec_skeleton", "count": 20}], 12)
	await process_frame
	var p0: Dictionary = bs._p_stacks[0]
	var hp2: int = _stack_hp(p0)
	bs._tower_shot()
	_check(_stack_hp(p0) < hp2, "Pfeilturm trifft den Angreifer (%d -> %d)" % [hp2, _stack_hp(p0)])

	# Zyklop schlaegt selbst ein Segment ein (attack_wall).
	bs = _siege_screen([{"type": "ork_cyclops", "count": 3}],
		[{"type": "nec_skeleton", "count": 10}])
	await process_frame
	var cy: Dictionary = bs._p_stacks[0]
	var seg: Vector2i = Vector2i(-1, -1)
	for pos in bs._wall_hp.keys():
		seg = pos
		break
	var hp_seg: int = int(bs._wall_hp[seg])
	_check(bs._try_attack_wall(cy, seg), "Zyklop greift die Mauer an")
	_check(int(bs._wall_hp.get(seg, 0)) == hp_seg - 1, "Segment verliert einen Punkt")
	# Eine Einheit ohne das Flag darf das nicht.
	var spear: Dictionary = {"type": "men_spearman", "count": 5, "count_start": 5,
		"top_hp": 10, "side": 0, "pos": Vector2i(1, 1), "status": {}}
	_check(not bs._try_attack_wall(spear, seg), "ohne attack_wall keine Mauer-Attacke")
	bs.queue_free()
	await process_frame
	_done.append("_test_defender_bonus_and_tower")


func _test_faction_guards() -> void:
	print("== Stadt-Wache nach Fraktion ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 4242)
	for fid in range(4):
		var stacks: Array = wm.call("_build_enemy_stacks", "Stadtwache", 20, fid)
		var all_ok: bool = not stacks.is_empty()
		for s in stacks:
			if UnitType.faction_of(String(s["type"])) != fid:
				all_ok = false
		_check(all_ok, "Fraktion %d: Wache aus eigenen Einheiten (%s)" % [
			fid, str(stacks.map(func(s): return String(s["type"])))])
	# Ohne Fraktion bleibt die alte generische Synthese.
	var generic: Array = wm.call("_build_enemy_stacks", "Monster", 8, -1)
	_check(not generic.is_empty(), "Monster-Synthese ohne Fraktion laeuft weiter")
	# Belagerungs-Kontext: Mauer an/aus.
	var walled: Dictionary = wm.call("_siege_ctx_for",
		{"faction": 2, "buildings": ["mauer", "wachturm"]})
	_check(bool(walled["siege"]) and int(walled["tower_dmg"]) > 0,
		"Stadt mit Mauer+Wachturm: Belagerung mit starkem Turm")
	var open_city: Dictionary = wm.call("_siege_ctx_for",
		{"faction": 1, "buildings": ["kaserne"]})
	_check(not bool(open_city["siege"]) and int(open_city["tower_dmg"]) == 0,
		"Stadt ohne Mauer: keine Belagerung")
	wm.queue_free()
	await process_frame
	_done.append("_test_faction_guards")


func _stack_hp(s: Dictionary) -> int:
	if int(s["count"]) <= 0:
		return 0
	var per: int = UnitType.hp_of(String(s["type"]))
	return (int(s["count"]) - 1) * per + int(s["top_hp"])
