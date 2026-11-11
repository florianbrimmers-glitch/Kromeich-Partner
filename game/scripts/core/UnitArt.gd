extends RefCounted

# Kreatur-Grafik und Kreatur-Werte fuer die Oberflaeche (It. 29).
#
# Reine statische Schicht wie die anderen core-Module, eingebunden per
# `preload` (kein class_name - Android-Export-Vorsicht).
#
# WARUM: die Zuordnung "Unit-ID -> SVG-Datei" stand nur im Kampf-Screen
# (`_unit_texture` mit eigener Konstante und eigenem Cache). Die 28
# Kreatur-Sprites waren dadurch an genau EINER Stelle sichtbar; Rekrutier-
# und Garnisons-Panel zeigten Textkuerzel ("Sk:5 Zo:1"), obwohl die Bilder
# im Repo lagen. Jetzt fragt jeder Bildschirm hier nach.
#
# ACHTUNG, zweimal reingefallen: der Fraktionsname aus units.json
# (`orkstaemme`) ist NICHT der Verzeichnisname (`orks`). Die Reihenfolge
# hier ist die FACTION_ID-Reihenfolge aus UnitType.FACTION_STR_TO_ID.

const FACTION_DIRS := ["waldvolk", "menschen", "totenreich", "orks"]
const SPRITE_PATH := "res://assets/units/%s/%s.svg"

# Fehlende Dateien werden als null gemerkt, damit nicht bei jedem Frame
# neu gesucht wird.
static var _cache: Dictionary = {}


static func path_for(uid: String) -> String:
	var fid: int = UnitType.faction_of(uid)
	if fid < 0 or fid >= FACTION_DIRS.size():
		return ""
	return SPRITE_PATH % [String(FACTION_DIRS[fid]), uid]


static func texture_for(uid: String) -> Texture2D:
	if _cache.has(uid):
		return _cache[uid] as Texture2D
	var tex: Texture2D = null
	var path: String = path_for(uid)
	if path != "" and ResourceLoader.exists(path):
		tex = load(path) as Texture2D
	_cache[uid] = tex
	return tex


static func has_sprite(uid: String) -> bool:
	return texture_for(uid) != null


# Ein fertiges Bild-Element fuer ein Panel. Gibt null zurueck, wenn kein
# Sprite da ist - der Aufrufer soll dann seine Textzeile behalten und
# nicht eine leere Kachel in die Reihe haengen.
static func icon(uid: String, px: int) -> TextureRect:
	var tex: Texture2D = texture_for(uid)
	if tex == null:
		return null
	var tr := TextureRect.new()
	tr.texture = tex
	tr.custom_minimum_size = Vector2(px, px)
	tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	tr.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return tr


# Kampfwerte in einer Zeile. Bisher stand im Rekrutier-Panel nur Name,
# Tier, Bestand und Wachstum - der Spieler kaufte, ohne zu sehen, was er
# kauft.
static func stat_line(uid: String) -> String:
	var t: Dictionary = UnitType.get_type(uid)
	if t.is_empty():
		return ""
	var out: String = "A%d  V%d  TP%d  Sch %d-%d  Tempo %d" % [
		int(t.get("att", 0)), int(t.get("def", 0)), int(t.get("hp", 0)),
		int(t.get("dmg_min", 0)), int(t.get("dmg_max", 0)),
		int(t.get("speed", 0))]
	var shots: int = int(t.get("shots", 0))
	if shots > 0:
		out += "  %d Schuss" % shots
	return out
