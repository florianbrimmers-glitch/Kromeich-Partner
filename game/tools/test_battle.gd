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
const Fx := preload("res://scripts/core/StatusFx.gd")
const Mor := preload("res://scripts/core/Morale.gd")

var _fails: int = 0


func _init() -> void:
	_test_getters()
	_test_melee_penalty_flags()
	_test_ability_rules()
	_test_heal()
	_test_status_rules()
	_test_morale_rules()
	await _test_limited_shots()
	await _test_ability_combat()
	await _test_status_combat()
	await _test_morale_combat()

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
	# Pass 10b: Regeneration heilt 25 % der max-HP, nicht mehr voll.
	_check(Abil.regen_hp("elf_treefather", 100, 158) == 40,
		"Baumvater heilt 25 %% der max-HP (40 von 158)")
	_check(Abil.regen_hp("elf_treefather", 150, 158) == 8,
		"Regeneration heilt nie ueber das Maximum hinaus")
	_check(Abil.regen_hp("elf_treefather", 158, 158) == 0, "voller Stack regeneriert nicht")
	_check(Abil.regen_hp("nec_wight", 20, 25) == 0, "Gespenst ueber 50 %: keine Regeneration")
	_check(Abil.regen_hp("nec_wight", 10, 25) == 7, "Gespenst unter 50 %: heilt 7 von 25")
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


func _test_status_rules() -> void:
	print("== StatusFx: Regeln + Dauer ==")
	var s: Dictionary = {"type": "men_spearman", "count": 5, "top_hp": 10, "status": {}}
	Fx.add(s, Fx.DISEASED, 3)
	_check(Fx.has(s, Fx.DISEASED), "Status wird gesetzt")
	_check(Fx.att_mod(s) == -2 and Fx.def_mod(s) == -2, "Krankheit: -2 Angriff/-2 Verteidigung")
	Fx.add(s, Fx.DISEASED, 1)
	_check(int(s["status"][Fx.DISEASED]) == 3, "neuer Treffer verkuerzt die Dauer nicht")
	for i in range(3):
		Fx.tick(s)
	_check(not Fx.has(s, Fx.DISEASED), "Status laeuft nach 3 Runden ab")

	var c: Dictionary = {"type": "men_spearman", "count": 5, "top_hp": 10, "status": {}}
	Fx.add(c, Fx.CURSED, 2)
	_check(abs(Fx.dealt_factor(c) - 0.75) < 0.001, "Fluch: 25 % weniger Schaden")
	_check(abs(Fx.taken_factor(c) - 1.0) < 0.001, "Fluch aendert erlittenen Schaden nicht")
	Fx.add(c, Fx.AGED, 2)
	_check(abs(Fx.taken_factor(c) - 1.25) < 0.001, "Alterung: 25 % mehr erlittener Schaden")

	var b: Dictionary = {"type": "men_spearman", "count": 5, "top_hp": 10, "status": {}}
	Fx.add(b, Fx.BLINDED, 1)
	_check(Fx.blocks_turn(b) and Fx.blocks_move(b), "Blendung nimmt Zug und Bewegung")
	_check(Fx.wake_on_melee(b), "Nahkampf-Treffer weckt den geblendeten Stack")
	_check(not Fx.blocks_turn(b), "geweckt = wieder handlungsfaehig")
	Fx.add(b, Fx.ROOTED, 1)
	_check(Fx.blocks_move(b) and not Fx.blocks_turn(b),
		"Verwurzelt blockt nur Bewegung, nicht den Angriff")
	_check(Fx.marker_text(b) == "W", "Marker fuer verwurzelt ist W")

	# Wuerfel-Regeln: Krankheit trifft immer, Fluch nur manchmal.
	var rng := RandomNumberGenerator.new()
	rng.seed = 3
	var t1: Dictionary = {"type": "men_spearman", "count": 5, "top_hp": 10, "status": {}}
	_check(Fx.apply_on_hit("nec_zombie", t1, rng).has(Fx.DISEASED),
		"Zombie steckt immer an (disease_on_hit)")
	var hits: int = 0
	for i in range(400):
		var t2: Dictionary = {"type": "men_spearman", "count": 5, "top_hp": 10, "status": {}}
		if not Fx.apply_on_hit("nec_blackknight", t2, rng).is_empty():
			hits += 1
	_check(hits > 10 and hits < 100,
		"Schwarzritter verflucht in ~10 %% der Treffer (%d von 400)" % hits)
	var dead: Dictionary = {"type": "men_spearman", "count": 0, "top_hp": 0, "status": {}}
	_check(Fx.apply_on_hit("nec_zombie", dead, rng).is_empty(),
		"vernichteter Stack bekommt keinen Status")
	_check(Fx.aoe_fraction("nec_lich") > 0.0 and Fx.aoe_fraction("men_archer") == 0.0,
		"nur der Lich hat eine Todeswolke")


