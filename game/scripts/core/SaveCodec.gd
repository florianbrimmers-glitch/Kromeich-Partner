class_name SaveCodec
extends RefCounted

# Reine, statische Konvertierungs-Helfer fuer das Save-Format.
#
# Konventionen:
#   - Vector2i  <-> JSON-Array [x, y]
#   - JSON parst alle Zahlen als float -> ueberall int()-Casts
#   - Dictionary-Keys, die im Spiel ints sind (z.B. rivals_seen nach
#     owner_id), werden beim Laden von String zurueck auf int gemappt.
#
# Kein Zustand, kein Autoload - damit headless Tools-Skripte (die ohne
# Autoloads starten) alles direkt aufrufen koennen.

const V2I_NONE := Vector2i(-1, -1)


static func v2i(v: Vector2i) -> Array:
	return [v.x, v.y]


static func to_v2i(a: Variant, fallback: Vector2i = V2I_NONE) -> Vector2i:
	if a is Vector2i:
		return a
	if a is Array and (a as Array).size() == 2:
		var arr: Array = a
		return Vector2i(int(arr[0]), int(arr[1]))
	return fallback


# Fog-/Tile-Arrays: JSON liefert float-Arrays, das Spiel erwartet ints.
static func int_array(a: Variant) -> Array:
	var out: Array = []
	if a is Array:
		for v in (a as Array):
			out.append(int(v))
	return out


# Dictionary {unit_id: count} - Werte nach int casten (Keys sind Strings).
static func int_dict(d: Variant) -> Dictionary:
	var out: Dictionary = {}
	if d is Dictionary:
		for k in (d as Dictionary).keys():
			out[String(k)] = int((d as Dictionary)[k])
	return out
