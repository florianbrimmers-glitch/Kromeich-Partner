extends SceneTree

# Headless-Tests fuer die raeumlichen Kreaturen und das Kampffeld (It. 54):
#
#   godot --headless --path game/ --script tools/test_creatures3d.gd
#
# WIE AUSSEHEN wird hier nicht geprueft - dafuer gibt es
# tools/preview_creatures3d.gd. Diese Suite haelt die Stellen fest, an
# denen etwas SCHIEF sein kann, ohne dass ein Bild es verraet:
#
#  * Eine Einheit ohne Modell faellt stumm aus (_fill kehrt einfach um).
#  * Ein Modell, dessen Ursprung nicht eingebacken ist, verliert seinen
#    Versatz beim Laden - Moench und Lich standen so bis zur Huefte im
#    Boden, und die Markierungsscheiben lagen 0.01 zu tief. Das eine sah
#    man, das andere nicht.
#  * Ein Modell breiter als eine Zelle ragt ins Nachbarfeld, und dann ist
#    nicht mehr zu sehen, wo die Einheit steht.
#  * Die Groesse erzaehlt die Stufe. Laeuft die Reihenfolge auseinander,
#    ist die Aussage falsch, aber das Bild sieht normal aus.

const Field := preload("res://scripts/ui/BattleField3D.gd")
const Scene3D := preload("res://scripts/ui/Scene3D.gd")

var _fails: int = 0
var _done: Array = []
var _f = null
var _units: Array = []


