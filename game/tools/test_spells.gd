extends SceneTree

# Headless-Tests fuer die Zauber (M8 Teil 1):
#
#   godot --headless --path game/ --script tools/test_spells.gd
#
# Abgedeckt:
#   1. HeroSpells laedt spells.json; Kosten, Stufen und Schulen stimmen mit
#      der Datendatei ueberein, und die Schadens-/Heilformeln decken sich
#      mit den Effekt-Strings ("dmg=15+15*power")
#   2. Mana aus Wissen, Zauberstufe aus Weisheit
#   3. Bekannte Zauber: nur Umgesetztes, nur Fraktions-Schulen, nur bis zur
#      erlaubten Stufe
#   4. Status-Zauber wirken ueber StatusFx (inkl. Geschwindigkeit)
#   5. Kampf: Zauberbuch, Mana-Abzug, ein Zauber pro Runde, Schaden,
#      Heilung, Flaechenschaden, Restmana im Ergebnis
#   6. Weltkarte: Mana startet voll, regeneriert pro Tag, Deckel aus Wissen

const Spl := preload("res://scripts/core/HeroSpells.gd")
const Skills := preload("res://scripts/core/HeroSkills.gd")
const Fx := preload("res://scripts/core/StatusFx.gd")
const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")

var _fails: int = 0
var _done: Array = []
# GDScript-Lambdas fangen lokale Variablen als KOPIE. Ein
# "func(r): got = r" auf eine lokale Variable schreibt also ins Nichts -
# das Kampf-Ergebnis muss in einem Feld landen.
var _last_result: Dictionary = {}


