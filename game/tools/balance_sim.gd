extends SceneTree

# Monte-Carlo-Balance-Simulator fuer Kromeich Heroes.
#
# Zweck (M4 Teil 2):
#   4x4-Fraktions-Matrix - jede Fraktion tritt mit genau EINER Woche
#   Wachstum aller 7 Tiers an (7 Stacks, Counts = weekly_growth aus
#   units.json). Nutzt die *selbe* Schadensformel wie der Live-Kampf
#   (scripts/core/CombatMath.gd) und ein abstraktes Anmarsch-Modell:
#     - Fernkaempfer schiessen ab Runde 1 aus der Distanz
#     - Nahkaempfer erreichen den Gegner nach ceil(7 Felder / speed)
#
# WICHTIG: Der Sim ist INFORMATIV (Exit immer 0). Die units.json-Balance
# gilt erst vollstaendig, wenn die Battle-Abilities (M6b: flying,
# double_attack, begrenzte Schuesse, ...) implementiert sind - bis dahin
# sind Ausreisser ausserhalb 30-70% nur Warnungen, kein CI-Fail.
#
# Ausfuehrung:
#   godot --headless --path game/ --script tools/balance_sim.gd
#   godot --headless --path game/ --script tools/balance_sim.gd -- --runs=2000 --seed=7

const DEFAULT_RUNS: int = 1000
const DEFAULT_SEED: int = 12345
const WARN_MIN: float = 0.30
const WARN_MAX: float = 0.70
const FACTION_LABELS: Array = ["Waldvolk", "Menschen", "Totenreich", "Orks"]

const MAX_ROUNDS: int = 30
# Abstrakte Schlachtfeld-Distanz in Feldern fuer das Anmarsch-Modell.
const ENGAGE_DISTANCE: float = 7.0

# Ability-Regeln kommen aus derselben Quelle wie der Live-Kampf, sonst
# luegt die Matrix (M6b Teil 1).
const Abil := preload("res://scripts/core/Abilities.gd")
const Fx := preload("res://scripts/core/StatusFx.gd")
const Mor := preload("res://scripts/core/Morale.gd")


func _init() -> void:
	var runs: int = DEFAULT_RUNS
	var seed_val: int = DEFAULT_SEED
	var args: PackedStringArray = OS.get_cmdline_user_args()
	for arg in args:
		if arg.begins_with("--runs="):
			runs = int(arg.substr(len("--runs=")))
		elif arg.begins_with("--seed="):
			seed_val = int(arg.substr(len("--seed=")))

	print("# Kromeich Heroes - Balance-Simulator (4x4 Fraktionen)")
	print("")
	print("Parameter: runs=%d, seed=%d, Armee = 1 Wochen-Wachstum (7 Tiers)" % [runs, seed_val])
	print("Warn-Korridor Winrate: %.2f - %.2f (informativ, kein Gate)" % [WARN_MIN, WARN_MAX])
	print("")

	var warnings: int = _run_faction_matrix(runs, seed_val)

	print("")
	print("Modell-Grenze: Fernkaempfer werden im abstrakten Kampf NIE physisch")
	print("blockiert und feuern ab Runde 1 - schuetzenlastige Fraktionen sehen")
	print("hier darum besser aus als auf dem echten 10x8-Gitter. Vor dem")
	print("Zahlen-Tuning fehlt noch Moral/Glueck (M6); danach ist ein eigener")
	print("Tuning-Pass in balance_notes.md dran.")
	print("")
	if warnings == 0:
		print("Urteil: Alle Matchups im Warn-Korridor.")
	else:
		print("Urteil: %d Matchup(s) ausserhalb %.2f-%.2f (informativ)." % [warnings, WARN_MIN, WARN_MAX])
	# Informativ: Exit 0 auch mit Warnungen (siehe Kopf-Kommentar).
	quit(0)


# --------- 4x4-Fraktions-Matrix ---------

