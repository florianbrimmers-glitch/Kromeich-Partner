extends SceneTree

# Headless-Tests fuer den Kampf (M4 Teil 3: Abilities-Minimalset):
#
#   godot --headless --path game/ --script tools/test_battle.gd
#
# Abgedeckt:
#   1. UnitType-Getter (shots_of, has_ability)
#   2. CombatMath-Nahkampfmalus je Ability-Flag:
#      Standard x0.5, melee_penalty_half x0.75, no_melee_penalty x1.0
#   3. Begrenzte Schuesse im TacticalBattleScreen: Schuss dekrementiert,
#      leerer Koecher -> Nahkampf statt Fernkampf (mit Malus).

# Kein class_name am Screen (Android-Export-Falle, siehe Datei-Kopf
# dort) -> preload wie im Spiel selbst.
const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")

var _fails: int = 0


func _init() -> void:
	_test_getters()
	_test_melee_penalty_flags()
	await _test_limited_shots()

	print("")
	if _fails == 0:
		print("Kampf-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Kampf-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_getters() -> void:
	print("== UnitType: Ability-Getter ==")
	_check(UnitType.shots_of("men_archer") == 11, "Armbruster hat 11 Schuss")
	_check(UnitType.shots_of("men_spearman") == 0, "Speertraeger hat 0 Schuss")
	_check(UnitType.has_ability("men_monk", "no_melee_penalty"), "Moench: no_melee_penalty")
	_check(UnitType.has_ability("men_archer", "melee_penalty_half"), "Armbruster: melee_penalty_half")
	_check(not UnitType.has_ability("ork_orc", "no_melee_penalty"), "Orkschuetze: Standard-Malus")
	_check(UnitType.has_ability("bow", "melee_penalty_half"), "Getter folgt Alias (bow -> men_archer)")


func _test_melee_penalty_flags() -> void:
	print("== CombatMath: Nahkampfmalus je Flag ==")
	# Gleicher RNG-Seed vor jedem damage()-Call -> identischer Basiswurf.
	# Damit laesst sich der Malus-Faktor direkt aus dem Verhaeltnis lesen
	# (Toleranz 1 wegen int-Truncation nach der Multiplikation).
	var defender: Dictionary = {"type": "men_spearman", "count": 10, "top_hp": 10}
	var cases: Dictionary = {"ork_orc": 0.5, "men_archer": 0.75, "men_monk": 1.0}
	var rng := RandomNumberGenerator.new()
	for uid in cases.keys():
		var atk: Dictionary = {"type": uid, "count": 10, "top_hp": UnitType.hp_of(String(uid))}
		rng.seed = 99
		var d_no: int = CombatMath.damage(atk, defender, false, 0, 0, rng)
		rng.seed = 99
		var d_pen: int = CombatMath.damage(atk, defender, true, 0, 0, rng)
		var factor: float = float(cases[uid])
		if factor >= 1.0:
			_check(d_pen == d_no, "%s: kein Malus (%d == %d)" % [uid, d_pen, d_no])
		else:
			_check(absf(float(d_pen) - float(d_no) * factor) <= 1.0,
				"%s: Malus x%.2f (%d von %d)" % [uid, factor, d_pen, d_no])
		_check(d_no >= 10, "%s: Basis-Schaden plausibel (%d)" % [uid, d_no])


func _test_limited_shots() -> void:
	print("== TacticalBattleScreen: begrenzte Schuesse ==")
	# Variant statt Control: dynamischer Zugriff auf Screen-Interna.
	var bs = TBS.new()
	bs.size = Vector2(1080, 1920)
	root.add_child(bs)   # _ready baut HUD
	await process_frame  # Node muss im Tree sein (AI-Step nutzt get_tree)
	bs.set_battle({
		"player_stacks": [{"type": "men_archer", "count": 5}],
		"enemy_stacks": [{"type": "elf_treant", "count": 3}],
		"seed": 7, "allow_flee": true,
	})
	# Freie Schusslinie erzwingen - der Test prueft Munition, nicht LOS.
	bs._obstacles = []
	bs._ob_map = {}
	var p: Dictionary = bs._p_stacks[0]
	var e: Dictionary = bs._e_stacks[0]
	_check(int(p["shots_left"]) == 11, "Stack startet mit 11 Schuss (ist %d)" % int(p["shots_left"]))

	# Spieler-Slot aktiv setzen (Turn-Order haengt an Speed) und schiessen.
	_activate_player_slot(bs)
	var e_hp_before: int = _stack_hp(e)
	bs._try_attack_enemy(0)
	_check(int(p["shots_left"]) == 10, "Schuss dekrementiert auf 10 (ist %d)" % int(p["shots_left"]))
	_check(_stack_hp(e) < e_hp_before, "Fernkampf-Schaden angekommen")
	# Verzoegerten KI-Zug (0.3s-Timer in _advance) ausrollen lassen.
	await create_timer(0.6).timeout

	# Koecher leeren: Schuetze muss in den Nahkampf. Adjazent stellen,
	# damit der Melee-Zweig direkt greift.
	p["shots_left"] = 0
	_check(not bs._can_shoot(p), "_can_shoot false bei 0 Schuss")
	p["pos"] = Vector2i(5, 5)
	e["pos"] = Vector2i(6, 5)
	_activate_player_slot(bs)
	bs._build_reachable()
	var e_hp_mid: int = _stack_hp(e)
	bs._try_attack_enemy(0)
	_check(int(p["shots_left"]) == 0, "leerer Koecher bleibt leer")
	_check(_stack_hp(e) < e_hp_mid, "Nahkampf-Angriff trotz 0 Schuss moeglich")

	# Offene Step-Timer ausrollen lassen, dann aufraeumen.
	await create_timer(0.6).timeout
	bs.queue_free()
	await process_frame


# Turn-Order-Slot des Spieler-Stacks aktivieren, egal welche Speed.
func _activate_player_slot(bs) -> void:
	bs._rebuild_order()
	for i in range(bs._turn_order.size()):
		if int(bs._turn_order[i]["side"]) == 0:
			bs._active_slot = i
			return


func _stack_hp(s: Dictionary) -> int:
	if int(s["count"]) <= 0:
		return 0
	var per: int = UnitType.hp_of(String(s["type"]))
	return (int(s["count"]) - 1) * per + int(s["top_hp"])
