extends RefCounted

# Zauber (M8 Teil 1).
#
# Datenschicht ueber data/spells.json - dieselbe Bauart wie HeroSkills:
# statisch, per `preload` eingebunden, ohne `class_name`. Sie loest die
# Wirkformeln der JSON ("dmg=15+15*power") in ZAHLEN auf. Der Kampf-Screen
# fragt nur "wie viel Schaden" und "welcher Status, wie viele Runden" - er
# parst nie einen Effekt-String.
#
# WARUM: spells.json lag wie skills.json ungenutzt im Repo. 21 Zauber, 5
# Schulen, Kosten und Formeln - kein Code hat es gelesen. Und `knowledge`
# sowie `spell_power` im Helden waren Felder ohne Wirkung.
#
# WELCHE ZAUBER GELTEN: nur die, deren Wirkung mit den vorhandenen
# Systemen wirklich eintritt (siehe IMPLEMENTED). Alles andere braucht
# erst ein Grundsystem und wird dem Spieler NICHT angeboten - ein Zauber,
# der nichts tut, ist schlimmer als kein Zauber.

const DATA_PATH := "res://data/spells.json"

# Mana: HoMM3-Regel, Wissen x 10. Damit tut `knowledge` endlich etwas.
const MANA_PER_KNOWLEDGE := 10
# Grundstock, damit auch ein Held ohne Wissen zaubern kann.
const BASE_MANA := 10

# Zauberstufe, die ohne Weisheit erlaubt ist. Weisheit I/II/III hebt sie
# auf 2/3/4 (siehe skills.json). Stufe 5 bleibt vorerst unerreichbar -
# laut skills.json braucht sie ein Relikt, und das gibt es noch nicht.
const BASE_SPELL_LEVEL := 1

# Ein Zauber pro Runde und Held - HoMM3-Regel.
const CASTS_PER_ROUND := 1

# Umgesetzt und wirksam. Der Rest aus spells.json bleibt bewusst draussen:
#   protection_fire  -> es gibt keinen Schadenstyp "Feuer"
#   summon_boat, town_gate -> Abenteuerkarten-Zauber, es gibt keine Boote
#   resurrect, implosion, armageddon -> Stufe 5, ohne Relikt nicht lernbar
const IMPLEMENTED := [
	"heal",           # licht   L1
	"bless",          # licht   L1
	"prayer",         # licht   L3
	"haste",          # ordnung L1
	"shield",         # ordnung L1
	"slow",           # ordnung L2
	"counterstrike",  # ordnung L4
	"stone_skin",     # natur   L1
	"magic_arrow",    # chaos   L1
	"fire_bolt",      # chaos   L2
	"fireball",       # chaos   L3
	"weakness",       # tod     L1
	"curse",          # tod     L2
	"blind",          # tod     L3
	"animate_dead",   # tod     L4
]

# Zauber -> Status und Dauer. Die JSON schreibt "-3_spd_for_3_turns"; die
# Zuordnung auf die Status-Namen steht hier, damit StatusFx die einzige
# Quelle fuer Status-Mechanik bleibt.
const STATUS_SPELLS := {
	"haste":      {"status": "beschleunigt", "rounds": 3, "friendly": true},
	"slow":       {"status": "verlangsamt",  "rounds": 3, "friendly": false},
	"stone_skin": {"status": "steinhaut",    "rounds": 3, "friendly": true},
	"weakness":   {"status": "geschwaecht",  "rounds": 3, "friendly": false},
	"curse":      {"status": "verflucht",    "rounds": 3, "friendly": false},
	"blind":      {"status": "geblendet",    "rounds": 1, "friendly": false},
	# M8 Teil 2
	"bless":         {"status": "gesegnet",     "rounds": 3, "friendly": true},
	"shield":        {"status": "geschirmt",    "rounds": 3, "friendly": true},
	"counterstrike": {"status": "konterbereit", "rounds": 3, "friendly": true},
	# Gebet trifft die GANZE eigene Seite - target ist all_friendly.
	"prayer":        {"status": "gebet",        "rounds": 3, "friendly": true},
}

# Zauber, die die ganze eigene Seite treffen und deshalb KEIN Ziel-Tippen
# brauchen. Wird aus dem `target`-Feld der JSON abgeleitet, hier nur als
# Nachschlagehilfe.
const NO_TARGET_TARGETS := ["all_friendly", "battlefield"]

