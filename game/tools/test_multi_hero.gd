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
#   8. M13b: Anwerben (Kosten, Obergrenze, Startarmee der STADT-Fraktion,
#      Nebel) und die Niederlage-Regel - ein gefallener Held beendet das
#      Spiel nur, wenn er der letzte war
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
	_test_hire()
	_test_defeat_keeps_playing()
	_test_city_defense_any_hero()

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


# --- M13b -----------------------------------------------------------------

func _test_hire() -> void:
	print("")
	print("== Held anwerben ==")
	# Frischer Zustand: ein Held, eine eigene Stadt, Held steht darauf.
	_wm.call("_start", 4711, 1)
	var heroes: Array = _wm.get("_heroes")
	_check(heroes.size() == 1, "ein Held zum Start (%d)" % heroes.size())
	var city_idx: int = -1
	var cities: Array = _wm.get("_cities")
	for i in range(cities.size()):
		if int(cities[i]["owner"]) == int(_wm.get("OWNER_HERO")):
			city_idx = i
			break
	_check(city_idx >= 0, "eigene Stadt gefunden")
	_wm.set("_selected_city", city_idx)
	var purse: Wallet = _wm.get("_purse")
	var cost: Dictionary = _wm.get("HERO_HIRE_COST")

	# Zu wenig Gold: nichts passiert.
	purse.set_amount("gold", 10)
	_wm.call("_on_hire_hero")
	_check((_wm.get("_heroes") as Array).size() == 1,
		"ohne Gold kein Held (%d)" % (_wm.get("_heroes") as Array).size())

	# Mit Gold: Held kommt, Gold weg.
	purse.set_amount("gold", int(cost.get("gold", 0)) + 100)
	var fog_before: int = _explored(_wm)
	_wm.call("_on_hire_hero")
	var heroes2: Array = _wm.get("_heroes")
	_check(heroes2.size() == 2, "Held angeworben (%d)" % heroes2.size())
	_check(purse.get_amount("gold") == 100,
		"Gold bezahlt (Rest %d)" % purse.get_amount("gold"))
	var nh: Hero = heroes2[1] as Hero
	_check(nh.position == Vector2i(cities[city_idx]["pos"]),
		"er steht in der Stadt %s" % str(nh.position))
	_check(nh.total_count() == int(_wm.get("HERO_HIRE_UNITS")),
		"mit %d Einheiten (sind %d)" % [int(_wm.get("HERO_HIRE_UNITS")), nh.total_count()])
	# Startarmee in der Fraktion DER STADT - das macht den Moral-Mix zur
	# Entscheidung (M6) und ist bei einer erobereten Fremdstadt der ganze
	# Witz.
	var city_fid: int = int(cities[city_idx].get("faction", -1))
	var army_fid: int = -2
	for uid in nh.army.keys():
		army_fid = int(UnitType.faction_of(String(uid)))
	_check(army_fid == city_fid,
		"Einheiten in der Fraktion der Stadt (%d == %d)" % [army_fid, city_fid])
	_check(int(nh.mp) == int(nh.max_mp), "und mit vollen Bewegungspunkten")
	_check(int(nh.mana) > 0, "und mit Mana (%d)" % int(nh.mana))
	# Nebel: der neue Held deckt auf. Er steht in der eigenen Stadt, die
	# ohnehin Sicht gibt - deshalb wird hier nur geprueft, dass NICHTS
	# verloren geht.
	_check(_explored(_wm) >= fog_before,
		"Nebel nicht geschrumpft (%d -> %d)" % [fog_before, _explored(_wm)])

	# Obergrenze.
	var maxh: int = int(_wm.get("MAX_HEROES"))
	for k in range(maxh + 2):
		purse.set_amount("gold", int(cost.get("gold", 0)) + 50)
		_wm.call("_on_hire_hero")
	_check((_wm.get("_heroes") as Array).size() == maxh,
		"Obergrenze %d haelt (%d)" % [maxh, (_wm.get("_heroes") as Array).size()])
	_check(purse.get_amount("gold") == int(cost.get("gold", 0)) + 50,
		"und der letzte, abgelehnte Versuch kostet nichts")
	_done.append("_test_hire")


