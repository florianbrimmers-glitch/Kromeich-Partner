extends SceneTree

# Durchspiel-Test (It. 38):
#
#   godot --headless --path game/ --script tools/test_playthrough.gd
#
# WARUM DIESE SUITE: es gab 17 Suiten und KEINE hat das Spiel gespielt.
# test_ai_smoke druckt 30 Mal "Tag beenden" - der Spieler tut dabei
# nichts: er baut nicht, rekrutiert nicht, laeuft nicht, kaempft nicht.
# Jeder Teil war einzeln geprueft, die KETTE nie:
#   Weltkarte -> Kampf-Overlay -> Callback -> Weltkarte
# Genau in dieser Kette sitzen die Fehler, die ein Spieler als
# "haengt" erlebt.
#
# Der Test spielt selbst: bauen und rekrutieren in der eigenen Stadt,
# dann zum naechsten erreichbaren Ziel laufen (Objekt, Monster, fremde
# Stadt), Kaempfe im Overlay ausspielen, Tag beenden. Danach wird
# FORTSCHRITT verlangt, nicht nur Abwesenheit von Abstuerzen.
#
# Die Kampf-Heuristik ist absichtlich dumm (angreifen was nebendran
# steht, sonst hinlaufen, sonst warten) - sie soll den Kampf ZU ENDE
# bringen, nicht gut spielen.

const MAX_TURNS := 40
const MAX_BATTLE_STEPS := 400
# Zwei Seeds fuer die CI (rund 5 s). Breiter pruefen von Hand: SEEDS auf
# [1, 42, 777, 4711, 90210, 123456] und MAX_TURNS auf 60 - so wurden die
# Fehler aus It. 38 und 39 gefunden.
const SEEDS := [4711, 90210]

var _fails: int = 0
var _done: Array = []
# Ergebnisse aus dem Kampf-Signal. Feld, nicht lokal: GDScript-Lambdas
# fangen Locals als KOPIE (Lehrgeld aus It. 23).
var _battles: int = 0
var _battle_wins: int = 0
var _outcomes: Array = []
var _deadlocks: Array = []
# Kaempfe, die die KI angefangen hat (Pflichtkampf gegen den Helden ODER
# Verteidigung der eigenen Stadt). Hiess zuerst _defense_battles - das war
# falsch beschriftet, und die Zahl hat mich in die Irre gefuehrt: ich hielt
# einen Pflichtkampf gegen einen KI-Helden fuer einen Stadtangriff.
var _ai_initiated: int = 0
# Summen ueber ALLE Seeds. Einzelne Durchlaeufe duerfen unglueklich
# laufen - ein dummer Test-Spieler darf verlieren. Was NICHT passieren
# darf: dass ueberhaupt kein Kampf gewinnbar ist (genau das war der
# Zustand, den It. 38 aufgedeckt hat).
var _tot_battles: int = 0
var _tot_wins: int = 0
var _tot_xp: int = 0
var _tot_ai: int = 0