# Wiederbelebung: hebt `count` wieder an (CombatMath.heal mit
# allow_revive). Nur Untote, so steht es in spells.json.
const REVIVE_SPELLS := {
	"animate_dead": {"base": 30, "per_power": 40, "undead_only": true},
}

# Zauber -> Schadensformel aus der JSON, als Zahlenpaar (Basis, je Kraft).
# Tabelle statt Regex: ein Tippfehler in der JSON faellt im Test auf,
# statt still einen falschen Wert zu erzeugen.
const DAMAGE_SPELLS := {
	"magic_arrow": {"base": 10, "per_power": 10, "aoe": false},
	"fire_bolt":   {"base": 15, "per_power": 15, "aoe": false},
	"fireball":    {"base": 15, "per_power": 10, "aoe": true},
}
const HEAL_SPELLS := {
	"heal": {"base": 25, "per_power": 5},
}
# Fireball trifft die Nachbarfelder mit diesem Anteil - gleiche Mechanik
# wie die Lich-Todeswolke (StatusFx.AOE_FRACTION).
const AOE_FRACTION: float = 0.5

static var _cache: Dictionary = {}


static func _data() -> Dictionary:
	if not _cache.is_empty():
		return _cache
	var f := FileAccess.open(DATA_PATH, FileAccess.READ)
	if f == null:
		push_error("spells.json fehlt: " + DATA_PATH)
		return {}
	var raw: Variant = JSON.parse_string(f.get_as_text())
	if typeof(raw) != TYPE_DICTIONARY:
		push_error("spells.json unlesbar")
		return {}
	_cache = raw as Dictionary
	return _cache


static func all_defs() -> Array:
	return _data().get("spells", []) as Array


static func def_of(spell_id: String) -> Dictionary:
	for s in all_defs():
		if String((s as Dictionary).get("id", "")) == spell_id:
			return s as Dictionary
	return {}


static func level_of(spell_id: String) -> int:
	return int(def_of(spell_id).get("level", 1))


static func school_of(spell_id: String) -> String:
	return String(def_of(spell_id).get("school", ""))


static func cost_of(spell_id: String) -> int:
	return int(def_of(spell_id).get("cost_sp", 5))


static func target_of(spell_id: String) -> String:
	return String(def_of(spell_id).get("target", ""))


static func is_friendly_target(spell_id: String) -> bool:
	var tgt: String = target_of(spell_id)
	return tgt.begins_with("friendly") or tgt == "all_friendly"


# Braucht dieser Zauber ein angetipptes Ziel? Gebet und Flaechen-Zauber
# nicht - sie wirken sofort auf die ganze Seite.
static func needs_target(spell_id: String) -> bool:
	return not NO_TARGET_TARGETS.has(target_of(spell_id))


# Nur auf untote Stacks wirkbar (Untote erwecken).
static func undead_only(spell_id: String) -> bool:
	var d: Dictionary = REVIVE_SPELLS.get(spell_id, {}) as Dictionary
	return bool(d.get("undead_only", false))


static func revive_of(spell_id: String, power: int) -> int:
	var d: Dictionary = REVIVE_SPELLS.get(spell_id, {}) as Dictionary
	if d.is_empty():
		return 0
	return int(d["base"]) + int(d["per_power"]) * max(0, power)


static func display_name(spell_id: String) -> String:
	return String(NAMES.get(spell_id, spell_id))


# Deutsche Namen. spells.json hat nur IDs; die Anzeige gehoert nicht in
# eine Balance-Datendatei.
const NAMES := {
	"heal": "Heilen", "haste": "Eile", "slow": "Verlangsamen",
	"stone_skin": "Steinhaut", "magic_arrow": "Magischer Pfeil",
	"fire_bolt": "Feuerblitz", "fireball": "Feuerball",
	"weakness": "Schwaeche", "curse": "Fluch", "blind": "Blenden",
	"bless": "Segen", "prayer": "Gebet", "shield": "Schild",
	"counterstrike": "Konterschlag", "animate_dead": "Untote erwecken",
}


# --- Mana ----------------------------------------------------------------

static func max_mana(knowledge: int) -> int:
	return BASE_MANA + MANA_PER_KNOWLEDGE * max(0, knowledge)


# --- Was der Held kennt --------------------------------------------------

# Erlaubte Zauberstufe. wisdom_tier 0..3 -> 1/2/3/4.
static func max_spell_level(wisdom_tier: int) -> int:
	return BASE_SPELL_LEVEL + clampi(wisdom_tier, 0, 3)


