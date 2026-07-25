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
const SAVE_VERSION := 1

# Vom Hauptmenue gesetzt, von WorldMapScreen._ready konsumiert.
var pending_load: Dictionary = {}


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
	# while int(d["save_version"]) < SAVE_VERSION:
	#     d = _migrate_1_to_2(d)  # kommt, wenn noetig
	return d
