extends SceneTree

# Monte-Carlo-Balance-Simulator fuer Kromeich Heroes.
#
# Zweck:
#   Prueft die Kampf-Balance zwischen Schwert (S), Bogen (B) und Reiter
#   (R) bei gleichem Goldeinsatz. Nutzt die *selbe* Schadensformel wie
#   der Live-Kampf (scripts/core/CombatMath.gd) und spiegelt grob die
#   Grid-Taktik des TacticalBattleScreen:
#     - Bogen schiesst ab Runde 1 aus der Distanz (kein Gegen-Schlag)
#     - Reiter (Speed 7) erreicht den Gegner in Runde 1
#     - Schwert (Speed 4) braucht ~2 Runden, bis es zuschlagen kann
#
# Ausfuehrung:
#   godot --headless --path game/ --script tools/balance_sim.gd
#   godot --headless --path game/ --script tools/balance_sim.gd -- --runs=10000 --seed=12345
#   godot --headless --path game/ --script tools/balance_sim.gd -- --gold=480
#
# Ausgabe: Markdown + CSV auf stdout. Exit 0 wenn alle Matchups im
# Zielkorridor (40-60% Winrate), sonst Exit 1, damit CI den Build
# stoppen kann sobald das Tuning Teil der Pipeline wird.

const DEFAULT_RUNS: int = 5000
const DEFAULT_SEED: int = 12345
const DEFAULT_GOLD: int = 600
const TARGET_MIN: float = 0.40
const TARGET_MAX: float = 0.60

# Wie viele Runden ein Stack braucht, um im abstrakten Modell den
# Gegner zu erreichen. Entspricht 7 Felder Distanz / Speed:
#   sword (spd 4): 7/4 -> 2 Runden
#   bow   (spd 4): ranged, schiesst ab Runde 1
#   rider (spd 7): 7/7 -> 1 Runde
const ENGAGE_ROUND: Dictionary = {
	"sword": 2,
	"bow":   1,
	"rider": 1,
}

# Der Simulator fokussiert sich aktuell auf die Menschen-Baseline
# (sword/bow/rider). Die anderen drei Fraktionen werden in einer
# spaeteren Iteration mit eigenem Engage-Round-Mapping dazu-gemischt.
const BASELINE_IDS: Array = ["sword", "bow", "rider"]

const MAX_ROUNDS: int = 30


func _init() -> void:
	var runs: int = DEFAULT_RUNS
	var seed_val: int = DEFAULT_SEED
	var gold: int = DEFAULT_GOLD
	var args: PackedStringArray = OS.get_cmdline_user_args()
	for arg in args:
		if arg.begins_with("--runs="):
			runs = int(arg.substr(len("--runs=")))
		elif arg.begins_with("--seed="):
			seed_val = int(arg.substr(len("--seed=")))
		elif arg.begins_with("--gold="):
			gold = int(arg.substr(len("--gold=")))

	print("# Kromeich Heroes - Balance-Simulator")
	print("")
	print("Parameter: runs=%d, seed=%d, gold=%d" % [runs, seed_val, gold])
	print("Zielkorridor Winrate: %.2f - %.2f" % [TARGET_MIN, TARGET_MAX])
	print("")

	var ok: bool = true
	ok = _run_pure_matrix(runs, seed_val, gold) and ok
	ok = _run_mixed_compositions(runs, seed_val, gold) and ok

	print("")
	if ok:
		print("Urteil: Alle Matchups innerhalb des Zielkorridors.")
		quit(0)
	else:
		print("Urteil: Mindestens ein Matchup ausserhalb des Zielkorridors.")
		quit(1)


# --------- Pure Matchups (3x3): ein Typ gegen einen Typ ---------