# Zauber, die dieser Held wirken kann.
#
# Vereinfachung, bewusst und dokumentiert: es gibt noch keine Magiergilde
# als Gebaeude, also kennt der Held von Anfang an alle umgesetzten Zauber
# seiner Fraktions-Schulen bis zur erlaubten Stufe. `affinity_schools`
# kommt aus data/factions.json und gibt den Fraktionen damit eine eigene
# Magie. Eine Gilde kann das spaeter einschraenken, ohne dass sich hier
# etwas aendert.
static func known(schools: Array, wisdom_tier: int) -> Array:
	var cap: int = max_spell_level(wisdom_tier)
	var out: Array = []
	for sid in IMPLEMENTED:
		var s: String = String(sid)
		if level_of(s) > cap:
			continue
		if not schools.is_empty() and not schools.has(school_of(s)):
			continue
		out.append(s)
	return out


# Schulen einer Fraktion aus data/factions.json. Der Index folgt
# FACTION_DIRS (0 waldvolk, 1 menschen, 2 totenreich, 3 orks), die JSON hat
# eine ANDERE Reihenfolge - deshalb ueber die ID nachschlagen und nicht
# ueber die Position.
const FACTION_IDS := ["waldvolk", "menschen", "totenreich", "orkstaemme"]
static var _schools_cache: Dictionary = {}


static func schools_for_faction(faction_index: int) -> Array:
	if faction_index < 0 or faction_index >= FACTION_IDS.size():
		return []
	var fid: String = String(FACTION_IDS[faction_index])
	if _schools_cache.has(fid):
		return _schools_cache[fid] as Array
	var out: Array = []
	var f := FileAccess.open("res://data/factions.json", FileAccess.READ)
	if f != null:
		var raw: Variant = JSON.parse_string(f.get_as_text())
		if typeof(raw) == TYPE_DICTIONARY:
			for entry in ((raw as Dictionary).get("factions", []) as Array):
				var e: Dictionary = entry as Dictionary
				if String(e.get("id", "")) == fid:
					out = (e.get("affinity_schools", []) as Array).duplicate()
					break
	if out.is_empty():
		push_warning("keine affinity_schools fuer " + fid)
	_schools_cache[fid] = out
	return out


static func castable(schools: Array, wisdom_tier: int, mana: int) -> Array:
	var out: Array = []
	for sid in known(schools, wisdom_tier):
		if cost_of(String(sid)) <= mana:
			out.append(String(sid))
	return out


# --- Wirkung -------------------------------------------------------------

static func damage_of(spell_id: String, power: int) -> int:
	var d: Dictionary = DAMAGE_SPELLS.get(spell_id, {}) as Dictionary
	if d.is_empty():
		return 0
	return int(d["base"]) + int(d["per_power"]) * max(0, power)


static func heal_of(spell_id: String, power: int) -> int:
	var d: Dictionary = HEAL_SPELLS.get(spell_id, {}) as Dictionary
	if d.is_empty():
		return 0
	return int(d["base"]) + int(d["per_power"]) * max(0, power)


static func is_aoe(spell_id: String) -> bool:
	var d: Dictionary = DAMAGE_SPELLS.get(spell_id, {}) as Dictionary
	return bool(d.get("aoe", false))


static func status_of(spell_id: String) -> Dictionary:
	return STATUS_SPELLS.get(spell_id, {}) as Dictionary


# Zeile fuer das Zauberbuch: "Feuerblitz - 12 Mana - 45 Schaden".
static func book_line(spell_id: String, power: int) -> String:
	var parts: Array = [display_name(spell_id), "%d Mana" % cost_of(spell_id)]
	if DAMAGE_SPELLS.has(spell_id):
		var dmg: int = damage_of(spell_id, power)
		parts.append("%d Schaden%s" % [dmg, " (+Umfeld)" if is_aoe(spell_id) else ""])
	elif REVIVE_SPELLS.has(spell_id):
		parts.append("%d HP wiederbeleben" % revive_of(spell_id, power))
	elif HEAL_SPELLS.has(spell_id):
		parts.append("%d HP heilen" % heal_of(spell_id, power))
	else:
		var st: Dictionary = status_of(spell_id)
		if not st.is_empty():
			var scope: String = "ganze Armee" if not needs_target(spell_id) else ""
			parts.append("%s, %d Runden%s" % [String(st["status"]),
				int(st["rounds"]), (" (" + scope + ")") if scope != "" else ""])
	return "  -  ".join(parts)
