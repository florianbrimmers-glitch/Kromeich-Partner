extends SceneTree

# Headless-Tests fuer die Kampf-Effekte (Iteration 17):
#
#   godot --headless --path game/ --script tools/test_battle_vfx.gd
#
# Abgedeckt:
#   1. Queue-Mechanik: spawn/advance/busy, abgelaufene Effekte fliegen raus
#   2. Verzoegerung: pending-Effekte starten spaeter und werden nicht
#      gezeichnet (der Treffer darf nicht blitzen, waehrend der Pfeil fliegt)
#   3. Test-Bremse: fx_speed = 0.0 raeumt die Queue in einem Schritt -
#      genau darauf verlassen sich test_battle und test_siege
#   4. Kurven: arc_point trifft beide Enden exakt und woelbt sich dazwischen
#   5. Ein echter Kampf erzeugt Treffer, Zahlen und einen Zerfall
#   6. Kein Leck: am Kampfende ist die Queue leer

const Vfx := preload("res://scripts/core/BattleVfx.gd")
const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")

var _fails: int = 0
var _done: Array = []


func _init() -> void:
	_test_queue()
	_test_delay()
	_test_brake()
	_test_curves()
	await _test_in_battle()

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
		print("Effekt-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Effekt-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_queue() -> void:
	print("== Queue-Mechanik ==")
	var q: Array = Vfx.new_queue()
	_check(q.is_empty(), "neue Queue ist leer")
	_check(not Vfx.busy(q), "leere Queue blockt nicht")
	_check(not Vfx.advance(q, 0.1), "leere Queue meldet keine Aenderung")

	Vfx.spawn(q, Vfx.IMPACT, {"at": Vector2i(2, 3)})
	_check(q.size() == 1, "Effekt liegt in der Queue")
	_check(Vfx.busy(q), "IMPACT blockt die Zugkette")
	_check(Vfx.has_kind(q, Vfx.IMPACT), "has_kind findet ihn")
	_check(is_equal_approx(float(q[0]["dur"]), float(Vfx.DUR[Vfx.IMPACT])),
		"Dauer kommt aus der DUR-Tabelle")

	# Halbe Dauer: noch da, Fortschritt bei ~0.5.
	Vfx.advance(q, float(Vfx.DUR[Vfx.IMPACT]) * 0.5)
	_check(q.size() == 1, "nach halber Dauer noch da")
	_check(absf(Vfx.progress(q[0]) - 0.5) < 0.05,
		"Fortschritt ~0.5 (ist %.2f)" % Vfx.progress(q[0]))
	# Rest: weg.
	Vfx.advance(q, float(Vfx.DUR[Vfx.IMPACT]))
	_check(q.is_empty(), "abgelaufener Effekt fliegt raus")
	_check(not Vfx.busy(q), "Kette ist wieder frei")

	# NUMBER und POPUP duerfen die Kette NICHT aufhalten, sonst steht der
	# Kampf 0.8 s pro Schlag still.
	var q2: Array = Vfx.new_queue()
	Vfx.spawn(q2, Vfx.NUMBER, {"at": Vector2i.ZERO, "text": "7"})
	Vfx.spawn(q2, Vfx.POPUP, {"at": Vector2i.ZERO, "text": "Moral!"})
	_check(not Vfx.busy(q2), "Zahlen und Einblendungen blocken nicht")
	_done.append("_test_queue")


func _test_delay() -> void:
	print("== Verzoegerung (Staffelung) ==")
	var q: Array = Vfx.new_queue()
	var flight: float = Vfx.shot(q, Vector2i(0, 0), Vector2i(4, 0))
	_check(flight > 0.0, "shot() liefert die Flugdauer (%.2f s)" % flight)
	Vfx.hit(q, Vector2i(4, 0), 12, Color(1, 1, 1), flight)
	var impacts: Array = Vfx.of_kind(q, Vfx.IMPACT)
	_check(impacts.size() == 1, "ein Einschlag in der Queue")
	_check(Vfx.pending(impacts[0]),
		"Einschlag wartet noch (t = %.2f)" % float(impacts[0]["t"]))
	_check(Vfx.progress(impacts[0]) == 0.0, "pending -> Fortschritt 0")
	# Der Bremsweg muss die Flugzeit einschliessen, sonst zieht die Kette
	# weiter, bevor der Einschlag gezeichnet wurde.
	_check(Vfx.busy_time_left(q) >= flight,
		"Bremsweg deckt die Flugzeit (%.2f >= %.2f)" % [Vfx.busy_time_left(q), flight])

	Vfx.advance(q, flight + 0.01)
	impacts = Vfx.of_kind(q, Vfx.IMPACT)
	_check(impacts.size() == 1 and not Vfx.pending(impacts[0]),
		"nach der Flugzeit laeuft der Einschlag")
	_check(not Vfx.has_kind(q, Vfx.PROJECTILE), "Geschoss ist angekommen und weg")

	# time_left_of filtert nach Art - der Nahkampf staffelt sich damit
	# hinter einen laufenden Anmarsch.
	var q3: Array = Vfx.new_queue()
	Vfx.moved(q3, Vector2i(1, 1), Vector2i(3, 1), "men_spearman", 0)
	_check(Vfx.time_left_of(q3, Vfx.MOVE) > 0.0, "Anmarsch hat Restzeit")
	_check(Vfx.time_left_of(q3, Vfx.IMPACT) == 0.0,
		"time_left_of filtert nach Art")
	_done.append("_test_delay")


func _test_brake() -> void:
	print("== Test-Bremse fx_speed = 0 ==")
	var q: Array = Vfx.new_queue()
	Vfx.shot(q, Vector2i(0, 0), Vector2i(9, 7))
	Vfx.hit(q, Vector2i(9, 7), 30, Color(1, 1, 1), 5.0)
	Vfx.died(q, Vector2i(9, 7), "men_spearman", 1, 5.0)
	_check(q.size() >= 3, "mehrere Effekte, teils weit verzoegert")
	var changed: bool = Vfx.advance(q, 0.016, 0.0)
	_check(changed, "advance mit speed 0 meldet Aenderung")
	_check(q.is_empty(), "EIN Schritt raeumt alles ab, auch die verzoegerten")
	_check(not Vfx.busy(q), "Kette laeuft synchron durch")
	_done.append("_test_brake")


func _test_curves() -> void:
	print("== Kurven ==")
	var a := Vector2(0, 100)
	var b := Vector2(200, 100)
	_check(Vfx.arc_point(a, b, 0.0, 50.0).is_equal_approx(a), "Bogen startet exakt bei from")
	_check(Vfx.arc_point(a, b, 1.0, 50.0).is_equal_approx(b), "Bogen endet exakt bei to")
	var mid: Vector2 = Vfx.arc_point(a, b, 0.5, 50.0)
	_check(absf(mid.x - 100.0) < 0.01, "Scheitel liegt in der Mitte")
	# y waechst in Godot nach unten -> der Scheitel muss KLEINER sein.
	_check(absf(mid.y - 50.0) < 0.01, "Scheitel liegt 50 px hoch (ist %.1f)" % mid.y)

	_check(Vfx.ping_pong(0.0) == 0.0 and Vfx.ping_pong(1.0) == 0.0,
		"Ausfallschritt endet dort, wo er begann")
	_check(absf(Vfx.ping_pong(0.5) - 1.0) < 0.001, "Scheitel des Ausfallschritts bei 0.5")

	_check(Vfx.ease_out(0.0) == 0.0 and Vfx.ease_out(1.0) == 1.0, "ease_out trifft beide Enden")
	_check(Vfx.ease_out(0.5) > 0.5, "ease_out ist vorne schneller")
	_check(Vfx.ease_in_out(0.0) == 0.0 and Vfx.ease_in_out(1.0) == 1.0,
		"ease_in_out trifft beide Enden")

	# Wackeln klingt ab und ist deterministisch.
	var s1: Vector2 = Vfx.shake_offset(0.2, 8.0)
	var s2: Vector2 = Vfx.shake_offset(0.2, 8.0)
	_check(s1.is_equal_approx(s2), "shake ist deterministisch (Vorschau-Bilder!)")
	_check(Vfx.shake_offset(1.0, 8.0).is_equal_approx(Vector2.ZERO),
		"shake ist am Ende bei null")

	var rf: Array = Vfx.rise_fade(0.0)
	_check(float(rf[1]) == 1.0, "Zahl startet voll sichtbar")
	rf = Vfx.rise_fade(1.0)
	_check(float(rf[1]) == 0.0, "Zahl ist am Ende ausgeblendet")
	rf = Vfx.rise_fade(0.5)
	_check(float(rf[1]) == 1.0 and float(rf[0]) > 0.0,
		"in der Mitte schon gestiegen, aber noch voll lesbar")
	_done.append("_test_curves")


func _test_in_battle() -> void:
	print("== Effekte in einem echten Kampf ==")
	var bs = TBS.new()
	bs.size = Vector2(1080, 1920)
	root.add_child(bs)
	await process_frame
	# Effekte AN, aber die Kette wird von Hand getrieben - so laesst sich
	# pruefen, was ein Schlag tatsaechlich erzeugt.
	bs.set_battle({
		"player_stacks": [{"type": "men_archer", "count": 20}],
		"enemy_stacks": [{"type": "ork_goblin", "count": 1}],
		"seed": 7, "allow_flee": true,
	})
	bs._obstacles = []
	bs._ob_map = {}
	await process_frame

	var player: Dictionary = bs._p_stacks[0]
	var enemy: Dictionary = bs._e_stacks[0]
	# Schuetze und Ziel in Schusslinie setzen.
	player["pos"] = Vector2i(1, 4)
	enemy["pos"] = Vector2i(6, 4)
	bs._fx.clear()

	# Direkter Schuss ueber den Spieler-Pfad.
	_activate_player_slot(bs)
	bs._try_attack_enemy(0)

	_check(Vfx.has_kind(bs._fx, Vfx.PROJECTILE), "Schuss erzeugt ein Geschoss")
	_check(Vfx.has_kind(bs._fx, Vfx.IMPACT), "Schuss erzeugt einen Einschlag")
	_check(Vfx.has_kind(bs._fx, Vfx.NUMBER), "Schuss erzeugt eine Schadenszahl")
	# 20 Armbruster gegen 1 Goblin: der Stack muss fallen.
	_check(int(enemy["count"]) <= 0, "Ziel ist gefallen")
	_check(Vfx.has_kind(bs._fx, Vfx.DEATH), "gefallener Stack erzeugt einen Zerfall")
	# Der Zerfall traegt Typ und Seite selbst - sonst kann er nicht
	# gezeichnet werden, weil der Stack datenseitig schon leer ist.
	var deaths: Array = Vfx.of_kind(bs._fx, Vfx.DEATH)
	_check(String(deaths[0].get("uid", "")) == "ork_goblin",
		"Zerfall kennt die Einheit (%s)" % String(deaths[0].get("uid", "")))
	_check(Vector2i(deaths[0]["at"]) == Vector2i(6, 4), "Zerfall kennt das Feld")

	# Einschlag und Zerfall sind hinter die Flugzeit gestaffelt.
	var imp: Array = Vfx.of_kind(bs._fx, Vfx.IMPACT)
	_check(Vfx.pending(imp[0]), "Einschlag wartet auf das Geschoss")

	# Kein Leck: Zeit weit genug vorspulen -> Queue leer.
	Vfx.advance(bs._fx, 10.0)
	_check(bs._fx.is_empty(), "kein Effekt ueberlebt seine Dauer")

	# Nahkampf erzeugt einen Ausfallschritt.
	bs._fx.clear()
	var e2: Dictionary = {"type": "ork_goblin", "count": 40,
		"top_hp": UnitType.hp_of("ork_goblin"), "count_start": 40,
		"pos": Vector2i(2, 4), "side": 1, "retaliations": 0}
	bs._e_stacks = [e2]
	player["pos"] = Vector2i(1, 4)
	bs._melee_exchange(player, e2)
	_check(Vfx.has_kind(bs._fx, Vfx.LUNGE), "Nahkampf erzeugt einen Ausfallschritt")
	var lunges: Array = Vfx.of_kind(bs._fx, Vfx.LUNGE)
	_check(Vector2i(lunges[0]["from"]) == Vector2i(1, 4)
		and Vector2i(lunges[0]["to"]) == Vector2i(2, 4),
		"Ausfallschritt zeigt zum Ziel")
	# Nach dem Austausch muss die Verzoegerung zurueckgesetzt sein, sonst
	# startet der naechste Effekt mit einem Rest-Offset.
	_check(bs._fx_delay == 0.0, "_fx_delay ist nach dem Austausch zurueckgesetzt")

	bs.queue_free()


# Setzt den aktiven Slot auf den ersten lebenden Spieler-Stack, damit
# _try_attack_enemy den richtigen Angreifer findet.
	_done.append("_test_in_battle")
func _activate_player_slot(bs) -> void:
	bs._rebuild_order()
	for i in range(bs._turn_order.size()):
		if int(bs._turn_order[i]["side"]) == 0:
			bs._active_slot = i
			return