func _test_morale_rules() -> void:
	print("== Moral + Glueck: Regeln ==")
	# Fraktions-Mix (Nutzer-Entscheidung: HoMM3-streng)
	_check(Mor.morale_for([_st("men_spearman"), _st("men_archer")]) == 1,
		"reine Menschen-Armee: +1")
	_check(Mor.morale_for([_st("men_spearman"), _st("elf_dwarf")]) == 0,
		"zwei Fraktionen: 0")
	_check(Mor.morale_for([_st("men_spearman"), _st("elf_dwarf"), _st("ork_goblin")]) == -1,
		"drei Fraktionen: -1")
	_check(Mor.morale_for([_st("men_spearman"), _st("elf_dwarf"),
		_st("ork_goblin"), _st("nec_skeleton")]) == -3,
		"vier Fraktionen inkl. Untote: -2 und -1 fuer den Untoten-Bruch")
	_check(Mor.morale_for([_st("men_spearman"), _st("nec_skeleton")]) == -1,
		"Menschen + Totenreich: -1 (zwei Fraktionen 0, Untoten-Malus -1)")
	_check(Mor.morale_for([_st("nec_skeleton"), _st("nec_zombie")]) == 1,
		"reine Untoten-Armee: +1, kein Mix-Malus")
	_check(Mor.morale_for([_st("men_angel"), _st("men_spearman")]) == 2,
		"Engel-Aura hebt die reine Armee auf +2")
	_check(Mor.morale_for([]) == 0, "leere Armee: 0")
	# Tote Stacks zaehlen nicht mehr mit.
	var dead_mix: Array = [_st("men_spearman"), _st("elf_dwarf", 0)]
	_check(Mor.morale_for(dead_mix) == 1, "gefallene Stacks zaehlen nicht mehr mit")

	# Immunitaet + Wahrscheinlichkeiten
	# Pass 10: Untote sind nur gegen SCHLECHTE Moral immun (sonst verlieren
	# sie dauerhaft die Extrazuege, die jede reine Armee bekommt).
	_check(Mor.immune_to_bad_morale("nec_skeleton")
		and not Mor.immune_to_bad_morale("men_spearman"),
		"undead-Flag schuetzt vor schlechter Moral")
	_check(abs(Mor.extra_turn_chance(2) - 0.20) < 0.001, "Moral +2: 20 % Extrazug")
	_check(Mor.extra_turn_chance(-2) == 0.0, "negative Moral gibt keinen Extrazug")
	_check(abs(Mor.freeze_chance(-1) - 0.10) < 0.001, "Moral -1: 10 % Zugverlust")
	_check(Mor.freeze_chance(1) == 0.0, "positive Moral verliert keinen Zug")

	# Glueck: Verteilung ueber viele Wuerfe (10 % je Punkt).
	var rng := RandomNumberGenerator.new()
	rng.seed = 17
	_check(Mor.luck_factor(0, rng) == 1.0, "ohne Glueck immer Faktor 1")
	var lucky: int = 0
	for i in range(400):
		if Mor.luck_factor(3, rng) > 1.0:
			lucky += 1
	_check(lucky > 60 and lucky < 180,
		"Glueck 3: ~30 %% Volltreffer (%d von 400)" % lucky)
	var unlucky: int = 0
	for i in range(400):
		if Mor.luck_factor(-2, rng) < 1.0:
			unlucky += 1
	_check(unlucky > 30 and unlucky < 130,
		"Pech -2: ~20 %% Pechschlaege (%d von 400)" % unlucky)

	# Erzfeind-Bonus (hates:necro_tier7)
	_check(Abil.hate_bonus_pct("men_angel", "nec_bonedragon") == 50,
		"Engel gegen Knochendrache: +50 %")
	_check(Abil.hate_bonus_pct("men_angel", "nec_skeleton") == 0,
		"Engel gegen Skelett: kein Hass-Bonus")
	_check(Abil.hate_bonus_pct("men_spearman", "nec_bonedragon") == 0,
		"ohne hates-Flag kein Bonus")
	_check(Abil.melee_bonus_pct("men_angel", "nec_bonedragon", 0) == 50,
		"Hass-Bonus fliesst in melee_bonus_pct")


