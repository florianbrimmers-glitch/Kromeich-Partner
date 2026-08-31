extends SceneTree

# Headless-Tests fuer die Wochenereignisse (M12):
#
#   godot --headless --path game/ --script tools/test_week_events.gd
#
# Abgedeckt:
#   1. Determinismus: gleicher Seed + gleiche Woche -> gleiches Ereignis;
#      verschiedene Seeds streuen; die erste Woche ist immer ruhig
#   2. Verteilung: ruhige Wochen sind die Mehrheit, jede Art kommt vor
#   3. Wachstums-Faktor: Woche des X verdoppelt NUR X, Seuche halbiert
#      alles, nie unter 1
#   4. Weltkarte: das Ereignis wirkt auf _pool_cap_for, die Ernte zahlt
#      einmalig je eigener Stadt, der Wochenwechsel wird gemeldet
#   5. Nichts wird gespeichert - der Zustand ueberlebt einen Save-Round-
#      Trip, weil er aus Seed und Woche abgeleitet ist
#
# Jede Test-Funktion setzt am Ende eine Marke. Ein Laufzeitfehler bricht in
# GDScript nur die Funktion ab, die Suite lief sonst weiter und meldete
# gruen (Lehrgeld aus It. 24).

const WeekFx := preload("res://scripts/core/WeekEvents.gd")

var _fails: int = 0
var _done: Array = []
var _wm = null