func _run_faction_matrix(runs: int, seed_val: int) -> int:
	var armies: Array = []
	for fid in range(4):
		armies.append(_week_army(fid))
	print("## Fraktions-Matrix (Zeile A vs Spalte B, Winrate A)")
	print("")
	var header: String = "| A \\ B |"
	for lbl in FACTION_LABELS:
		header += " %s |" % lbl
	print(header)
	var sep: String = "|---|"
	for _l in FACTION_LABELS:
		sep += "---|"
	print(sep)
	var warnings: int = 0
	var draw_pairs: int = 0
	var csv: Array = []
	for fa in range(4):
		var row: String = "| %s " % FACTION_LABELS[fa]
		for fb in range(4):
			var r: Dictionary = _run_matchup(armies[fa], armies[fb], runs, seed_val)
			var wr: float = float(r["wins_a"]) / float(runs)
			var dr: float = float(r["draws"]) / float(runs)
			var mark: String = ""
			if dr >= 0.5:
				# Ueberwiegend Unentschieden -> Winrate sagt hier nichts aus.
				mark = "="
				draw_pairs += 1
			elif wr < WARN_MIN or wr > WARN_MAX:
				warnings += 1
				mark = "!"
			row += "| %.2f%s " % [wr, mark]
			csv.append("%s_vs_%s,%.4f,%.4f,%.2f" % [
				FACTION_LABELS[fa], FACTION_LABELS[fb], wr, dr, r["avg_rounds"]])
		row += "|"
		print(row)
	print("")
	print("Legende: `!` ausserhalb des Korridors, `=` mehrheitlich unentschieden")
	print("(beide Armeen leben nach %d Runden - z.B. Regeneration heilt schneller" % MAX_ROUNDS)
	print("als der Gegner Schaden macht; dort ist die Winrate bedeutungslos).")
	if draw_pairs > 0:
		print("Unentschieden-Matchups: %d" % draw_pairs)
	print("")
	print("CSV (pair,winrate_A,draw_rate,avg_rounds):")
	for line in csv:
		print(line)
	return warnings


# Armee einer Fraktion: pro Tier 1 Stack mit weekly_growth Einheiten.
func _week_army(fid: int) -> Array:
	var out: Array = []
	for uid in UnitType.ids_for_faction(fid):
		var cnt: int = UnitType.growth_of(String(uid))
		if cnt > 0:
			out.append({"type": String(uid), "count": cnt})
	return out


# --------- Matchup-Runner ---------

func _run_matchup(a_list: Array, b_list: Array, runs: int, seed_val: int) -> Dictionary:
	var wins_a: int = 0
	var draws: int = 0
	var rounds_sum: int = 0
	var rng: RandomNumberGenerator = RandomNumberGenerator.new()
	rng.seed = seed_val
	for i in range(runs):
		var res: Dictionary = _simulate(a_list, b_list, rng)
		var w: int = int(res["winner"])
		if w == 0:
			wins_a += 1
		elif w < 0:
			# Beide Seiten leben nach MAX_ROUNDS - z.B. wenn Regeneration
			# schneller heilt als der Gegner Schaden macht. Das ist KEINE
			# Niederlage von A und wird darum getrennt gezaehlt.
			draws += 1
		rounds_sum += int(res["rounds"])
	return {
		"wins_a": wins_a,
		"draws": draws,
		"avg_rounds": float(rounds_sum) / float(max(1, runs)),
	}


# --------- Einzelner abstrakter Kampf ---------

