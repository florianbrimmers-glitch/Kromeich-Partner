extends SceneTree

# Headless-Test fuer M2 (Fraktionswahl + Seed):
#
#   godot --headless --path game/ --script tools/test_new_game.gd
#
# 4 Fraktionen x 3 Seeds: WorldMap starten mit Wunsch-Fraktion, pruefen
# dass _player_faction stimmt, die Startstadt der Fraktion gehoert und
# ein simulierter Tag ohne Fehler durchlaeuft. Zusaetzlich: Zufalls-
# Fraktion (-1) startet weiterhin, und derselbe Seed liefert dieselbe
# Karte unabhaengig von der Fraktionswahl (Determinismus-Invariante).

var _fails: int = 0
var _done: Array = []


func _init() -> void:
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm := scene.instantiate()
	root.add_child(wm)
	await process_frame

	var owner_hero: int = wm.get("OWNER_HERO") if wm.get("OWNER_HERO") != null else 0

	for fid in range(4):
		for seed_val in [11, 4711, 987654]:
			wm.call("_start", seed_val, fid)
			var got_faction: int = wm.get("_player_faction")
			_check(got_faction == fid,
				"Fraktion %d/Seed %d: _player_faction == %d (ist %d)" % [fid, seed_val, fid, got_faction])
			var start_city_ok := false
			for c in (wm.get("_cities") as Array):
				if int(c["owner"]) == owner_hero:
					start_city_ok = int(c["faction"]) == fid
					break
			_check(start_city_ok, "Fraktion %d/Seed %d: Startstadt gehoert Fraktion" % [fid, seed_val])
			wm.call("_on_end_turn")
			await process_frame

	# Zufalls-Fraktion (-1): startet und hat irgendeine gueltige Fraktion.
	wm.call("_start", 11, -1)
	var f_rand: int = wm.get("_player_faction")
	_check(f_rand >= 0 and f_rand <= 3, "Zufalls-Fraktion liefert 0..3 (ist %d)" % f_rand)

	# Determinismus: gleicher Seed -> gleiche Stadt-Positionen, egal ob
	# Fraktion 0 oder 3 gewaehlt wurde.
	wm.call("_start", 2024, 0)
	var pos_a: Array = []
	for c in (wm.get("_cities") as Array):
		pos_a.append(c["pos"])
	wm.call("_start", 2024, 3)
	var pos_b: Array = []
	for c in (wm.get("_cities") as Array):
		pos_b.append(c["pos"])
	_check(str(pos_a) == str(pos_b), "Seed 2024: Stadt-Layout unabhaengig von Fraktionswahl")

	_test_tileset(wm)
	_test_city_margins(wm)
	_test_monsters(wm)

	wm.queue_free()
	await process_frame

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
		print("Neues-Spiel-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Neues-Spiel-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


# Weltkarten-Tileset (It. 19). Sperre gegen zwei Fehler, die man nur auf dem
# Geraet sieht: fehlt eine Variante, faellt der Screen still auf die alte
# Einzelkachel zurueck und die Karte kachelt wieder sichtbar; ist
# _tile_variant nicht deterministisch, sieht dieselbe Karte nach Save/Load
# anders aus.
func _test_tileset(wm) -> void:
	print("")
	print("== Weltkarten-Tileset ==")
	var names: Array = wm.get("TERRAIN_NAMES").values()
	var variants: int = int(wm.get("TERRAIN_VARIANTS"))
	var missing: Array = []
	for n in names:
		for v in range(variants):
			var path: String = "res://assets/world/terrain/%s_%d.svg" % [String(n), v]
			if not ResourceLoader.exists(path):
				missing.append("%s_%d" % [String(n), v])
	_check(missing.is_empty(), "%d Gelaende x %d Varianten vorhanden (fehlen: %s)"
		% [names.size(), variants, str(missing)])

	var missing_fringe: Array = []
	for side in wm.get("FRINGE_SIDES"):
		if not ResourceLoader.exists("res://assets/world/terrain/fringe_%s.svg" % String(side)):
			missing_fringe.append(String(side))
	_check(missing_fringe.is_empty(),
		"Uebergangs-Fransen fuer alle vier Seiten (fehlen: %s)" % str(missing_fringe))

	var missing_fog: Array = []
	for v2 in range(int(wm.get("FOG_VARIANTS"))):
		if not ResourceLoader.exists("res://assets/world/terrain/fog_%d.svg" % v2):
			missing_fog.append(str(v2))
	_check(missing_fog.is_empty(), "Nebelkacheln vorhanden (fehlen: %s)" % str(missing_fog))

	# Determinismus + Wertebereich.
	wm.call("_start", 4242, 1)
	var first: Array = []
	for x in range(12):
		for y in range(12):
			first.append(int(wm.call("_tile_variant", x, y, variants)))
	var in_range := true
	for v3 in first:
		if int(v3) < 0 or int(v3) >= variants:
			in_range = false
			break
	_check(in_range, "alle Varianten-Indizes liegen in 0..%d" % (variants - 1))
	wm.call("_start", 4242, 1)
	var second: Array = []
	for x2 in range(12):
		for y2 in range(12):
			second.append(int(wm.call("_tile_variant", x2, y2, variants)))
	_check(str(first) == str(second), "gleicher Seed -> gleiche Varianten")
	# Und: verschiedene Seeds streuen anders, sonst waere der Seed wirkungslos.
	wm.call("_start", 777, 1)
	var third: Array = []
	for x3 in range(12):
		for y3 in range(12):
			third.append(int(wm.call("_tile_variant", x3, y3, variants)))
	_check(str(first) != str(third), "anderer Seed -> andere Streuung")
	# Nachbarfelder duerfen nicht systematisch dieselbe Variante bekommen,
	# sonst entstehen sichtbare Bloecke gleicher Kacheln.
	var same_as_right: int = 0
	for x4 in range(11):
		for y4 in range(12):
			if int(wm.call("_tile_variant", x4, y4, variants)) \
					== int(wm.call("_tile_variant", x4 + 1, y4, variants)):
				same_as_right += 1
	# Erwartungswert ist 1/count. BEIDE Schranken pruefen: zu viele gleiche
	# Nachbarn ergeben Bloecke, ZU WENIGE ein Schachbrett. Der erste Hash
	# lieferte exakt 0 % - waagerechte Nachbarn konnten wegen der
	# Paritaets-Kopplung nie uebereinstimmen - und eine reine
	# Obergrenzen-Pruefung haette das durchgelassen.
	var ratio: float = float(same_as_right) / float(11 * 12)
	var expect: float = 1.0 / float(variants)
	_check(ratio > expect * 0.5 and ratio < expect * 2.0,
		"Nachbarn streuen wie erwartet (%.0f%% gleich, erwartet %.0f%%, erlaubt %.0f-%.0f%%)"
		% [ratio * 100.0, expect * 100.0, expect * 50.0, expect * 200.0])
	_done.append("_test_tileset")


# Staedte muessen Abstand zum Kartenrand halten (It. 34). Eine der Staedte
# ist der STARTPUNKT des Helden: lag sie in Reihe 0, begann das Spiel in der
# Kartenecke, der erste Bildschirm war fast vollstaendig Nebel und die halbe
# Sichtweite fiel aus der Karte. Der Fehler war im Kachel-Kontaktbogen nicht
# zu sehen, sondern erst in der komponierten Ansicht
# (tools/preview_world_full.gd).
func _test_city_margins(wm) -> void:
	print("")
	print("== Staedte halten Abstand zum Kartenrand ==")
	var margin: int = int(wm.get("CITY_BORDER_MARGIN"))
	var w: int = int(wm.get("MAP_WIDTH"))
	var h: int = int(wm.get("MAP_HEIGHT"))
	_check(margin >= 1, "Rand-Abstand ist gesetzt (%d)" % margin)
	var bad: Array = []
	var starts_at_edge: Array = []
	for seed_value in [1, 7, 42, 555, 4711, 90210]:
		wm.call("_start", seed_value, -1)
		for c in (wm.get("_cities") as Array):
			var p: Vector2i = c["pos"]
			if p.x < margin or p.y < margin \
					or p.x > w - 1 - margin or p.y > h - 1 - margin:
				bad.append("Seed %d: %s" % [seed_value, str(p)])
		var hero = wm.get("_hero")
		var hp: Vector2i = hero.position
		if hp.x < margin or hp.y < margin \
				or hp.x > w - 1 - margin or hp.y > h - 1 - margin:
			starts_at_edge.append("Seed %d: %s" % [seed_value, str(hp)])
	_check(bad.is_empty(), "keine Stadt am Rand ueber 6 Seeds (%s)" % str(bad))
	_check(starts_at_edge.is_empty(),
		"kein Start in der Kartenecke (%s)" % str(starts_at_edge))
	_done.append("_test_city_margins")


# Wandernde Monster (It. 35): echte Kreatur auf der Karte UND im Kampf,
# ohne dass die Begegnung staerker wird als vorher.
func _test_monsters(wm) -> void:
	print("")
	print("== Wandernde Monster: Kreatur und Kraft ==")
	wm.call("_start", 2468, 1)
	var monsters: Array = wm.get("_monsters")
	_check(monsters.size() == int(wm.get("MONSTER_COUNT")),
		"%d Monster platziert" % monsters.size())

	var pool: Array = wm.get("MONSTER_POOL")
	# GOLD, nicht HP (It. 38): Trefferpunkte sind ueber die Tiers hinweg
	# nicht vergleichbar - 30 HP als ein Greif schlagen 30 HP als drei
	# Speertraeger muehelos. Die Preise sind das balancierte Kraftmass.
	var per: int = int(wm.get("MONSTER_GOLD_PER_STRENGTH"))
	var tol: float = float(wm.get("MONSTER_GOLD_TOLERANCE"))
	var bad_unit: Array = []
	var bad_budget: Array = []
	var too_big: Array = []
	for m in monsters:
		var uid: String = String(wm.call("_monster_unit", m))
		var cnt: int = int(wm.call("_monster_count", m))
		var price: int = UnitType.cost_of(uid)
		var budget: int = int(m["strength"]) * per
		if not pool.has(uid):
			bad_unit.append(uid)
		if cnt < 1:
			bad_budget.append("%s x%d" % [uid, cnt])
		# Kraft-Schranke: der Gold-Wert des Stacks muss im Rahmen des
		# Budgets bleiben. Ohne sie waere aus der Anzeige-Aenderung von
		# It. 35 still eine Schwierigkeits-Aenderung geworden - und genau
		# das ist passiert, bis der Durchspiel-Test es zeigte.
		if float(cnt * price) > float(budget) * tol + 0.001:
			too_big.append("%s x%d = %d Gold, Budget %d"
				% [uid, cnt, cnt * price, budget])
	_check(bad_unit.is_empty(), "jede Kreatur kommt aus MONSTER_POOL (%s)" % str(bad_unit))
	_check(bad_budget.is_empty(), "jeder Stack hat mindestens 1 Kreatur (%s)" % str(bad_budget))
	_check(too_big.is_empty(), "kein Stack sprengt sein Gold-Budget (%s)" % str(too_big))
	# Und die Startarmee muss gegen ein Staerke-1-Monster klar vorn liegen:
	# das ist der erste Kampf des Spiels.
	var start_gold: int = UnitType.cost_of("men_spearman") * 3
	var s1_gold: int = int(wm.call("_army_gold",
		wm.call("_monster_army", {"pos": Vector2i(3, 3), "strength": 1})))
	_check(s1_gold * 2 <= start_gold * 2 and s1_gold <= start_gold,
		"Staerke-1-Monster (%d Gold) ist schwaecher als die Startarmee (%d Gold)"
		% [s1_gold, start_gold])

	# Verschiedene Kreaturen ueber die Karte - sonst waere die Auswahl
	# wirkungslos (dasselbe Problem wie die Kachel-Variante in It. 19).
	var kinds: Array = []
	for seed_value in [1, 42, 2468, 7777]:
		wm.call("_start", seed_value, 1)
		for m2 in (wm.get("_monsters") as Array):
			var u2: String = String(wm.call("_monster_unit", m2))
			if not kinds.has(u2):
				kinds.append(u2)
	_check(kinds.size() >= 4, "%d verschiedene Kreaturen ueber 4 Seeds (%s)"
		% [kinds.size(), str(kinds)])

	# Staerke 1 darf nie eine teure Kreatur sein. Genau das hat It. 35
	# nicht verhindert: ueber HP gemessen war ein Greif (25 HP) fuer
	# Staerke 3 zulaessig, obwohl er 200 Gold wert ist - mehr als die
	# ganze Startarmee.
	var heavy: Array = []
	for h in range(64):
		var u3: String = String(wm.call("_pick_monster_unit", 1, h * 7919))
		if float(UnitType.cost_of(u3)) > float(per) * tol + 0.001:
			heavy.append(u3)
	_check(heavy.is_empty(), "Staerke 1 bleibt billig (%s)" % str(heavy))
	var heavy3: Array = []
	for h2 in range(64):
		var u4: String = String(wm.call("_pick_monster_unit", 3, h2 * 6151))
		if UnitType.cost_of(u4) > 3 * per:
			heavy3.append(u4)
	_check(heavy3.is_empty(),
		"auch Staerke 3 bleibt im Budget (%s)" % str(heavy3))

	# ALTER SPIELSTAND ohne "unit": Kreatur wird abgeleitet, bleibt aber
	# ueber Aufrufe stabil - sonst wechselte das Monsterbild bei jedem
	# Neuzeichnen.
	var legacy: Dictionary = {"pos": Vector2i(5, 9), "strength": 2}
	var a: String = String(wm.call("_monster_unit", legacy))
	var b: String = String(wm.call("_monster_unit", legacy))
	_check(a != "" and a == b,
		"Alt-Monster ohne Feld 'unit' bekommt stabil eine Kreatur (%s)" % a)
	_check(int(wm.call("_monster_count", legacy)) >= 1,
		"und eine Stackgroesse")

	# Der Kampf bekommt genau diese Kreatur.
	var army: Dictionary = wm.call("_monster_army", legacy)
	_check(army.size() == 1 and army.has(a),
		"Kampf-Armee enthaelt die gezeigte Kreatur (%s)" % str(army))

	# Objekt-Wachen laufen ueber dieselbe Herleitung - vorher waren ALLE
	# Wachen menschliche Speertraeger, auch im Ork-Gebiet.
	wm.call("_start", 2468, 1)
	var guarded: int = 0
	var human_only: bool = true
	var empty_army: Array = []
	for obj in (wm.get("_objects") as Array):
		var g: int = int(obj.get("guard", 0))
		if g <= 0:
			continue
		guarded += 1
		var ga: Dictionary = wm.call("_object_guard_army", obj)
		if ga.is_empty():
			empty_army.append(str(obj.get("pos", Vector2i.ZERO)))
		for k in ga.keys():
			if String(k) != "men_spearman":
				human_only = false
	_check(guarded > 0, "%d bewachte Objekte auf der Karte" % guarded)
	_check(empty_army.is_empty(),
		"jede Wache hat eine Kampf-Armee (%s)" % str(empty_army))
	_check(not human_only,
		"Wachen sind nicht mehr alle menschliche Speertraeger")
	# Wache 0 = kein Kampf, also auch keine Armee.
	_check((wm.call("_object_guard_army", {"guard": 0}) as Dictionary).is_empty(),
		"unbewachtes Objekt hat keine Armee")
	_done.append("_test_monsters")
