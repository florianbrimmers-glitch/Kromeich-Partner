class_name UnitType
extends RefCounted

# Einheiten-Registry (M4 Teil 1): Fassade ueber data/units.json.
#
# Die 28 Einheiten (4 Fraktionen x 7 Tiers) samt der in balance_notes.md
# dokumentierten Balance kommen aus der JSON (UnitRepo laedt sie). Diese
# Klasse behaelt ALLE bisherigen Signaturen, damit WorldMapScreen,
# CityScreen, TacticalBattleScreen, CombatMath und balance_sim
# unveraendert weiterlaufen.
#
# Die 12 Alt-IDs der 3-Tier-Aera (sword/bow/...) sind seit Save-Version 2
# Geschichte: alte Saves werden EINMAL beim Laden migriert
# (SaveManager.LEGACY_UNIT_IDS), der Live-Pfad kennt nur noch JSON-IDs.
#
# Gebaeude-Zuordnung (Teil 2): 4 Rekrut-Gebaeude decken alle 7 Tiers -
# kaserne T1+2, schmiede T3+4, reiterei T5+6, zitadelle T7. Ein Gebaeude
# schaltet also bis zu 2 Einheiten frei (units_for_building).

const SLOT_MELEE := "melee"
const SLOT_RANGED := "ranged"
const SLOT_HEAVY := "heavy"

# JSON-Fraktions-Strings in Spiel-Fraktions-IDs (Reihenfolge wie
# FACTION_NAMES in WorldMapScreen: Waldvolk, Menschen, Totenreich, Orks).
const FACTION_STR_TO_ID := {
	"waldvolk": 0, "menschen": 1, "totenreich": 2, "orkstaemme": 3,
}

# Tier -> Rekrutierungs-Gebaeude (Teil 2: alle 7 Tiers).
const TIER_BUILDING := {
	1: "kaserne", 2: "kaserne",
	3: "schmiede", 4: "schmiede",
	5: "reiterei", 6: "reiterei",
	7: "zitadelle",
}

static var _types: Dictionary = {}
static var _faction_order: Dictionary = {}
static var _order: Array = []


static func _ensure_loaded() -> void:
	if not _types.is_empty():
		return
	var raw: Dictionary = UnitRepo.load_all()
	# Nach Fraktion+Tier sortiert aufbauen, damit all_ids()/
	# ids_for_faction() stabile, anzeigefreundliche Reihenfolgen liefern.
	var per_faction: Dictionary = {0: [], 1: [], 2: [], 3: []}
	for uid in raw.keys():
		var u: Dictionary = raw[uid]
		var norm := _normalize(u)
		_types[String(uid)] = norm
		per_faction[int(norm["faction"])].append(String(uid))
	for fid in per_faction.keys():
		var lst: Array = per_faction[fid]
		lst.sort_custom(func(a, b):
			return int(_types[a]["tier"]) < int(_types[b]["tier"]))
		_faction_order[fid] = lst
	_order.clear()
	for fid in [0, 1, 2, 3]:
		for uid in _faction_order.get(fid, []):
			_order.append(uid)


# JSON-Schema -> Runtime-Schema (flach, wie es die Battle-Engine kennt).
static func _normalize(u: Dictionary) -> Dictionary:
	var stats: Dictionary = u.get("stats", {})
	var dmg: Array = stats.get("dmg", [1, 1])
	var shots: int = int(stats.get("shots", 0))
	var tier: int = int(u.get("tier", 1))
	# Slot-Semantik der alten Engine beibehalten: ranged wenn shots > 0,
	# sonst melee (T1/T2) bzw. heavy (T3+). Nur fuer Anzeige-Zwecke.
	var slot: String = SLOT_RANGED if shots > 0 else (SLOT_MELEE if tier <= 2 else SLOT_HEAVY)
	return {
		"id": String(u.get("id", "")),
		"name": String(u.get("name", u.get("id", "?"))),
		"short": String(u.get("short", String(u.get("id", "??")).substr(0, 2))),
		"faction": int(FACTION_STR_TO_ID.get(String(u.get("faction", "menschen")), 1)),
		"slot": slot,
		"tier": tier,
		"att": int(stats.get("att", 1)),
		"def": int(stats.get("def", 1)),
		"hp": int(stats.get("hp", 1)),
		"dmg_min": int(dmg[0]) if dmg.size() > 0 else 1,
		"dmg_max": int(dmg[1]) if dmg.size() > 1 else 1,
		"speed": int(stats.get("speed", 4)),
		"shots": shots,
		"cost": (u.get("cost", {}) as Dictionary).duplicate(),
		"weekly_growth": int(u.get("weekly_growth", 1)),
		"abilities": (u.get("abilities", []) as Array).duplicate(),
	}


