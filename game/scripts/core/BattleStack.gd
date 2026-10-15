class_name BattleStack
extends RefCounted

# Top-Level-Script (statt Inner-Class in Battle.gd), weil Inner-Classes
# in GDScript beim exportierten Android-Build nicht zuverlaessig via
# "Battle.Stack.new(...)" konstruiert werden koennen.

var unit: Dictionary
var count: int
var top_unit_hp: int
var side: int

func _init(unit_data: Dictionary, unit_count: int, unit_side: int) -> void:
	unit = unit_data
	count = unit_count
	top_unit_hp = int(unit_data["stats"]["hp"])
	side = unit_side

func is_alive() -> bool:
	return count > 0

func eff_att() -> int:
	return int(unit["stats"]["att"])

func eff_def() -> int:
	return int(unit["stats"]["def"])

func total_hp() -> int:
	var max_hp: int = int(unit["stats"]["hp"])
	return (count - 1) * max_hp + top_unit_hp

func has_ability(a: String) -> bool:
	return a in (unit.get("abilities", []) as Array)

func take_damage(dmg: int) -> void:
	if dmg <= 0:
		return
	var total := total_hp() - dmg
	if total <= 0:
		count = 0
		top_unit_hp = 0
		return
	var max_hp: int = int(unit["stats"]["hp"])
	count = int((total - 1) / max_hp) + 1
	var remainder := total % max_hp
	top_unit_hp = max_hp if remainder == 0 else remainder
