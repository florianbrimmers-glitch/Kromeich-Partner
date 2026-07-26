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
const SAVE_VERSION := 2

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
			_:
				# Unbekannte Zwischenversion: nicht endlos schleifen.
				d["save_version"] = SAVE_VERSION
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