# Kleiner Stack-Helfer fuer die Moral-Tests.
func _st(uid: String, count: int = 5) -> Dictionary:
	return {"type": uid, "count": count, "top_hp": UnitType.hp_of(uid)}


func _test_morale_combat() -> void:
	print("== Kampf-Screen: Moral + Glueck in Aktion ==")
	var bs = TBS.new()
	bs.size = Vector2(1080, 1920)
	root.add_child(bs)
	await process_frame
	# Gemischte Spieler-Armee (Menschen + Totenreich) -> Moral -1.
	bs.set_battle({
		"player_stacks": [
			{"type": "men_spearman", "count": 10},
			{"type": "nec_skeleton", "count": 10},
		],
		"enemy_stacks": [{"type": "ork_goblin", "count": 10}],
		"seed": 4, "allow_flee": true, "player_luck": 3,
	})
	bs._obstacles = []
	bs._ob_map = {}
	_check(bs._p_morale == -1, "gemischte Armee: Moral -1 (ist %d)" % bs._p_morale)
	_check(bs._e_morale == 1, "reine Ork-Armee: Moral +1 (ist %d)" % bs._e_morale)
	_check(bs._p_luck == 3, "Glueck aus dem Kontext uebernommen")

	# Moral -3 erzwingen: der lebende Stack muss Zuege verlieren, der
	# untote nie. Ueber viele _step-Versuche pruefen.
	bs._p_morale = -3
	var living: Dictionary = bs._p_stacks[0]
	var undead: Dictionary = bs._p_stacks[1]
	var lost_living: int = 0
	var lost_undead: int = 0
	for i in range(60):
		for target in [living, undead]:
			var idx: int = 0 if target == living else 1
			bs._log.clear()
			# Slot des gewuenschten Stacks aktivieren.
			bs._rebuild_order()
			for k in range(bs._turn_order.size()):
				if int(bs._turn_order[k]["side"]) == 0 and int(bs._turn_order[k]["idx"]) == idx:
					bs._active_slot = k
					break
			bs._step()
			for line in bs._log:
				if String(line).contains("keine Moral"):
					if idx == 0:
						lost_living += 1
					else:
						lost_undead += 1
	_check(lost_living > 0, "lebender Stack verliert bei Moral -3 Zuege (%d)" % lost_living)
	_check(lost_undead == 0, "untoter Stack verliert nie den Zug (%d)" % lost_undead)

	# Glueck 3: unter vielen Schlaegen muss ein Volltreffer auftauchen.
	bs.set_battle({
		"player_stacks": [{"type": "men_spearman", "count": 20}],
		"enemy_stacks": [{"type": "elf_treant", "count": 20}],
		"seed": 9, "allow_flee": true, "player_luck": 3,
	})
	bs._obstacles = []
	bs._ob_map = {}
	var atk: Dictionary = bs._p_stacks[0]
	var def_stack: Dictionary = bs._e_stacks[0]
	var crits: int = 0
	for i in range(60):
		bs._dmg(atk, def_stack, false)
		if bs._last_luck > 1.0:
			crits += 1
	_check(crits > 0, "Glueck 3 erzeugt Volltreffer (%d von 60)" % crits)
	# Pass 10: Untote wuerfeln Glueck wie alle anderen - ihre Immunitaet
	# gilt nur gegen schlechte Moral.
	bs._p_stacks[0] = {"type": "nec_skeleton", "count": 20, "count_start": 20,
		"top_hp": UnitType.hp_of("nec_skeleton"), "side": 0, "pos": Vector2i(1, 1),
		"status": {}, "tiles_moved": 0, "retaliations": 0}
	var undead_crits: int = 0
	for i in range(60):
		bs._dmg(bs._p_stacks[0], def_stack, false)
		if bs._last_luck > 1.0:
			undead_crits += 1
	_check(undead_crits > 0,
		"untoter Stack profitiert von Glueck (%d Volltreffer von 60)" % undead_crits)

	bs.queue_free()
	await process_frame


