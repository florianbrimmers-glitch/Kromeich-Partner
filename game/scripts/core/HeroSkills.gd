extends RefCounted

# Helden-Skills (M7 Teil 1).
#
# Reine statische Regelschicht ueber data/skills.json - dieselbe Bauart wie
# Abilities/StatusFx/Morale/Garrison, eingebunden per `preload` (NICHT
# `class_name`, das ist im Android-Export unzuverlaessig).
#
# WARUM: skills.json lag seit Iteration 5 im Repo und wurde von KEINER
# Zeile Code gelesen. Der Held kannte nur Position, Bewegungspunkte,
# Geldbeutel, Armee, XP und Stufe - kein Angriff, keine Verteidigung, keine
# Skills. Ein Stufenaufstieg gab stumpf +1 Einheit, ohne dass der Spieler
# etwas entscheidet. Damit fehlte die Schleife, die HoMM3 traegt.
#
# Diese Schicht rechnet Skill-Stufen in ZAHLEN um. Der Kampf-Screen sieht
# nie einen Skill, nur Prozentwerte im Kontext - so bleibt die Kampflogik
# frei von Skill-Parsing und beides ist getrennt testbar.

const DATA_PATH := "res://data/skills.json"

# Primaerwerte. In M7 Teil 1 zog die Auswahl nur aus Angriff und
# Verteidigung, weil Zauberkraft und Wissen nichts taten. Mit M8 wirken
# beide: Wissen bestimmt das Mana-Maximum, Zauberkraft skaliert jede
# Zauberwirkung. Der Topf umfasst deshalb jetzt alle vier.
const PRIMARY_IDS := ["attack", "defense", "spell_power", "knowledge"]
const PRIMARY_POOL := ["attack", "defense", "spell_power", "knowledge"]
const PRIMARY_NAMES := {
	"attack": "Angriff", "defense": "Verteidigung",
	"spell_power": "Zauberkraft", "knowledge": "Wissen",
}

# Skills, deren Grundsystem noch fehlt. Sie werden NICHT angeboten - der
# Spieler soll keinen toten Skill ziehen koennen.
#   pathfinding -> braucht Gelaende-Bewegungskosten
#   tactics     -> braucht eine Aufstellungsphase vor dem Kampf
#   necromancy  -> braucht Armee-Zuwachs nach dem Sieg (M7 Teil 2)
# Weisheit und Mystizismus sind seit M8 drin - sie brauchten Zauber und
# Mana, und beides gibt es jetzt.
const NOT_YET_IMPLEMENTED := ["pathfinding", "tactics", "necromancy"]

const MAX_TIER := 3
const MAX_SLOTS := 8
const OFFER_COUNT := 2

# Fraktions-Gewichte fuer den Primaerwert. Quelle der Absicht:
# hero_classes und affinity_schools in data/factions.json.
# Reihenfolge = FACTION_DIRS-Index: 0 waldvolk, 1 menschen, 2 totenreich,
# 3 orks. Werte sind Gewichte fuer PRIMARY_POOL in dessen Reihenfolge:
# Angriff, Verteidigung, Zauberkraft, Wissen.
const FACTION_WEIGHTS := {
	0: [3, 2, 3, 2],   # Waldvolk: offensiv und naturmagisch
	1: [3, 3, 2, 2],   # Menschen: ausgewogen (Referenz)
	2: [2, 3, 3, 2],   # Totenreich: zaeh und magielastig
	3: [4, 3, 1, 1],   # Orks: schlagen zu, zaubern kaum
}

static var _cache: Dictionary = {}


static func _data() -> Dictionary:
	if not _cache.is_empty():
		return _cache
	var f := FileAccess.open(DATA_PATH, FileAccess.READ)
	if f == null:
		push_error("skills.json fehlt: " + DATA_PATH)
		return {}
	var raw: Variant = JSON.parse_string(f.get_as_text())
	if typeof(raw) != TYPE_DICTIONARY:
		push_error("skills.json unlesbar")
		return {}
	_cache = raw as Dictionary
	return _cache


static func secondary_defs() -> Array:
	return _data().get("secondary_skills", []) as Array


static func def_of(skill_id: String) -> Dictionary:
	for s in secondary_defs():
		if String((s as Dictionary).get("id", "")) == skill_id:
			return s as Dictionary
	return {}


static func display_name(skill_id: String) -> String:
	var d: Dictionary = def_of(skill_id)
	return String(d.get("name", skill_id))


static func all_secondary_ids() -> Array:
	var out: Array = []
	for s in secondary_defs():
		out.append(String((s as Dictionary).get("id", "")))
	return out


# Anbietbar = umgesetzt. Alles andere waere ein toter Zug fuer den Spieler.
static func offerable_ids() -> Array:
	var out: Array = []
	for sid in all_secondary_ids():
		if not NOT_YET_IMPLEMENTED.has(sid):
			out.append(sid)
	return out


static func conflicts_of(skill_id: String) -> Array:
	return def_of(skill_id).get("conflicts_with", []) as Array


# --- Angebot beim Stufenaufstieg ------------------------------------------

