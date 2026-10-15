class_name UnitRepo
extends RefCounted

# Laedt data/units.json und liefert Dictionary<id -> unit_data>.
# unit_data ist selbst ein Dictionary mit Keys wie in der JSON.

const UNITS_PATH := "res://data/units.json"

static func load_all() -> Dictionary:
	var f := FileAccess.open(UNITS_PATH, FileAccess.READ)
	assert(f != null, "units.json nicht gefunden unter %s" % UNITS_PATH)
	var raw := f.get_as_text()
	var parsed: Variant = JSON.parse_string(raw)
	assert(parsed is Dictionary, "units.json ist kein JSON-Objekt")
	var units_array: Array = parsed["units"]
	var out := {}
	for u in units_array:
		out[u["id"]] = u
	return out
