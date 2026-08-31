extends Node

# Save/Load-Verwaltung (M1). Als Autoload "SaveManager" registriert.
#
# WICHTIG: Alle Kernfunktionen sind static, damit headless Tools-Skripte
# (SceneTree-Scripts starten OHNE Autoloads!) sie direkt via
# SaveManagerLib-Preload aufrufen koennen. Das Autoload-Singleton dient
# nur als Traeger fuer pending_load (Menue -> WorldMap-Uebergabe).
#
# Format: JSON, menschenlesbar, mit save_version fuer Migrationen.
# Atomar geschrieben (.tmp + rename), damit ein App-Kill mitten im
# Schreiben keinen korrupten Autosave hinterlaesst.

const SAVE_DIR := "user://saves"
const AUTOSAVE_PATH := "user://saves/autosave.json"
const SAVE_VERSION := 4

# v1 -> v2: Einheiten-IDs der 3-Tier-Aera (M4-Migration). Das Mapping
# lebte als LEGACY_ALIASES in UnitType und wurde bei jedem Lookup
# angewendet; seit v2 wird stattdessen genau EINMAL beim Laden migriert.
# Gemappt nach TIER (nicht Rolle - Fraktionen sind bewusst asymmetrisch).
const LEGACY_UNIT_IDS := {
	"dryade": "elf_dwarf", "elfbogen": "elf_archer", "einhorn": "elf_pegasus",
	"sword": "men_spearman", "bow": "men_archer", "rider": "men_griffin",
	"skelett": "nec_skeleton", "knochen": "nec_zombie", "vampir": "nec_wight",
	"goblin": "ork_goblin", "orkbogen": "ork_wolfrider", "oger": "ork_orc",
}

# Vom Hauptmenue gesetzt, von WorldMapScreen._ready konsumiert.
var pending_load: Dictionary = {}
# Neues Spiel: {seed: int, faction: int 0..3 oder -1 fuer Zufall}.
var pending_new_game: Dictionary = {}


static func write_save(state: Dictionary, path: String = AUTOSAVE_PATH) -> Error:
	var d := state.duplicate()
	d["save_version"] = SAVE_VERSION
	d["saved_at_unix"] = int(Time.get_unix_time_from_system())
	var dir_err := DirAccess.make_dir_recursive_absolute(SAVE_DIR)
	if dir_err != OK and dir_err != ERR_ALREADY_EXISTS:
		return dir_err
	var tmp_path := path + ".tmp"
	var f := FileAccess.open(tmp_path, FileAccess.WRITE)
	if f == null:
		return FileAccess.get_open_error()
	f.store_string(JSON.stringify(d, "\t"))
	f.close()
	# Atomarer Tausch: rename ueberschreibt das alte Save erst, wenn die
	# neue Datei vollstaendig auf der Platte ist.
	return DirAccess.rename_absolute(tmp_path, path)


static func read_save(path: String = AUTOSAVE_PATH) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return {}
	var raw: Variant = JSON.parse_string(f.get_as_text())
	if typeof(raw) != TYPE_DICTIONARY:
		return {}
	return migrate(raw as Dictionary)


static func has_autosave() -> bool:
	return FileAccess.file_exists(AUTOSAVE_PATH)


static func delete_autosave() -> void:
	if FileAccess.file_exists(AUTOSAVE_PATH):
		DirAccess.remove_absolute(AUTOSAVE_PATH)


# Migrations-Kette: hebt aeltere Formate Schritt fuer Schritt auf
# SAVE_VERSION. Neue Felder brauchen KEINE Migration (tolerante Defaults
# in from_dict/_restore_state) - nur semantische Umbauten (z.B. Unit-ID-
# Umbenennung) bekommen hier einen _migrate_N_to_M-Schritt.
static func migrate(d: Dictionary) -> Dictionary:
	var v := int(d.get("save_version", 0))
	if v <= 0:
		# Version 0 existiert nicht in freier Wildbahn; behandle wie 1.
		d["save_version"] = 1
	while int(d["save_version"]) < SAVE_VERSION:
		match int(d["save_version"]):
			1:
				d = _migrate_1_to_2(d)
			2:
				d = _migrate_2_to_3(d)
			3:
				d = _migrate_3_to_4(d)
			_:
				# Unbekannte Zwischenversion: nicht endlos schleifen.
				d["save_version"] = SAVE_VERSION
	return d