func _test_defeat_keeps_playing() -> void:
	print("")
	print("== Ein gefallener Held ist nicht das Spielende ==")
	_wm.call("_start", 4711, 1)
	var heroes: Array = _wm.get("_heroes")
	_add_hero(heroes[0].position + Vector2i(2, 0))
	_wm.set("_active_hero", 1)
	_check((_wm.get("_heroes") as Array).size() == 2, "zwei Helden")

	# Der aktive (zweite) Held faellt.
	_wm.call("_on_battle_defeat")
	_check(not bool(_wm.get("_game_lost")),
		"Spiel laeuft weiter, solange ein Held lebt")
	_check((_wm.get("_heroes") as Array).size() == 1,
		"der gefallene ist aus der Liste (%d)" % (_wm.get("_heroes") as Array).size())
	_check(int(_wm.get("_active_hero")) == 0,
		"der aktive Index zeigt auf einen lebenden Helden (%d)"
		% int(_wm.get("_active_hero")))
	_check(_wm.get("_hero") != null, "und _hero liefert ihn")

	# Der letzte Held faellt: JETZT ist Schluss. Er bleibt aber in der
	# Liste stehen - siehe die Begruendung in _on_battle_defeat: der ganze
	# Screen darf sich darauf verlassen, dass `_hero` nie null ist, und ein
	# Weltzustand ohne Helden hat vor M13b nie existiert.
	_wm.call("_on_battle_defeat")
	_check(bool(_wm.get("_game_lost")), "das Spiel ist verloren")
	_check((_wm.get("_heroes") as Array).size() == 1,
		"der letzte Held bleibt als Objekt stehen (Invariante _hero != null)")
	_check(_wm.get("_hero") != null, "und _hero liefert weiter etwas")

	# Ein NICHT aktiver Held kann fallen (Verteidigungskampf um eine Stadt,
	# in der ein anderer Held stand) - dann muss genau DER verschwinden.
	_wm.call("_start", 4711, 1)
	var h0 = (_wm.get("_heroes") as Array)[0]
	var hb: Hero = _add_hero(h0.position + Vector2i(2, 0))
	hb.army = {"men_archer": 5}
	_wm.set("_active_hero", 0)
	_wm.call("_on_battle_defeat", 1)
	var rest: Array = _wm.get("_heroes")
	_check(rest.size() == 1 and rest[0] == h0,
		"der benannte Held ist gefallen, nicht der aktive")
	_check(not bool(_wm.get("_game_lost")), "und das Spiel laeuft weiter")
	_done.append("_test_defeat_keeps_playing")


func _test_city_defense_any_hero() -> void:
	print("")
	print("== Jeder Held in der Stadt verteidigt sie ==")
	_wm.call("_start", 4711, 1)
	var cities: Array = _wm.get("_cities")
	var city_idx: int = -1
	for i in range(cities.size()):
		if int(cities[i]["owner"]) == int(_wm.get("OWNER_HERO")):
			city_idx = i
			break
	_check(city_idx >= 0, "eigene Stadt gefunden")
	var city_pos: Vector2i = Vector2i(cities[city_idx]["pos"])
	# Der AKTIVE Held steht woanders, ein zweiter steht in der Stadt.
	var heroes: Array = _wm.get("_heroes")
	(heroes[0] as Hero).position = city_pos + Vector2i(3, 0)
	var hb: Hero = _add_hero(city_pos)
	hb.army = {"men_archer": 6}
	_wm.set("_active_hero", 0)
	_check(int(_wm.call("_hero_index_at", city_pos)) == 1,
		"_hero_index_at findet den nicht-aktiven Helden")

	# Sieg: er bekommt zurueck, was von SEINEM Beitrag uebrig ist.
	cities[city_idx]["garrison_army"] = {"men_spearman": 10}
	# WICHTIG: das letzte Argument ist ein INDEX. Ein bool wuerde zu 0 -
	# und 0 ist ein gueltiger Held.
	_wm.call("_on_city_defense_result", {
		"outcome": "victory", "casualties": {},
		"player_remaining": {"men_spearman": 8, "men_archer": 4},
		"enemy_remaining": {},
	}, city_idx, -1, 99, 1)
	_check(hb.count_of("men_archer") == 4,
		"der Verteidiger bekommt seine Ueberlebenden (%d)" % hb.count_of("men_archer"))
	_check((heroes[0] as Hero).count_of("men_archer") == 0,
		"und der aktive Held nicht")
	_check(int(cities[city_idx]["owner"]) == int(_wm.get("OWNER_HERO")),
		"Sieg: die Stadt bleibt beim Spieler")

	# Niederlage: GENAU dieser Held faellt, der aktive lebt weiter.
	_wm.call("_on_city_defense_result", {
		"outcome": "defeat", "casualties": {},
		"player_remaining": {}, "enemy_remaining": {},
	}, city_idx, -1, 99, 1)
	var rest: Array = _wm.get("_heroes")
	_check(rest.size() == 1, "der Verteidiger ist gefallen (%d uebrig)" % rest.size())
	_check(rest[0] == heroes[0], "und zwar er, nicht der aktive")
	_check(not bool(_wm.get("_game_lost")), "das Spiel laeuft weiter")
	_done.append("_test_city_defense_any_hero")


# Wie viele Felder sind aufgedeckt? (Nur fuer den Nebel-Check beim
# Anwerben; test_playthrough.gd hat dieselbe Hilfsfunktion - sie ist drei
# Zeilen lang und ein gemeinsames Modul dafuer waere mehr Aufwand als
# Nutzen.)
func _explored(wm) -> int:
	var fog: Array = wm.get("_fog_player")
	var hidden: int = int(wm.get("FOG_HIDDEN"))
	var n: int = 0
	for v in fog:
		if int(v) != hidden:
			n += 1
	return n
