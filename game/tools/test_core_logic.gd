extends SceneTree

# Headless-Tests fuer die Kern-Logik (kein Rendering noetig):
#
#   godot --headless --path game/ --script tools/test_core_logic.gd
#
# Abgedeckt: GameCalendar (Kalender + Bresenham-Wachstum), Hero
# (Slot-Limit, Verluste), UnitType (Fraktions-/Gebaeude-Lookups).
# Exit 0 = gruen, Exit 1 = mindestens ein Check rot (CI-tauglich).

var _fails: int = 0
var _done: Array = []


func _init() -> void:
	_test_calendar()
	_test_growth_math()
	_test_hero_army()
	_test_hero_losses()
	_test_unit_type()
	_test_other_modules_parse()

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
		print("Core-Logik-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Core-Logik-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


# --- GameCalendar: Datums-Mathe ---

func _test_calendar() -> void:
	print("== GameCalendar ==")
	_check(GameCalendar.calendar_text(0) == "T1 W1 M1 J1",
		"Tag 1 -> T1 W1 M1 J1 (ist %s)" % GameCalendar.calendar_text(0))
	_check(GameCalendar.day_of_week(6) == 7, "turn 6 = Wochentag 7")
	_check(GameCalendar.day_of_week(7) == 1, "turn 7 = Wochentag 1 (neue Woche)")
	_check(GameCalendar.week_of_month(7) == 2, "turn 7 = Woche 2")
	# 28 Tage = 1 Monat: turn 28 ist Tag 29 -> Monat 2.
	_check(GameCalendar.month_of_year(27) == 1, "turn 27 = noch Monat 1")
	_check(GameCalendar.month_of_year(28) == 2, "turn 28 = Monat 2")
	# 12 Monate * 28 Tage = 336 Tage = 1 Jahr.
	_check(GameCalendar.year_num(335) == 1, "turn 335 = noch Jahr 1")
	_check(GameCalendar.year_num(336) == 2, "turn 336 = Jahr 2")
	_check(GameCalendar.calendar_text(336) == "T1 W1 M1 J2",
		"turn 336 -> T1 W1 M1 J2 (ist %s)" % GameCalendar.calendar_text(336))
	# Lange Form fuer die Anzeige (It. 19): das Jahr erscheint erst ab Jahr 2,
	# sonst frisst es Platz in der Kopfzeile ohne Information.
	_check(not GameCalendar.calendar_long(0).contains("Jahr"),
		"Jahr 1 wird nicht genannt (ist '%s')" % GameCalendar.calendar_long(0))
	_check(GameCalendar.calendar_long(0).begins_with("Tag 1"),
		"lange Form beginnt mit dem Tag (ist '%s')" % GameCalendar.calendar_long(0))
	_check(GameCalendar.calendar_long(336).contains("Jahr 2"),
		"ab Jahr 2 steht es drin (ist '%s')" % GameCalendar.calendar_long(336))


# --- GameCalendar: Bresenham-Wachstum ---
	_done.append("_test_calendar")

func _test_growth_math() -> void:
	print("== Wachstums-Verteilung ==")
	# Kerninvariante: Summe der 7 Tagesrationen == Wochen-Cap, fuer jeden Cap.
	for cap in range(0, 17):
		var total: int = 0
		for dow in range(1, 8):
			var d: int = GameCalendar.day_delta(cap, dow)
			_check(d >= 0, "day_delta(%d,%d) nie negativ" % [cap, dow]) if d < 0 else null
			total += d
		_check(total == cap, "Summe ueber 7 Tage == %d (ist %d)" % [cap, total])
	# catch_up(cap, 7) muss dem vollen Wochen-Cap entsprechen.
	_check(GameCalendar.catch_up(8, 7) == 8, "catch_up(8, Tag 7) == 8")
	_check(GameCalendar.catch_up(2, 3) == 0, "catch_up(2, Tag 3) == 0 (Reiterei liefert erst Tag 4)")
	_check(GameCalendar.catch_up(2, 4) == 1, "catch_up(2, Tag 4) == 1")


# --- Hero: Armee-Slots ---
	_done.append("_test_growth_math")

func _test_hero_army() -> void:
	print("== Hero: Armee-Slots ==")
	var h := Hero.new(Vector2i(0, 0))
	var ids: Array = ["a", "b", "c", "d", "e", "f"]
	for uid in ids:
		h.add_units(String(uid), 1)
	_check(h.army.size() == 6, "6 Typen passen rein")
	h.add_units("g", 1)
	_check(not h.army.has("g"), "7. Typ wird abgewiesen")
	h.add_units("a", 5)
	_check(h.count_of("a") == 6, "bestehender Stack waechst trotz vollem Limit")
	h.remove_units("b", 1)
	_check(not h.army.has("b"), "Stack auf 0 wird entfernt")
	h.add_units("g", 2)
	_check(h.count_of("g") == 2, "frei gewordener Slot wieder belegbar")


# --- Hero: Verlust-Verteilung ---
	_done.append("_test_hero_army")

func _test_hero_losses() -> void:
	print("== Hero: Verluste ==")
	var h := Hero.new(Vector2i(0, 0))
	h.add_units("men_spearman", 10)
	h.add_units("men_archer", 5)
	h.apply_proportional_losses(6)
	_check(h.total_count() == 9, "proportionale Verluste erhalten Gesamtzahl (15-6=9, ist %d)" % h.total_count())
	h.apply_proportional_losses(100)
	_check(h.army.is_empty(), "Ueberschuss-Verlust leert die Armee")
	var h2 := Hero.new(Vector2i(0, 0))
	h2.add_units("men_spearman", 4)
	h2.apply_casualties({"men_spearman": 2, "men_archer": 9})
	_check(h2.count_of("men_spearman") == 2, "apply_casualties zieht nur Vorhandenes ab")


# --- UnitType: Lookups ---
	_done.append("_test_hero_losses")

func _test_unit_type() -> void:
	print("== UnitType (units.json-Fassade, M4) ==")
	_check(UnitType.all_ids().size() == 28, "28 Einheiten geladen (%d)" % UnitType.all_ids().size())
	for fid in range(4):
		var ids: Array = UnitType.ids_for_faction(fid)
		_check(ids.size() == 7, "Fraktion %d hat 7 Tiers (%d)" % [fid, ids.size()])
		var rec: Array = UnitType.recruitable_ids_for_faction(fid)
		_check(rec.size() == 7, "Fraktion %d: alle 7 Tiers rekrutierbar (Teil 2)" % fid)
		# Tiers aufsteigend sortiert + Invarianten je Einheit
		var last_tier: int = 0
		for uid in ids:
			var t: Dictionary = UnitType.get_type(String(uid))
			_check(int(t["tier"]) >= last_tier, "%s: Tiers sortiert" % uid) if int(t["tier"]) < last_tier else null
			last_tier = int(t["tier"])
			if int(t["dmg_min"]) > int(t["dmg_max"]):
				_check(false, "%s: dmg_min <= dmg_max verletzt" % uid)
			if UnitType.growth_of(String(uid)) <= 0:
				_check(false, "%s: weekly_growth <= 0" % uid)
		# Gebaeude-Roundtrip: jede Einheit taucht in der units_for_building-
		# Liste ihres Gebaeudes auf.
		for uid in rec:
			var bid: String = UnitType.building_for(String(uid))
			var lst: Array = UnitType.units_for_building(fid, bid)
			_check(lst.has(String(uid)),
				"Fraktion %d: %s in units_for_building(%s)" % [fid, uid, bid])
	# Seit Save-v2 sind die Alt-IDs komplett aus dem Live-Pfad verschwunden
	# (Migration passiert einmalig in SaveManager, siehe test_save_load).
	for legacy in ["sword", "bow", "rider", "skelett", "vampir", "dryade"]:
		if UnitType.all_ids().has(legacy):
			_check(false, "Alt-ID %s lebt noch in all_ids()" % legacy)
	_check(not UnitType.all_ids().has("sword"), "keine Alt-IDs im Live-Pfad")
	_check(UnitType.unit_for_building(1, "markt") == "", "Markt produziert keine Einheit")
	_check(UnitType.starter_id_for_faction(2) == "nec_skeleton", "Totenreich-Starter = nec_skeleton")
	_check(UnitType.tier_of("men_angel") == 7, "Engel ist Tier 7")
	# M4 Teil 2: 4 Gebaeude decken die 7 Tiers ab.
	_check(UnitType.building_for("men_angel") == "zitadelle", "Tier 7 kommt aus der Zitadelle")
	_check(UnitType.units_for_building(1, "kaserne") == ["men_spearman", "men_archer"],
		"Kaserne (Menschen) = Speertraeger + Armbruster")
	_check(UnitType.units_for_building(1, "zitadelle") == ["men_angel"],
		"Zitadelle (Menschen) = nur Engel")
	_check(UnitType.unit_for_building(1, "kaserne") == "men_spearman",
		"unit_for_building liefert erste Einheit (Kompat)")
	# M4 Teil 3: Ability-Getter (Details in tools/test_battle.gd)
	_check(UnitType.shots_of("ork_orc") == 10, "shots_of aus den Daten")
	_check(UnitType.abilities_of("men_monk").has("ranged"), "abilities_of liefert Flags")


# Static-Calls auf weitere Module zwingen Godot, deren Scripts wirklich
# zu kompilieren - sonst gleitet ein Parse-Fehler in MapGen/Pathfinder
# durch --quit (siehe Run 27363969609, Android-Export hat es erst beim
# Build erwischt).
	_done.append("_test_unit_type")
func _test_other_modules_parse() -> void:
	print("== Andere Module (Parse-Smoke) ==")
	var rng := DeterministicRng.new(42)
	var map: Dictionary = MapGen.generate(8, 8, rng)
	_check(int(map.get("width", 0)) == 8 and (map.get("tiles", []) as Array).size() == 64,
		"MapGen.generate kompiliert + erzeugt 8x8")
	var costs: Dictionary = Pathfinder.compute_costs(map, Vector2i(0, 0))
	_check(int(costs.get(Vector2i(0, 0), -1)) == 0,
		"Pathfinder.compute_costs kompiliert + Start-Kosten == 0")
	_done.append("_test_other_modules_parse")