# v3 -> v4: Bewegungspunkte in feinerer Einheit (M7 Teil 2). Ein flaches
# Feld kostete 1 Punkt und ein raues 2; damit war der Prozent-Abschlag des
# Skills Wegfindung in ganzen Zahlen nicht darstellbar. Jetzt kostet ein
# flaches Feld Movement.UNIT (4) Punkte, ein raues 8.
#
# Ohne diesen Schritt haette ein alter Spielstand einen Helden mit 7 von 40
# Punkten geladen - der koennte an dem Tag kein einziges Feld weit gehen,
# obwohl er beim Speichern fast voll war. Betroffen sind Held und
# KI-Helden; max_mp wird beim Laden ohnehin neu gerechnet, mp nicht.
const MP_SCALE_3_TO_4 := 4

static func _migrate_3_to_4(d: Dictionary) -> Dictionary:
	_scale_mp_in(d.get("hero"))
	for e in d.get("enemies", []) as Array:
		if e is Dictionary:
			_scale_mp_in((e as Dictionary).get("hero"))
	d["save_version"] = 4
	return d


static func _scale_mp_in(hero: Variant) -> void:
	if not (hero is Dictionary):
		return
	var hd: Dictionary = hero as Dictionary
	for key in ["mp", "max_mp"]:
		if hd.has(key):
			hd[key] = int(hd[key]) * MP_SCALE_3_TO_4


# v2 -> v3: Stadt-Garnisonen werden echte Einheiten. Vorher stand dort
# nur eine Staerke-Zahl, aus der der Kampf Stacks synthetisierte; jetzt
# haelt jede Stadt ein { unit_id: count }-Dictionary wie der Held.
# Die alte Zahl wird ueber Garrison.synth in Einheiten der Stadt-Fraktion
# umgesetzt - ein Save aus v2 verliert also keine Verteidiger.
static func _migrate_2_to_3(d: Dictionary) -> Dictionary:
	for c in d.get("cities", []) as Array:
		if not (c is Dictionary):
			continue
		var cd: Dictionary = c as Dictionary
		if cd.has("garrison_army"):
			continue
		var strength: int = int(cd.get("garrison", 0))
		var fid: int = int(cd.get("faction", 1))
		cd["garrison_army"] = Garrison.synth(fid, strength) if strength > 0 else {}
	d["save_version"] = 3
	return d


# v1 -> v2: alte Einheiten-Schluessel in Held-Armee, KI-Armeen und
# Stadt-Pools umbenennen (LEGACY_UNIT_IDS). Werte werden gemerged,
# falls ein Save alte UND neue Keys enthaelt.
static func _migrate_1_to_2(d: Dictionary) -> Dictionary:
	_map_army_in(d.get("hero"))
	for e in d.get("enemies", []) as Array:
		if e is Dictionary:
			# KI-Held kann null sein (im Kampf gefallen).
			_map_army_in((e as Dictionary).get("hero"))
	for c in d.get("cities", []) as Array:
		if c is Dictionary and (c as Dictionary).has("pools"):
			var cd: Dictionary = c as Dictionary
			cd["pools"] = _map_unit_keys(cd["pools"] as Dictionary)
	d["save_version"] = 2
	return d


static func _map_army_in(hero: Variant) -> void:
	if hero is Dictionary and (hero as Dictionary).has("army"):
		var hd: Dictionary = hero as Dictionary
		hd["army"] = _map_unit_keys(hd["army"] as Dictionary)


static func _map_unit_keys(src: Dictionary) -> Dictionary:
	var out: Dictionary = {}
	for k in src.keys():
		var nk: String = String(LEGACY_UNIT_IDS.get(String(k), String(k)))
		out[nk] = int(out.get(nk, 0)) + int(src[k])
	return out