func _simulate(a_list: Array, b_list: Array, rng: RandomNumberGenerator) -> Dictionary:
	var a: Array = _init_stacks(a_list, 0)
	var b: Array = _init_stacks(b_list, 1)
	# Moral aus der Armee-Zusammenstellung (M6). Die Sim-Armeen sind rein,
	# also stehen beide Seiten bei +1 - der Effekt ist symmetrisch, der
	# Code laeuft aber mit und wuerde eine gemischte Aufstellung strafen.
	var morale: Array = [Mor.morale_for(a), Mor.morale_for(b)]
	var round_num: int = 1
	while _any_alive(a) and _any_alive(b) and round_num <= MAX_ROUNDS:
		_reset_round(a)
		_reset_round(b)
		var order: Array = _build_order(a, b)
		for slot in order:
			if not _any_alive(a) or not _any_alive(b):
				break
			var side: int = int(slot["side"])
			var idx: int = int(slot["idx"])
			var mine: Array = a if side == 0 else b
			var enemy: Array = b if side == 0 else a
			if idx >= mine.size() or int(mine[idx]["count"]) <= 0:
				continue
			var st: Dictionary = mine[idx]
			var mor: int = int(morale[side])
			var immune: bool = Mor.is_immune(String(st["type"]))
			# Schlechte Moral kostet den Zug, gute schenkt einen zweiten
			# (max einen pro Runde) - genau wie im Live-Kampf.
			if not immune and Mor.rolls_freeze(mor, rng):
				continue
			_take_turn(st, enemy, round_num, rng)
			if not immune and not bool(st.get("morale_extra_used", false)) \
					and Mor.rolls_extra_turn(mor, rng):
				st["morale_extra_used"] = true
				if _any_alive(a) and _any_alive(b) and int(st["count"]) > 0:
					_take_turn(st, enemy, round_num, rng)
		round_num += 1

	var a_live: bool = _any_alive(a)
	var b_live: bool = _any_alive(b)
	var winner: int = -1
	if a_live and not b_live:
		winner = 0
	elif b_live and not a_live:
		winner = 1
	return {"winner": winner, "rounds": round_num - 1}


# Ab welcher Runde ein Stack angreifen kann: Fernkampf sofort, Flieger
# ebenfalls (sie ueberqueren das Feld ungehindert), Nahkampf nach dem
# Anmarsch ueber ENGAGE_DISTANCE Felder mit seiner Speed.
func _engage_round(uid: String) -> int:
	if UnitType.is_ranged(uid) or Abil.ignores_obstacles(uid):
		return 1
	return int(ceil(ENGAGE_DISTANCE / float(max(1, UnitType.speed_of(uid)))))


func _take_turn(stack: Dictionary, enemy: Array, round_num: int, rng: RandomNumberGenerator) -> void:
	var target: Dictionary = _pick_target(enemy)
	if target.is_empty():
		return
	var uid: String = String(stack["type"])
	# Betaeubt/geblendet: Zug verloren (M6b Teil 2).
	if Fx.blocks_turn(stack):
		return
	var is_ranged_unit: bool = UnitType.is_ranged(uid)
	var can_shoot: bool = is_ranged_unit and int(stack.get("shots_left", 0)) > 0
	if not is_ranged_unit and round_num < _engage_round(uid):
		# Noch im Anmarsch, kein Angriff in dieser Runde. Leergeschossene
		# Schuetzen gelten als bereits im Getuemmel (kein neuer Anmarsch).
		return
	var melee_penalty: bool
	if can_shoot:
		# Nahkampfmalus: Wenn feindliche Nahkaempfer bereits engagiert
		# haben, steht der Fernkaempfer unter Druck und schiesst mit Malus.
		melee_penalty = _enemy_melee_engaged(enemy, round_num)
	else:
		# Nahkampf; Fernkaempfer ohne Munition kassieren den Malus
		# (ability-abhaengig, siehe CombatMath).
		melee_penalty = is_ranged_unit
	# Jousting: beim ersten Nahkampf-Angriff hat der Stack die ganze
	# Anmarschstrecke hinter sich, danach steht er beim Gegner.
	var opts: Dictionary = {}
	if not can_shoot:
		if not bool(stack.get("engaged", false)):
			opts["tiles_moved"] = int(ENGAGE_DISTANCE)
			stack["engaged"] = true
	var hits: int = Abil.attacks_per_turn(uid, can_shoot)
	var t_uid: String = String(target["type"])
	var drain: float = Abil.drain_fraction(uid)
	for _i in range(hits):
		if int(target["count"]) <= 0 or int(stack["count"]) <= 0:
			break
		if can_shoot:
			if int(stack["shots_left"]) <= 0:
				break
			stack["shots_left"] = int(stack["shots_left"]) - 1
		var dmg: int = CombatMath.damage(stack, target, melee_penalty, 0, 0, rng, opts)
		CombatMath.apply(target, dmg)
		if not can_shoot:
			Fx.wake_on_melee(target)
		if drain > 0.0:
			CombatMath.heal(stack, int(float(dmg) * drain))
		# Status-Effekte + Todeswolke wie im Live-Kampf.
		Fx.apply_on_hit(uid, target, rng)
		_apply_aoe(uid, target, dmg, enemy)
		# Gegenschlag nur bei Nahkampf-Angriff; Konter-Regeln wie live.
		# Betaeubte/geblendete Verteidiger kontern nicht.
		if not can_shoot and int(target["count"]) > 0 and not Fx.blocks_turn(target) \
				and Abil.retaliation_allowed(
				t_uid, uid, int(target.get("retaliations", 0))):
			target["retaliations"] = int(target.get("retaliations", 0)) + 1
			target["retaliated"] = true
			var rdmg: int = max(1, CombatMath.damage(
				target, stack, UnitType.is_ranged(t_uid), 0, 0, rng) / 2)
			CombatMath.apply(stack, rdmg)


