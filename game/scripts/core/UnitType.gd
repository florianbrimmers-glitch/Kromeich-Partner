class_name UnitType
extends RefCounted

# Unit-Registry mit vier Fraktionen (Phase C+).
#
# Jede Fraktion hat genau drei Slots (Nahkampf / Fernkampf / Schwer),
# die jeweils das gleiche Gebaeude benoetigen (Kaserne / Schmiede /
# Reiterei). Die 4x3 = 12 Einheiten haben fraktions-typische
# Stat-Profile:
#
#   Waldvolk   - agil, zerbrechlich, hoher Schaden
#   Menschen   - ausgewogener Baseline (deckt sword/bow/rider)
#   Totenreich - billiger Zerg, schwaches Einzelprofil
#   Orks       - langsam, zaeh, teuer
#
# Die Menschen-IDs (sword/bow/rider) bleiben erhalten, damit der
# bestehende Balance-Simulator und Taktik-Kampf weiterlaufen.

const SLOT_MELEE := "melee"
const SLOT_RANGED := "ranged"
const SLOT_HEAVY := "heavy"

const SLOT_BUILDING := {
	SLOT_MELEE: "kaserne",
	SLOT_RANGED: "schmiede",
	SLOT_HEAVY: "reiterei",
}

const TYPES := {
	# Fraktion 0: Waldvolk
	"dryade": {
		"id": "dryade", "name": "Dryade", "short": "Dr",
		"faction": 0, "slot": SLOT_MELEE, "tier": 1,
		"att": 5, "def": 3, "hp": 8,
		"dmg_min": 2, "dmg_max": 3,
		"speed": 5, "shots": 0, "cost": 100,
	},
	"elfbogen": {
		"id": "elfbogen", "name": "Elfenbogen", "short": "Eb",
		"faction": 0, "slot": SLOT_RANGED, "tier": 2,
		"att": 7, "def": 2, "hp": 9,
		"dmg_min": 2, "dmg_max": 5,
		"speed": 5, "shots": 99, "cost": 140,
	},
	"einhorn": {
		"id": "einhorn", "name": "Einhorn", "short": "Eh",
		"faction": 0, "slot": SLOT_HEAVY, "tier": 3,
		"att": 7, "def": 5, "hp": 17,
		"dmg_min": 3, "dmg_max": 5,
		"speed": 8, "shots": 0, "cost": 220,
	},

	# Fraktion 1: Menschen (Baseline - IDs bleiben stabil fuer Sim/Combat)
	"sword": {
		"id": "sword", "name": "Schwert", "short": "Sw",
		"faction": 1, "slot": SLOT_MELEE, "tier": 1,
		"att": 4, "def": 5, "hp": 10,
		"dmg_min": 1, "dmg_max": 3,
		"speed": 4, "shots": 0, "cost": 100,
	},
	"bow": {
		"id": "bow", "name": "Bogen", "short": "Bw",
		"faction": 1, "slot": SLOT_RANGED, "tier": 2,
		"att": 6, "def": 3, "hp": 11,
		"dmg_min": 2, "dmg_max": 5,
		"speed": 4, "shots": 99, "cost": 140,
	},
	"rider": {
		"id": "rider", "name": "Reiter", "short": "Ri",
		"faction": 1, "slot": SLOT_HEAVY, "tier": 3,
		"att": 7, "def": 6, "hp": 20,
		"dmg_min": 3, "dmg_max": 5,
		"speed": 7, "shots": 0, "cost": 220,
	},

	# Fraktion 2: Totenreich
	"skelett": {
		"id": "skelett", "name": "Skelett", "short": "Sk",
		"faction": 2, "slot": SLOT_MELEE, "tier": 1,
		"att": 3, "def": 4, "hp": 8,
		"dmg_min": 1, "dmg_max": 2,
		"speed": 4, "shots": 0, "cost": 70,
	},
	"knochen": {
		"id": "knochen", "name": "Knochenbogen", "short": "Kb",
		"faction": 2, "slot": SLOT_RANGED, "tier": 2,
		"att": 5, "def": 2, "hp": 9,
		"dmg_min": 2, "dmg_max": 4,
		"speed": 4, "shots": 99, "cost": 120,
	},
	"vampir": {
		"id": "vampir", "name": "Vampir", "short": "Va",
		"faction": 2, "slot": SLOT_HEAVY, "tier": 3,
		"att": 6, "def": 5, "hp": 18,
		"dmg_min": 2, "dmg_max": 5,
		"speed": 7, "shots": 0, "cost": 200,
	},

	# Fraktion 3: Orks
	"goblin": {
		"id": "goblin", "name": "Goblin", "short": "Go",
		"faction": 3, "slot": SLOT_MELEE, "tier": 1,
		"att": 4, "def": 4, "hp": 9,
		"dmg_min": 1, "dmg_max": 3,
		"speed": 3, "shots": 0, "cost": 90,
	},
	"orkbogen": {
		"id": "orkbogen", "name": "Orkschuetze", "short": "Ob",
		"faction": 3, "slot": SLOT_RANGED, "tier": 2,
		"att": 5, "def": 3, "hp": 10,
		"dmg_min": 2, "dmg_max": 5,
		"speed": 3, "shots": 99, "cost": 130,
	},
	"oger": {
		"id": "oger", "name": "Oger", "short": "Og",
		"faction": 3, "slot": SLOT_HEAVY, "tier": 3,
		"att": 8, "def": 7, "hp": 24,
		"dmg_min": 4, "dmg_max": 6,
		"speed": 5, "shots": 0, "cost": 260,
	},
}

# Reihenfolge pro Fraktion: immer melee -> ranged -> heavy.
const FACTION_ORDER := {
	0: ["dryade",  "elfbogen", "einhorn"],
	1: ["sword",   "bow",      "rider"],
	2: ["skelett", "knochen",  "vampir"],
	3: ["goblin",  "orkbogen", "oger"],
}

# Flache Gesamtliste aller IDs in Fraktions-Reihenfolge. Hero.army_summary
# iteriert darueber, um gemischte Armeen zu rendern.
const ORDER := [
	"dryade",  "elfbogen", "einhorn",
	"sword",   "bow",      "rider",
	"skelett", "knochen",  "vampir",
	"goblin",  "orkbogen", "oger",
]


static func get_type(id: String) -> Dictionary:
	if TYPES.has(id):
		return TYPES[id]
	return TYPES["sword"]


static func all_ids() -> Array:
	return ORDER


static func ids_for_faction(fid: int) -> Array:
	if FACTION_ORDER.has(fid):
		return FACTION_ORDER[fid]
	return FACTION_ORDER[1]


static func faction_of(uid: String) -> int:
	return int(get_type(uid).get("faction", 1))


static func slot_of(uid: String) -> String:
	return String(get_type(uid).get("slot", SLOT_MELEE))


static func building_for(uid: String) -> String:
	return String(SLOT_BUILDING.get(slot_of(uid), "kaserne"))


# Umgekehrter Lookup: welche Einheit der Fraktion wird durch das
# gegebene Gebaeude freigeschaltet? Leerer String, wenn das Gebaeude
# keine Einheit produziert (z.B. Spaeher, Kapelle).
static func unit_for_building(fid: int, bid: String) -> String:
	for uid in ids_for_faction(fid):
		if building_for(uid) == bid:
			return String(uid)
	return ""


static func starter_id_for_faction(fid: int) -> String:
	var ids: Array = ids_for_faction(fid)
	if ids.is_empty():
		return "sword"
	return String(ids[0])


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
