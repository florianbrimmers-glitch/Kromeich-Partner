extends SceneTree

# Headless-Tests fuer die Helden-Skills (M7 Teil 1):
#
#   godot --headless --path game/ --script tools/test_hero_skills.gd
#
# Abgedeckt:
#   1. HeroSkills laedt skills.json, Effekt-Werte stimmen mit den JSON-
#      Strings ueberein (die Zahlen liegen im Modul als Tabelle - dieser
#      Test ist die Bruecke zurueck zur Datendatei)
#   2. Angebot: Slot-Limit, Stufen-Limit, Konflikt-Paar, nichts
#      Unfertiges, Determinismus bei gleichem Seed
#   3. Held: Primaerwerte, Skill-Stufen, Save-Round-Trip OHNE Migration
#   4. Weltkarte: Aufstieg setzt Wert und legt eine Wahl in die
#      Warteschlange; Auswahl wirkt auf Bewegung und Sichtweite
#   5. Kampf: Angriff und Verteidigung sind GETRENNT, Fuehrung hebt die
#      Moral, Bogenkampf/Offensive/Ruestungskunde aendern den Schaden
#   6. M7 Teil 2: Taktik-Aufstellung im Kampf und Totenerweckung nach
#      dem Sieg (Wegfindung steckt in tools/test_movement.gd)
#
# Jede Test-Funktion setzt am Ende eine Marke - ein Laufzeitfehler bricht
# in GDScript nur die Funktion ab, die Suite bliebe sonst gruen.

const Skills := preload("res://scripts/core/HeroSkills.gd")
const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")

var _fails: int = 0
var _done: Array = []
# Ergebnis aus dem battle_finished-Signal. MUSS ein Feld sein: GDScript-
# Lambdas fangen lokale Variablen als KOPIE, ein Schreiben in eine lokale
# Variable landet im Nichts (Lehrgeld aus It. 23).
var _last_result: Dictionary = {}


