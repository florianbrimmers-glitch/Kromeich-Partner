extends SceneTree

# Headless-Tests fuer die Kern-Logik (kein Rendering noetig):
#
#   godot --headless --path game/ --script tools/test_core_logic.gd
#
# Abgedeckt: GameCalendar (Kalender + Bresenham-Wachstum), Hero
# (Slot-Limit, Verluste), UnitType (Fraktions-/Gebaeude-Lookups).
# Exit 0 = gruen, Exit 1 = mindestens ein Check rot (CI-tauglich).

var _fails: int = 0


func _init() -> void:
	_test_calendar()
	_test_growth_math()
	_test_hero_army()
	_test_hero_losses()
	_test_unit_type()

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


# --- GameCalendar: Bresenham-Wachstum ---

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

func _test_hero_losses() -> void:
	print("== Hero: Verluste ==")
	var h := Hero.new(Vector2i(0, 0))
	h.add_units("sword", 10)
	h.add_units("bow", 5)
	h.apply_proportional_losses(6)
	_check(h.total_count() == 9, "proportionale Verluste erhalten Gesamtzahl (15-6=9, ist %d)" % h.total_count())
	h.apply_proportional_losses(100)
	_check(h.army.is_empty(), "Ueberschuss-Verlust leert die Armee")
	var h2 := Hero.new(Vector2i(0, 0))
	h2.add_units("sword", 4)
	h2.apply_casualties({"sword": 2, "bow": 9})
	_check(h2.count_of("sword") == 2, "apply_casualties zieht nur Vorhandenes ab")


# --- UnitType: Lookups ---

func _test_unit_type() -> void:
	print("== UnitType ==")
	for fid in range(4):
		var ids: Array = UnitType.ids_for_faction(fid)
		_check(ids.size() == 3, "Fraktion %d hat 3 Einheiten" % fid)
		for uid in ids:
			var bid: String = UnitType.building_for(String(uid))
			var back: String = UnitType.unit_for_building(fid, bid)
			_check(back == String(uid),
				"Fraktion %d: %s <-> %s Roundtrip" % [fid, uid, bid])
	_check(UnitType.unit_for_building(1, "markt") == "", "Markt produziert keine Einheit")
	_check(UnitType.starter_id_for_faction(2) == "skelett", "Totenreich-Starter = Skelett")
