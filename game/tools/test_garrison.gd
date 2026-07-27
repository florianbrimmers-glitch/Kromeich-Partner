extends SceneTree

# Headless-Tests fuer echte Stadt-Garnisonen (M9b):
#
#   godot --headless --path game/ --script tools/test_garrison.gd
#
# Abgedeckt:
#   1. Garrison-Mathe (synth/total/add/remove/casualties/stacks)
#   2. Karte startet mit echten Verteidigern in neutralen Staedten
#   3. Rekrutieren ohne Held vor Ort fuellt die Garnison
#   4. Verschieben Held <-> Stadt inkl. Slot-Limit
#   5. Angriff auf eine Stadt nutzt die gespeicherten Einheiten
#   6. Gescheiterte Belagerung laesst Ueberlebende zurueck
#   7. Verteidigungskampf-Callback (Sieg haelt die Stadt, Niederlage nicht)

const SaveLib := preload("res://scripts/core/SaveManager.gd")

var _fails: int = 0


func _init() -> void:
	_test_math()
	await _test_map_and_recruit()
	await _test_battle_paths()

	print("")
	if _fails == 0:
		print("Garnison-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Garnison-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_math() -> void:
	print("== Garrison: Mathe ==")
	var small: Dictionary = Garrison.synth(2, 2)
	_check(Garrison.total(small) == 2, "synth(2) hat Staerke 2")
	_check(small.has("nec_skeleton"), "kleine Garnison = nur Tier 1")
	var mid: Dictionary = Garrison.synth(1, 5)
	_check(Garrison.total(mid) == 5, "synth(5) hat Staerke 5 (ist %d)" % Garrison.total(mid))
	_check(mid.size() == 2, "mittlere Garnison mischt zwei Tiers")
	var big: Dictionary = Garrison.synth(3, 12)
	_check(Garrison.total(big) == 12, "synth(12) hat Staerke 12 (ist %d)" % Garrison.total(big))
	_check(big.size() == 3, "grosse Garnison mischt drei Tiers")
	for uid in big.keys():
		if UnitType.faction_of(String(uid)) != 3:
			_check(false, "synth nutzt nur Einheiten der Fraktion")
	_check(Garrison.total(Garrison.synth(1, 0)) == 0, "synth(0) ist leer")
	_check(Garrison.is_empty({}), "is_empty erkennt leere Garnison")

	var a: Dictionary = {}
	Garrison.add(a, "men_archer", 3)
	Garrison.add(a, "men_archer", 2)
	_check(int(a["men_archer"]) == 5, "add summiert")
	Garrison.remove(a, "men_archer", 5)
	_check(not a.has("men_archer"), "remove auf 0 loescht den Eintrag")
	Garrison.add(a, "men_spearman", 4)
	Garrison.apply_casualties(a, {"men_spearman": 3, "men_archer": 9})
	_check(int(a.get("men_spearman", 0)) == 1, "apply_casualties zieht nur Vorhandenes ab")

	var stacks: Array = Garrison.to_stacks({"men_archer": 2, "men_spearman": 5})
	_check(stacks.size() == 2, "to_stacks liefert beide Stacks")
	_check(String(stacks[0]["type"]) == "men_spearman", "to_stacks sortiert nach Tier")
	var back: Dictionary = Garrison.from_stacks(stacks)
	_check(int(back["men_spearman"]) == 5 and int(back["men_archer"]) == 2,
		"from_stacks ist die Umkehrung")
	_check(Garrison.summary({}) == "leer", "summary fuer leere Garnison")
	_check(Garrison.summary({"men_spearman": 3}).contains("3"), "summary nennt die Anzahl")


func _world():
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	return wm


func _test_map_and_recruit() -> void:
	print("== Karte + Rekrutieren ==")
	var wm = _world()
	await process_frame
	wm.call("_start", 20250, 1)
	var cities: Array = wm._cities
	var neutral_with_units: int = 0
	for c in cities:
		if int(c["owner"]) == -1 and not Garrison.is_empty(c.get("garrison_army", {})):
			neutral_with_units += 1
			# Verteidiger muessen zur Stadt-Fraktion passen.
			for uid in (c["garrison_army"] as Dictionary).keys():
				if UnitType.faction_of(String(uid)) != int(c["faction"]):
					_check(false, "Garnison-Einheit passt nicht zur Stadt-Fraktion")
	_check(neutral_with_units > 0,
		"neutrale Staedte haben echte Verteidiger (%d)" % neutral_with_units)

	# Eigene Stadt finden, Kaserne + Pool setzen und OHNE Held rekrutieren.
	var own_idx: int = -1
	for i in range(cities.size()):
		if int(cities[i]["owner"]) == 0:
			own_idx = i
			break
	_check(own_idx >= 0, "Startstadt gefunden")
	var own: Dictionary = cities[own_idx]
	var fid: int = int(own["faction"])
	var t1: String = String(UnitType.recruitable_ids_for_faction(fid)[0])
	(own["buildings"] as Array).append("kaserne")
	own["pools"] = {t1: 5}
	# Held wegstellen, damit "ohne Held" gilt.
	var away := Vector2i(Vector2i(own["pos"]).x + 3, Vector2i(own["pos"]).y + 3)
	wm._hero.position = away
	wm._hero.wallet.set_amount("gold", 99999)
	var hero_before: int = wm._hero.total_count()
	wm.call("_recruit_unit", own_idx, t1)
	_check(int((own["garrison_army"] as Dictionary).get(t1, 0)) == 1,
		"Rekrut ohne Held vor Ort landet in der Garnison")
	_check(wm._hero.total_count() == hero_before, "Heldenarmee bleibt unveraendert")

	# Jetzt Held in die Stadt und verschieben. Der Held startet mit einer
	# Anfangsarmee, deshalb wird mit Differenzen geprueft.
	wm._hero.position = Vector2i(own["pos"])
	var h0: int = wm._hero.count_of(t1)
	wm.call("_recruit_unit", own_idx, t1)
	_check(wm._hero.count_of(t1) == h0 + 1, "mit Held vor Ort geht der Rekrut zum Helden")
	var g0: int = int((own["garrison_army"] as Dictionary).get(t1, 0))
	wm.call("_move_garrison", own_idx, t1, true, false)
	_check(wm._hero.count_of(t1) == h0
		and int((own["garrison_army"] as Dictionary).get(t1, 0)) == g0 + 1,
		"1 Einheit vom Helden in die Stadt verschoben")
	var g1: int = int((own["garrison_army"] as Dictionary).get(t1, 0))
	wm.call("_move_garrison", own_idx, t1, false, true)
	_check(wm._hero.count_of(t1) == h0 + g1
		and int((own["garrison_army"] as Dictionary).get(t1, 0)) == 0,
		"alle Einheiten zurueck zum Helden (%d beim Helden)" % wm._hero.count_of(t1))
	# Slot-Limit: Held voll -> neuer Typ bleibt in der Stadt.
	var gar2: Dictionary = own["garrison_army"] as Dictionary
	Garrison.add(gar2, "men_angel", 1)
	wm._hero.army = {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1, "f": 1}
	wm.call("_move_garrison", own_idx, "men_angel", false, false)
	_check(int(gar2.get("men_angel", 0)) == 1,
		"voller Held: Einheit bleibt in der Garnison")
	wm.queue_free()
	await process_frame


func _test_battle_paths() -> void:
	print("== Kampf-Pfade ==")
	var wm = _world()
	await process_frame
	wm.call("_start", 777, 1)
	# Stadt-Angriff: die uebergebenen Gegner-Stacks muessen die
	# gespeicherten Einheiten sein.
	var target: Dictionary = {}
	for c in wm._cities:
		if int(c["owner"]) == -1 and not Garrison.is_empty(c.get("garrison_army", {})):
			target = c
			break
	_check(not target.is_empty(), "neutrale Stadt mit Garnison gefunden")
	var gar: Dictionary = target["garrison_army"]
	var stacks: Array = Garrison.to_stacks(gar)
	_check(Garrison.total(Garrison.from_stacks(stacks)) == Garrison.total(gar),
		"Stacks entsprechen genau der Garnison")

	# Gescheiterte Belagerung: _on_city_result mit "defeat" muss die
	# Ueberlebenden in die Stadt zurueckschreiben.
	var city_idx: int = wm._cities.find(target)
	var survivors: Dictionary = {}
	for uid in gar.keys():
		survivors[String(uid)] = 1
		break
	wm._hero.army = {"men_spearman": 5}
	wm.call("_on_city_result", {
		"outcome": "defeat", "casualties": {},
		"player_remaining": {}, "enemy_remaining": survivors,
	}, city_idx, Vector2i(target["pos"]), 0)
	_check(Garrison.total(wm._cities[city_idx]["garrison_army"]) == 1,
		"gescheiterte Belagerung laesst Ueberlebende zurueck (%d)"
		% Garrison.total(wm._cities[city_idx]["garrison_army"]))

	# Verteidigungskampf: Sieg haelt die Stadt, Niederlage verliert sie.
	var own_idx: int = -1
	for i in range(wm._cities.size()):
		if int(wm._cities[i]["owner"]) == 0:
			own_idx = i
			break
	var own: Dictionary = wm._cities[own_idx]
	own["garrison_army"] = {"men_spearman": 10}
	wm._hero.army = {"men_archer": 3}
	wm._hero.position = Vector2i(99, 99)   # Held NICHT in der Stadt
	wm.call("_on_city_defense_result", {
		"outcome": "victory", "casualties": {},
		"player_remaining": {"men_spearman": 6}, "enemy_remaining": {},
	}, own_idx, 0, 99, false)
	_check(int(own["owner"]) == 0, "Sieg: Stadt bleibt beim Spieler")
	_check(Garrison.total(own["garrison_army"]) == 6,
		"Sieg: Ueberlebende bleiben Garnison (%d)" % Garrison.total(own["garrison_army"]))
	_check(wm._hero.count_of("men_archer") == 3, "Held war nicht beteiligt")

	own["garrison_army"] = {"men_spearman": 10}
	# Anderer Angreifer-Index: der erste ist im Sieg-Fall oben gefallen,
	# und ein gefallener Angreifer kann keine Stadt uebernehmen.
	var att_idx: int = -1
	for i in range(wm._enemies.size()):
		if wm._enemies[i]["hero"] != null:
			att_idx = i
			break
	_check(att_idx >= 0, "lebende KI als Angreifer gefunden")
	wm.call("_on_city_defense_result", {
		"outcome": "defeat", "casualties": {},
		"player_remaining": {}, "enemy_remaining": {"ork_goblin": 4},
	}, own_idx, att_idx, 99, false)
	_check(int(own["owner"]) != 0, "Niederlage: Stadt wechselt den Besitzer")
	_check(Garrison.is_empty(own["garrison_army"]), "Niederlage: Garnison ist gefallen")
	wm.queue_free()
	await process_frame

	# Save-Migration v2 -> v3: alte Zahl wird zu echten Einheiten.
	print("== Save-Migration v2 -> v3 ==")
	var mig: Dictionary = SaveLib.migrate({
		"save_version": 2, "seed": 1, "hero": {},
		"cities": [{"faction": 2, "garrison": 4}],
	})
	_check(int(mig["save_version"]) == SaveLib.SAVE_VERSION,
		"migrate hebt auf v%d" % SaveLib.SAVE_VERSION)
	var mc: Dictionary = (mig["cities"] as Array)[0]
	_check(mc.has("garrison_army") and Garrison.total(mc["garrison_army"]) == 4,
		"Staerke 4 wurde zu 4 echten Einheiten")
	for uid in (mc["garrison_army"] as Dictionary).keys():
		if UnitType.faction_of(String(uid)) != 2:
			_check(false, "migrierte Garnison nutzt die Stadt-Fraktion")
	_check(true, "migrierte Garnison passt zur Fraktion")
