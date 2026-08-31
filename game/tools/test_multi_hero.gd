extends SceneTree

# Headless-Tests fuer die Helden-Struktur (M13a):
#
#   godot --headless --path game/ --script tools/test_multi_hero.gd
#
# Abgedeckt:
#   1. EIN Held verhaelt sich wie vorher - das ist die Abnahmebedingung
#      dieser Iteration, es kommt kein Gameplay dazu
#   2. Zwei Helden: eigene Position, eigene Bewegungspunkte, eigene Armee,
#      eigene Skills
#   3. Der Geldbeutel ist GETEILT - er gehoert dem Spieler, nicht dem
#      Helden (genau der Fehler, den M13a behebt)
#   4. Tap auf einen anderen eigenen Helden wechselt ihn und rechnet die
#      Reichweite neu
#   5. Tageswechsel setzt die Punkte ALLER Helden zurueck
#   6. Save/Load mit zwei Helden, inklusive aktivem Index
#   7. `_hero` liefert null bei leerer Liste - 16 Stellen im Screen pruefen
#      auf null und wuerden sonst auf einem kaputten Zugriff sterben
#
# Jede Test-Funktion setzt am Ende eine Marke; die Soll-Liste kommt aus
# get_method_list() (It. 31).

var _fails: int = 0
var _done: Array = []
var _wm = null