func _init() -> void:
	_test_data()
	_test_known()
	_test_status()
	await _test_battle()
	await _test_worldmap()
	await _test_adventure()
	await _test_fire_ward()

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
		print("Zauber-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Zauber-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_data() -> void:
	print("== spells.json + Formeln ==")
	_check(Spl.all_defs().size() == 21, "21 Zauber geladen (sind %d)" % Spl.all_defs().size())

	# Jeder umgesetzte Zauber muss in der JSON stehen - sonst zeigt das
	# Zauberbuch etwas an, das es nicht gibt.
	var unknown: Array = []
	for sid in Spl.IMPLEMENTED:
		if Spl.def_of(String(sid)).is_empty():
			unknown.append(String(sid))
	_check(unknown.is_empty(), "alle umgesetzten Zauber stehen in der JSON (%s)" % str(unknown))

	# Und jeder braucht einen deutschen Namen.
	var nameless: Array = []
	for sid2 in Spl.IMPLEMENTED:
		if not Spl.NAMES.has(String(sid2)):
			nameless.append(String(sid2))
	_check(nameless.is_empty(), "jeder umgesetzte Zauber hat einen Namen (%s)" % str(nameless))

	# Formeln gegen die Effekt-Strings zurueckrechnen. Die Zahlen liegen im
	# Modul als Tabelle; laufen Tabelle und JSON auseinander, faellt es hier
	# auf und nicht erst im Spiel.
	var f := FileAccess.open("res://data/spells.json", FileAccess.READ)
	var raw: Dictionary = JSON.parse_string(f.get_as_text()) as Dictionary
	var checked: int = 0
	var bad: Array = []
	for entry in (raw["spells"] as Array):
		var e: Dictionary = entry as Dictionary
		var sid3: String = String(e["id"])
		if not Spl.DAMAGE_SPELLS.has(sid3) and not Spl.HEAL_SPELLS.has(sid3):
			continue
		# "dmg=15+15*power" bzw. "heal_dmg=25+5*power"
		var eff: String = String(e["effect"])
		var rhs: String = eff.substr(eff.find("=") + 1)
		var plus: int = rhs.find("+")
		var star: int = rhs.find("*")
		if plus < 0 or star < 0:
			continue
		var base_json: int = int(rhs.substr(0, plus))
		var per_json: int = int(rhs.substr(plus + 1, star - plus - 1))
		var base_mod: int = int(Spl.damage_of(sid3, 0)) if Spl.DAMAGE_SPELLS.has(sid3) \
			else int(Spl.heal_of(sid3, 0))
		var per_mod: int = (int(Spl.damage_of(sid3, 1)) - base_mod) if Spl.DAMAGE_SPELLS.has(sid3) \
			else (int(Spl.heal_of(sid3, 1)) - base_mod)
		checked += 1
		if base_mod != base_json or per_mod != per_json:
			bad.append("%s: Modul %d+%d != JSON %d+%d"
				% [sid3, base_mod, per_mod, base_json, per_json])
	_check(bad.is_empty(), "%d Formeln deckungsgleich mit der JSON (%s)" % [checked, str(bad)])
	_check(checked == 4, "vier Formel-Zauber geprueft (sind %d)" % checked)

	_check(Spl.damage_of("fire_bolt", 3) == 15 + 45,
		"Feuerblitz mit Zauberkraft 3 = 60 (ist %d)" % Spl.damage_of("fire_bolt", 3))
	_check(Spl.heal_of("heal", 4) == 25 + 20, "Heilen mit Zauberkraft 4 = 45")
	_check(Spl.is_aoe("fireball") and not Spl.is_aoe("fire_bolt"),
		"nur Feuerball trifft die Flaeche")
	_check(Spl.is_friendly_target("heal") and not Spl.is_friendly_target("curse"),
		"Zielseite kommt aus der JSON")

	print("")
	print("== Mana und Zauberstufe ==")
	_check(Spl.max_mana(0) == Spl.BASE_MANA, "ohne Wissen der Grundstock (%d)" % Spl.max_mana(0))
	_check(Spl.max_mana(5) == Spl.BASE_MANA + 50, "Wissen 5 gibt +50 Mana")
	_check(Spl.max_spell_level(0) == 1, "ohne Weisheit nur Stufe 1")
	_check(Spl.max_spell_level(2) == 3, "Weisheit II erlaubt Stufe 3")
	_check(Spl.max_spell_level(3) == 4, "Weisheit III erlaubt Stufe 4")
	# Stufe 5 bleibt unerreichbar - genau deshalb sind Implosion und
	# Armageddon nicht umgesetzt.
	_check(Spl.max_spell_level(9) == 4, "kein Weg auf Stufe 5 (Relikt fehlt)")
	_done.append("_test_data")


func _test_known() -> void:
	print("")
	print("== Bekannte Zauber ==")
	# Schulen aus factions.json, ueber die ID nachgeschlagen: die JSON hat
	# eine andere Reihenfolge als FACTION_DIRS.
	var men: Array = Spl.schools_for_faction(1)
	_check(men.has("ordnung") and men.has("licht"),
		"Menschen: Ordnung + Licht (ist %s)" % str(men))
	var nec: Array = Spl.schools_for_faction(2)
	_check(nec.has("tod") and nec.has("chaos"),
		"Totenreich: Tod + Chaos (ist %s)" % str(nec))

	# Ohne Weisheit nur Stufe 1 - und nur aus den eigenen Schulen.
	var k_men: Array = Spl.known(men, 0)
	var wrong_school: Array = []
	var too_high: Array = []
	for sid in k_men:
		if not men.has(Spl.school_of(String(sid))):
			wrong_school.append(String(sid))
		if Spl.level_of(String(sid)) > 1:
			too_high.append(String(sid))
	_check(wrong_school.is_empty(), "keine fremde Schule (%s)" % str(wrong_school))
	_check(too_high.is_empty(), "keine zu hohe Stufe (%s)" % str(too_high))
	_check(k_men.has("heal") and k_men.has("haste"),
		"Menschen kennen Heilen und Eile (ist %s)" % str(k_men))
	_check(not k_men.has("magic_arrow"), "Menschen kennen keinen Chaos-Zauber")

	# Weisheit oeffnet hoehere Stufen.
	var k2: Array = Spl.known(men, 2)
	_check(k2.size() > k_men.size(),
		"Weisheit erweitert die Liste (%d -> %d)" % [k_men.size(), k2.size()])
	_check(k2.has("slow"), "Ordnung Stufe 2 kommt dazu")

	# Nichts Unfertiges - und die Stufe-5-Zauber tauchen nie auf.
	var all_known: Array = []
	for fid in range(4):
		for w in range(4):
			for sid2 in Spl.known(Spl.schools_for_faction(fid), w):
				if not all_known.has(String(sid2)):
					all_known.append(String(sid2))
	var not_impl: Array = []
	for sid3 in all_known:
		if not Spl.IMPLEMENTED.has(String(sid3)):
			not_impl.append(String(sid3))
	_check(not_impl.is_empty(), "nur umgesetzte Zauber (%s)" % str(not_impl))
	_check(not all_known.has("implosion") and not all_known.has("armageddon"),
		"Stufe-5-Zauber sind nie dabei")

	# Jede Fraktion muss ueberhaupt etwas kennen, sonst waere das
	# Zauberbuch fuer sie leer.
	var empty_fac: Array = []
	for fid2 in range(4):
		if Spl.known(Spl.schools_for_faction(fid2), 3).is_empty():
			empty_fac.append(str(fid2))
	_check(empty_fac.is_empty(), "jede Fraktion hat Zauber (leer: %s)" % str(empty_fac))

	# Mana begrenzt die Auswahl.
	_check(Spl.castable(men, 3, 0).is_empty(), "ohne Mana nichts wirkbar")
	_check(not Spl.castable(men, 3, 999).is_empty(), "mit viel Mana wirkbar")
	_done.append("_test_known")


func _test_status() -> void:
	print("")
	print("== Status-Zauber ueber StatusFx ==")
	var s: Dictionary = {"type": "men_spearman", "count": 5, "status": {}}
	_check(Fx.spd_mod(s) == 0, "ohne Status keine Geschwindigkeitsaenderung")
	Fx.add(s, Fx.HASTENED, 3)
	_check(Fx.spd_mod(s) == Fx.HASTE_SPD_BONUS, "Eile beschleunigt (+%d)" % Fx.spd_mod(s))
	Fx.add(s, Fx.SLOWED, 3)
	_check(Fx.spd_mod(s) == 0, "Eile und Verlangsamen heben sich auf")
	Fx.clear(s, Fx.HASTENED)
	_check(Fx.spd_mod(s) == -Fx.SLOW_SPD_MALUS, "Verlangsamen allein bremst")

	var s2: Dictionary = {"type": "men_spearman", "count": 5, "status": {}}
	Fx.add(s2, Fx.STONE_SKIN, 3)
	_check(Fx.def_mod(s2) == Fx.STONE_SKIN_DEF_BONUS, "Steinhaut hebt die Verteidigung")
	Fx.add(s2, Fx.WEAKENED, 3)
	_check(Fx.att_mod(s2) == -Fx.WEAKNESS_ATT_MALUS, "Schwaeche senkt den Angriff")
	# Krankheit und Schwaeche stapeln - beides sind Angriffs-Mali.
	Fx.add(s2, Fx.DISEASED, 3)
	_check(Fx.att_mod(s2) == -(Fx.WEAKNESS_ATT_MALUS + Fx.DISEASE_STAT_MALUS),
		"Schwaeche und Krankheit stapeln (ist %d)" % Fx.att_mod(s2))

	# Jeder Status-Zauber muss einen Status treffen, den StatusFx kennt.
	var unknown: Array = []
	for sid in Spl.STATUS_SPELLS.keys():
		var nm: String = String((Spl.STATUS_SPELLS[sid] as Dictionary)["status"])
		if not Fx.MARKERS.has(nm):
			unknown.append("%s -> %s" % [String(sid), nm])
	_check(unknown.is_empty(),
		"jeder Status-Zauber trifft einen bekannten Status (%s)" % str(unknown))
	_done.append("_test_status")


func _test_battle() -> void:
	print("")
	print("== Kampf: wirken, Mana, ein Zauber pro Runde ==")
	var bs = TBS.new()
	bs.fx_speed = 0.0
	root.add_child(bs)
	await process_frame
	bs.set_battle({
		"player_stacks": [{"type": "men_spearman", "count": 20}],
		"enemy_stacks": [
			{"type": "ork_goblin", "count": 30},
			{"type": "ork_orc", "count": 30},
		],
		"seed": 11, "allow_flee": true,
		"player_mana": 40, "player_spell_power": 3,
		"player_spells": ["magic_arrow", "fireball", "heal", "blind"],
	})
	bs._obstacles = []
	bs._ob_map = {}
	await process_frame

	_check(int(bs._p_mana) == 40, "Mana kommt aus dem Kontext")
	_check(int(bs._casts_left) == Spl.CASTS_PER_ROUND, "ein Zauber pro Runde")
	_check(bs._castable_spells().size() == 4, "alle vier wirkbar bei 40 Mana")

	# Schaden. Die beiden Gegner nebeneinander legen, damit der Feuerball
	# ein Nachbarfeld hat.
	var e0: Dictionary = bs._e_stacks[0]
	var e1: Dictionary = bs._e_stacks[1]
	e0["pos"] = Vector2i(6, 4)
	e1["pos"] = Vector2i(6, 5)
	var before0: int = int(e0["count"])
	var before1: int = int(e1["count"])
	var mana0: int = int(bs._p_mana)
	bs._cast("fireball", e0)
	_check(int(bs._p_mana) == mana0 - Spl.cost_of("fireball"),
		"Mana abgezogen (%d -> %d)" % [mana0, int(bs._p_mana)])
	_check(int(e0["count"]) < before0, "Hauptziel getroffen")
	_check(int(e1["count"]) < before1, "Nachbarfeld mitgetroffen (Flaeche)")
	_check(int(bs._casts_left) == 0, "Zauber der Runde verbraucht")

	# Zweiter Zauber in derselben Runde muss abgelehnt werden.
	var mana1: int = int(bs._p_mana)
	bs._cast("magic_arrow", e0)
	_check(int(bs._p_mana) == mana1, "zweiter Zauber in derselben Runde prallt ab")

	# Neue Runde gibt den Zauber zurueck.
	bs._next_round()
	_check(int(bs._casts_left) == Spl.CASTS_PER_ROUND, "neue Runde, neuer Zauber")

	# Status-Zauber.
	bs._cast("blind", e0)
	_check(Fx.has(e0, Fx.BLINDED), "Blenden setzt den Status")

	# --- M8 Teil 2 -------------------------------------------------------
	# Segen: Hoechstschaden. Gleicher Seed vor beiden Wuerfen, sonst
	# vergleicht man zwei verschiedene Zufallswerte.
	var atk: Dictionary = {"type": "men_spearman", "count": 10, "side": 0,
		"top_hp": UnitType.hp_of("men_spearman"), "pos": Vector2i(1, 4),
		"status": {}}
	var dfn: Dictionary = {"type": "ork_goblin", "count": 40, "side": 1,
		"top_hp": UnitType.hp_of("ork_goblin"), "pos": Vector2i(2, 4),
		"status": {}}
	bs._p_luck = 0
	bs._e_luck = 0
	bs._p_archery_pct = 0
	bs._p_offense_pct = 0
	bs._p_armorer_pct = 0
	var max_seen: int = 0
	for i in range(30):
		bs._rng.seed = 100 + i
		max_seen = max(max_seen, int(bs._dmg(atk, dfn, false, false)))
	Fx.add(atk, Fx.BLESSED, 3)
	var blessed_min: int = 999999
	for i in range(30):
		bs._rng.seed = 100 + i
		blessed_min = min(blessed_min, int(bs._dmg(atk, dfn, false, false)))
	_check(blessed_min >= max_seen,
		"Segen richtet immer Hoechstschaden an (gesegnet min %d >= ungesegnet max %d)"
		% [blessed_min, max_seen])
	Fx.clear(atk, Fx.BLESSED)

	# Schild: weniger NAHKAMPF-Schaden, im Fernkampf unveraendert.
	var target2: Dictionary = {"type": "men_spearman", "count": 10, "side": 0,
		"top_hp": UnitType.hp_of("men_spearman"), "pos": Vector2i(1, 4),
		"status": {}}
	var e_atk: Dictionary = {"type": "ork_goblin", "count": 40, "side": 1,
		"top_hp": UnitType.hp_of("ork_goblin"), "pos": Vector2i(2, 4),
		"status": {}}
	bs._rng.seed = 500
	var melee_plain: int = int(bs._dmg(e_atk, target2, false, false))
	bs._rng.seed = 500
	var ranged_plain: int = int(bs._dmg(e_atk, target2, false, true))
	Fx.add(target2, Fx.SHIELDED, 3)
	bs._rng.seed = 500
	var melee_shield: int = int(bs._dmg(e_atk, target2, false, false))
	bs._rng.seed = 500
	var ranged_shield: int = int(bs._dmg(e_atk, target2, false, true))
	_check(melee_shield < melee_plain,
		"Schild senkt Nahkampf-Schaden (%d -> %d)" % [melee_plain, melee_shield])
	_check(ranged_shield == ranged_plain,
		"und laesst Fernkampf unveraendert (%d)" % ranged_plain)

	# Gebet: wirkt ohne Ziel-Tippen auf die ganze eigene Seite.
	_check(not Spl.needs_target("prayer"), "Gebet braucht kein Ziel")
	_check(Spl.needs_target("bless"), "Segen dagegen schon")
	# NICHT _next_round(): das laesst die KI ziehen und veraendert die
	# Stacks (hier hat sie die Speertraeger von 4 auf 1 gehauen). Fuer
	# "ein Zauber pro Runde" genuegt der Zaehler.
	bs._casts_left = Spl.CASTS_PER_ROUND
	bs._p_mana = 60
	var p_all: Array = bs._p_stacks
	bs._cast_no_target("prayer")
	var prayed: int = 0
	for s in p_all:
		if Fx.has(s, Fx.PRAYED):
			prayed += 1
	_check(prayed == p_all.size(), "Gebet trifft alle eigenen Stacks (%d von %d)"
		% [prayed, p_all.size()])
	var one: Dictionary = p_all[0]
	_check(Fx.att_mod(one) >= Fx.PRAYER_STAT_BONUS, "und hebt den Angriff")
	_check(Fx.spd_mod(one) >= Fx.PRAYER_STAT_BONUS, "und die Geschwindigkeit")

	# Konterschlag: ein zusaetzlicher Konter.
	var ready: Dictionary = {"type": "men_spearman", "status": {}}
	_check(Fx.extra_retaliations(ready) == 0, "ohne Status kein Extra-Konter")
	Fx.add(ready, Fx.READY, 3)
	_check(Fx.extra_retaliations(ready) == Fx.READY_EXTRA_RETALIATIONS,
		"Konterschlag gibt einen dazu")
	_check(not Abilities.retaliation_allowed("men_spearman", "ork_goblin", 1),
		"normal ist nach einem Konter Schluss")
	_check(Abilities.retaliation_allowed("men_spearman", "ork_goblin", 1, 1),
		"mit Konterschlag geht ein zweiter")

	# Untote erwecken: nur auf Untote, und es hebt count wieder an.
	_check(Spl.undead_only("animate_dead"), "Untote erwecken ist auf Untote begrenzt")
	_check(not Spl.undead_only("heal"), "Heilen nicht")
	var undead: Dictionary = {"type": "nec_skeleton", "count": 4, "count_start": 10,
		"top_hp": UnitType.hp_of("nec_skeleton"), "side": 0,
		"pos": Vector2i(1, 5), "status": {}}
	bs._p_stacks = [undead]
	# NICHT _next_round(): das laesst die KI ziehen und veraendert die
	# Stacks (hier hat sie die Speertraeger von 4 auf 1 gehauen). Fuer
	# "ein Zauber pro Runde" genuegt der Zaehler.
	bs._casts_left = Spl.CASTS_PER_ROUND
	bs._p_mana = 60
	bs._cast("animate_dead", undead)
	_check(int(undead["count"]) > 4,
		"Wiederbeleben hebt die Stackgroesse (4 -> %d)" % int(undead["count"]))

	# Heilen darf das NICHT: es fuellt nur auf.
	var hurt: Dictionary = {"type": "men_spearman", "count": 4, "count_start": 10,
		"top_hp": 1, "side": 0, "pos": Vector2i(1, 6), "status": {}}
	bs._p_stacks = [hurt]
	# NICHT _next_round(): das laesst die KI ziehen und veraendert die
	# Stacks (hier hat sie die Speertraeger von 4 auf 1 gehauen). Fuer
	# "ein Zauber pro Runde" genuegt der Zaehler.
	bs._casts_left = Spl.CASTS_PER_ROUND
	bs._p_mana = 60
	bs._cast("heal", hurt)
	_check(int(hurt["count"]) == 4,
		"Heilen belebt NICHT wieder (count bleibt 4, ist %d)" % int(hurt["count"]))
	_check(int(hurt["top_hp"]) > 1, "aber es heilt (top_hp %d)" % int(hurt["top_hp"]))

	# Zu wenig Mana.
	bs._next_round()
	bs._p_mana = 1
	var cast_left: int = int(bs._casts_left)
	bs._cast("fire_bolt", e0)
	_check(int(bs._casts_left) == cast_left, "ohne Mana wird nicht gewirkt")
	_check(bs._castable_spells().is_empty(), "bei 1 Mana ist nichts wirkbar")
	bs.queue_free()
	await process_frame

	# Heilung und Flucht brauchen einen FRISCHEN Kampf. Im ersten Anlauf
	# standen sie hinter mehreren _next_round()-Aufrufen - dort zieht die
	# KI, der Spieler-Stack starb, und damit heilte nichts mehr und die
	# Flucht prallte an _finished ab. Beides war ein Test-Fehler, kein
	# Code-Fehler, aber genau so verstecken sich echte.
	var bs2 = TBS.new()
	bs2.fx_speed = 0.0
	root.add_child(bs2)
	await process_frame
	bs2.set_battle({
		"player_stacks": [{"type": "men_spearman", "count": 20}],
		"enemy_stacks": [{"type": "ork_goblin", "count": 5}],
		"seed": 3, "allow_flee": true,
		"player_mana": 40, "player_spell_power": 3,
		"player_spells": ["heal", "magic_arrow"],
	})
	await process_frame
	var p0: Dictionary = bs2._p_stacks[0]
	var hp_max: int = UnitType.hp_of(String(p0["type"]))
	_check(int(p0["count"]) > 0, "Spieler-Stack lebt (Voraussetzung fuer Heilen)")
	p0["top_hp"] = 1
	bs2._cast("heal", p0)
	_check(int(p0["top_hp"]) > 1, "Heilen hebt die HP (auf %d von %d)"
		% [int(p0["top_hp"]), hp_max])

	# Restmana muss im Ergebnis stehen, sonst waere der Held nach jedem
	# Kampf wieder voll aufgeladen.
	_last_result = {}
	bs2.battle_finished.connect(_on_battle_result)
	_check(not bs2._finished, "Kampf laeuft noch (Voraussetzung fuer Flucht)")
	bs2._p_mana = 7
	bs2._on_flee()
	await process_frame
	_check(int(_last_result.get("mana_left", -1)) == 7,
		"Flucht gibt das Restmana zurueck (ist %s)"
		% str(_last_result.get("mana_left")))

	bs2.queue_free()
	await process_frame
	_done.append("_test_battle")


func _test_worldmap() -> void:
	print("")
	print("== Weltkarte: Mana-Deckel und Regeneration ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 321, 1)
	await process_frame
	var hero = wm.get("_hero")

	_check(int(hero.mana) == Spl.max_mana(int(hero.knowledge)),
		"Mana startet voll (%d)" % int(hero.mana))
	_check(int(wm.call("_hero_max_mana")) == Spl.max_mana(int(hero.knowledge)),
		"Deckel leitet sich aus dem Wissen ab")

	# Wissen hebt den Deckel sofort.
	hero.knowledge = 4
	_check(int(wm.call("_hero_max_mana")) == Spl.BASE_MANA + 40,
		"mehr Wissen, mehr Mana (%d)" % int(wm.call("_hero_max_mana")))

	# Regeneration: Grundwert, mit Mystizismus mehr, nie ueber den Deckel.
	hero.mana = 0
	hero.skills = {}
	wm.call("_regen_mana")
	_check(int(hero.mana) == 1, "Grundregeneration +1 (ist %d)" % int(hero.mana))
	hero.mana = 0
	hero.skills = {"mysticism": 3}
	wm.call("_regen_mana")
	_check(int(hero.mana) == 1 + 3, "Mystizismus III gibt +3 dazu (ist %d)" % int(hero.mana))
	hero.mana = int(wm.call("_hero_max_mana"))
	wm.call("_regen_mana")
	_check(int(hero.mana) == int(wm.call("_hero_max_mana")),
		"Regeneration laeuft nicht ueber den Deckel")

	wm.queue_free()
	await process_frame
	_done.append("_test_worldmap")


# Abenteuer-Zauber (It. 43). Sie wirken auf der WELTKARTE und gehoeren
# NICHT ins Zauberbuch des Kampfes - das ist der erste Check.
func _test_adventure() -> void:
	print("")
	print("== Abenteuer-Zauber: Stadttor ==")
	_check(not Spl.IMPLEMENTED.has("town_gate"),
		"Stadttor steht NICHT in den Kampf-Zaubern")
	_check(Spl.ADVENTURE.has("town_gate"), "sondern in den Abenteuer-Zaubern")
	# Stufe 4 heisst: ohne Weisheit III gibt es ihn nicht.
	_check(Spl.known_adventure(["natur"], 0).is_empty(),
		"ohne Weisheit kein Stadttor")
	_check(Spl.known_adventure(["natur"], 3).has("town_gate"),
		"mit Weisheit III schon")
	_check(not Spl.known_adventure(["chaos"], 3).has("town_gate"),
		"und nur in der Schule Natur")

	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 4711, 0)   # Waldvolk hat die Schule Natur
	await process_frame
	var hero = wm.get("_hero")
	hero.skills = {"wisdom": 3}
	hero.knowledge = 10
	hero.mana = int(wm.call("_hero_max_mana"))
	var cities: Array = wm.get("_cities")
	var city_pos := Vector2i(-1, -1)
	for c in cities:
		if int(c["owner"]) == int(wm.get("OWNER_HERO")):
			city_pos = Vector2i(c["pos"])
			break
	_check(city_pos.x >= 0, "eigene Stadt gefunden")

	# Auf der eigenen Stadt STEHEND ist das Tor sinnlos - der Knopf muss
	# aus sein, statt erst beim Druecken zu meckern.
	hero.position = city_pos
	_check(not bool(wm.call("_can_cast_adventure", "town_gate")),
		"in der eigenen Stadt ist das Tor gesperrt")

	# Weit weg: wirkt, nimmt Mana, beendet den Tag, Armee kommt MIT.
	hero.position = city_pos + Vector2i(5, 3)
	hero.army = {"elf_dwarf": 4}
	hero.mp = hero.max_mp
	var mana_before: int = int(hero.mana)
	_check(bool(wm.call("_can_cast_adventure", "town_gate")),
		"ausserhalb ist es wirkbar")
	wm.call("_cast_adventure", "town_gate")
	_check(hero.position == city_pos, "Held steht in der Stadt %s" % str(hero.position))
	_check(hero.count_of("elf_dwarf") == 4, "die Armee kommt mit (%d)" % hero.count_of("elf_dwarf"))
	_check(int(hero.mana) == mana_before - Spl.cost_of("town_gate"),
		"Mana bezahlt (%d von %d)" % [mana_before - int(hero.mana), Spl.cost_of("town_gate")])
	_check(int(hero.mp) == 0, "der Tag ist zu Ende")

	# Zu wenig Mana: gesperrt.
	hero.position = city_pos + Vector2i(5, 3)
	hero.mana = Spl.cost_of("town_gate") - 1
	_check(not bool(wm.call("_can_cast_adventure", "town_gate")),
		"ohne genug Mana gesperrt")
	wm.queue_free()
	await process_frame
	_done.append("_test_adventure")


# Feuerschutz (It. 43): halbiert Schaden von Feuer-Zaubern, sonst nichts.
func _test_fire_ward() -> void:
	print("")
	print("== Feuerschutz ==")
	_check(Spl.is_fire("fireball") and Spl.is_fire("fire_bolt"),
		"Feuerball und Feuerblitz sind Feuer")
	_check(not Spl.is_fire("magic_arrow"),
		"der Magische Pfeil ist es NICHT (sonst waere der Schutz allgemein)")
	var warded: Dictionary = {"type": "men_spearman", "count": 5,
		"count_start": 5, "top_hp": 10, "side": 1, "pos": Vector2i(5, 3),
		"status": {}}
	_check(Fx.spell_taken_factor(warded, true) == 1.0,
		"ohne Status kein Abschlag")
	Fx.add(warded, Fx.FIRE_WARD, 3)
	_check(Fx.spell_taken_factor(warded, true) == Fx.FIRE_WARD_FACTOR,
		"mit Schutz halber Feuerschaden")
	_check(Fx.spell_taken_factor(warded, false) == 1.0,
		"gegen NICHT-Feuer wirkt er nicht")
	# Und er darf den Waffen-Schaden nicht anfassen - das ist taken_factor.
	_check(Fx.taken_factor(warded, true) == 1.0,
		"Nahkampf-Schaden bleibt unberuehrt")
	_check(Spl.status_of("protection_fire").get("status", "") == Fx.FIRE_WARD,
		"der Zauber setzt genau diesen Status")
	_done.append("_test_fire_ward")


func _on_battle_result(r: Dictionary) -> void:
	_last_result = r
