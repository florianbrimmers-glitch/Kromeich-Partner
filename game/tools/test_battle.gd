extends SceneTree

# Headless-Tests fuer den Kampf (Abilities, M4 Teil 3 + M6b Teil 1):
#
#   godot --headless --path game/ --script tools/test_battle.gd
#
# Abgedeckt:
#   1. UnitType-Getter (shots_of, has_ability)
#   2. CombatMath-Nahkampfmalus je Ability-Flag:
#      Standard x0.5, melee_penalty_half x0.75, no_melee_penalty x1.0
#   3. Begrenzte Schuesse im TacticalBattleScreen: Schuss dekrementiert,
#      leerer Koecher -> Nahkampf statt Fernkampf (mit Malus).
#   4. Abilities-Regeln als reine Funktionen (Mehrfachangriff, Konter,
#      Verteidigungs-Ignoranz, Jousting/Speertraeger, Regeneration)
#   5. CombatMath.heal (Auffuellen + Wiederbelebung bis Startstaerke)
#   6. Am echten Screen: Vampir-Angriff ohne Konter + Lebensentzug,
#      Greif kontert mehrfach, Flieger ueberquert Steine.

# Kein class_name am Screen (Android-Export-Falle, siehe Datei-Kopf
# dort) -> preload wie im Spiel selbst.
const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")
const Abil := preload("res://scripts/core/Abilities.gd")

var _fails: int = 0


func _init() -> void:
	_test_getters()
	_test_melee_penalty_flags()
	_test_ability_rules()
	_test_heal()
	await _test_limited_shots()
	await _test_ability_combat()

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
	_check(not UnitType.has_ability("elf_treant", "ranged"), "Treant ist kein Schuetze")


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


func _test_ability_rules() -> void:
	print("== Abilities: Regeln als reine Funktionen ==")
	# Mehrfachangriff / Doppelschuss
	_check(Abil.attacks_per_turn("men_crusader", false) == 2, "Kreuzritter: 2 Nahkampf-Angriffe")
	_check(Abil.attacks_per_turn("men_spearman", false) == 1, "Speertraeger: 1 Angriff")
	_check(Abil.attacks_per_turn("elf_archer", true) == 2, "Erz-Elfen: Doppelschuss")
	_check(Abil.attacks_per_turn("elf_archer", false) == 1, "Doppelschuss gilt nicht im Nahkampf")
	# Konter-Regeln
	_check(Abil.retaliation_allowed("men_spearman", "men_griffin", 0), "erster Konter erlaubt")
	_check(not Abil.retaliation_allowed("men_spearman", "men_griffin", 1), "zweiter Konter normal verboten")
	_check(Abil.retaliation_allowed("men_griffin", "men_spearman", 3), "Greif kontert unbegrenzt")
	_check(not Abil.retaliation_allowed("men_griffin", "nec_vampire", 0),
		"Vampir laesst nicht kontern (schlaegt Greif-Regel)")
	# Verteidigungs-Ignoranz
	_check(Abil.def_after_ignore("ork_behemoth", 12) == 9, "Behemoth: def 12 -> 9")
	_check(Abil.def_after_ignore("ork_ogre", 12) == 12, "Oger: def unveraendert")
	# Jousting + Speertraeger-Bonus
	_check(Abil.melee_bonus_pct("men_cavalier", "men_spearman", 0) == 0, "Kavalier ohne Anlauf: kein Bonus")
	_check(Abil.melee_bonus_pct("men_cavalier", "men_spearman", 4) == 20, "Kavalier 4 Felder: +20 %")
	_check(Abil.melee_bonus_pct("ork_wolfrider", "men_spearman", 4) == 8, "Wolfsreiter 4 Felder: +8 %")
	_check(Abil.is_cavalry("men_cavalier") and Abil.is_cavalry("ork_wolfrider"),
		"Jousting-Traeger gelten als Kavallerie")
	_check(not Abil.is_cavalry("men_spearman"), "Speertraeger ist keine Kavallerie")
	_check(Abil.melee_bonus_pct("men_spearman", "men_cavalier", 0) == 50,
		"Speertraeger gegen Kavallerie: +50 %")
	_check(Abil.melee_bonus_pct("men_spearman", "men_monk", 0) == 0,
		"Speertraeger gegen Fussvolk: kein Bonus")
	# Lebensentzug + Regeneration
	_check(Abil.drain_fraction("nec_vampire") > 0.0, "Vampir hat Lebensentzug")
	_check(Abil.drain_fraction("nec_lich") == 0.0, "Lich hat keinen Lebensentzug")
	_check(Abil.regen_hp("elf_treefather", 100, 158) == 58, "Baumvater heilt immer voll auf")
	_check(Abil.regen_hp("elf_treefather", 158, 158) == 0, "voller Stack regeneriert nicht")
	_check(Abil.regen_hp("nec_wight", 20, 25) == 0, "Gespenst ueber 50 %: keine Regeneration")
	_check(Abil.regen_hp("nec_wight", 10, 25) == 15, "Gespenst unter 50 %: heilt voll auf")
	_check(Abil.regen_hp("men_spearman", 1, 10) == 0, "ohne Flag keine Regeneration")
	# Flug
	_check(Abil.ignores_obstacles("men_angel") and Abil.ignores_obstacles("nec_bonedragon"),
		"Engel und Knochendrache fliegen")
	_check(not Abil.ignores_obstacles("men_spearman"), "Speertraeger fliegt nicht")