func _init() -> void:
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	_wm = scene.instantiate()
	root.add_child(_wm)
	await process_frame
	_wm.call("_start", 4711, 1)
	await process_frame

	_test_single_hero()
	_test_purse_shared()
	_test_two_heroes()
	_test_switch_by_tap()
	_test_end_turn_all()
	await _test_save_roundtrip()
	_test_empty_list()

	var missing: Array = []
	for m in get_method_list():
		var mn: String = String(m["name"])
		if mn.begins_with("_test") and not _done.has(mn):
			missing.append(mn)
	_check(missing.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)" % str(missing))

	_wm.queue_free()
	await process_frame

	print("")
	if _fails == 0:
		print("Helden-Struktur-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Helden-Struktur-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


# Zweiten Helden anlegen - in M13a gibt es dafuer noch keinen Spielweg
# (keine Taverne), der Test setzt ihn direkt in die Liste.
func _add_hero(pos: Vector2i) -> Hero:
	var h := Hero.new(pos, int(_wm.get("BASE_MAX_MP")))
	(_wm.get("_heroes") as Array).append(h)
	# Was JEDER echte "Held dazu"-Pfad tun muss (Taverne in M13b): Nebel
	# und Reichweite neu rechnen. Ohne das deckt der neue Held nichts auf,
	# und ein Save-Roundtrip liefert danach ein anderes Nebelbild als der
	# Zustand davor - genau daran ist dieser Test zuerst haengengeblieben.
	_wm.call("_recompute_fog_player")
	_wm.call("_recompute_costs")
	return h


func _test_single_hero() -> void:
	print("== Ein Held: alles wie vorher ==")
	var heroes: Array = _wm.get("_heroes")
	_check(heroes.size() == 1, "genau EIN Held nach _start (sind %d)" % heroes.size())
	_check(int(_wm.get("_active_hero")) == 0, "der aktive Index ist 0")
	var hero = _wm.get("_hero")
	_check(hero != null, "_hero liefert den aktiven Helden")
	_check(hero == heroes[0], "und zwar genau den aus der Liste")
	_check(hero.position == (_wm.get("_map") as Dictionary)["hero_spawn"],
		"er steht auf dem Spawn %s" % str(hero.position))
	_check(int(hero.max_mp) == int(_wm.get("BASE_MAX_MP")),
		"mit den Start-Bewegungspunkten (%d)" % int(hero.max_mp))
	_check(hero.total_count() > 0, "und der Start-Armee (%d)" % hero.total_count())
	_done.append("_test_single_hero")


func _test_purse_shared() -> void:
	print("")
	print("== Der Beutel gehoert dem Spieler ==")
	var purse: Wallet = _wm.get("_purse")
	_check(purse != null, "es gibt einen Spieler-Beutel")
	_check(purse.get_amount("gold") == int(_wm.get("STARTING_GOLD")),
		"mit dem Start-Gold (%d)" % purse.get_amount("gold"))
	# Der HELD darf kein eigenes Gold mehr fuehren - sonst gaebe es zwei
	# Wahrheiten und die Frage "welcher Held haelt das Gold" waere zurueck.
	var hero = _wm.get("_hero")
	_check(int(hero.gold) == 0,
		"der Held selbst fuehrt kein Gold mehr (ist %d)" % int(hero.gold))

	# Zwei Helden, EIN Beutel: Ausgabe wirkt fuer beide.
	var b := _add_hero(Vector2i(hero.position.x, hero.position.y))
	var before: int = purse.get_amount("gold")
	purse.pay({"gold": 100})
	_check(purse.get_amount("gold") == before - 100,
		"Ausgabe senkt den Beutel (%d -> %d)" % [before, purse.get_amount("gold")])
	_wm.set("_active_hero", 1)
	_check((_wm.get("_purse") as Wallet).get_amount("gold") == before - 100,
		"und der zweite Held sieht denselben Stand")
	_check(_wm.get("_hero") == b, "Wechsel auf Index 1 liefert den zweiten Helden")
	_wm.set("_active_hero", 0)
	purse.add("gold", 100)
	_done.append("_test_purse_shared")


func _test_two_heroes() -> void:
	print("")
	print("== Zwei Helden, getrennte Werte ==")
	var heroes: Array = _wm.get("_heroes")
	while heroes.size() > 1:
		heroes.remove_at(heroes.size() - 1)
	_wm.set("_active_hero", 0)
	var a = heroes[0]
	var b := _add_hero(a.position + Vector2i(2, 0))

	_check(a.position != b.position, "eigene Positionen (%s / %s)"
		% [str(a.position), str(b.position)])
	a.mp = 12
	b.mp = 36
	_check(int(a.mp) == 12 and int(b.mp) == 36, "eigene Bewegungspunkte")
	b.add_units("men_archer", 4)
	_check(int(a.army.get("men_archer", 0)) == 0
			and int(b.army.get("men_archer", 0)) == 4,
		"eigene Armeen (A %s, B %s)" % [str(a.army), str(b.army)])
	a.skills = {"logistics": 3}
	b.skills = {}
	_wm.call("_recalc_max_mp")
	_check(int(a.max_mp) > int(b.max_mp),
		"eigene Skills wirken je Held (Logistik: %d vs %d)"
		% [int(a.max_mp), int(b.max_mp)])
	# Mana ebenfalls pro Held: unterschiedliches Wissen, unterschiedlicher
	# Deckel.
	a.knowledge = 5
	b.knowledge = 0
	a.mana = 0
	b.mana = 0
	_wm.call("_regen_mana")
	_check(int(a.mana) > 0 and int(b.mana) > 0, "beide regenerieren Mana")
	a.knowledge = 0
	_done.append("_test_two_heroes")


func _test_switch_by_tap() -> void:
	print("")
	print("== Tap wechselt den Helden ==")
	var heroes: Array = _wm.get("_heroes")
	_check(heroes.size() >= 2, "zwei Helden vorhanden (%d)" % heroes.size())
	_wm.set("_active_hero", 0)
	_wm.call("_recompute_costs")
	var costs_a: int = (_wm.get("_costs") as Dictionary).size()
	var b_pos: Vector2i = heroes[1].position

	# Tap-Position aus Feldkoordinate: dieselbe Rechnung wie im Screen.
	var origin: Vector2 = _wm.call("_map_origin")
	var ts: float = float(_wm.get("_tile_size"))
	var pos: Vector2 = origin + Vector2(float(b_pos.x) + 0.5,
		float(b_pos.y) + 0.5) * ts
	_wm.call("_handle_tap", pos)
	_check(int(_wm.get("_active_hero")) == 1,
		"Tap auf Held B macht ihn aktiv (Index %d)" % int(_wm.get("_active_hero")))
	_check(_wm.get("_hero") == heroes[1], "_hero zeigt jetzt auf B")
	# Die Reichweite MUSS neu gerechnet sein - sie haengt an Position und
	# Punkten des Helden. Ohne das liefe der naechste Zug auf den Kosten
	# des alten Helden.
	var costs_b: int = (_wm.get("_costs") as Dictionary).size()
	_check(costs_b > 0, "Reichweite fuer B berechnet (%d Felder)" % costs_b)
	_check(_wm.get("_costs").has(b_pos) and int(_wm.get("_costs")[b_pos]) == 0,
		"und sie beginnt auf SEINEM Feld")

	# Tap auf den AKTIVEN Helden darf nicht umschalten (er kann auf einer
	# eigenen Stadt stehen - dann soll das Stadt-Panel aufgehen).
	_wm.call("_handle_tap", pos)
	_check(int(_wm.get("_active_hero")) == 1, "Tap auf den aktiven Helden aendert nichts")
	print("        (Reichweite A %d Felder, B %d Felder)" % [costs_a, costs_b])
	_wm.set("_active_hero", 0)
	_wm.call("_recompute_costs")
	_done.append("_test_switch_by_tap")


func _test_end_turn_all() -> void:
	print("")
	print("== Tageswechsel gilt fuer alle Helden ==")
	var heroes: Array = _wm.get("_heroes")
	_check(heroes.size() >= 2, "zwei Helden vorhanden")
	for h in heroes:
		h.mp = 1
	_wm.call("_on_end_turn")
	var not_reset: Array = []
	for i in range(heroes.size()):
		var h2 = heroes[i]
		if int(h2.mp) != int(h2.max_mp):
			not_reset.append("Held %d: %d von %d" % [i + 1, int(h2.mp), int(h2.max_mp)])
	_check(not_reset.is_empty(),
		"alle Helden haben ihre Punkte zurueck (%s)" % str(not_reset))
	_done.append("_test_end_turn_all")


func _test_save_roundtrip() -> void:
	print("")
	print("== Save/Load mit zwei Helden ==")
	var heroes: Array = _wm.get("_heroes")
	while heroes.size() > 2:
		heroes.remove_at(heroes.size() - 1)
	if heroes.size() < 2:
		_add_hero(heroes[0].position + Vector2i(3, 1))
	# Armee SETZEN, nicht addieren: _test_two_heroes hat B schon vier
	# Armbruster gegeben, und dann prueft dieser Test gegen eine Zahl, die
	# er selbst nicht kontrolliert.
	heroes[1].army = {"men_archer": 7}
	heroes[1].position = heroes[0].position + Vector2i(3, 1)
	_wm.set("_active_hero", 1)
	(_wm.get("_purse") as Wallet).set_amount("gold", 4242)
	# Der Test hat den zweiten Helden versetzt - im Spiel folgt darauf
	# immer eine Nebel-Neuberechnung. Ohne sie vergleicht der
	# Roundtrip-Check einen veralteten Nebel mit einem frisch gerechneten.
	_wm.call("_recompute_fog_player")

	var snap: Dictionary = _wm.call("_capture_state")
	_check((snap.get("heroes", []) as Array).size() == 2,
		"Snapshot enthaelt beide Helden (%d)" % (snap.get("heroes", []) as Array).size())
	_check(int(snap.get("active_hero", -1)) == 1, "und den aktiven Index")
	_check(int((snap.get("purse", {}) as Dictionary).get("gold", 0)) == 4242,
		"und den Beutel")
	_check(not snap.has("hero"), "der alte Einzel-Schluessel wird nicht mehr geschrieben")

	# Ueber JSON, so kommt es von der Platte zurueck.
	var json_snap: Dictionary = JSON.parse_string(JSON.stringify(snap))
	var ok: bool = _wm.call("_restore_state", json_snap)
	_check(ok, "_restore_state akzeptiert den Snapshot")
	var heroes2: Array = _wm.get("_heroes")
	_check(heroes2.size() == 2, "zwei Helden wiederhergestellt (%d)" % heroes2.size())
	_check(int(_wm.get("_active_hero")) == 1, "aktiver Index wiederhergestellt")
	_check(int((_wm.get("_purse") as Wallet).get_amount("gold")) == 4242,
		"Beutel wiederhergestellt")
	_check(int(heroes2[1].army.get("men_archer", 0)) == 7,
		"die Armee des zweiten Helden ueberlebt (%s)" % str(heroes2[1].army))
	# Und der Vergleich, der alles auf einmal prueft.
	var snap2: Dictionary = _wm.call("_capture_state")
	_check(JSON.stringify(snap) == JSON.stringify(snap2),
		"capture -> restore -> capture identisch")
	_done.append("_test_save_roundtrip")


func _test_empty_list() -> void:
	print("")
	print("== Leere Liste: _hero ist null ==")
	# 16 Stellen im Screen pruefen `_hero != null`. Der Getter MUSS null
	# liefern, sonst stirbt der erste dieser Aufrufe an einem
	# Index-Zugriff auf ein leeres Array.
	var saved: Array = (_wm.get("_heroes") as Array).duplicate()
	_wm.set("_heroes", [])
	_check(_wm.get("_hero") == null, "_hero == null bei leerer Liste")
	_wm.set("_active_hero", 5)
	_check(_wm.get("_hero") == null, "_hero == null bei Index ausserhalb")
	_wm.set("_heroes", saved)
	_wm.set("_active_hero", 0)
	_check(_wm.get("_hero") != null, "und wieder da, sobald die Liste steht")
	_done.append("_test_empty_list")
