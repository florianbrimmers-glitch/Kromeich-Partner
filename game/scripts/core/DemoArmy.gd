class_name DemoArmy
extends RefCounted

# Baut feste Demo-Armeen fuer den Battle-Prototyp.
# GDScript-Port von scripts/ui/DemoArmy.cs.

static func build_men_vs_orks() -> Dictionary:
	var units := UnitRepo.load_all()
	var s0: Array = [
		BattleStack.new(units["men_angel"],    2,  0),
		BattleStack.new(units["men_cavalier"], 6,  0),
		BattleStack.new(units["men_crusader"], 14, 0),
		BattleStack.new(units["men_archer"],   20, 0),
		BattleStack.new(units["men_spearman"], 40, 0),
	]
	var s1: Array = [
		BattleStack.new(units["ork_behemoth"], 2,  1),
		BattleStack.new(units["ork_cyclops"],  4,  1),
		BattleStack.new(units["ork_ogre"],     8,  1),
		BattleStack.new(units["ork_orc"],      20, 1),
		BattleStack.new(units["ork_goblin"],   60, 1),
	]
	return {
		"side0": s0,
		"side1": s1,
		"label0": "Menschen",
		"label1": "Orkstaemme",
	}