func _test_heal() -> void:
	print("== CombatMath.heal ==")
	# men_spearman: 10 HP je Einheit. 5 gestartet, 2 tot, oberste auf 3 HP.
	var s: Dictionary = {"type": "men_spearman", "count": 3, "count_start": 5, "top_hp": 3}
	var healed: int = CombatMath.heal(s, 7)
	_check(healed == 7 and int(s["count"]) == 3 and int(s["top_hp"]) == 10,
		"heal fuellt die vorderste Einheit auf (%d HP, top %d)" % [healed, int(s["top_hp"])])
	healed = CombatMath.heal(s, 10)
	_check(int(s["count"]) == 4 and int(s["top_hp"]) == 10, "heal belebt eine Einheit wieder")
	healed = CombatMath.heal(s, 999)
	_check(int(s["count"]) == 5 and healed == 10,
		"heal stoppt bei der Startstaerke (count %d, %d HP)" % [int(s["count"]), healed])
	var dead: Dictionary = {"type": "men_spearman", "count": 0, "count_start": 5, "top_hp": 0}
	_check(CombatMath.heal(dead, 50) == 0 and int(dead["count"]) == 0,
		"vernichteter Stack bleibt tot")


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


func _test_ability_combat() -> void:
	print("== Kampf-Screen: Abilities in Aktion ==")
	var bs = TBS.new()
	bs.size = Vector2(1080, 1920)
	root.add_child(bs)
	await process_frame
	# Vampir (no_retaliation + life_drain) gegen Speertraeger.
	bs.set_battle({
		"player_stacks": [{"type": "nec_vampire", "count": 4}],
		"enemy_stacks": [{"type": "men_spearman", "count": 20}],
		"seed": 11, "allow_flee": true,
	})
	bs._obstacles = []
	bs._ob_map = {}
	var vamp: Dictionary = bs._p_stacks[0]
	var spears: Dictionary = bs._e_stacks[0]
	# Angeschlagen starten, damit der Lebensentzug messbar heilt.
	vamp["top_hp"] = 10
	vamp["pos"] = Vector2i(4, 4)
	spears["pos"] = Vector2i(5, 4)
	_activate_player_slot(bs)
	bs._build_reachable()
	var vamp_hp_before: int = _stack_hp(vamp)
	var spear_hp_before: int = _stack_hp(spears)
	bs._try_attack_enemy(0)
	_check(_stack_hp(spears) < spear_hp_before, "Vampir trifft die Speertraeger")
	_check(_stack_hp(vamp) > vamp_hp_before,
		"Lebensentzug heilt den Vampir (%d -> %d), kein Konter" % [vamp_hp_before, _stack_hp(vamp)])
	_check(int(spears.get("retaliations", 0)) == 0, "no_retaliation verhindert den Konter")
	await create_timer(0.6).timeout

	# Greif (unlimited_retaliations) wird von einem Doppelangriff
	# getroffen -> muss zweimal kontern.
	bs.set_battle({
		"player_stacks": [{"type": "men_crusader", "count": 10}],
		"enemy_stacks": [{"type": "men_griffin", "count": 10}],
		"seed": 5, "allow_flee": true,
	})
	bs._obstacles = []
	bs._ob_map = {}
	var crusader: Dictionary = bs._p_stacks[0]
	var griffin: Dictionary = bs._e_stacks[0]
	crusader["pos"] = Vector2i(3, 3)
	griffin["pos"] = Vector2i(4, 3)
	_activate_player_slot(bs)
	bs._build_reachable()
	bs._try_attack_enemy(0)
	_check(int(griffin.get("retaliations", 0)) == 2,
		"Greif kontert beide Angriffe des Kreuzritters (%d)" % int(griffin.get("retaliations", 0)))
	await create_timer(0.6).timeout

	# Flug: Stein-Wand zwischen Start und Ziel. kind 0 = Stein (blockt).
	var wall: Array = []
	for y in range(bs.GRID_ROWS):
		wall.append({"pos": Vector2i(3, y), "kind": 0})
	bs._obstacles = wall
	bs._ob_map = {}
	for o in wall:
		bs._ob_map[Vector2i(o["pos"])] = int(o["kind"])
	var goal := Vector2i(5, 3)
	var walk: Dictionary = bs._dijkstra_for(Vector2i(1, 3), [], false)
	var fly: Dictionary = bs._dijkstra_for(Vector2i(1, 3), [], true)
	_check(not walk.has(goal), "Fussvolk kommt nicht durch die Steinwand")
	_check(fly.has(goal) and int(fly[goal]) == 4,
		"Flieger ueberquert die Steinwand (Kosten %d)" % int(fly.get(goal, -1)))

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