static func get_type(id: String) -> Dictionary:
	_ensure_loaded()
	if _types.has(id):
		return _types[id]
	return _types.get("men_spearman", {})


static func all_ids() -> Array:
	_ensure_loaded()
	return _order


static func ids_for_faction(fid: int) -> Array:
	_ensure_loaded()
	if _faction_order.has(fid):
		return _faction_order[fid]
	return _faction_order.get(1, [])


# Nur die Tiers, die ein Rekrutierungs-Gebaeude haben - seit Teil 2
# sind das alle 7. CityScreen/KI arbeiten hierueber.
static func recruitable_ids_for_faction(fid: int) -> Array:
	var out: Array = []
	for uid in ids_for_faction(fid):
		if TIER_BUILDING.has(int(get_type(String(uid))["tier"])):
			out.append(uid)
	return out


static func faction_of(uid: String) -> int:
	return int(get_type(uid).get("faction", 1))


static func slot_of(uid: String) -> String:
	return String(get_type(uid).get("slot", SLOT_MELEE))


static func tier_of(uid: String) -> int:
	return int(get_type(uid).get("tier", 1))


static func growth_of(uid: String) -> int:
	return int(get_type(uid).get("weekly_growth", 1))


static func building_for(uid: String) -> String:
	return String(TIER_BUILDING.get(tier_of(uid), ""))


# Umgekehrter Lookup: alle Einheiten der Fraktion, die dieses Gebaeude
# freischaltet (1-2 Stueck, tier-sortiert weil ids_for_faction sortiert).
static func units_for_building(fid: int, bid: String) -> Array:
	var out: Array = []
	for uid in ids_for_faction(fid):
		if building_for(String(uid)) == bid:
			out.append(uid)
	return out


# Kompat-Wrapper: erste Einheit des Gebaeudes ("" wenn keins).
static func unit_for_building(fid: int, bid: String) -> String:
	var lst: Array = units_for_building(fid, bid)
	return String(lst[0]) if not lst.is_empty() else ""


static func starter_id_for_faction(fid: int) -> String:
	var ids: Array = ids_for_faction(fid)
	if ids.is_empty():
		return "men_spearman"
	return String(ids[0])


static func is_ranged(id: String) -> bool:
	return int(get_type(id).get("shots", 0)) > 0


# Munitionsvorrat pro Kampf (0 = reiner Nahkaempfer). M4 Teil 3:
# der Kampf zaehlt shots_left pro Stack herunter.
static func shots_of(id: String) -> int:
	return int(get_type(id).get("shots", 0))


static func abilities_of(id: String) -> Array:
	return get_type(id).get("abilities", []) as Array


static func has_ability(id: String, ability: String) -> bool:
	return abilities_of(id).has(ability)


static func speed_of(id: String) -> int:
	return int(get_type(id).get("speed", 4))


static func hp_of(id: String) -> int:
	return int(get_type(id).get("hp", 10))


# Legacy-Pfad: liefert den GOLD-Anteil der Kosten als int. Der volle
# Ressourcen-Preis (cost_dict_of) wird ab M4 Teil 2 im Rekrut-Pfad
# verwendet; T1-T3-Einheiten kosten in der JSON ohnehin nur Gold.
static func cost_of(id: String) -> int:
	return int((get_type(id).get("cost", {}) as Dictionary).get("gold", 100))


static func cost_dict_of(id: String) -> Dictionary:
	return (get_type(id).get("cost", {}) as Dictionary).duplicate()


static func name_of(id: String) -> String:
	return String(get_type(id).get("name", "?"))


static func short_of(id: String) -> String:
	return String(get_type(id).get("short", "?"))
