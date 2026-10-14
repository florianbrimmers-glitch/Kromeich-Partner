extends SceneTree

# Headless-Tests fuer die Bonus-Karten-Objekte (M5):
#
#   godot --headless --path game/ --script tools/test_map_objects.gd
#
# Abgedeckt:
#   1. Platzierung: alle geplanten Arten kommen auf die Karte, Bonus-
#      Objekte sind unbewacht, Sprites vorhanden
#   2. Stat-Schreine: +1 auf den richtigen Wert, EINMALIG
#   3. Brunnen: Mana auf Maximum, einmal pro Tag
#   4. Lehrmeister: XP einmalig, kann eine Stufe ausloesen
#   5. Windmuehle: Ressource einmal pro Woche, deterministisch
#   6. Save: der Verbraucht-Zustand ueberlebt einen Round-Trip
#   7. Zweite Welle (It. 78): Lagerfeuer, Artefakt, Wassermuehle,
#      Stallungen, Oase, Aussichtsturm, Arena, Gluecksbrunnen, Tempel,
#      Baum des Wissens, Hexenhuette, Schrein der Magie, Gefaengnis,
#      Handelsposten - je Wirkung, Wiederholungsregel und Save

const Spl := preload("res://scripts/core/HeroSpells.gd")
const MO := preload("res://scripts/core/MapObjects.gd")
const Artifacts := preload("res://scripts/core/Artifacts.gd")

var _fails: int = 0
var _wm = null
# Ein Laufzeitfehler in einer Test-Funktion bricht NUR diese Funktion ab -
# die Suite lief danach weiter und meldete gruen. Jede Funktion setzt
# deshalb am Ende ihre Marke; fehlt eine, ist die Suite rot.
var _done: Array = []


