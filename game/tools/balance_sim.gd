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
	if warnings == 0:
		print("Urteil: Alle Matchups im Warn-Korridor.")
	else:
		print("Urteil: %d Matchup(s) ausserhalb %.2f-%.2f - Abilities (M6b) abwarten, dann tunen." % [warnings, WARN_MIN, WARN_MAX])
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
	var csv: Array = []
	for fa in range(4):
		var row: String = "| %s " % FACTION_LABELS[fa]
		for fb in range(4):
			var r: Dictionary = _run_matchup(armies[fa], armies[fb], runs, seed_val)
			var wr: float = float(r["wins_a"]) / float(runs)
			var mark: String = ""
			if wr < WARN_MIN or wr > WARN_MAX:
				warnings += 1
				mark = "!"
			row += "| %.2f%s " % [wr, mark]
			csv.append("%s_vs_%s,%.4f,%.2f" % [FACTION_LABELS[fa], FACTION_LABELS[fb], wr, r["avg_rounds"]])
		row += "|"
		print(row)
	print("")
	print("CSV (pair,winrate_A,avg_rounds):")
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
	var rounds_sum: int = 0
	var rng: RandomNumberGenerator = RandomNumberGenerator.new()
	rng.seed = seed_val
	for i in range(runs):
		var res: Dictionary = _simulate(a_list, b_list, rng)
		if int(res["winner"]) == 0:
			wins_a += 1
		rounds_sum += int(res["rounds"])
	return {
		"wins_a": wins_a,
		"avg_rounds": float(rounds_sum) / float(max(1, runs)),
	}


# --------- Einzelner abstrakter Kampf ---------

func _simulate(a_list: Array, b_list: Array, rng: RandomNumberGenerator) -> Dictionary:
	var a: Array = _init_stacks(a_list, 0)
	var b: Array = _init_stacks(b_list, 1)
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
			_take_turn(mine[idx], enemy, round_num, rng)
		round_num += 1

	var a_live: bool = _any_alive(a)
	var b_live: bool = _any_alive(b)
	var winner: int = -1
	if a_live and not b_live:
		winner = 0
	elif b_live and not a_live:
		winner = 1
	return {"winner": winner, "rounds": round_num - 1}


# Ab welcher Runde ein Stack angreifen kann: Fernkampf sofort, Nahkampf
# nach dem Anmarsch ueber ENGAGE_DISTANCE Felder mit seiner Speed.
func _engage_round(uid: String) -> int:
	if UnitType.is_ranged(uid):
		return 1
	return int(ceil(ENGAGE_DISTANCE / float(max(1, UnitType.speed_of(uid)))))


func _take_turn(stack: Dictionary, enemy: Array, round_num: int, rng: RandomNumberGenerator) -> void:
	var target: Dictionary = _pick_target(enemy)
	if target.is_empty():
		return
	var uid: String = String(stack["type"])
	if round_num < _engage_round(uid):
		# Noch im Anmarsch, kein Angriff in dieser Runde.
		return
	var is_ranged: bool = UnitType.is_ranged(uid)
	# Nahkampfmalus: Wenn feindliche Nahkaempfer bereits engagiert haben,
	# steht der Fernkaempfer unter Druck und schiesst mit Malus.
	var melee_penalty: bool = is_ranged and _enemy_melee_engaged(enemy, round_num)
	var dmg: int = CombatMath.damage(stack, target, melee_penalty, 0, 0, rng)
	CombatMath.apply(target, dmg)
	# Gegenschlag nur bei Nahkampf-Angriff; einmal pro Runde pro Ziel.
	if not is_ranged and int(target["count"]) > 0 and not bool(target.get("retaliated", false)):
		target["retaliated"] = true
		var t_ranged: bool = UnitType.is_ranged(String(target["type"]))
		var rdmg: int = max(1, CombatMath.damage(target, stack, t_ranged, 0, 0, rng) / 2)
		CombatMath.apply(stack, rdmg)


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
			"type": uid, "count": cnt, "side": side,
			"top_hp": UnitType.hp_of(uid), "retaliated": false,
		})
	return out


func _reset_round(stacks: Array) -> void:
	for s in stacks:
		s["retaliated"] = false


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