func _test_status_combat() -> void:
	print("== Kampf-Screen: Status-Effekte in Aktion ==")
	var bs = TBS.new()
	bs.size = Vector2(1080, 1920)
	root.add_child(bs)
	await process_frame
	# Zombie (disease_on_hit, 100 %) trifft Speertraeger -> krank.
	bs.set_battle({
		"player_stacks": [{"type": "nec_zombie", "count": 10}],
		"enemy_stacks": [{"type": "men_spearman", "count": 10}],
		"seed": 21, "allow_flee": true,
	})
	bs._obstacles = []
	bs._ob_map = {}
	var zombie: Dictionary = bs._p_stacks[0]
	var spears: Dictionary = bs._e_stacks[0]
	zombie["pos"] = Vector2i(4, 4)
	spears["pos"] = Vector2i(5, 4)
	_activate_player_slot(bs)
	bs._build_reachable()
	bs._try_attack_enemy(0)
	_check(Fx.has(spears, Fx.DISEASED), "Zombie-Treffer macht die Speertraeger krank")
	await create_timer(0.6).timeout

	# Betaeubter Stack verliert seinen Zug. Geprueft wird die Meldung im
	# Kampf-Log, nicht der Slot-Index: nach dem Ueberspringen laeuft die
	# Zug-Kette weiter (KI-Zug, Rundenwechsel) und der Index kann
	# zufaellig wieder auf dem alten Wert landen.
	Fx.add(zombie, Fx.STUNNED, 1)
	_activate_player_slot(bs)
	bs._log.clear()
	bs._step()
	var skipped: bool = false
	for line in bs._log:
		if String(line).contains("Zug verloren") and String(line).contains(Fx.STUNNED):
			skipped = true
	_check(skipped, "betaeubter Stack wird uebersprungen (Log: %s)" % str(bs._log))
	Fx.clear(zombie, Fx.STUNNED)
	Fx.add(zombie, Fx.ROOTED, 1)
	_activate_player_slot(bs)
	bs._build_reachable()
	_check(bs._reachable.size() == 1 and bs._reachable.has(Vector2i(zombie["pos"])),
		"verwurzelt: nur das eigene Feld erreichbar (%d Felder)" % bs._reachable.size())
	Fx.clear(zombie, Fx.ROOTED)
	# Dauer laeuft mit dem Rundenwechsel ab.
	Fx.add(zombie, Fx.CURSED, 1)
	bs._next_round()
	_check(not Fx.has(zombie, Fx.CURSED), "Rundenwechsel laesst Status ablaufen")
	await create_timer(0.6).timeout

	# Lich-Todeswolke: Nachbar des Ziels nimmt halben Schaden mit.
	bs.set_battle({
		"player_stacks": [{"type": "nec_lich", "count": 8}],
		"enemy_stacks": [
			{"type": "men_spearman", "count": 20},
			{"type": "men_archer", "count": 20},
		],
		"seed": 33, "allow_flee": true,
	})
	bs._obstacles = []
	bs._ob_map = {}
	var lich: Dictionary = bs._p_stacks[0]
	var t_main: Dictionary = bs._e_stacks[0]
	var t_neigh: Dictionary = bs._e_stacks[1]
	lich["pos"] = Vector2i(1, 4)
	t_main["pos"] = Vector2i(6, 4)
	t_neigh["pos"] = Vector2i(6, 5)   # direkt neben dem Ziel
	var neigh_hp: int = _stack_hp(t_neigh)
	_activate_player_slot(bs)
	bs._build_reachable()
	bs._try_attack_enemy(0)
	_check(_stack_hp(t_neigh) < neigh_hp,
		"Todeswolke trifft den Nachbar-Stack mit (%d -> %d)" % [neigh_hp, _stack_hp(t_neigh)])

	bs.queue_free()
	await process_frame


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