func _init() -> void:
	_test_data()
	_test_offer()
	_test_hero()
	await _test_worldmap()
	await _test_battle()
	await _test_tactics()
	await _test_necromancy()

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
		print("Helden-Skill-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Helden-Skill-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_data() -> void:
	print("== skills.json + Effekt-Werte ==")
	var defs: Array = Skills.secondary_defs()
	_check(defs.size() == 12, "12 Sekundaer-Skills geladen (sind %d)" % defs.size())
	_check(Skills.display_name("leadership") == "Fuehrung",
		"Anzeigename kommt aus der JSON (ist '%s')" % Skills.display_name("leadership"))

	# Die Zahlen liegen im Modul als Tabelle, die Wahrheit steht als Text in
	# der JSON ("ranged_dmg_+25pct"). Hier wird gegengerechnet - laufen die
	# beiden auseinander, faellt es auf.
	var f := FileAccess.open("res://data/skills.json", FileAccess.READ)
	var raw: Dictionary = JSON.parse_string(f.get_as_text()) as Dictionary
	var checked: int = 0
	var mismatched: Array = []
	for s in (raw["secondary_skills"] as Array):
		var sd: Dictionary = s as Dictionary
		var sid: String = String(sd["id"])
		for i in range((sd["tiers"] as Array).size()):
			var eff: String = String((sd["tiers"] as Array)[i]["effect"])
			# Erste Zahl im Effekt-String.
			var num: String = ""
			for ch in eff:
				if ch >= "0" and ch <= "9":
					num += ch
				elif num != "":
					break
			if num == "":
				continue
			var from_json: int = int(num)
			var from_mod: int = Skills.value_of(sid, i + 1)
			if from_mod == 0:
				continue   # nicht umgesetzter Skill, keine Tabelle
			checked += 1
			if from_mod != from_json:
				mismatched.append("%s T%d: Modul %d != JSON %d"
					% [sid, i + 1, from_mod, from_json])
	_check(mismatched.is_empty(), "%d Effekt-Werte deckungsgleich mit der JSON (%s)"
		% [checked, str(mismatched)])
	_check(checked >= 18, "genug Werte geprueft (%d)" % checked)

	_check(Skills.value_of("archery", 3) == 50, "Bogenkampf III = +50 %")
	_check(Skills.value_of("armorer", 1) == 5, "Ruestungskunde I = -5 %")
	_check(Skills.value_of("leadership", 0) == 0, "Stufe 0 = kein Effekt")
	# Seit M7 Teil 2 hat JEDER Skill aus der JSON eine Wirkung. Der Filter
	# bleibt als Mechanik, aber er darf niemanden mehr aussperren - sonst
	# faellt ein Skill still aus dem Angebot.
	_check(Skills.NOT_YET_IMPLEMENTED.is_empty(),
		"kein Skill mehr ohne Wirkung (%s)" % str(Skills.NOT_YET_IMPLEMENTED))
	_check(Skills.offerable_ids().size() == Skills.all_secondary_ids().size(),
		"alle %d Skills sind anbietbar" % Skills.all_secondary_ids().size())
	var no_value: Array = []
	for sid in Skills.all_secondary_ids():
		if Skills.value_of(String(sid), 1) == 0:
			no_value.append(String(sid))
	_check(no_value.is_empty(), "jeder Skill hat auf Stufe 1 einen Wert (%s)"
		% str(no_value))
	_check(Skills.value_of("pathfinding", 1) == 25, "Wegfindung I = -25 %")
	_check(Skills.tactics_cols({"tactics": 2}) == 2, "Taktik II = 2 Spalten")
	_check(Skills.necromancy_pct({"necromancy": 3}) == 30,
		"Totenerweckung III = 30 %")
	_check(Skills.value_of("wisdom", 2) == 3, "Weisheit II erlaubt Stufe 3")
	_check(Skills.mana_regen({"mysticism": 3}) == 3, "Mystizismus III = +3 Mana/Tag")
	_check(Skills.next_tier_text("logistics", {}).contains("10"),
		"Beschreibung der naechsten Stufe nennt den Wert (ist '%s')"
		% Skills.next_tier_text("logistics", {}))
	# Auch die neuen drei muessen sich beschreiben lassen - ein leerer Text
	# im Auswahl-Overlay waere ein Blindkauf.
	var empty_text: Array = []
	for sid2 in Skills.all_secondary_ids():
		if Skills.next_tier_text(String(sid2), {}).is_empty():
			empty_text.append(String(sid2))
	_check(empty_text.is_empty(), "jeder Skill beschreibt seine Stufe (%s)"
		% str(empty_text))
	_done.append("_test_data")


func _test_offer() -> void:
	print("")
	print("== Angebot beim Stufenaufstieg ==")
	var rng := RandomNumberGenerator.new()
	rng.seed = 12345

	var o: Array = Skills.offer(rng, {})
	_check(o.size() == Skills.OFFER_COUNT,
		"%d Vorschlaege (sind %d)" % [Skills.OFFER_COUNT, o.size()])
	_check(o[0] != o[1], "keine Dopplung im Angebot")

	# Unfertige Skills duerfen NIE auftauchen - der Spieler soll keinen
	# toten Zug ziehen koennen.
	var bad: Array = []
	for i in range(400):
		rng.seed = i
		for sid in Skills.offer(rng, {}):
			if Skills.NOT_YET_IMPLEMENTED.has(String(sid)):
				bad.append(String(sid))
	_check(bad.is_empty(), "kein unfertiger Skill im Angebot (%s)" % str(bad))

	# Konflikt-Paar: mit Fuehrung nie Totenerweckung (und umgekehrt).
	var clash: Array = []
	for i in range(400):
		rng.seed = 9000 + i
		for sid in Skills.offer(rng, {"leadership": 1}):
			if String(sid) == "necromancy":
				clash.append("necromancy trotz Fuehrung")
	_check(clash.is_empty(), "Konflikt-Paar respektiert (%s)" % str(clash))

	# Stufen-Limit: ein Skill auf MAX_TIER wird nicht mehr angeboten.
	var maxed: Dictionary = {"archery": Skills.MAX_TIER}
	var again: Array = []
	for i in range(200):
		rng.seed = 300 + i
		for sid in Skills.offer(rng, maxed):
			if String(sid) == "archery":
				again.append("archery")
	_check(again.is_empty(), "voll ausgebauter Skill kommt nicht wieder")

	# Slot-Limit: sind alle Plaetze belegt, nur noch Aufstufungen.
	var full: Dictionary = {}
	var ids: Array = Skills.offerable_ids()
	for k in range(min(Skills.MAX_SLOTS, ids.size())):
		full[String(ids[k])] = 1
	var new_ids: Array = []
	for i in range(200):
		rng.seed = 700 + i
		for sid in Skills.offer(rng, full):
			if not full.has(String(sid)):
				new_ids.append(String(sid))
	_check(new_ids.is_empty(),
		"bei %d belegten Plaetzen nur Aufstufungen (%s)" % [full.size(), str(new_ids)])

	# Determinismus: gleicher Seed -> gleiches Angebot.
	rng.seed = 4242
	var a: Array = Skills.offer(rng, {})
	rng.seed = 4242
	var b: Array = Skills.offer(rng, {})
	_check(str(a) == str(b), "gleicher Seed -> gleiches Angebot")

	# Primaerwert: nur aus dem Topf, und Orks schlagen haeufiger zu.
	# Seit M8 umfasst der Topf alle vier Werte (Wissen gibt Mana,
	# Zauberkraft skaliert Zauber). Die Pruefung faellt deshalb nicht auf
	# eine Mehrheit, sondern darauf, dass Angriff bei den Orks der
	# HAEUFIGSTE Wert ist - das ist die eigentliche Absicht der Gewichte.
	var counts: Dictionary = {}
	var off_pool: Array = []
	for i in range(600):
		rng.seed = i
		var s3: String = Skills.roll_primary(rng, 3)
		counts[s3] = int(counts.get(s3, 0)) + 1
		if not off_pool.has(s3):
			off_pool.append(s3)
	var only_pool := true
	for s4 in off_pool:
		if not Skills.PRIMARY_POOL.has(String(s4)):
			only_pool = false
	_check(only_pool, "Primaerwert kommt nur aus PRIMARY_POOL (%s)" % str(off_pool))
	var top: String = ""
	var top_n: int = -1
	for k in counts.keys():
		if int(counts[k]) > top_n:
			top_n = int(counts[k])
			top = String(k)
	_check(top == "attack", "Orks ziehen am haeufigsten Angriff (%s)" % str(counts))
	# Und Zauberkraft bleibt bei Orks selten - sonst waeren die Gewichte
	# wirkungslos.
	_check(int(counts.get("spell_power", 0)) < int(counts.get("attack", 0)) / 2,
		"Orks zaubern kaum (Zauberkraft %d vs Angriff %d)"
		% [int(counts.get("spell_power", 0)), int(counts.get("attack", 0))])
	_done.append("_test_offer")


func _test_hero() -> void:
	print("")
	print("== Held: Werte, Skills, Save ==")
	var h := Hero.new(Vector2i(3, 4), 10)
	_check(h.att == 0 and h.def == 0, "Held startet ohne Primaerwerte")
	h.add_primary("attack", 2)
	h.add_primary("defense", 1)
	_check(h.att == 2 and h.def == 1, "add_primary trifft das richtige Feld")
	_check(h.raise_skill("archery") == 1, "erste Stufe")
	_check(h.raise_skill("archery") == 2, "zweite Stufe")
	h.raise_skill("archery")
	_check(h.raise_skill("archery", 3) == 3, "Stufe bei MAX_TIER gedeckelt")
	_check(h.skill_tier("offense") == 0, "ungelernter Skill = Stufe 0")

	# Save-Round-Trip. M7 ergaenzt nur Felder, also KEIN SAVE_VERSION-Bump.
	var d: Dictionary = h.to_dict()
	var h2: Hero = Hero.from_dict(d)
	_check(h2.att == 2 and h2.def == 1, "Primaerwerte ueberleben to_dict/from_dict")
	_check(h2.skill_tier("archery") == 3, "Skill-Stufe ueberlebt")
	# Alter Save ohne die neuen Felder: tolerante Defaults.
	var old_save: Dictionary = {"position": {"x": 1, "y": 1}, "mp": 5, "max_mp": 10,
		"army": {}, "xp": 0, "level": 1}
	var h3: Hero = Hero.from_dict(old_save)
	_check(h3.att == 0 and h3.skills.is_empty(),
		"Save ohne M7-Felder laedt mit Nullwerten (keine Migration noetig)")
	_done.append("_test_hero")


func _test_worldmap() -> void:
	print("")
	print("== Weltkarte: Aufstieg, Logistik, Aufklaeren ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 777, 1)
	await process_frame

	var hero = wm.get("_hero")
	var att0: int = int(hero.att) + int(hero.def)
	# Genug XP fuer mehrere Stufen auf einmal.
	hero.xp = 400
	var leveled: bool = wm.call("_check_level_up")
	_check(leveled, "Aufstieg ausgeloest")
	_check(int(hero.level) > 1, "Stufe gestiegen (ist %d)" % int(hero.level))
	_check(int(hero.att) + int(hero.def) > att0,
		"Primaerwert vergeben (Angriff %d, Verteidigung %d)" % [int(hero.att), int(hero.def)])
	var queue: Array = wm.get("_skill_queue")
	_check(queue.size() >= 1, "Skill-Wahl in der Warteschlange (%d)" % queue.size())
	_check((queue[0] as Array).size() >= 1, "Angebot ist nicht leer")

	# Auswahl anwenden und die Karten-Wirkung pruefen.
	var mp_before: int = int(hero.max_mp)
	hero.skills = {"logistics": 3}
	wm.call("_recalc_max_mp")
	_check(int(hero.max_mp) > mp_before,
		"Logistik III hebt die Bewegung (%d -> %d)" % [mp_before, int(hero.max_mp)])
	var sight_base: int = int(wm.get("HERO_SIGHT"))
	hero.skills = {"scouting": 2}
	_check(int(wm.call("_hero_sight")) == sight_base + 2,
		"Aufklaeren II gibt +2 Sichtweite (ist %d)" % int(wm.call("_hero_sight")))
	hero.skills = {}
	_check(int(wm.call("_hero_sight")) == sight_base,
		"ohne Skill die Grundsichtweite")

	# Der Panel-Aufbau darf nicht abstuerzen (er laeuft im Spiel deferred).
	wm.call("_show_skill_choice", ["archery", "offense"])
	var panel = wm.get("_skill_panel")
	_check(panel != null and panel.visible, "Auswahl-Panel steht")
	wm.call("_on_skill_picked", "archery")
	_check(int(hero.skill_tier("archery")) == 1, "Auswahl gelernt")

	wm.queue_free()
	await process_frame
	_done.append("_test_worldmap")


func _test_battle() -> void:
	print("")
	print("== Kampf: getrennte Boni, Fuehrung, Prozent-Skills ==")
	var bs = TBS.new()
	bs.fx_speed = 0.0
	root.add_child(bs)
	await process_frame
	bs.set_battle({
		"player_stacks": [{"type": "men_archer", "count": 10}],
		"enemy_stacks": [{"type": "ork_goblin", "count": 10}],
		"seed": 5, "allow_flee": true,
		"player_att": 7, "player_def": 2,
		"player_morale_bonus": 2,
		"player_archery_pct": 50, "player_offense_pct": 25,
		"player_armorer_pct": 15,
	})
	await process_frame
	_check(int(bs._p_att) == 7 and int(bs._p_def) == 2,
		"Angriff und Verteidigung sind getrennt (%d / %d)" % [int(bs._p_att), int(bs._p_def)])
	# Reine Menschen-Armee: +1 Reinheit, plus 2 aus Fuehrung.
	_check(int(bs._p_morale) == 3, "Fuehrung hebt die Moral (ist %d)" % int(bs._p_morale))

	# Rueckfall: alte Aufrufer schicken nur player_bonus.
	var bs2 = TBS.new()
	bs2.fx_speed = 0.0
	root.add_child(bs2)
	await process_frame
	bs2.set_battle({
		"player_stacks": [{"type": "men_archer", "count": 10}],
		"enemy_stacks": [{"type": "ork_goblin", "count": 10}],
		"seed": 5, "allow_flee": true, "player_bonus": 4,
	})
	await process_frame
	_check(int(bs2._p_att) == 4 and int(bs2._p_def) == 4,
		"ohne die neuen Keys faellt beides auf player_bonus zurueck")

	# Schaden: derselbe Wurf mit und ohne Prozent-Skill. Gleicher Seed vor
	# jedem Aufruf, sonst vergleicht man zwei verschiedene Wuerfe.
	var atk: Dictionary = {"type": "men_archer", "count": 10, "side": 0,
		"top_hp": UnitType.hp_of("men_archer"), "pos": Vector2i(1, 4)}
	var dfn: Dictionary = {"type": "ork_goblin", "count": 10, "side": 1,
		"top_hp": UnitType.hp_of("ork_goblin"), "pos": Vector2i(6, 4)}
	bs._p_archery_pct = 0
	bs._p_offense_pct = 0
	bs._p_armorer_pct = 0
	bs._p_luck = 0
	bs._e_luck = 0
	bs._rng.seed = 99
	var plain: int = int(bs._dmg(atk, dfn, false, true))
	bs._p_archery_pct = 50
	bs._rng.seed = 99
	var boosted: int = int(bs._dmg(atk, dfn, false, true))
	_check(boosted > plain, "Bogenkampf hebt den Schuss-Schaden (%d -> %d)" % [plain, boosted])
	# Nahkampf darf davon NICHT betroffen sein.
	bs._rng.seed = 99
	var melee_plain: int = int(bs._dmg(atk, dfn, false, false))
	bs._p_archery_pct = 50
	bs._p_offense_pct = 0
	bs._rng.seed = 99
	var melee_same: int = int(bs._dmg(atk, dfn, false, false))
	_check(melee_plain == melee_same, "Bogenkampf wirkt NICHT im Nahkampf")
	bs._p_offense_pct = 40
	bs._rng.seed = 99
	var melee_boost: int = int(bs._dmg(atk, dfn, false, false))
	_check(melee_boost > melee_plain,
		"Offensive hebt den Nahkampf-Schaden (%d -> %d)" % [melee_plain, melee_boost])

	# Ruestungskunde: der Held steckt weniger ein. Angreifer ist jetzt die
	# Gegnerseite, Verteidiger die Spielerseite.
	var e_atk: Dictionary = {"type": "ork_goblin", "count": 10, "side": 1,
		"top_hp": UnitType.hp_of("ork_goblin"), "pos": Vector2i(6, 4)}
	var p_def: Dictionary = {"type": "men_archer", "count": 10, "side": 0,
		"top_hp": UnitType.hp_of("men_archer"), "pos": Vector2i(1, 4)}
	bs._p_offense_pct = 0
	bs._p_armorer_pct = 0
	bs._rng.seed = 55
	var taken: int = int(bs._dmg(e_atk, p_def, false, false))
	bs._p_armorer_pct = 15
	bs._rng.seed = 55
	var taken_less: int = int(bs._dmg(e_atk, p_def, false, false))
	_check(taken_less < taken,
		"Ruestungskunde senkt den erlittenen Schaden (%d -> %d)" % [taken, taken_less])

	bs.queue_free()
	bs2.queue_free()
	await process_frame
	_done.append("_test_battle")


# --- M7 Teil 2: Taktik-Aufstellung ---------------------------------------

func _test_tactics() -> void:
	print("")
	print("== Taktik: Aufstellung vor dem Kampf ==")
	var bs = TBS.new()
	bs.fx_speed = 0.0
	root.add_child(bs)
	await process_frame
	bs.set_battle({
		"player_stacks": [{"type": "men_archer", "count": 10},
			{"type": "men_spearman", "count": 10}],
		"enemy_stacks": [{"type": "ork_goblin", "count": 10}],
		"seed": 11, "allow_flee": true,
		"player_tactics": 2,
	})
	# Hindernisse raus, damit die Zielfelder im Test frei sind.
	bs._obstacles = []
	bs._ob_map = {}
	await process_frame

	_check(bool(bs._tactics_phase), "Phase laeuft bei Taktik II")
	_check(bs._tactics_btn != null and bs._tactics_btn.visible,
		"'Kampf beginnen' steht bereit")
	_check(bs._wait_btn != null and not bs._wait_btn.visible,
		"Warten ist waehrend der Aufstellung weg")

	var s0: Dictionary = bs._p_stacks[0]
	var from: Vector2i = Vector2i(s0["pos"])
	_check(from.x == bs.TACTICS_FIRST_COL, "Stacks stehen in Spalte %d"
		% bs.TACTICS_FIRST_COL)

	# Ohne Auswahl bewegt sich nichts.
	bs._tactics_tap(Vector2i(3, from.y))
	_check(Vector2i(s0["pos"]) == from, "Tap ohne Auswahl verschiebt nichts")

	# Auswaehlen, dann in die Zone: Spalte 1 bis 3 bei Stufe 2.
	bs._tactics_tap(from)
	_check(int(bs._tactics_pick) == 0, "Stack ausgewaehlt")
	bs._tactics_tap(Vector2i(3, from.y))
	_check(Vector2i(s0["pos"]) == Vector2i(3, from.y),
		"Stack steht auf dem Zielfeld (ist %s)" % str(Vector2i(s0["pos"])))
	_check(int(bs._tactics_pick) == -1, "Auswahl nach dem Setzen zurueckgesetzt")

	# Ausserhalb der Zone: Spalte 4 ist bei Stufe 2 zu weit.
	bs._tactics_tap(Vector2i(3, from.y))
	bs._tactics_tap(Vector2i(4, from.y))
	_check(Vector2i(s0["pos"]) == Vector2i(3, from.y),
		"Spalte 4 wird bei Stufe 2 verweigert")
	_check(not bs._tactics_allows(Vector2i(4, from.y)),
		"_tactics_allows sagt dasselbe")
	_check(not bs._tactics_allows(Vector2i(0, from.y)),
		"Spalte 0 ebenfalls tabu (Rand)")

	# Blockiertes Feld.
	bs._ob_map[Vector2i(2, from.y)] = 1
	bs._tactics_tap(Vector2i(3, from.y))
	bs._tactics_tap(Vector2i(2, from.y))
	_check(Vector2i(s0["pos"]) == Vector2i(3, from.y),
		"Hindernis-Feld wird verweigert")
	bs._ob_map.erase(Vector2i(2, from.y))

	# Zweiter Stack auf dasselbe Feld? Erlaubt ist es nicht - aber der
	# erste Tap waehlt dort ohnehin den Stack aus, deshalb pruefen wir das
	# ueber ein Feld, auf dem der andere eigene Stack steht: der Tap muss
	# ihn AUSWAEHLEN, nicht den ersten dorthin schieben.
	var s1: Dictionary = bs._p_stacks[1]
	var other: Vector2i = Vector2i(s1["pos"])
	bs._tactics_tap(Vector2i(3, from.y))
	bs._tactics_tap(other)
	_check(int(bs._tactics_pick) == 1, "Tap auf den zweiten Stack waehlt ihn aus")
	_check(Vector2i(s0["pos"]) == Vector2i(3, from.y), "der erste bleibt stehen")

	# Phase beenden -> der Kampf laeuft.
	bs._end_tactics()
	_check(not bool(bs._tactics_phase), "Phase beendet")
	_check(not bs._tactics_btn.visible and bs._wait_btn.visible,
		"Knopfzeile ist zurueck")
	_check(bs._turn_order.size() > 0 and int(bs._active_slot) < bs._turn_order.size(),
		"Zugreihenfolge steht (%d Slots)" % bs._turn_order.size())
	bs.queue_free()

	# Ohne Skill gibt es die Phase nicht - der Kampf startet sofort.
	var bs2 = TBS.new()
	bs2.fx_speed = 0.0
	root.add_child(bs2)
	await process_frame
	bs2.set_battle({
		"player_stacks": [{"type": "men_archer", "count": 10}],
		"enemy_stacks": [{"type": "ork_goblin", "count": 10}],
		"seed": 11, "allow_flee": true,
	})
	await process_frame
	_check(not bool(bs2._tactics_phase), "ohne Skill keine Aufstellungsphase")
	_check(bs2._tactics_btn != null and not bs2._tactics_btn.visible,
		"und kein Knopf dafuer")
	bs2.queue_free()
	await process_frame
	_done.append("_test_tactics")


# --- M7 Teil 2: Totenerweckung -------------------------------------------

func _test_necromancy() -> void:
	print("")
	print("== Totenerweckung: Skelette nach dem Sieg ==")
	var sk_hp: int = UnitType.hp_of("nec_skeleton")
	_check(sk_hp > 0, "Skelett-HP bekannt (%d)" % sk_hp)
	_check(Skills.raised_skeletons({}, 1000, sk_hp) == 0, "ohne Skill nichts")
	_check(Skills.raised_skeletons({"necromancy": 1}, 0, sk_hp) == 0,
		"ohne Gefallene nichts")
	var t1: int = Skills.raised_skeletons({"necromancy": 1}, 700, sk_hp)
	var t3: int = Skills.raised_skeletons({"necromancy": 3}, 700, sk_hp)
	_check(t1 == int(700 * 10 / (100 * sk_hp)),
		"Stufe 1 = 10 %% der gefallenen HP (%d Skelette)" % t1)
	_check(t3 > t1, "hoehere Stufe gibt mehr (%d -> %d)" % [t1, t3])
	# Ein gefallener Drache muss mehr bringen als ein gefallener Goblin -
	# genau das leistet die HP-Rechnung gegenueber der Koepfe-Zaehlung.
	var dragon: int = Skills.raised_skeletons({"necromancy": 3},
		UnitType.hp_of("nec_bonedragon"), sk_hp)
	var goblin: int = Skills.raised_skeletons({"necromancy": 3},
		UnitType.hp_of("ork_goblin"), sk_hp)
	_check(dragon > goblin,
		"ein gefallener Knochendrache bringt mehr als ein Goblin (%d vs %d)"
		% [dragon, goblin])

	# Das Kampf-Ergebnis muss die gefallenen HP mitliefern.
	var bs = TBS.new()
	bs.fx_speed = 0.0
	root.add_child(bs)
	await process_frame
	_last_result = {}
	bs.battle_finished.connect(func(r: Dictionary) -> void: _last_result = r)
	bs.set_battle({
		"player_stacks": [{"type": "men_archer", "count": 20}],
		"enemy_stacks": [{"type": "ork_goblin", "count": 6}],
		"seed": 3, "allow_flee": false,
	})
	await process_frame
	var enemy: Dictionary = bs._e_stacks[0]
	var e_uid: String = String(enemy["type"])
	var e_cnt: int = int(enemy["count"])
	bs._apply_dmg(enemy, 99999)
	bs._check_end()
	_check(String(_last_result.get("outcome", "")) == "victory", "Sieg gemeldet")
	_check(int(_last_result.get("enemy_killed", 0)) == e_cnt,
		"%d gefallene Gegner gezaehlt (sind %d)"
		% [e_cnt, int(_last_result.get("enemy_killed", 0))])
	_check(int(_last_result.get("enemy_killed_hp", 0)) == e_cnt * UnitType.hp_of(e_uid),
		"und ihre Trefferpunkte (%d)" % int(_last_result.get("enemy_killed_hp", 0)))
	bs.queue_free()

	# Weltkarte: der Trichter haengt die Skelette in die Heldenarmee.
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 909, 1)
	await process_frame
	var hero = wm.get("_hero")

	hero.skills = {}
	var before: int = int(hero.army.get("nec_skeleton", 0))
	wm.call("_apply_necromancy", 1000)
	_check(int(hero.army.get("nec_skeleton", 0)) == before,
		"ohne Skill kommt niemand zurueck")

	hero.skills = {"necromancy": 3}
	wm.call("_apply_necromancy", 700)
	var expect: int = Skills.raised_skeletons({"necromancy": 3}, 700, sk_hp)
	_check(int(hero.army.get("nec_skeleton", 0)) == before + expect,
		"%d Skelette in der Armee (sind %d)"
		% [expect, int(hero.army.get("nec_skeleton", 0))])
	# Zweiter Sieg: der bestehende Stack waechst, es gibt keinen zweiten.
	wm.call("_apply_necromancy", 700)
	_check(int(hero.army.get("nec_skeleton", 0)) == before + 2 * expect,
		"bestehender Stack waechst statt einen zweiten anzulegen")

	# Armee voll und kein Skelett-Stack: der Skill darf nicht still
	# verpuffen, aber auch keinen Slot erzwingen.
	hero.army = {}
	var fillers: Array = ["men_spearman", "men_archer", "men_griffin",
		"men_crusader", "men_monk", "men_cavalier"]
	for i in range(Hero.MAX_ARMY_SLOTS):
		hero.army[String(fillers[i % fillers.size()])] = 5
	var slots_before: int = hero.army.size()
	var msg: String = String(wm.call("_apply_necromancy", 700))
	_check(hero.army.size() == slots_before
			and not hero.army.has("nec_skeleton"),
		"bei voller Armee kommt kein Stack dazu (%d Slots)" % hero.army.size())
	_check(msg.contains("kein Platz"), "und der Spieler erfaehrt warum ('%s')" % msg)

	wm.queue_free()
	await process_frame
	_done.append("_test_necromancy")