# Liefert bis zu OFFER_COUNT Skill-IDs. `have` ist {skill_id: stufe}.
# Deterministisch ueber den uebergebenen RNG, damit derselbe Spielstand
# dasselbe Angebot zeigt.
static func offer(rng: RandomNumberGenerator, have: Dictionary) -> Array:
	var pool: Array = []
	# Slot-Limit: sind alle Plaetze belegt, gibt es nur noch Aufstufungen
	# der bereits gelernten Skills.
	var slots_full: bool = have.size() >= MAX_SLOTS
	for sid in offerable_ids():
		var tier: int = int(have.get(sid, 0))
		if tier >= MAX_TIER:
			continue
		if tier == 0:
			if slots_full:
				continue
			# Konflikt-Paare: Fuehrung und Totenerweckung schliessen sich
			# aus (Menschen gegen Totenreich).
			var blocked := false
			for other in conflicts_of(sid):
				if int(have.get(String(other), 0)) > 0:
					blocked = true
					break
			if blocked:
				continue
		pool.append(sid)
	if pool.is_empty():
		return []
	# Ziehen ohne Zuruecklegen.
	var out: Array = []
	while out.size() < OFFER_COUNT and not pool.is_empty():
		var i: int = rng.randi_range(0, pool.size() - 1)
		out.append(String(pool[i]))
		pool.remove_at(i)
	return out


# Primaerwert beim Stufenaufstieg, fraktionsgewichtet.
static func roll_primary(rng: RandomNumberGenerator, faction_id: int) -> String:
	var weights: Array = FACTION_WEIGHTS.get(faction_id, [2, 2]) as Array
	var total: int = 0
	for w in weights:
		total += int(w)
	if total <= 0:
		return String(PRIMARY_POOL[0])
	var roll: int = rng.randi_range(1, total)
	var acc: int = 0
	for i in range(PRIMARY_POOL.size()):
		acc += int(weights[i]) if i < weights.size() else 0
		if roll <= acc:
			return String(PRIMARY_POOL[i])
	return String(PRIMARY_POOL[PRIMARY_POOL.size() - 1])


# --- Effekt-Werte ---------------------------------------------------------
# Die Zahlen stehen als Text in skills.json ("ranged_dmg_+25pct"). Hier
# werden sie EINMAL in Zahlen uebersetzt; niemand sonst parst diese
# Strings. Tabellen statt Regex, damit ein Tippfehler in der JSON auffaellt
# (0 statt eines falschen Werts) und die Werte im Test nachlesbar sind.

const _TABLES := {
	"leadership": [1, 2, 3],           # Moralpunkte
	"logistics": [10, 20, 30],         # Prozent Bewegung
	"scouting": [1, 2, 2],             # Felder Sichtweite (Stufe 3 = wie 2)
	"archery": [10, 25, 50],           # Prozent Fernkampfschaden
	"offense": [10, 25, 40],           # Prozent Nahkampfschaden
	"armorer": [5, 10, 15],            # Prozent weniger erlittener Schaden
	"estates": [125, 250, 500],        # Gold pro Tag
	"wisdom": [2, 3, 4],               # hoechste lernbare Zauberstufe
	"mysticism": [1, 2, 3],            # Mana pro Tag zusaetzlich
	"necromancy": [10, 20, 30],        # Prozent der Gefallenen (Teil 2)
}


static func value_of(skill_id: String, tier: int) -> int:
	if tier <= 0:
		return 0
	var tbl: Array = _TABLES.get(skill_id, []) as Array
	if tbl.is_empty():
		return 0
	return int(tbl[min(tier, tbl.size()) - 1])


static func value_in(have: Dictionary, skill_id: String) -> int:
	return value_of(skill_id, int(have.get(skill_id, 0)))


# Bequeme Namen fuer die Aufrufer.
static func morale_bonus(have: Dictionary) -> int:
	return value_in(have, "leadership")

static func move_pct(have: Dictionary) -> int:
	return value_in(have, "logistics")

static func sight_bonus(have: Dictionary) -> int:
	return value_in(have, "scouting")

static func archery_pct(have: Dictionary) -> int:
	return value_in(have, "archery")

static func offense_pct(have: Dictionary) -> int:
	return value_in(have, "offense")

static func armorer_pct(have: Dictionary) -> int:
	return value_in(have, "armorer")

static func estates_gold(have: Dictionary) -> int:
	return value_in(have, "estates")

# Weisheit als STUFE, nicht als Wert: HeroSpells.max_spell_level rechnet
# daraus die erlaubte Zauberstufe. Die Tabelle oben haelt die Stufen-Werte
# nur fuer die Anzeige.
static func wisdom_tier(have: Dictionary) -> int:
	return int(have.get("wisdom", 0))

static func mana_regen(have: Dictionary) -> int:
	return value_in(have, "mysticism")


# Kurzbeschreibung der NAECHSTEN Stufe - fuer die Auswahl beim Aufstieg.
# Der Spieler muss sehen, was der Zug bringt, nicht nur den Namen.
static func next_tier_text(skill_id: String, have: Dictionary) -> String:
	var cur: int = int(have.get(skill_id, 0))
	var nxt: int = cur + 1
	var val: int = value_of(skill_id, nxt)
	match skill_id:
		"leadership":
			return "Moral +%d im Kampf" % val
		"logistics":
			return "+%d %% Bewegung auf der Karte" % val
		"scouting":
			return "+%d Feld(er) Sichtweite" % val
		"archery":
			return "+%d %% Schaden im Fernkampf" % val
		"offense":
			return "+%d %% Schaden im Nahkampf" % val
		"armorer":
			return "-%d %% erlittener Schaden" % val
		"estates":
			return "+%d Gold pro Tag" % val
		"necromancy":
			return "%d %% der Gefallenen als Skelette" % val
		"wisdom":
			return "Zauber bis Stufe %d lernbar" % val
		"mysticism":
			return "+%d Mana pro Tag" % val
	return ""


# Zeile fuer das Helden-Panel: "Fuehrung II (Moral +2)".
static func summary_line(skill_id: String, tier: int) -> String:
	var roman: Array = ["", "I", "II", "III"]
	var name: String = display_name(skill_id)
	var val: int = value_of(skill_id, tier)
	if val == 0:
		return "%s %s" % [name, String(roman[min(tier, 3)])]
	return "%s %s (%d)" % [name, String(roman[min(tier, 3)]), val]
