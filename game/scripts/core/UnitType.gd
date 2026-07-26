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
# Legacy: die 12 alten IDs (sword/bow/... aus der 3-Tier-Aera) leben als
# Aliase weiter - canonical() mappt sie auf die JSON-IDs. Save-Dateien
# mit alten army-/pool-Keys laden dadurch ohne Migrationsschritt.
# Die Aliase werden eine spaetere Iteration wieder entfernt.
#
# Gebaeude-Zuordnung (Teil 1, bewusst konservativ): kaserne schaltet
# Tier 1 frei, schmiede Tier 2, reiterei Tier 3. Tiers 4-7 haben noch
# KEIN Gebaeude und sind nicht rekrutierbar, bis M4 Teil 2 die
# Dwelling-Struktur baut.

const SLOT_MELEE := "melee"
const SLOT_RANGED := "ranged"
const SLOT_HEAVY := "heavy"

# JSON-Fraktions-Strings in Spiel-Fraktions-IDs (Reihenfolge wie
# FACTION_NAMES in WorldMapScreen: Waldvolk, Menschen, Totenreich, Orks).
const FACTION_STR_TO_ID := {
	"waldvolk": 0, "menschen": 1, "totenreich": 2, "orkstaemme": 3,
}

# Tier -> Rekrutierungs-Gebaeude (Teil 1: nur T1-T3).
const TIER_BUILDING := {1: "kaserne", 2: "schmiede", 3: "reiterei"}

# Alte 3-Tier-IDs -> JSON-IDs, gemappt nach TIER (nicht nach Rolle -
# die Fraktionen sind bewusst asymmetrisch, z.B. hat Totenreich erst
# auf T5 Fernkampf). Fuer Save-Kompatibilitaet.
const LEGACY_ALIASES := {
	"dryade": "elf_dwarf", "elfbogen": "elf_archer", "einhorn": "elf_pegasus",
	"sword": "men_spearman", "bow": "men_archer", "rider": "men_griffin",
	"skelett": "nec_skeleton", "knochen": "nec_zombie", "vampir": "nec_wight",
	"goblin": "ork_goblin", "orkbogen": "ork_wolfrider", "oger": "ork_orc",
}

static var _types: Dictionary = {}
static var _faction_order: Dictionary = {}
static var _order: Array = []


static func canonical(id: String) -> String:
	return String(LEGACY_ALIASES.get(id, id))


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
	var cid := canonical(id)
	if _types.has(cid):
		return _types[cid]
	return _types.get("men_spearman", {})


static func all_ids() -> Array:
	_ensure_loaded()
	return _order


static func ids_for_faction(fid: int) -> Array:
	_ensure_loaded()
	if _faction_order.has(fid):
		return _faction_order[fid]
	return _faction_order.get(1, [])


# Nur die Tiers, die schon ein Rekrutierungs-Gebaeude haben (T1-T3 in
# Teil 1). CityScreen/KI arbeiten hierueber, damit T4-7 erst mit den
# Dwellings aus Teil 2 auftauchen.
static func recruitable_ids_for_faction(fid: int) -> Array:
	var out: Array = []
	for uid in ids_for_faction(fid):
		if int(get_type(String(uid))["tier"]) <= 3:
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


# Umgekehrter Lookup: welche Einheit der Fraktion schaltet das Gebaeude
# frei? (Teil 1: 1 Einheit je Gebaeude; Teil 2 macht daraus Listen.)
static func unit_for_building(fid: int, bid: String) -> String:
	for uid in ids_for_faction(fid):
		if building_for(String(uid)) == bid:
			return String(uid)
	return ""


static func starter_id_for_faction(fid: int) -> String:
	var ids: Array = ids_for_faction(fid)
	if ids.is_empty():
		return "men_spearman"
	return String(ids[0])


static func is_ranged(id: String) -> bool:
	return int(get_type(id).get("shots", 0)) > 0


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
