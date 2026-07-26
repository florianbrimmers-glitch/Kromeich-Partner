class_name CombatMath
extends RefCounted

# Zentrale Kampf-Formel. Wird sowohl vom TacticalBattleScreen (Live-
# Kampf) als auch vom Balance-Simulator (tools/balance_sim.gd) benutzt.
# Aendert sich hier etwas, bleibt das automatisch konsistent.
#
# Stack-Dict-Konvention:
#   { "type": "<units.json-id>", "count": int, "top_hp": int, ... }
#
# Schadensformel (angelehnt an HoMM3):
#   base      = rand(dmg_min..dmg_max) * count
#   mod       = 1 + clamp((att - def) * 0.05, -0.7, 1.5)
#   melee_pen = Malus fuer Fernkaempfer im Nahkampf, ability-abhaengig
#               (M4 Teil 3): Standard x0.5, melee_penalty_half x0.75,
#               no_melee_penalty x1.0. units.json definiert die Flags
#               nicht formal - das hier ist die dokumentierte
#               Interpretation (HoMM3-analog: Moench ohne Malus).
#   damage    = max(1, base * mod)


static func damage(attacker: Dictionary, defender: Dictionary,
		melee_penalty: bool, att_bonus: int, def_bonus: int,
		rng: RandomNumberGenerator) -> int:
	var uid: String = String(attacker["type"])
	var ut: Dictionary = UnitType.get_type(uid)
	var att: int = int(ut.get("att", 4)) + att_bonus
	var dut: Dictionary = UnitType.get_type(String(defender["type"]))
	var def_val: int = int(dut.get("def", 4)) + def_bonus
	var base: int = rng.randi_range(int(ut.get("dmg_min", 1)), int(ut.get("dmg_max", 3)))
	var total: float = float(base * int(attacker["count"]))
	var diff: int = att - def_val
	var mod: float = 1.0 + clampf(float(diff) * 0.05, -0.7, 1.5)
	if melee_penalty:
		var abilities: Array = ut.get("abilities", []) as Array
		if abilities.has("no_melee_penalty"):
			pass
		elif abilities.has("melee_penalty_half"):
			mod *= 0.75
		else:
			mod *= 0.5
	return int(max(1.0, total * mod))


# HP-Pool-Logik: Damage frisst zuerst die top_hp der vordersten Einheit,
# danach weitere Einheiten. Gibt die Anzahl gefallener Einheiten zurueck,
# damit der Aufrufer Kampf-Logs schreiben kann.
static func apply(stack: Dictionary, dmg: int) -> int:
	if dmg <= 0 or int(stack["count"]) <= 0:
		return 0
	var before: int = int(stack["count"])
	var hp_per: int = UnitType.hp_of(String(stack["type"]))
	var total: int = (before - 1) * hp_per + int(stack["top_hp"]) - dmg
	if total <= 0:
		stack["count"] = 0
		stack["top_hp"] = 0
		return before
	stack["count"] = (total - 1) / hp_per + 1
	var rem: int = total % hp_per
	stack["top_hp"] = hp_per if rem == 0 else rem
	return before - int(stack["count"])