# Todeswolke im abstrakten Modell: das Gitter fehlt, also trifft die
# Wolke EINEN weiteren lebenden Stack der Gegenseite mit halbem Schaden
# (live sind es die 1-2 Nachbarn des Ziels).
func _apply_aoe(attacker_uid: String, target: Dictionary, dmg: int, enemy: Array) -> void:
	var frac: float = Fx.aoe_fraction(attacker_uid)
	if frac <= 0.0 or dmg <= 0:
		return
	var splash: int = int(float(dmg) * frac)
	if splash <= 0:
		return
	for s in enemy:
		if s == target or int(s["count"]) <= 0:
			continue
		CombatMath.apply(s, splash)
		return


func _enemy_melee_engaged(enemy: Array, round_num: int) -> bool:
	for s in enemy:
		if int(s["count"]) <= 0:
			continue
		var uid: String = String(s["type"])
		if UnitType.is_ranged(uid):
			continue
		if round_num >= _engage_round(uid):
			return true
	return false


# --------- Helpers ---------

func _init_stacks(list: Array, side: int) -> Array:
	var out: Array = []
	for e in list:
		var uid: String = String(e["type"])
		var cnt: int = int(e["count"])
		if cnt <= 0:
			continue
		out.append({
			"type": uid, "count": cnt, "count_start": cnt, "side": side,
			"top_hp": UnitType.hp_of(uid), "retaliated": false,
			"shots_left": UnitType.shots_of(uid),
			"retaliations": 0, "engaged": false, "status": {},
			"morale_extra_used": false,
		})
	return out


func _reset_round(stacks: Array) -> void:
	for s in stacks:
		s["retaliated"] = false
		s["retaliations"] = 0
		s["morale_extra_used"] = false
		Fx.tick(s)
		# Rundenstart-Regeneration wie im Live-Kampf.
		if int(s["count"]) > 0:
			var hp_max: int = UnitType.hp_of(String(s["type"]))
			var gain: int = Abil.regen_hp(String(s["type"]), int(s["top_hp"]), hp_max)
			if gain > 0:
				s["top_hp"] = min(hp_max, int(s["top_hp"]) + gain)


func _build_order(a: Array, b: Array) -> Array:
	var out: Array = []
	for i in range(a.size()):
		if int(a[i]["count"]) > 0:
			out.append({"side": 0, "idx": i,
				"speed": UnitType.speed_of(String(a[i]["type"]))})
	for i in range(b.size()):
		if int(b[i]["count"]) > 0:
			out.append({"side": 1, "idx": i,
				"speed": UnitType.speed_of(String(b[i]["type"]))})
	out.sort_custom(func(x, y): return int(x["speed"]) > int(y["speed"]))
	return out


func _pick_target(arr: Array) -> Dictionary:
	# Wie die Live-AI: staerkstes Ziel = groesster Count.
	var best: Dictionary = {}
	var best_cnt: int = -1
	for s in arr:
		if int(s["count"]) <= 0:
			continue
		if int(s["count"]) > best_cnt:
			best_cnt = int(s["count"])
			best = s
	return best


func _any_alive(arr: Array) -> bool:
	for s in arr:
		if int(s["count"]) > 0:
			return true
	return false
