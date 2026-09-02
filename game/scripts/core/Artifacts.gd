extends RefCounted

# Artefakte (It. 51), kleine Fassung.
#
# WAS SIE TUN: sie heben die vier Primaerwerte des Helden (Angriff,
# Verteidigung, Zauberkraft, Wissen). Sonst nichts - keine Faehigkeiten,
# keine Zauber, keine Bewegung. Das war die Entscheidung des Nutzers und
# haelt den Eingriff in die austarierte Balance klein.
#
# WAS SIE NICHT TUN: Relikte. skills.json verlangt fuer Zauber der Stufe 5
# ein Relikt; die drei Zauber (resurrect, implosion, armageddon) bleiben
# deshalb weiter drin und unerreichbar, so wie in HeroSpells dokumentiert.
#
# Rein statisch wie Abilities/Morale/Garrison, Einbindung per preload
# (Android-class_name-Falle, siehe Kopf von TacticalBattleScreen.gd).

const DATA_PATH := "res://data/artifacts.json"

# Ein Held traegt hoechstens so viele. Drei ist die Zahl, bei der ein
# Fund noch eine ENTSCHEIDUNG ist (was lege ich ab?) und nicht bloss
# Buchhaltung.
const MAX_SLOTS := 3

# Die Werte, auf die ein Artefakt wirken darf, und ihre Namen: DIESELBEN wie
# bei den Skills (HeroSkills.PRIMARY_IDS/PRIMARY_NAMES, aus skills.json).
# Die Code-Review zu It. 51 fand hier ein zweites Vokabular ("att"/"def"
# neben "attack"/"defense") - zwei Listen fuer dieselben vier Werte, und ein
# Autor, der "attack" aus skills.json abschreibt, bekaeme einen still
# ignorierten Bonus. HeroSkills laedt selbst nichts nach, kein Preload-Kreis.
const Skills := preload("res://scripts/core/HeroSkills.gd")
const STAT_IDS: Array = Skills.PRIMARY_IDS
const STAT_NAMES: Dictionary = Skills.PRIMARY_NAMES

static var _cache: Dictionary = {}


static func _data() -> Dictionary:
	if not _cache.is_empty():
		return _cache
	var f := FileAccess.open(DATA_PATH, FileAccess.READ)
	if f == null:
		push_error("artifacts.json fehlt: " + DATA_PATH)
		return {}
	var raw: Variant = JSON.parse_string(f.get_as_text())
	if typeof(raw) != TYPE_DICTIONARY:
		push_error("artifacts.json unlesbar")
		return {}
	_cache = raw as Dictionary
	return _cache


static func all_defs() -> Array:
	return _data().get("artifacts", []) as Array



static func def_of(id: String) -> Dictionary:
	for a in all_defs():
		if String((a as Dictionary).get("id", "")) == id:
			return a as Dictionary
	return {}


static func exists(id: String) -> bool:
	return not def_of(id).is_empty()


static func name_of(id: String) -> String:
	var d: Dictionary = def_of(id)
	return String(d.get("name", id))


# Summe eines Wertes ueber alle getragenen Artefakte. Unbekannte IDs
# zaehlen null - ein alter Spielstand mit einem ausgemusterten Artefakt
# soll laden, nicht abstuerzen.
static func bonus(ids: Array, stat: String) -> int:
	var total: int = 0
	for id in ids:
		var b: Dictionary = def_of(String(id)).get("bonus", {}) as Dictionary
		total += int(b.get(stat, 0))
	return total


# "+2 Angriff" bzw. "+3 Angriff, -1 Verteidigung" - in der Reihenfolge von
# STAT_IDS, damit zwei Artefakte mit denselben Werten gleich aussehen.
static func summary(id: String) -> String:
	var b: Dictionary = def_of(id).get("bonus", {}) as Dictionary
	var parts: Array = []
	for stat in STAT_IDS:
		var v: int = int(b.get(stat, 0))
		if v != 0:
			parts.append("%s%d %s" % ["+" if v > 0 else "", v,
				String(STAT_NAMES.get(stat, stat))])
	return ", ".join(parts)


# Deterministische, nach `rarity` gewichtete Wahl. `h` ist ein beliebiger
# Hash - dieselbe Zahl liefert immer dasselbe Artefakt, damit eine Truhe
# beim Neuzeichnen nicht ihren Inhalt wechselt (dieselbe Regel wie bei den
# Monstern, It. 35).
static func pick(h: int) -> String:
	var defs: Array = all_defs()
	if defs.is_empty():
		return ""
	var weights: Array = []
	var total: int = 0
	for a in defs:
		var w: int = maxi(1, int((a as Dictionary).get("rarity", 1)))
		weights.append(w)
		total += w
	var roll: int = absi(h) % total
	for i in range(defs.size()):
		roll -= int(weights[i])
		if roll < 0:
			return String((defs[i] as Dictionary).get("id", ""))
	# roll liegt in [0, total-1] und total ist die Summe derselben Gewichte -
	# die Schleife kehrt immer zurueck. Die Zeile ist fuer den Parser.
	return String((defs[0] as Dictionary).get("id", ""))
