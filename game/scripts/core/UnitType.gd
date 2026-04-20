class_name UnitType
extends RefCounted

# Statisches Unit-Registry fuer Phase C. Drei Einheiten-Typen mit
# klaren Rollen: Nahkampf (sword), Fernkampf (bow), schnelle Kavallerie
# (rider). Die Werte sind bewusst niedrig gehalten, damit Kaempfe auf
# dem 10x8-Grid in wenigen Runden durch sind.
#
# Balance-Quellen: data/units.json (men_spearman/men_archer/elf_pegasus),
# aber vereinfacht fuer den Phase-C-Prototyp. Eigener Balance-Pass
# folgt via tools/balance_sim.py in Phase D+.

const TYPES := {
	"sword": {
		"id": "sword",
		"name": "Schwert",
		"short": "S",
		"tier": 1,
		"att": 4,
		"def": 5,
		"hp": 10,
		"dmg_min": 1,
		"dmg_max": 3,
		"speed": 4,
		"shots": 0,
		"cost": 80,
	},
	"bow": {
		"id": "bow",
		"name": "Bogen",
		"short": "B",
		"tier": 2,
		"att": 6,
		"def": 3,
		"hp": 8,
		"dmg_min": 2,
		"dmg_max": 4,
		"speed": 4,
		"shots": 99,
		"cost": 140,
	},
	"rider": {
		"id": "rider",
		"name": "Reiter",
		"short": "R",
		"tier": 3,
		"att": 7,
		"def": 6,
		"hp": 20,
		"dmg_min": 3,
		"dmg_max": 5,
		"speed": 7,
		"shots": 0,
		"cost": 250,
	},
}

const ORDER := ["sword", "bow", "rider"]


static func get_type(id: String) -> Dictionary:
	if TYPES.has(id):
		return TYPES[id]
	return TYPES["sword"]


static func all_ids() -> Array:
	return ORDER


static func is_ranged(id: String) -> bool:
	return int(get_type(id).get("shots", 0)) > 0


static func speed_of(id: String) -> int:
	return int(get_type(id).get("speed", 4))


static func hp_of(id: String) -> int:
	return int(get_type(id).get("hp", 10))


static func cost_of(id: String) -> int:
	return int(get_type(id).get("cost", 100))


static func name_of(id: String) -> String:
	return String(get_type(id).get("name", "?"))


static func short_of(id: String) -> String:
	return String(get_type(id).get("short", "?"))