func _init() -> void:
	_units = _load_units()
	_f = Field.new()
	root.add_child(_f)
	await process_frame

	await _test_every_unit_has_a_model()
	await _test_stands_on_the_ground()
	await _test_fits_the_cell()
	await _test_size_tells_the_tier()
	await _test_instance_colors_enabled()
	await _test_field_places_everything()

	var missing: Array = []
	for m in get_method_list():
		var mn: String = String(m["name"])
		if mn.begins_with("_test") and not _done.has(mn):
			missing.append(mn)
	_check(missing.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)" % str(missing))

	print("")
	if _fails == 0:
		print("Kreaturen-3D-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Kreaturen-3D-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _load_units() -> Array:
	var f := FileAccess.open("res://data/units.json", FileAccess.READ)
	return (JSON.parse_string(f.get_as_text()) as Dictionary)["units"] as Array


func _test_every_unit_has_a_model() -> void:
	print("== Jede Einheit aus units.json hat ein Modell ==")
	var missing: Array = []
	for u in _units:
		var id: String = String((u as Dictionary)["id"])
		if not _f._meshes.has(id):
			missing.append(id)
	_check(missing.is_empty(),
		"%d Einheiten, keine ohne Modell (fehlend: %s)" % [_units.size(), str(missing)])
	# Und die Gegenrichtung: ein Modell ohne Einheit ist eine Leiche im
	# glb, die niemand mehr aufraeumt.
	var ids: Dictionary = {}
	for u in _units:
		ids[String((u as Dictionary)["id"])] = true
	var orphan: Array = []
	for name in _f._meshes.keys():
		var n: String = String(name)
		if (n.begins_with("men_") or n.begins_with("elf_")
				or n.begins_with("nec_") or n.begins_with("ork_")) \
				and not ids.has(n):
			orphan.append(n)
	_check(orphan.is_empty(), "kein Modell ohne Einheit (%s)" % str(orphan))
	_done.append("_test_every_unit_has_a_model")


func _test_stands_on_the_ground() -> void:
	print("== Jede Figur steht auf dem Boden ==")
	var bad: Array = []
	for u in _units:
		var id: String = String((u as Dictionary)["id"])
		if not _f._meshes.has(id):
			continue
		var a: AABB = (_f._meshes[id] as Mesh).get_aabb()
		# Das Gespenst schwebt ABSICHTLICH - es hat keine Beine, und auf
		# dem Boden stehend waere es ein Mann im Bettlaken. Genau deshalb
		# steht es hier namentlich und mit eigener Erwartung: eine stille
		# Ausnahme waere in beide Richtungen wertlos.
		var floats: bool = id == "nec_wight"
		var lo: float = 0.06 if floats else -0.02
		var hi: float = 0.14 if floats else 0.03
		if a.position.y < lo or a.position.y > hi:
			bad.append("%s (Unterkante %+.3f, erwartet %.2f..%.2f)"
				% [id, a.position.y, lo, hi])
	_check(bad.is_empty(),
		"jede Figur auf dem Boden, das Gespenst darueber (%s)" % str(bad))
	_done.append("_test_stands_on_the_ground")


func _test_fits_the_cell() -> void:
	print("== Jede Figur bleibt auf ihrer Zelle ==")
	var over: Array = []
	for u in _units:
		var id: String = String((u as Dictionary)["id"])
		if not _f._meshes.has(id):
			continue
		var a: AABB = (_f._meshes[id] as Mesh).get_aabb()
		if a.size.x > Scene3D.CELL + 0.01 or a.size.z > Scene3D.CELL + 0.01:
			over.append("%s (%.2f x %.2f)" % [id, a.size.x, a.size.z])
	_check(over.is_empty(), "keine Figur breiter als eine Zelle (%s)" % str(over))
	_done.append("_test_fits_the_cell")


# Die Groesse IST die Stufenanzeige (in 2D uebernimmt das die Punktreihe am
# Sockel). Innerhalb einer Fraktion muss sie deshalb monoton wachsen.
#
# GEMESSEN WIRD DIE RAUMDIAGONALE, nicht die Hoehe. Der erste Anlauf hat
# die Hoehe genommen, und die Suite war zurecht rot: ein Vierbeiner ist
# lang statt hoch, ein Baum breit statt hoch - der Greif (Stufe 3) war
# niedriger als der Armbruster (Stufe 2), ohne kleiner zu sein. Der
# Generator passt jede Figur auf eine Diagonale je Stufe ein (TIER_SPAN);
# das hier ist die Gegenprobe dazu.
func _test_size_tells_the_tier() -> void:
	print("== Groesse waechst mit der Stufe ==")
	var by_fac: Dictionary = {}
	for u in _units:
		var ud: Dictionary = u as Dictionary
		var id: String = String(ud["id"])
		if not _f._meshes.has(id):
			continue
		var fac: String = String(ud["faction"])
		if not by_fac.has(fac):
			by_fac[fac] = []
		(by_fac[fac] as Array).append({
			"tier": int(ud["tier"]), "id": id,
			"h": (_f._meshes[id] as Mesh).get_aabb().size.length(),
		})
	for fac in by_fac.keys():
		var arr: Array = by_fac[fac]
		arr.sort_custom(func(a, b): return int(a["tier"]) < int(b["tier"]))
		var bad: Array = []
		for i in range(1, arr.size()):
			if float(arr[i]["h"]) <= float(arr[i - 1]["h"]) + 0.01:
				bad.append("%s (%.2f) nicht groesser als %s (%.2f)"
					% [arr[i]["id"], arr[i]["h"], arr[i - 1]["id"], arr[i - 1]["h"]])
		_check(bad.is_empty(), "%s: Stufe 1..7 wird durchgehend groesser (%s)"
			% [String(fac), str(bad)])
	_done.append("_test_size_tells_the_tier")


func _test_instance_colors_enabled() -> void:
	print("== Materialien nehmen die Instanzfarbe an ==")
	var off: Array = []
	for name in _f._meshes.keys():
		var m: Mesh = _f._meshes[String(name)] as Mesh
		for i in range(m.get_surface_count()):
			var mat := m.surface_get_material(i) as StandardMaterial3D
			if mat == null or not mat.vertex_color_use_as_albedo:
				off.append("%s[%d]" % [String(name), i])
	_check(off.is_empty(), "alle Materialien mit Instanzfarbe (aus: %s)" % str(off))
	_done.append("_test_instance_colors_enabled")


func _test_field_places_everything() -> void:
	print("== Das Kampffeld stellt auf, was der Kontext nennt ==")
	var stacks: Array = [
		{"pos": Vector2i(1, 2), "type": "men_spearman", "side": 0, "active": true},
		{"pos": Vector2i(1, 5), "type": "men_archer", "side": 0},
		{"pos": Vector2i(6, 2), "type": "ork_goblin", "side": 1},
	]
	_f.refresh({"cols": 8, "rows": 8, "terrain": 0, "seed": 3,
		"stacks": stacks, "obstacles": [{"pos": Vector2i(4, 4), "kind": "rock"}],
		"move": [Vector2i(2, 2), Vector2i(3, 2)], "targets": [Vector2i(6, 2)]})
	_check(_count("t_grass") == 64, "64 Bodenzellen (%d)" % _count("t_grass"))
	for s in stacks:
		var t: String = String((s as Dictionary)["type"])
		_check(_count(t) == 1, "%s steht einmal (%d)" % [t, _count(t)])
	_check(_count("deco_rock") == 1, "ein Hindernis (%d)" % _count("deco_rock"))
	# Ringe: drei Seiten-/Aktivringe plus zwei Laufziele plus ein Angriffsziel.
	_check(_count("marker_ring") == 6, "sechs Ringe (%d)" % _count("marker_ring"))

	# Zweiter Durchlauf ohne Einheiten: nichts darf stehenbleiben.
	_f.refresh({"cols": 8, "rows": 8, "terrain": 0, "seed": 3,
		"stacks": [], "obstacles": [], "move": [], "targets": []})
	var left: Array = []
	for s in stacks:
		var t2: String = String((s as Dictionary)["type"])
		if _count(t2) != 0:
			left.append(t2)
	_check(left.is_empty(), "gefallene Stapel verschwinden (%s)" % str(left))
	_check(_count("marker_ring") == 0, "und ihre Ringe mit ihnen (%d)"
		% _count("marker_ring"))
	_done.append("_test_field_places_everything")


func _count(model: String) -> int:
	var mmi = _f._multi.get(model)
	return 0 if mmi == null else (mmi as MultiMeshInstance3D).multimesh.instance_count