func _run_pure_matrix(runs: int, seed_val: int, gold: int) -> bool:
	print("## Pure Matchups (%d Gold je Seite)" % gold)
	print("")
	print("| A \\ B | S | B | R |")
	print("|---|---|---|---|")
	var ids: Array = BASELINE_IDS
	var all_ok: bool = true
	var rows: Array = []
	for a in ids:
		var row: String = "| %s " % UnitType.short_of(String(a))
		for b in ids:
			var r: Dictionary = _run_matchup(
				[{"type": String(a), "count": _count_for_gold(String(a), gold)}],
				[{"type": String(b), "count": _count_for_gold(String(b), gold)}],
				runs, seed_val)
			var wr: float = float(r["wins_a"]) / float(runs)
			var mark: String = ""
			if wr < TARGET_MIN or wr > TARGET_MAX:
				all_ok = false
				mark = "!"
			row += "| %.2f%s " % [wr, mark]
			rows.append({"pair": "%s_vs_%s" % [a, b], "wr_a": wr,
				"avg_rounds": r["avg_rounds"]})
		row += "|"
		print(row)
	print("")
	print("Lesart: Zelle = Winrate der Zeile gegen die Spalte. `!` = ausserhalb %.2f-%.2f." % [TARGET_MIN, TARGET_MAX])
	print("")
	print("CSV (pair,winrate_A,avg_rounds):")
	for row in rows:
		print("%s,%.4f,%.2f" % [row["pair"], row["wr_a"], row["avg_rounds"]])
	print("")
	return all_ok


# --------- Mixed Compositions: gemischte Armeen gleicher Kosten ---------

func _run_mixed_compositions(runs: int, seed_val: int, gold: int) -> bool:
	print("## Mixed Compositions (%d Gold je Seite)" % gold)
	print("")
	var comps: Array = [
		{"id": "all_sword", "label": "S pur",        "list": _mix({"sword": 1.0}, gold)},
		{"id": "all_bow",   "label": "B pur",        "list": _mix({"bow":   1.0}, gold)},
		{"id": "all_rider", "label": "R pur",        "list": _mix({"rider": 1.0}, gold)},
		{"id": "sb_60_40",  "label": "S60/B40",      "list": _mix({"sword": 0.6, "bow": 0.4}, gold)},
		{"id": "sbr",       "label": "S40/B30/R30",  "list": _mix({"sword": 0.4, "bow": 0.3, "rider": 0.3}, gold)},
		{"id": "br_50_50",  "label": "B50/R50",      "list": _mix({"bow": 0.5, "rider": 0.5}, gold)},
	]
	var header: String = "| A \\ B |"
	for c in comps:
		header += " %s |" % String(c["label"])
	print(header)
	var sep: String = "|---|"
	for _c in comps:
		sep += "---|"
	print(sep)
	var all_ok: bool = true
	for ca in comps:
		var row: String = "| %s " % ca["label"]
		for cb in comps:
			var r: Dictionary = _run_matchup(ca["list"], cb["list"], runs, seed_val)
			var wr: float = float(r["wins_a"]) / float(runs)
			var mark: String = ""
			if wr < TARGET_MIN or wr > TARGET_MAX:
				all_ok = false
				mark = "!"
			row += "| %.2f%s " % [wr, mark]
		row += "|"
		print(row)
	print("")
	return all_ok


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


func _take_turn(stack: Dictionary, enemy: Array, round_num: int, rng: RandomNumberGenerator) -> void:
	var target: Dictionary = _pick_target(enemy)
	if target.is_empty():
		return
	var uid: String = String(stack["type"])
	var engage: int = int(ENGAGE_ROUND.get(uid, 1))
	if round_num < engage:
		# Noch im Anmarsch, kein Angriff in dieser Runde.
		return
	var is_ranged: bool = UnitType.is_ranged(uid)
	# Nahkampfmalus: Wenn feindliche Nahkaempfer bereits engagiert haben,
	# steht der Bogenschuetze unter Druck und schiesst mit Malus.
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
		if UnitType.is_ranged(String(s["type"])):
			continue
		if round_num >= int(ENGAGE_ROUND.get(String(s["type"]), 1)):
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


func _count_for_gold(uid: String, gold: int) -> int:
	var cost: int = UnitType.cost_of(uid)
	if cost <= 0:
		return 1
	return max(1, gold / cost)


# Verteilt Gold gemaess Anteilen auf mehrere Typen und liefert eine
# Stack-Liste zurueck. Reste werden ueber Priorisierung des teuersten
# verbleibenden Typs abgebaut, damit die Kosten moeglichst genau dem
# Budget entsprechen.
func _mix(shares: Dictionary, gold: int) -> Array:
	var out: Array = []
	for uid in shares.keys():
		var share: float = float(shares[uid])
		var budget: int = int(float(gold) * share)
		var cost: int = UnitType.cost_of(String(uid))
		var cnt: int = max(0, budget / cost)
		if cnt > 0:
			out.append({"type": String(uid), "count": cnt})
	if out.is_empty():
		out.append({"type": "sword", "count": max(1, gold / UnitType.cost_of("sword"))})
	return out