func _init() -> void:
	for sd in SEEDS:
		await _play(sd)
	_test_totals()
	_test_marks()

	print("")
	if _fails == 0:
		print("Durchspiel-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Durchspiel-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


# Die eigentliche Aussage der Suite, ueber alle Seeds zusammen.
func _test_totals() -> void:
	print("")
	print("== Summe ueber alle Seeds ==")
	print("        %d Kaempfe, %d gewonnen, %d XP, %d von der KI angefangen"
		% [_tot_battles, _tot_wins, _tot_xp, _tot_ai])
	_check(_tot_battles > 0, "es wurde ueberhaupt gekaempft (%d)" % _tot_battles)
	# DAS ist der Kern: Kaempfe muessen gewinnbar sein. Vor der Korrektur
	# der Prognose (Gold statt Stueckzahl) gewann der Test-Spieler NULL
	# Kaempfe, weil die Karte aussichtslose Kaempfe als machbar anzeigte.
	_check(_tot_wins > 0, "Kaempfe sind gewinnbar (%d von %d gewonnen)"
		% [_tot_wins, _tot_battles])
	_check(_tot_xp > 0, "der Held hat XP verdient (%d)" % _tot_xp)
	_done.append("_test_totals")


func _test_marks() -> void:
	# Eigene Marke ZUERST: der erste Anlauf setzte sie am Ende und der
	# Check darueber sah sie deshalb nie - die Suite war rot, obwohl alles
	# gelaufen war. Ein Pruefer, der sich selbst nicht bestehen kann, ist
	# kaputt.
	_done.append("_test_marks")
	var missing: Array = []
	for m in get_method_list():
		var mn: String = String(m["name"])
		if mn.begins_with("_test") and not _done.has(mn):
			missing.append(mn)
	_check(missing.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)" % str(missing))


# --- ein Durchlauf ---------------------------------------------------------

func _play(seed_value: int) -> void:
	print("")
	print("== Durchspielen, Seed %d ==" % seed_value)
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", seed_value, 1)
	await process_frame

	# Gold liegt seit M13a im Spieler-Beutel, nicht im Helden.
	var purse: Wallet = wm.get("_purse")
	var gold0: int = purse.get_amount("gold")
	# XP und Armee werden ueber ALLE Helden summiert und JEDES MAL frisch
	# aus wm gelesen. Ein am Anfang gemerktes Hero-Objekt waere ein Fehler:
	# faellt gerade dieser Held, ist er aus _heroes verschwunden und der
	# Test wuerde die Zahlen einer Leiche vergleichen (M13b).
	var xp0: int = _total_xp(wm)
	var army0: int = _total_army(wm)
	var fog0: int = _explored(wm)
	var own0: int = _own_cities(wm)
	_battles = 0
	_battle_wins = 0
	_outcomes.clear()
	_ai_initiated = 0
	# Pro Seed leeren: sonst schleppt der Bericht die Meldungen des
	# vorherigen Seeds mit und man sucht den Fehler an der falschen Stelle.
	_deadlocks.clear()

	var turns_played: int = 0
	for t in range(MAX_TURNS):
		if bool(wm.get("_game_won")) or bool(wm.get("_game_lost")):
			break
		# JEDER Held zieht, nicht immer derselbe: _move_and_fight arbeitet
		# am aktiven Helden, also wird ueber die Liste rotiert. Genau das
		# deckt den Weg auf, den ein Spieler mit drei Helden geht - und
		# _switch_hero ist der Pfad, der die Reichweite neu rechnet.
		for hi in range((wm.get("_heroes") as Array).size()):
			if bool(wm.get("_game_won")) or bool(wm.get("_game_lost")):
				break
			# Die Liste kann WAEHREND der Runde kuerzer werden: faellt ein
			# Held im Kampf, verschwindet er sofort. Darum jedes Mal neu
			# gegen die aktuelle Groesse pruefen.
			if hi >= (wm.get("_heroes") as Array).size():
				break
			wm.call("_switch_hero", hi)
			_manage_city(wm)
			await _move_and_fight(wm, seed_value, t)
		wm.call("_on_end_turn")
		await process_frame
		# WICHTIG: auch NACH dem Tagesende nachsehen. Greift eine KI eine
		# eigene Stadt an, oeffnet der Weltkarten-Screen einen
		# Verteidigungskampf und suspendiert die KI-Phase, bis der Spieler
		# ihn ausgespielt hat (M9b). Ohne diesen Aufruf blieb das Overlay
		# stehen, die Stadt fiel und das Spiel war verloren - und genau
		# dieser Pfad war in keiner Suite abgedeckt.
		var before: int = _battles
		await _resolve_overlay(wm, seed_value, t)
		if _battles > before:
			_ai_initiated += 1
		turns_played += 1

	var won: bool = bool(wm.get("_game_won"))
	var lost: bool = bool(wm.get("_game_lost"))
	print("        %d Zuege, %d Kaempfe (%d gewonnen: %s), Ausgang: %s"
		% [turns_played, _battles, _battle_wins, str(_outcomes),
			"Sieg" if won else ("Niederlage" if lost else "laeuft")])
	print("        davon %d von der KI angefangen (Pflichtkampf oder Stadtangriff)"
		% _ai_initiated)

	# 1. Die Kette darf nicht haengen: jeder Zug muss durchgelaufen sein.
	_check(turns_played >= MAX_TURNS or won or lost,
		"alle %d Zuege gespielt oder Spiel entschieden (waren %d)"
		% [MAX_TURNS, turns_played])
	_check(_deadlocks.is_empty(),
		"kein Kampf blieb offen haengen (%s)" % str(_deadlocks))

	# 2. FORTSCHRITT. Ein Spiel, in dem nach 40 Zuegen nichts passiert
	#    ist, ist kaputt - auch wenn es nicht abstuerzt.
	var gold1: int = purse.get_amount("gold")
	var xp1: int = _total_xp(wm)
	var fog1: int = _explored(wm)
	print("        Gold %d -> %d, XP %d -> %d, Armee %d -> %d, erkundet %d -> %d, Staedte %d -> %d, Helden %d"
		% [gold0, gold1, xp0, xp1, army0, _total_army(wm),
			fog0, fog1, own0, _own_cities(wm), (wm.get("_heroes") as Array).size()])
	# Pro Seed nur das, was IMMER gelten muss: die Wirtschaft laeuft und
	# die Karte wird aufgedeckt. Beides haengt nicht am Kampfglueck.
	_check(gold1 > gold0, "Gold ist gewachsen (%d -> %d)" % [gold0, gold1])
	_check(fog1 > fog0, "Karte wurde erkundet (%d -> %d Felder)" % [fog0, fog1])
	# "es wurde gekaempft" steht in den Summen, NICHT hier: weicht der
	# Test-Spieler ueberlegenen KI-Helden aus, kann ein einzelner Seed
	# voellig friedlich verlaufen (im breiten Lauf war Seed 777 so). Eine
	# Pruefung, die von der Kartenverteilung abhaengt, wird sonst irgendwann
	# rot ohne dass etwas kaputt ist.
	_tot_battles += _battles
	_tot_wins += _battle_wins
	_tot_xp += (xp1 - xp0)
	_tot_ai += _ai_initiated

	wm.queue_free()
	await process_frame


# Summen ueber alle lebenden Helden des Spielers.
func _total_xp(wm) -> int:
	var n: int = 0
	for h in (wm.get("_heroes") as Array):
		n += int((h as Hero).xp)
	return n


func _total_army(wm) -> int:
	var n: int = 0
	for h in (wm.get("_heroes") as Array):
		n += int((h as Hero).total_count())
	return n


# Bauen und rekrutieren, wenn der Held auf einer eigenen Stadt steht.
func _manage_city(wm) -> void:
	var hero = wm.get("_hero")
	var idx: int = int(wm.call("_city_at", hero.position))
	if idx < 0 or int((wm.get("_cities") as Array)[idx]["owner"]) != int(wm.get("OWNER_HERO")):
		return
	# Der Reihe nach alles kaufen, was geht - _buy_building prueft selbst
	# Kosten und Voraussetzungen.
	var blds: Array = wm.get("BUILDINGS")
	for b in range(blds.size()):
		wm.call("_buy_building", idx, b)
	# Rekrutieren: alles, was der Pool hergibt.
	var city: Dictionary = (wm.get("_cities") as Array)[idx]
	var pools: Dictionary = city.get("pools", {}) as Dictionary
	for uid in pools.keys():
		if int(pools[uid]) > 0:
			wm.call("_recruit_unit", idx, String(uid))
	# Held anwerben, wenn Gold und Platz da sind (M13b). Damit laeuft der
	# Mehr-Helden-Pfad durch die ECHTE Zugkette - test_multi_hero prueft
	# ihn nur isoliert. _on_hire_hero liest die Stadt aus _selected_city,
	# genau wie der Knopf im Stadtschirm.
	var purse: Wallet = wm.get("_purse")
	if purse.can_afford(wm.get("HERO_HIRE_COST") as Dictionary) \
			and (wm.get("_heroes") as Array).size() < int(wm.get("MAX_HEROES")):
		var keep: int = int(wm.get("_selected_city"))
		wm.set("_selected_city", idx)
		wm.call("_on_hire_hero")
		wm.set("_selected_city", keep)


# Naechstes sinnvolles Ziel antippen und einen entstehenden Kampf
# ausspielen.
func _move_and_fight(wm, seed_value: int, turn: int) -> void:
	var hero = wm.get("_hero")
	var costs: Dictionary = wm.get("_costs")
	var target := Vector2i(-1, -1)
	var best: int = 1 << 30

	# Ziele nach Vorliebe: Bonus-Objekt/Truhe/Mine, dann Monster, dann
	# fremde Stadt. Immer das billigste erreichbare.
	var candidates: Array = []
	for obj in (wm.get("_objects") as Array):
		candidates.append(obj["pos"])
	for m in (wm.get("_monsters") as Array):
		candidates.append(m["pos"])
	for c in (wm.get("_cities") as Array):
		if int(c["owner"]) != int(wm.get("OWNER_HERO")):
			candidates.append(c["pos"])
	# Heimweg: mit Gold fuer einen Helden und einem freien Platz ist die
	# EIGENE Stadt ein Ziel - dort wird angeworben. Ohne diese Regel lief
	# der Test-Spieler nie wieder nach Hause, und der Anwerbe-Pfad kam in
	# der echten Zugkette nie vor (M13b).
	if (wm.get("_purse") as Wallet).can_afford(wm.get("HERO_HIRE_COST") as Dictionary) \
			and (wm.get("_heroes") as Array).size() < int(wm.get("MAX_HEROES")):
		for c2 in (wm.get("_cities") as Array):
			if int(c2["owner"]) == int(wm.get("OWNER_HERO")):
				candidates.append(c2["pos"])
	# Kampfkraft wie in der Oberflaeche - in GOLD (It. 38). Der
	# Test-Spieler geht KEINEN Kampf ein, den die Karte rot anzeigt:
	# sonst prueft der Test nur, dass ein aussichtsloser Angriff verliert.
	var eff: int = int(wm.call("_player_gold_power"))
	# Nur Kaempfe, die die Karte GRUEN faerbt (mindestens doppelter
	# Gold-Vorsprung, THREAT_SAFE_FACTOR). Gelb heisst "Sieg mit
	# Verlusten" - mit einer Drei-Einheiten-Startarmee ist das ein
	# Muenzwurf, und dann prueft der Test nur noch Glueck. Der Faktor
	# kommt aus dem Screen, damit Test und Anzeige dieselbe Grenze haben.
	var safe: float = float(wm.get("THREAT_SAFE_FACTOR"))
	for p in candidates:
		var pp: Vector2i = p
		if pp == hero.position:
			continue
		if not costs.has(pp):
			continue
		# Auf einem Feld mit einem ANDEREN eigenen Helden wechselt ein Tap
		# den aktiven Helden statt zu laufen (M13a) - der Zug waere
		# verpufft. Solche Ziele also auslassen.
		if int(wm.call("_hero_index_at", pp)) >= 0:
			continue
		var threat: int = _threat_at(wm, pp)
		if threat > 0 and float(eff) < float(threat) * safe:
			continue
		# Und nicht in die Reichweite eines ueberlegenen KI-Helden laufen.
		# Ohne diese Regel lief der Test-Spieler mit drei Einheiten in Zug
		# 1 zur Gegnerstadt und wurde unterwegs gestellt - danach prueft
		# der Test nur noch, dass ein aussichtsloser Kampf verloren geht.
		if _ai_hero_danger(wm, pp, eff, safe):
			continue
		var cost: int = int(costs[pp])
		if cost <= int(hero.mp) and cost < best:
			best = cost
			target = pp
	if target.x < 0:
		return

	var origin: Vector2 = wm.call("_map_origin")
	var ts: float = float(wm.get("_tile_size"))
	var pos: Vector2 = origin + Vector2(float(target.x) + 0.5,
		float(target.y) + 0.5) * ts
	wm.call("_handle_tap", pos)
	await process_frame
	await _resolve_overlay(wm, seed_value, turn)


# Sucht ein offenes Kampf-Overlay und spielt es aus. Genau hier wuerde
# ein Bruch in der Kette Weltkarte -> Kampf -> Callback auffallen: das
# Overlay bliebe stehen und der naechste Zug prallte ab.
func _resolve_overlay(wm, seed_value: int, turn: int) -> void:
	var bs = _find_overlay(wm)
	if bs == null:
		return
	_battles += 1
	bs.fx_speed = 0.0
	# Ausgang aus dem SIGNAL nehmen, nicht aus dem Zustand danach: der
	# Weltkarten-Trichter raeumt das Overlay bei JEDEM Ausgang ab (Sieg,
	# Niederlage, Flucht), also ist der Knoten hinterher weg. Der erste
	# Anlauf zaehlte deshalb 0 Siege, auch wenn welche dabei waren.
	bs.battle_finished.connect(_on_battle_done)
	var steps: int = 0
	# is_instance_valid ist Pflicht: verliert der Spieler, raeumt der
	# Weltkarten-Screen das Overlay im Callback ab (Niederlage-Panel), und
	# der naechste Zugriff auf den freien Knoten laesst Godot mit
	# Signal 11 abstuerzen. Der erste Anlauf dieses Tests tat genau das.
	while is_instance_valid(bs) and not bool(bs.get("_finished")) \
			and steps < MAX_BATTLE_STEPS:
		steps += 1
		var order: Array = bs.get("_turn_order")
		var slot: int = int(bs.get("_active_slot"))
		if order.is_empty() or slot >= order.size():
			bs.call("_next_round")
			continue
		if int(order[slot]["side"]) != 0:
			# KI ist dran - der Screen zieht selbst weiter; passiert nur,
			# wenn die Kette haengt.
			await process_frame
			continue
		if not _player_acts(bs):
			bs.call("_on_wait")
		await process_frame
	if not is_instance_valid(bs):
		# Normalfall: der Weltkarten-Trichter hat das Overlay nach dem
		# Signal abgeraeumt.
		return
	if not bool(bs.get("_finished")):
		_deadlocks.append("Seed %d Zug %d: Kampf nach %d Schritten offen"
			% [seed_value, turn, steps])
		# Nicht haengen lassen: fliehen beendet den Kampf regulaer.
		bs.call("_on_flee")
		await process_frame
	await process_frame
	await process_frame


# Eine Aktion fuer den aktiven Spieler-Stack. Rueckgabe false = nichts
# gefunden (dann wartet der Aufrufer).
func _on_battle_done(result: Dictionary) -> void:
	var outcome: String = String(result.get("outcome", "?"))
	_outcomes.append(outcome)
	if outcome == "victory":
		_battle_wins += 1


func _player_acts(bs) -> bool:
	var active: Dictionary = bs.call("_active_stack")
	if active.is_empty():
		return false
	var apos: Vector2i = active["pos"]
	var e_stacks: Array = bs.get("_e_stacks")
	# 1. Schuss oder Nahkampf auf einen erreichbaren Gegner.
	for i in range(e_stacks.size()):
		var es: Dictionary = e_stacks[i]
		if int(es["count"]) <= 0:
			continue
		var epos: Vector2i = es["pos"]
		var adj: bool = abs(epos.x - apos.x) <= 1 and abs(epos.y - apos.y) <= 1
		if adj or bool(bs.call("_can_shoot", active)):
			bs.call("_try_attack_enemy", i)
			return true
	# 2. Sonst auf das Feld ziehen, das dem naechsten Gegner am naechsten
	#    liegt.
	var reach: Dictionary = bs.get("_reachable")
	var goal := Vector2i(-1, -1)
	var bestd: int = 1 << 30
	for i2 in range(e_stacks.size()):
		if int(e_stacks[i2]["count"]) <= 0:
			continue
		var ep: Vector2i = e_stacks[i2]["pos"]
		for cell in reach.keys():
			var cv: Vector2i = cell
			var d: int = abs(cv.x - ep.x) + abs(cv.y - ep.y)
			if d < bestd:
				bestd = d
				goal = cv
	if goal.x >= 0 and goal != apos:
		var g: Array = bs.call("_geom")
		var o: Vector2 = g[0]
		var c: float = float(g[1])
		var ev := InputEventMouseButton.new()
		ev.button_index = MOUSE_BUTTON_LEFT
		ev.pressed = true
		ev.position = o + Vector2(float(goal.x) + 0.5, float(goal.y) + 0.5) * c
		bs.call("_on_grid_input", ev)
		return true
	return false


# Wie stark ist die Verteidigung dieses Feldes? Dieselben Zahlen, die die
# Karte in ihre Prognose-Farbe umrechnet.
# Steht ein ueberlegener KI-Held in Reichweite dieses Feldes?
func _ai_hero_danger(wm, p: Vector2i, own_gold: int, safe: float) -> bool:
	for e in (wm.get("_enemies") as Array):
		var eh = e["hero"]
		if eh == null:
			continue
		var d: int = abs(eh.position.x - p.x) + abs(eh.position.y - p.y)
		var reach: int = int(eh.max_mp) / int(wm.get("MONSTER_GOLD_PER_STRENGTH")) * 0 \
			+ 10   # rund 10 Felder pro Tag, siehe Movement.UNIT
		if d > reach:
			continue
		var g: int = int(wm.call("_army_gold", eh.army))
		if float(own_gold) < float(g) * safe:
			return true
	return false


func _threat_at(wm, p: Vector2i) -> int:
	for m in (wm.get("_monsters") as Array):
		if Vector2i(m["pos"]) == p:
			return int(wm.call("_threat_gold_of_monster", m))
	for obj in (wm.get("_objects") as Array):
		if Vector2i(obj["pos"]) == p:
			return int(wm.call("_army_gold", wm.call("_object_guard_army", obj)))
	for c in (wm.get("_cities") as Array):
		if Vector2i(c["pos"]) == p:
			return int(wm.call("_army_gold",
				c.get("garrison_army", {}) as Dictionary))
	return 0


func _find_overlay(wm):
	for ch in wm.get_children():
		if ch.has_method("set_battle") and ch.has_method("_active_stack"):
			return ch
	return null


func _explored(wm) -> int:
	var fog: Array = wm.get("_fog_player")
	var hidden: int = int(wm.get("FOG_HIDDEN"))
	var n: int = 0
	for v in fog:
		if int(v) != hidden:
			n += 1
	return n


func _own_cities(wm) -> int:
	var n: int = 0
	for c in (wm.get("_cities") as Array):
		if int(c["owner"]) == int(wm.get("OWNER_HERO")):
			n += 1
	return n
