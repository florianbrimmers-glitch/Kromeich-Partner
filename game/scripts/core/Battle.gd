class_name Battle
extends RefCounted

# GDScript-Port von scripts/core/Battle.cs.
# Deterministisch: gleicher Seed + gleiche Armeen -> gleicher Ausgang
# und gleiches Event-Log. Keine Hex-Positionen, keine Spells.

const MAX_TURNS := 100

# Outcome-Konstanten
const OUTCOME_SIDE0 := 0
const OUTCOME_SIDE1 := 1
const OUTCOME_DRAW := 2

# Stack ist als Top-Level-Script BattleStack ausgelagert
# (scripts/core/BattleStack.gd), weil Inner-Classes in exportierten
# Android-Builds nicht zuverlaessig via "Battle.Stack.new(...)" konstruiert
# werden koennen.


static func _compare_initiative(a: BattleStack, b: BattleStack) -> bool:
	var sa: int = int(a.unit["stats"]["speed"])
	var sb: int = int(b.unit["stats"]["speed"])
	if sa != sb:
		return sa > sb
	return a.count > b.count


static func simulate(side0: Array, side1: Array, rng: DeterministicRng) -> Dictionary:
	# Returns Dictionary mit keys: outcome, turns, events, side0_casualties, side1_casualties
	var events: Array = []
	if side0.is_empty() or side1.is_empty():
		return _done(OUTCOME_DRAW, side0, side1, 0, 0, 0, events)

	var s0_start := 0
	for s0 in side0:
		s0_start += (s0 as BattleStack).count
	var s1_start := 0
	for s1 in side1:
		s1_start += (s1 as BattleStack).count

	for turn in range(1, MAX_TURNS + 1):
		var order: Array = []
		for s in side0:
			var st: BattleStack = s
			if st.is_alive():
				order.append(st)
		for s in side1:
			var st: BattleStack = s
			if st.is_alive():
				order.append(st)
		order.sort_custom(_compare_initiative)

		for a in order:
			var attacker: BattleStack = a
			if not attacker.is_alive():
				continue
			var pool: Array = side1 if attacker.side == 0 else side0
			var target := _pick_target(attacker, pool)
			if target == null:
				break

			var dmg := _compute_damage(attacker, target, rng)
			target.take_damage(dmg)
			events.append({
				"turn": turn,
				"attacker_id": attacker.unit["id"],
				"target_id": target.unit["id"],
				"damage": dmg,
				"target_count_after": target.count,
			})

			if not target.has_ability("no_retaliation") and target.is_alive():
				@warning_ignore("integer_division")
				var retal := _compute_damage(target, attacker, rng) / 2
				attacker.take_damage(retal)
				events.append({
					"turn": turn,
					"attacker_id": target.unit["id"],
					"target_id": attacker.unit["id"],
					"damage": retal,
					"target_count_after": attacker.count,
				})

		var s0_alive := false
		for s in side0:
			if (s as BattleStack).is_alive():
				s0_alive = true
				break
		var s1_alive := false
		for s in side1:
			if (s as BattleStack).is_alive():
				s1_alive = true
				break
		if not s0_alive and not s1_alive:
			return _done(OUTCOME_DRAW, side0, side1, s0_start, s1_start, turn, events)
		if not s0_alive:
			return _done(OUTCOME_SIDE1, side0, side1, s0_start, s1_start, turn, events)
		if not s1_alive:
			return _done(OUTCOME_SIDE0, side0, side1, s0_start, s1_start, turn, events)

	return _done(OUTCOME_DRAW, side0, side1, s0_start, s1_start, MAX_TURNS, events)


static func _pick_target(attacker: BattleStack, pool: Array) -> BattleStack:
	var best: BattleStack = null
	var best_threat := -INF
	for s in pool:
		var st: BattleStack = s
		if not st.is_alive():
			continue
		var t := _threat(attacker, st)
		if t > best_threat:
			best_threat = t
			best = st
	return best


static func _threat(attacker: BattleStack, target: BattleStack) -> float:
	var dmg_min: int = int(target.unit["stats"]["dmg"][0])
	var dmg_max: int = int(target.unit["stats"]["dmg"][1])
	var dmg := (dmg_min + dmg_max) * 0.5 * target.count
	return dmg / max(1, attacker.total_hp())


static func _compute_damage(attacker: BattleStack, target: BattleStack, rng: DeterministicRng) -> int:
	var dmg_min: int = int(attacker.unit["stats"]["dmg"][0])
	var dmg_max: int = int(attacker.unit["stats"]["dmg"][1])
	var base := rng.next_int(dmg_min, dmg_max)
	var stack_dmg := base * attacker.count

	var att_diff := attacker.eff_att() - target.eff_def()
	var mod := 1.0
	if att_diff > 0:
		mod *= 1.0 + min(3.0, 0.05 * att_diff)
	elif att_diff < 0:
		mod *= max(0.3, 1.0 + 0.025 * att_diff)

	if attacker.has_ability("defense_ignore_25pct"):
		mod *= 1.0 + 0.25 * max(0, target.eff_def()) / float(max(1, attacker.eff_att()))
	elif attacker.has_ability("defense_ignore_40pct"):
		mod *= 1.0 + 0.4 * max(0, target.eff_def()) / float(max(1, attacker.eff_att()))
	if attacker.has_ability("double_attack"):
		mod *= 1.5

	return int(max(1, stack_dmg * mod))


static func _done(outcome: int, s0: Array, s1: Array, s0_start: int, s1_start: int, turns: int, events: Array) -> Dictionary:
	var s0_sum := 0
	for s in s0:
		s0_sum += (s as BattleStack).count
	var s1_sum := 0
	for s in s1:
		s1_sum += (s as BattleStack).count
	return {
		"outcome": outcome,
		"turns": turns,
		"events": events,
		"side0_casualties": s0_start - s0_sum,
		"side1_casualties": s1_start - s1_sum,
	}
