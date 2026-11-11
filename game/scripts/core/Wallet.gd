class_name Wallet
extends RefCounted

# Mehr-Ressourcen-Boerse (M3). Ressourcen-IDs entsprechen bewusst den
# Schluesseln aus data/units.json (gold, wood, ore, mercury, sulfur,
# crystal, gems), damit die Einheiten-Migration (M4) die Kosten-
# Dictionaries 1:1 durchreichen kann. Deutsche Namen nur fuer die UI.

const RESOURCE_IDS := ["gold", "wood", "ore", "mercury", "sulfur", "crystal", "gems"]

const DISPLAY_NAMES := {
	"gold": "Gold", "wood": "Holz", "ore": "Erz",
	"mercury": "Quecksilber", "sulfur": "Schwefel",
	"crystal": "Kristall", "gems": "Edelsteine",
}

# Kurz-Kuerzel fuer die Topbar (ein Buchstabe, deutsch).
const SHORT_NAMES := {
	"gold": "G", "wood": "H", "ore": "E",
	"mercury": "Q", "sulfur": "S", "crystal": "K", "gems": "J",
}

var res: Dictionary = {}


static func display_name(id: String) -> String:
	return String(DISPLAY_NAMES.get(id, id))


static func short_name(id: String) -> String:
	return String(SHORT_NAMES.get(id, id.substr(0, 1).to_upper()))


# Kompakte Kosten-Anzeige fuer UIs: {"gold":500,"wood":5} -> "500G 5H".
# Reihenfolge folgt RESOURCE_IDS, damit die Anzeige stabil ist.
static func cost_text(cost: Dictionary) -> String:
	var parts: Array = []
	for rid in RESOURCE_IDS:
		if cost.has(rid) and int(cost[rid]) > 0:
			parts.append("%d%s" % [int(cost[rid]), short_name(rid)])
	return " ".join(parts)


func get_amount(id: String) -> int:
	return int(res.get(id, 0))


func set_amount(id: String, n: int) -> void:
	res[id] = max(0, n)


func add(id: String, n: int) -> void:
	set_amount(id, get_amount(id) + n)


func add_all(gain: Dictionary) -> void:
	for k in gain.keys():
		add(String(k), int(gain[k]))


func can_afford(cost: Dictionary) -> bool:
	for k in cost.keys():
		if get_amount(String(k)) < int(cost[k]):
			return false
	return true


# Zieht die Kosten ab, wenn alles bezahlbar ist. false = nichts passiert.
func pay(cost: Dictionary) -> bool:
	if not can_afford(cost):
		return false
	for k in cost.keys():
		add(String(k), -int(cost[k]))
	return true


# --- Save/Load ---
func to_dict() -> Dictionary:
	# Nur Nicht-Null-Betraege speichern, haelt Saves kompakt.
	var out: Dictionary = {}
	for k in res.keys():
		if int(res[k]) != 0:
			out[k] = int(res[k])
	return out


static func from_dict(d: Variant) -> Wallet:
	var w := Wallet.new()
	if d is Dictionary:
		for k in (d as Dictionary).keys():
			w.set_amount(String(k), int((d as Dictionary)[k]))
	return w