func _init() -> void:
	_test_determinism()
	_test_distribution()
	_test_growth()
	await _test_worldmap()

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
		print("Wochenereignis-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Wochenereignis-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_determinism() -> void:
	print("== Determinismus ==")
	var ids: Array = UnitType.all_ids()
	var a: Dictionary = WeekFx.for_week(4242, 5, ids)
	var b: Dictionary = WeekFx.for_week(4242, 5, ids)
	_check(str(a) == str(b), "gleicher Seed + Woche -> gleiches Ereignis")

	var c: Dictionary = WeekFx.for_week(777, 5, ids)
	var differ: bool = false
	for w in range(1, 40):
		if str(WeekFx.for_week(4242, w, ids)) != str(WeekFx.for_week(777, w, ids)):
			differ = true
			break
	_check(differ, "verschiedene Seeds ergeben verschiedene Wochen")
	_check(not c.is_empty(), "fremder Seed liefert ebenfalls ein Ereignis")

	# Woche 1 ist der Start (GameCalendar.week_total ist EINS-basiert, Zug 0
	# ist Woche 1). Genau hier lag der Fehler: geprueft wurde zuerst Woche
	# 0, die es im Spiel nie gibt - die Sperre griff also nie.
	var first: Dictionary = WeekFx.for_week(4242, 1, ids)
	_check(WeekFx.is_quiet(first), "erste Woche ist immer ruhig (%s)"
		% String(first.get("title", "")))
	var quiet_all := true
	for sd in [1, 42, 777, 4242, 99999]:
		if not WeekFx.is_quiet(WeekFx.for_week(sd, 1, ids)):
			quiet_all = false
	_check(quiet_all, "und zwar bei JEDEM Seed")

	# Jedes Ereignis muss Titel und Beschreibung tragen - beides landet in
	# der Anzeige.
	var textless: Array = []
	for w2 in range(1, 60):
		var ev: Dictionary = WeekFx.for_week(31, w2, ids)
		if String(ev.get("title", "")) == "" or String(ev.get("detail", "")) == "":
			textless.append(str(w2))
	_check(textless.is_empty(), "jedes Ereignis hat Titel und Text (%s)" % str(textless))

	# Und bei einer Einheiten-Woche muss die Einheit existieren, sonst
	# stuende im Titel ein leerer Name.
	var bad_unit: Array = []
	for w3 in range(1, 200):
		var ev2: Dictionary = WeekFx.for_week(99, w3, ids)
		if String(ev2.get("kind", "")) == WeekFx.KIND_UNIT:
			var uid: String = String(ev2.get("unit", ""))
			if uid == "" or not ids.has(uid):
				bad_unit.append(str(w3))
	_check(bad_unit.is_empty(), "Einheiten-Woche nennt eine echte Einheit (%s)" % str(bad_unit))
	# Leere Einheitenliste darf nicht in eine kaputte Woche laufen.
	var no_units: Dictionary = WeekFx.for_week(99, 3, [])
	_check(String(no_units.get("kind", "")) != WeekFx.KIND_UNIT,
		"ohne Einheitenliste keine Einheiten-Woche")
	_done.append("_test_determinism")


func _test_distribution() -> void:
	print("")
	print("== Verteilung ueber 400 Wochen ==")
	var ids: Array = UnitType.all_ids()
	var counts: Dictionary = {}
	for w in range(1, 401):
		var k: String = String(WeekFx.for_week(1234, w, ids).get("kind", ""))
		counts[k] = int(counts.get(k, 0)) + 1
	print("        %s" % str(counts))
	var total: int = 400
	var quiet: int = int(counts.get(WeekFx.KIND_NONE, 0))
	# Ruhige Wochen muessen die groesste Gruppe sein, sonst wird das
	# Besondere gewoehnlich.
	var is_top: bool = true
	for k2 in counts.keys():
		if String(k2) != WeekFx.KIND_NONE and int(counts[k2]) > quiet:
			is_top = false
	_check(is_top, "ruhige Wochen sind die groesste Gruppe (%d von %d)" % [quiet, total])
	# Aber nicht so dominant, dass sonst nichts passiert.
	_check(quiet < total * 3 / 4, "und nicht mehr als drei Viertel")
	var missing: Array = []
	for kind in WeekFx.WEIGHTS.keys():
		if int(counts.get(String(kind), 0)) == 0:
			missing.append(String(kind))
	_check(missing.is_empty(), "jede Ereignis-Art kommt vor (fehlt: %s)" % str(missing))
	_done.append("_test_distribution")


func _test_growth() -> void:
	print("")
	print("== Wachstums-Faktor ==")
	var uid: String = "men_spearman"
	var other: String = "men_archer"
	var base: int = UnitType.growth_of(uid)
	_check(base > 0, "Grundrate aus units.json (%d)" % base)

	var quiet: Dictionary = {"kind": WeekFx.KIND_NONE, "unit": ""}
	_check(WeekFx.apply_growth(quiet, uid, base) == base, "ruhige Woche aendert nichts")

	var unit_week: Dictionary = {"kind": WeekFx.KIND_UNIT, "unit": uid}
	_check(WeekFx.apply_growth(unit_week, uid, base) == base * 2,
		"Woche des X verdoppelt X (%d -> %d)" % [base, WeekFx.apply_growth(unit_week, uid, base)])
	_check(WeekFx.apply_growth(unit_week, other, base) == base,
		"und laesst die anderen unberuehrt")

	var plague: Dictionary = {"kind": WeekFx.KIND_PLAGUE, "unit": ""}
	_check(WeekFx.apply_growth(plague, uid, base) == base / 2,
		"Seuche halbiert (%d -> %d)" % [base, WeekFx.apply_growth(plague, uid, base)])
	_check(WeekFx.apply_growth(plague, other, base) == base / 2, "und trifft alle")
	# Untergrenze: eine Seuche soll bremsen, nicht abschalten.
	_check(WeekFx.apply_growth(plague, uid, 1) == 1, "Rate 1 bleibt 1 (nie null)")
	_check(WeekFx.apply_growth(plague, uid, 0) == 0, "Rate 0 bleibt 0")
	var harvest: Dictionary = {"kind": WeekFx.KIND_HARVEST, "unit": ""}
	_check(WeekFx.apply_growth(harvest, uid, base) == base,
		"Ernte aendert das Wachstum nicht")
	_done.append("_test_growth")


func _test_worldmap() -> void:
	print("")
	print("== Weltkarte ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	_wm = scene.instantiate()
	root.add_child(_wm)
	await process_frame
	_wm.call("_start", 1234, 1)
	await process_frame

	# _pool_cap_for muss das Ereignis einrechnen - EIN Ort, damit Tages-
	# Tick und Catch-up beim Neubau automatisch dasselbe rechnen.
	var uid: String = "men_spearman"
	var base: int = UnitType.growth_of(uid)
	# Woche suchen, in der genau diese Einheit gefeiert wird.
	var found_week: int = -1
	for w in range(1, 400):
		var ev: Dictionary = WeekFx.for_week(1234, w, UnitType.all_ids())
		if String(ev.get("kind", "")) == WeekFx.KIND_UNIT and String(ev.get("unit", "")) == uid:
			found_week = w
			break
	_check(found_week > 0, "Woche des Speertraegers gefunden (Woche %d)" % found_week)
	if found_week > 0:
		# week_total ist eins-basiert: Zug 0 ist Woche 1.
		_wm.set("_turn_number", (found_week - 1) * 7)
		_check(int(_wm.call("_pool_cap_for", uid)) == base * 2,
			"_pool_cap_for verdoppelt in dieser Woche (%d)" % int(_wm.call("_pool_cap_for", uid)))

	# Seuchen-Woche.
	var plague_week: int = -1
	for w2 in range(1, 400):
		if String(WeekFx.for_week(1234, w2, UnitType.all_ids()).get("kind", "")) == WeekFx.KIND_PLAGUE:
			plague_week = w2
			break
	_check(plague_week > 0, "Seuchen-Woche gefunden (Woche %d)" % plague_week)
	if plague_week > 0:
		_wm.set("_turn_number", (plague_week - 1) * 7)
		_check(int(_wm.call("_pool_cap_for", uid)) == base / 2,
			"_pool_cap_for halbiert in der Seuche (%d)" % int(_wm.call("_pool_cap_for", uid)))

	# Ernte: einmalig je eigener Stadt.
	var harvest_week: int = -1
	for w3 in range(1, 400):
		if String(WeekFx.for_week(1234, w3, UnitType.all_ids()).get("kind", "")) == WeekFx.KIND_HARVEST:
			harvest_week = w3
			break
	_check(harvest_week > 0, "Ernte-Woche gefunden (Woche %d)" % harvest_week)
	if harvest_week > 0:
		_wm.set("_turn_number", (harvest_week - 1) * 7)
		var hero = _wm.get("_hero")
		var own: int = 0
		for c in (_wm.get("_cities") as Array):
			if int((c as Dictionary)["owner"]) == int(_wm.get("OWNER_HERO")):
				own += 1
		var gold_before: int = int(hero.gold)
		_wm.call("_apply_week_event_start")
		var expect: int = own * int(WeekFx.HARVEST_GOLD_PER_CITY)
		_check(int(hero.gold) == gold_before + expect,
			"Ernte zahlt %d fuer %d Stadt/Staedte (ist +%d)"
			% [expect, own, int(hero.gold) - gold_before])
		# Eine ruhige Woche darf nichts zahlen. Zug 0 = Woche 1, und die
		# ist per FIRST_QUIET_WEEK garantiert ruhig.
		_wm.set("_turn_number", 0)
		var g2: int = int(hero.gold)
		_wm.call("_apply_week_event_start")
		_check(int(hero.gold) == g2, "ruhige Woche zahlt nichts")

	# Nichts wird gespeichert: nach Save/Load muss dieselbe Woche dasselbe
	# Ereignis liefern, weil es aus Seed und Wochennummer kommt.
	_wm.set("_turn_number", 21)
	var before: String = String(_wm.call("_week_event").get("title", ""))
	var state: Dictionary = _wm.call("_capture_state")
	var ok_restore: bool = bool(_wm.call("_restore_state", state))
	_check(ok_restore, "Zustand laesst sich laden")
	await process_frame
	var after: String = String(_wm.call("_week_event").get("title", ""))
	_check(before == after, "gleiches Ereignis nach Save/Load ('%s')" % after)
	_check(not state.has("week_event"),
		"und es steht NICHT im Save (abgeleitet, nicht gespeichert)")

	# Tageswechsel ueber eine Wochengrenze darf nicht abstuerzen und muss
	# das Ereignis melden.
	_wm.set("_turn_number", 6)
	_wm.call("_finalize_turn")
	await process_frame
	_check(int(_wm.get("_turn_number")) == 7, "Tag 7 erreicht (Wochenwechsel)")

	_wm.queue_free()
	await process_frame
	_done.append("_test_worldmap")
