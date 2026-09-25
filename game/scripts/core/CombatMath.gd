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
#   ability   = Ziel-def x0.75 bei defense_ignore_25pct, + Jousting-/
#               Speertraeger-Bonus aus Abilities.melee_bonus_pct
#               (M6b Teil 1; opts["tiles_moved"] liefert die gelaufenen
#               Felder). Alle Bonus-Traeger sind Nahkaempfer, deshalb
#               braucht der Bonus keine Fernkampf-Sonderbehandlung.
#   damage    = max(1, base * mod)
#
# Der 7. Parameter opts ist optional - bestehende Aufrufer bleiben
# unveraendert gueltig.


const Abil := preload("res://scripts/core/Abilities.gd")
const Fx := preload("res://scripts/core/StatusFx.gd")


static func damage(attacker: Dictionary, defender: Dictionary,
		melee_penalty: bool, att_bonus: int, def_bonus: int,
		rng: RandomNumberGenerator, opts: Dictionary = {}) -> int:
	var uid: String = String(attacker["type"])
	var ut: Dictionary = UnitType.get_type(uid)
	# Status-Effekte (M6b Teil 2) sitzen im Stack selbst - Krankheit
	# senkt Angriff und Verteidigung.
	var att: int = int(ut.get("att", 4)) + att_bonus + Fx.att_mod(attacker)
	var did: String = String(defender["type"])
	var dut: Dictionary = UnitType.get_type(did)
	var def_val: int = Abil.def_after_ignore(uid,
		int(dut.get("def", 4)) + def_bonus + Fx.def_mod(defender))
	# Segen (M8 Teil 2) verschiebt den Wurf auf den Hoechstwert. Der Wurf
	# passiert TROTZDEM, damit die RNG-Folge gleich lang bleibt - sonst
	# haetten Segen und Nicht-Segen unterschiedliche Zufallsketten und der
	# Balance-Simulator waere nicht mehr vergleichbar.
	var dmin: int = int(ut.get("dmg_min", 1))
	var dmax: int = int(ut.get("dmg_max", 3))
	var roll: int = rng.randi_range(dmin, dmax)
	var bias: int = Fx.damage_bias(attacker)
	var base: int = roll
	if bias > 0:
		base = dmax
	elif bias < 0:
		base = dmin
	var total: float = float(base * int(attacker["count"]))
	var diff: int = att - def_val
	var mod: float = 1.0 + clampf(float(diff) * 0.05, -0.7, 1.5)
	var bonus_pct: int = Abil.melee_bonus_pct(uid, did, int(opts.get("tiles_moved", 0)))
	if bonus_pct != 0:
		mod *= 1.0 + float(bonus_pct) / 100.0
	# Fluch schwaecht den Angreifer, Alterung macht das Ziel anfaelliger.
	mod *= Fx.dealt_factor(attacker)
	# Der Schild-Zauber wirkt nur gegen Nahkampf; ob geschossen wird, weiss
	# nur der Aufrufer (opts["shooting"]).
	mod *= Fx.taken_factor(defender, not bool(opts.get("shooting", false)))
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


# Gegenstueck zu apply(): fuellt den HP-Pool wieder auf - erst die
# angeschlagene vorderste Einheit, dann (Lebensentzug der Vampire)
# gefallene Einheiten zurueck, aber nie ueber die Startstaerke hinaus.
# Ein vernichteter Stack bleibt tot. Rueckgabe: tatsaechlich geheilte HP.
# `allow_revive` false deckelt bei der AKTUELLEN Stackgroesse, statt
# gefallene Einheiten zurueckzubringen. Der Heil-Zauber (M8) braucht das:
# Heilen fuellt auf, Wiederbeleben ist ein eigener Zauber. Standard true,
# damit Lebensentzug und Regeneration unveraendert bleiben.
static func heal(stack: Dictionary, hp: int, allow_revive: bool = true) -> int:
	if hp <= 0 or int(stack["count"]) <= 0:
		return 0
	var hp_per: int = UnitType.hp_of(String(stack["type"]))
	if hp_per <= 0:
		return 0
	var cap_count: int = int(stack.get("count_start", stack["count"]))
	if not allow_revive:
		cap_count = int(stack["count"])
	var cur: int = (int(stack["count"]) - 1) * hp_per + int(stack["top_hp"])
	var new_total: int = min(cap_count * hp_per, cur + hp)
	var healed: int = new_total - cur
	if healed <= 0:
		return 0
	stack["count"] = (new_total - 1) / hp_per + 1
	var rem: int = new_total % hp_per
	stack["top_hp"] = hp_per if rem == 0 else rem
	return healed