func _init() -> void:
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	_wm = scene.instantiate()
	root.add_child(_wm)
	await process_frame
	_wm.call("_start", 2024, 1)
	await process_frame

	_test_placement()
	_test_shrines()
	_test_well()
	_test_learning()
	_test_windmill()
	await _test_save()
	await _test_wave2()

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

	_wm.queue_free()
	await process_frame

	print("")
	if _fails == 0:
		print("Karten-Objekt-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Karten-Objekt-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


# Baut ein Objekt-Dictionary wie _place_objects es anlegt.
func _obj(kind: int, pos: Vector2i = Vector2i(4, 4)) -> Dictionary:
	return {"pos": pos, "kind": kind, "owner": -1, "guard": 0, "gold": 0}


func _test_placement() -> void:
	print("== Platzierung ==")
	var objs: Array = _wm.get("_objects")
	var plan: Dictionary = _wm.get("BONUS_PLAN")
	var counts: Dictionary = {}
	for o in objs:
		var k: int = int((o as Dictionary)["kind"])
		counts[k] = int(counts.get(k, 0)) + 1
	var missing: Array = []
	for kind in plan.keys():
		if int(counts.get(int(kind), 0)) != int(plan[kind]):
			missing.append("Art %d: %d von %d" % [int(kind),
				int(counts.get(int(kind), 0)), int(plan[kind])])
	_check(missing.is_empty(), "alle geplanten Bonus-Arten liegen auf der Karte (%s)"
		% str(missing))

	# Bonus-Objekte sind unbewacht - sonst waeren sie fruehe Sackgassen.
	var guarded: Array = []
	for o2 in objs:
		var od: Dictionary = o2 as Dictionary
		if int(od["kind"]) >= int(_wm.get("OBJECT_SHRINE_ATT")) and int(od.get("guard", 0)) > 0 \
				and not MO.is_guarded(int(od["kind"])):
			guarded.append(str(int(od["kind"])))
	_check(guarded.is_empty(), "Bonus-Objekte sind unbewacht (%s)" % str(guarded))

	# Sprites muessen da sein, sonst zeichnet der Screen den alten
	# Farbklotz-Fallback.
	var sprites: Dictionary = _wm.get("OBJECT_SPRITES")
	var no_sprite: Array = []
	for kind2 in sprites.keys():
		var pth: String = "res://assets/world/objects/%s.svg" % String(sprites[kind2])
		if not ResourceLoader.exists(pth):
			no_sprite.append(String(sprites[kind2]))
	_check(no_sprite.is_empty(), "Sprite je Bonus-Art (fehlen: %s)" % str(no_sprite))
	_check(sprites.size() == plan.size(),
		"jede geplante Art hat einen Sprite-Eintrag (%d / %d)"
		% [sprites.size(), plan.size()])

	# Alle Bonus-Arten muessen in _visit_bonus_object behandelt sein -
	# sonst laeuft der Spieler hin und es passiert nichts.
	var silent: Array = []
	for kind3 in plan.keys():
		if String(_wm.call("_visit_bonus_object", _obj(int(kind3)))) == "":
			silent.append(str(int(kind3)))
	_check(silent.is_empty(), "jede Bonus-Art gibt eine Rueckmeldung (%s)" % str(silent))
	_done.append("_test_placement")


func _test_shrines() -> void:
	print("")
	print("== Stat-Schreine ==")
	var hero = _wm.get("_hero")
	var specs: Dictionary = _wm.get("SHRINE_STATS")
	for kind in specs.keys():
		var stat_id: String = String((specs[kind] as Array)[0])
		var before: int = int(hero.get(_field_of(stat_id)))
		var o: Dictionary = _obj(int(kind))
		var msg: String = String(_wm.call("_visit_bonus_object", o))
		var after: int = int(hero.get(_field_of(stat_id)))
		_check(after == before + 1, "%s: %s %d -> %d" % [msg, stat_id, before, after])
		# Zweiter Besuch darf nichts mehr geben.
		var msg2: String = String(_wm.call("_visit_bonus_object", o))
		_check(int(hero.get(_field_of(stat_id))) == after,
			"einmalig - zweiter Besuch gibt nichts (%s)" % msg2)
		_check(msg2.contains("schon"), "und sagt das auch")

	# Der Garten muss das Mana mitwachsen lassen, sonst wirkt er erst am
	# naechsten Tag.
	hero.knowledge = 0
	hero.mana = 0
	var garden: Dictionary = _obj(int(_wm.get("OBJECT_SHRINE_KNOW")))
	_wm.call("_visit_bonus_object", garden)
	_check(int(hero.mana) > 0, "Garten hebt das Mana sofort mit (ist %d)" % int(hero.mana))
	_done.append("_test_shrines")


func _field_of(stat_id: String) -> String:
	match stat_id:
		"attack": return "att"
		"defense": return "def"
		"spell_power": return "spell_power"
	return "knowledge"


func _test_well() -> void:
	print("")
	print("== Brunnen ==")
	var hero = _wm.get("_hero")
	hero.knowledge = 3
	hero.mana = 2
	var cap: int = int(_wm.call("_hero_max_mana"))
	var w: Dictionary = _obj(int(_wm.get("OBJECT_WELL")))
	var msg: String = String(_wm.call("_visit_bonus_object", w))
	_check(int(hero.mana) == cap, "Mana auf Maximum (%d/%d) - %s" % [int(hero.mana), cap, msg])

	# Zweiter Besuch am selben Tag: nichts.
	hero.mana = 1
	var msg2: String = String(_wm.call("_visit_bonus_object", w))
	_check(int(hero.mana) == 1, "am selben Tag nur einmal (%s)" % msg2)

	# Naechster Tag: wieder nutzbar.
	_wm.set("_turn_number", int(_wm.get("_turn_number")) + 1)
	_wm.call("_visit_bonus_object", w)
	_check(int(hero.mana) == cap, "am naechsten Tag wieder (%d)" % int(hero.mana))

	# Volles Mana: kein Verbrauch, damit der Brunnen nicht umsonst
	# "verbraucht" wird.
	_wm.set("_turn_number", int(_wm.get("_turn_number")) + 1)
	var msg3: String = String(_wm.call("_visit_bonus_object", w))
	_check(msg3.contains("voll"), "bei vollem Mana Hinweis statt Verbrauch (%s)" % msg3)
	_check(int(w.get("used_turn", -1)) != int(_wm.get("_turn_number")),
		"und der Brunnen bleibt fuer heute nutzbar")
	_done.append("_test_well")


func _test_learning() -> void:
	print("")
	print("== Lehrmeister ==")
	var hero = _wm.get("_hero")
	hero.xp = 0
	var l: Dictionary = _obj(int(_wm.get("OBJECT_LEARNING")))
	var msg: String = String(_wm.call("_visit_bonus_object", l))
	_check(int(hero.xp) == int(_wm.get("LEARNING_XP")),
		"XP gutgeschrieben (%d) - %s" % [int(hero.xp), msg])
	var msg2: String = String(_wm.call("_visit_bonus_object", l))
	_check(int(hero.xp) == int(_wm.get("LEARNING_XP")), "einmalig (%s)" % msg2)

	# Knapp unter der Schwelle: der Lehrmeister muss die Stufe ausloesen.
	var thresholds: Array = _wm.get("LEVEL_THRESHOLDS")
	var lvl: int = int(hero.level)
	if lvl < thresholds.size():
		hero.xp = int(thresholds[lvl]) - 1
		var l2: Dictionary = _obj(int(_wm.get("OBJECT_LEARNING")), Vector2i(5, 5))
		var msg3: String = String(_wm.call("_visit_bonus_object", l2))
		_check(int(hero.level) > lvl, "loest eine Stufe aus (%s)" % msg3)
	_done.append("_test_learning")


func _test_windmill() -> void:
	print("")
	print("== Windmuehle ==")
	var hero = _wm.get("_hero")
	var m: Dictionary = _obj(int(_wm.get("OBJECT_WINDMILL")), Vector2i(7, 9))
	var before: int = _total_resources(hero)
	var msg: String = String(_wm.call("_visit_bonus_object", m))
	_check(_total_resources(hero) > before, "Ressource gutgeschrieben - %s" % msg)

	var mid: int = _total_resources(hero)
	var msg2: String = String(_wm.call("_visit_bonus_object", m))
	_check(_total_resources(hero) == mid, "in derselben Woche nur einmal (%s)" % msg2)

	# Naechste Woche: wieder. Ein Sprung von 7 Zuegen ist genau eine Woche.
	_wm.set("_turn_number", int(_wm.get("_turn_number")) + 7)
	_wm.call("_visit_bonus_object", m)
	_check(_total_resources(hero) > mid, "naechste Woche wieder")

	# Deterministisch: derselbe Spielstand, dasselbe Feld, dieselbe Woche
	# -> dieselbe Ausbeute. Sonst waere Neuladen ein Gluecksspiel.
	var m2: Dictionary = _obj(int(_wm.get("OBJECT_WINDMILL")), Vector2i(7, 9))
	var snap_a: Dictionary = _resource_snapshot(hero)
	_wm.call("_visit_bonus_object", m2)
	var gain_a: Dictionary = _resource_delta(snap_a, hero)
	var m3: Dictionary = _obj(int(_wm.get("OBJECT_WINDMILL")), Vector2i(7, 9))
	var snap_b: Dictionary = _resource_snapshot(hero)
	_wm.call("_visit_bonus_object", m3)
	var gain_b: Dictionary = _resource_delta(snap_b, hero)
	_check(str(gain_a) == str(gain_b),
		"gleiche Woche und Feld -> gleiche Ausbeute (%s vs %s)" % [str(gain_a), str(gain_b)])
	_done.append("_test_windmill")


# Der Beutel gehoert seit M13a dem SPIELER (`_purse` im Screen), nicht dem
# Helden. Die Hilfsfunktionen nehmen den Helden weiter als Parameter, damit
# die Aufrufstellen unveraendert bleiben - gelesen wird der Screen-Beutel.
func _purse() -> Wallet:
	return _wm.get("_purse") as Wallet


func _total_resources(_hero_unused) -> int:
	var n: int = 0
	var p: Wallet = _purse()
	for rid in Wallet.RESOURCE_IDS:
		n += int(p.get_amount(String(rid)))
	return n


func _resource_snapshot(_hero_unused) -> Dictionary:
	var d: Dictionary = {}
	var p: Wallet = _purse()
	for rid in Wallet.RESOURCE_IDS:
		d[String(rid)] = int(p.get_amount(String(rid)))
	return d


func _resource_delta(snap: Dictionary, _hero_unused) -> Dictionary:
	var d: Dictionary = {}
	var p: Wallet = _purse()
	for rid in snap.keys():
		var diff: int = int(p.get_amount(String(rid))) - int(snap[rid])
		if diff != 0:
			d[String(rid)] = diff
	return d


func _test_save() -> void:
	print("")
	print("== Save: Verbraucht-Zustand ==")
	# Ein Schrein als benutzt markieren, speichern, laden, pruefen.
	var objs: Array = _wm.get("_objects")
	var target: Dictionary = {}
	for o in objs:
		if int((o as Dictionary)["kind"]) == int(_wm.get("OBJECT_SHRINE_ATT")):
			target = o as Dictionary
			break
	_check(not target.is_empty(), "Soeldnerlager auf der Karte gefunden")
	if target.is_empty():
		return
	target["used"] = true
	var pos: Vector2i = target["pos"]

	# Namen sind _capture_state/_restore_state (wie in test_save_load) - im
	# ersten Anlauf hatte ich sie geraten, und der Laufzeitfehler brach nur
	# DIESE Funktion ab, waehrend die Suite trotzdem gruen meldete. Deshalb
	# unten zusaetzlich eine Sperre, die genau das auffaellig macht.
	var state: Dictionary = _wm.call("_capture_state")
	var restored: bool = bool(_wm.call("_restore_state", state))
	_check(restored, "Zustand laesst sich wieder laden")
	await process_frame
	var objs2: Array = _wm.get("_objects")
	var found := false
	for o2 in objs2:
		var od: Dictionary = o2 as Dictionary
		if Vector2i(od["pos"]) == pos and int(od["kind"]) == int(_wm.get("OBJECT_SHRINE_ATT")):
			found = bool(od.get("used", false))
			break
	_check(found, "'used' ueberlebt Speichern und Laden (reine Feld-Ergaenzung)")
	_done.append("_test_save")


func _test_wave2() -> void:
	print("")
	print("== Zweite Welle (It. 78) ==")
	var hero = _wm.get("_hero")
	var purse: Wallet = _purse()
	_wm.call("_hide_object_choice")

	# Jede neue Art steht im Katalog mit Sprite und Modell.
	for k in MO.CATALOG.keys():
		_check(MO.sprite_of(int(k)) != "" and MO.model_of(int(k)).begins_with("obj_"),
			"%s: Sprite und Modell im Katalog" % MO.name_of(int(k)))

	# Bewachte Artefakte liegen mit Wache und gueltigem Artefakt auf der Karte.
	var arts: int = 0
	for o in (_wm.get("_objects") as Array):
		var od: Dictionary = o as Dictionary
		if int(od["kind"]) == MO.ARTIFACT:
			arts += 1
			_check(int(od.get("guard", 0)) > 0, "Artefakt am Boden ist bewacht")
			_check(Artifacts.exists(String(od.get("resource", ""))), "und liegt mit gueltigem Artefakt")
	_check(arts == int(MO.CATALOG[MO.ARTIFACT]["count"]), "alle Artefakte platziert (%d)" % arts)

	# Lagerfeuer: Gold UND Ressource, danach weg.
	var objs: Array = _wm.get("_objects")
	var fire: Dictionary = {"pos": Vector2i(1, 1), "kind": MO.CAMPFIRE, "owner": -1, "guard": 0,
		"gold": 300, "resource": "gems", "amount": 4}
	objs.append(fire)
	var g0: int = purse.get_amount("gold")
	var gem0: int = purse.get_amount("gems")
	var m: String = String(_wm.call("_visit_bonus_object", fire))
	_check(purse.get_amount("gold") == g0 + 300 and purse.get_amount("gems") == gem0 + 4,
		"Lagerfeuer gibt Gold und Edelsteine (%s)" % m)
	_check(int(_wm.call("_object_at", Vector2i(1, 1))) < 0, "Lagerfeuer ist danach weg")

	# Artefakt: anlegen, weg von der Karte.
	(hero.artifacts as Array).clear()
	var aid: String = Artifacts.pick(7)
	var art: Dictionary = {"pos": Vector2i(1, 2), "kind": MO.ARTIFACT, "owner": -1, "guard": 0,
		"gold": 0, "resource": aid}
	objs.append(art)
	m = String(_wm.call("_visit_bonus_object", art))
	_check((hero.artifacts as Array).has(aid), "Artefakt angelegt (%s)" % m)
	_check(int(_wm.call("_object_at", Vector2i(1, 2))) < 0, "Artefakt ist danach weg")

	# Wassermuehle: Gold einmal pro Woche.
	var mill: Dictionary = _obj(MO.WATERMILL, Vector2i(2, 2))
	g0 = purse.get_amount("gold")
	_wm.call("_visit_bonus_object", mill)
	_check(purse.get_amount("gold") == g0 + MO.WATERMILL_GOLD, "Wassermuehle: Gold")
	m = String(_wm.call("_visit_bonus_object", mill))
	_check(purse.get_amount("gold") == g0 + MO.WATERMILL_GOLD and m.contains("schon"),
		"Wassermuehle: einmal pro Woche (%s)" % m)

	# Stallungen: Bewegung sofort und mehr max_mp bis Wochenende.
	_wm.call("_recalc_max_mp_of", hero)
	var mp0: int = int(hero.mp)
	var max0: int = int(hero.max_mp)
	var st: Dictionary = _obj(MO.STABLES, Vector2i(2, 3))
	_wm.call("_visit_bonus_object", st)
	_check(int(hero.mp) == mp0 + MO.STABLES_MP and int(hero.max_mp) == max0 + MO.STABLES_MP,
		"Stallungen: +%d Bewegung und Maximum (%d -> %d)" % [MO.STABLES_MP, max0, int(hero.max_mp)])
	m = String(_wm.call("_visit_bonus_object", st))
	_check(m.contains("schon") and bool(_wm.call("_bonus_spent", st)), "Stallungen: einmal pro Woche")
	_wm.set("_turn_number", int(_wm.get("_turn_number")) + 7)
	_wm.call("_recalc_max_mp_of", hero)
	_check(int(hero.max_mp) == max0, "Stallungen: naechste Woche wieder normal")

	# Oase: Bewegung, einmal pro Tag.
	var oa: Dictionary = _obj(MO.OASIS, Vector2i(2, 4))
	mp0 = int(hero.mp)
	_wm.call("_visit_bonus_object", oa)
	_wm.call("_visit_bonus_object", oa)
	_check(int(hero.mp) == mp0 + MO.OASIS_MP, "Oase: einmal +%d am Tag" % MO.OASIS_MP)

	# Aussichtsturm: besetzt und deckt auf.
	var look: Dictionary = {"pos": Vector2i(9, 20), "kind": MO.LOOKOUT, "owner": -1, "guard": 0,
		"gold": 0}
	objs.append(look)
	var seen0: int = _seen_tiles()
	m = String(_wm.call("_visit_bonus_object", look))
	_check(int(look["owner"]) == int(_wm.get("OWNER_HERO")),
		"Aussichtsturm: besetzt (%s)" % m)
	_check(_seen_tiles() > seen0, "Aussichtsturm deckt auf (%d -> %d)" % [seen0, _seen_tiles()])
	_wm.call("_remove_object", look)

	# Arena: Wahl, +2 auf den gewaehlten Wert, einmalig.
	var ar: Dictionary = _obj(MO.ARENA, Vector2i(3, 3))
	m = String(_wm.call("_visit_bonus_object", ar))
	_check(m.contains("waehle"), "Arena fragt nach (%s)" % m)
	var def0: int = int(hero.def)
	_wm.call("_arena_pick", ar, hero, "defense")
	_check(int(hero.def) == def0 + MO.ARENA_BONUS, "Arena: Verteidigung +%d" % MO.ARENA_BONUS)
	_wm.call("_arena_pick", ar, hero, "defense")
	_check(int(hero.def) == def0 + MO.ARENA_BONUS, "Arena: einmalig")
	_wm.call("_hide_object_choice")

	# Gluecksbrunnen und Tempel: Bonus bis zum naechsten Kampf.
	hero.luck_bonus = 0
	hero.morale_bonus = 0
	_wm.call("_visit_bonus_object", _obj(MO.FOUNTAIN, Vector2i(3, 4)))
	_wm.call("_visit_bonus_object", _obj(MO.TEMPLE, Vector2i(3, 5)))
	_check(int(hero.luck_bonus) == MO.FOUNTAIN_LUCK and int(hero.morale_bonus) == MO.TEMPLE_MORALE,
		"Gluecksbrunnen und Tempel setzen Glueck/Moral")

	# Baum des Wissens: genau eine Stufe.
	var lvl0: int = int(hero.level)
	var thresholds: Array = _wm.get("LEVEL_THRESHOLDS")
	if lvl0 < thresholds.size():
		m = String(_wm.call("_visit_bonus_object", _obj(MO.TREE, Vector2i(4, 5))))
		_check(int(hero.level) == lvl0 + 1, "Baum des Wissens: eine Stufe (%s)" % m)

	# Hexenhuette: eine Faehigkeit mehr (oder eine Stufe hoeher).
	var tiers0: int = 0
	for k2 in (hero.skills as Dictionary).keys():
		tiers0 += int(hero.skills[k2])
	m = String(_wm.call("_visit_bonus_object", _obj(MO.WITCH_HUT, Vector2i(4, 6))))
	var tiers1: int = 0
	for k3 in (hero.skills as Dictionary).keys():
		tiers1 += int(hero.skills[k3])
	_check(tiers1 == tiers0 + 1, "Hexenhuette lehrt (%s)" % m)

	# Schrein der Magie: ein Zauber, den der Held vorher nicht kannte.
	var known0: Array = _wm.call("_known_spells_of", hero)
	m = String(_wm.call("_visit_bonus_object", _obj(MO.MAGIC_SHRINE, Vector2i(4, 7))))
	var known1: Array = _wm.call("_known_spells_of", hero)
	_check(known1.size() == known0.size() + 1, "Schrein der Magie: neuer Zauber (%s)" % m)

	# Gefaengnis: ein Held mehr - oder Hinweis, wenn kein Platz ist.
	var heroes: Array = _wm.get("_heroes")
	while heroes.size() > 1:
		heroes.remove_at(heroes.size() - 1)
	var pr: Dictionary = {"pos": Vector2i(5, 5), "kind": MO.PRISON, "owner": -1, "guard": 0, "gold": 0}
	objs.append(pr)
	m = String(_wm.call("_visit_bonus_object", pr))
	_check(heroes.size() == 2, "Gefaengnis: Held befreit (%s)" % m)
	_check((heroes[1].army as Dictionary).size() > 0, "der Befreite hat Truppen")
	_check(int(_wm.call("_object_at", Vector2i(5, 5))) < 0, "Gefaengnis ist danach leer")

	# Handelsposten: besser als der Markt.
	var buy: Dictionary = _wm.get("MARKET_BUY")
	purse.add("gold", 5000)
	g0 = purse.get_amount("gold")
	_wm.call("_trading_post_trade", "ore", true)
	_check(g0 - purse.get_amount("gold") < int(buy["ore"]), "Handelsposten kauft billiger als der Markt")
	_wm.call("_hide_object_choice")

	# Die KI loescht keine Bonus-Gebaeude mehr von der Karte.
	var ai_ok: bool = true
	var src: String = (load("res://scripts/ui/WorldMapScreen.gd") as Script).source_code
	ai_ok = src.contains("MapObj.is_pickup(okind)")
	_check(ai_ok, "KI-Zielwahl beschraenkt auf Minen und Einsammel-Objekte")

	# Save: die neuen Heldenfelder ueberleben einen Round-Trip.
	hero.extra_spells = ["fireball"]
	hero.stable_week = 3
	hero.luck_bonus = 1
	var state: Dictionary = _wm.call("_capture_state")
	_wm.call("_restore_state", state)
	await process_frame
	var h2 = _wm.get("_hero")
	_check((h2.extra_spells as Array).has("fireball") and int(h2.stable_week) == 3
		and int(h2.luck_bonus) == 1, "neue Heldenfelder ueberleben Speichern und Laden")
	_done.append("_test_wave2")


func _seen_tiles() -> int:
	var n: int = 0
	for f in (_wm.get("_fog_player") as Array):
		if int(f) != 0:
			n += 1
	return n
