extends SceneTree

# Headless-Tests fuer die raeumliche Weltkarte (It. 53):
#
#   godot --headless --path game/ --script tools/test_world3d.gd
#
# WAS HIER GEPRUEFT WIRD, IST NICHT DAS AUSSEHEN. Wie ein Modell wirkt,
# entscheidet nur ein Bild; dafuer gibt es tools/preview_models3d.gd und
# tools/preview_world3d.gd. Diese Suite haelt die Stellen fest, an denen
# ZWEI WAHRHEITEN ueber dieselbe Sache entstehen koennen - und genau die
# haben in dieser Iteration jeder fuer sich einen Fehler erzeugt, den man
# auf der Karte nicht sah:
#
#  * TERRAIN_TOP in der Ansicht gegen die tatsaechliche Oberkante im glb.
#    Beide standen auf 1.10 fuer Gebirge, das Modell war aber flach - die
#    Zahl in GDScript stimmte, die Geometrie nicht.
#  * Modellnamen gegen den Inhalt des glb. Ein fehlendes Modell faellt
#    heute stumm aus (_fill kehrt einfach um).
#  * Grundflaeche gegen die Kachelbreite. Die Stadt mass 1.19 bei
#    Kachelbreite 1.0 und ragte ins Nachbarfeld.
#  * Instanzfarben gegen die Materialien. Standen sie aus, kam WEDER
#    Nebel NOCH Besitzerfarbe an - sichtbar war nur eine weisse Scheibe.

const Map3D := preload("res://scripts/ui/WorldMap3D.gd")
const WMS := preload("res://scripts/ui/WorldMapScreen.gd")
const UnitArt := preload("res://scripts/core/UnitArt.gd")

var _fails: int = 0
var _done: Array = []
var _view = null


func _init() -> void:
	_view = Map3D.new()
	root.add_child(_view)
	await process_frame

	await _test_models_present()
	await _test_terrain_tops_match()
	await _test_footprints_fit_tile()
	await _test_instance_colors_enabled()
	await _test_fog_hides_tiles()
	await _test_tile_at_roundtrip()

	var missing: Array = []
	for m in get_method_list():
		var mn: String = String(m["name"])
		if mn.begins_with("_test") and not _done.has(mn):
			missing.append(mn)
	_check(missing.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)" % str(missing))

	print("")
	if _fails == 0:
		print("Weltkarte-3D-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Weltkarte-3D-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


# Jeder Name, den die Ansicht anfordert, muss im glb liegen.
func _test_models_present() -> void:
	print("== Alle angeforderten Modelle liegen im glb ==")
	var want: Array = []
	want.append_array(Map3D.TERRAIN_MODEL)
	for v in Map3D.DECO_MODEL.values():
		want.append(String(v))
	for v in WMS.MAP3D_OBJECT_MODEL.values():
		want.append(String(v))
	for f in UnitArt.FACTION_DIRS:
		want.append("city_" + String(f))
	want.append_array(["hero", "monster", "marker_disc", "marker_ring"])
	var missing: Array = []
	for n in want:
		if not _view._meshes.has(String(n)):
			missing.append(String(n))
	_check(missing.is_empty(),
		"%d Modelle angefordert, keines fehlt (fehlend: %s)" % [want.size(), str(missing)])
	_done.append("_test_models_present")


# Die Zahl in der Ansicht und die Geometrie im glb muessen dasselbe sagen.
# Toleranz 0.02: die Fase rundet die Kante minimal ab.
func _test_terrain_tops_match() -> void:
	print("== TERRAIN_TOP passt zur Oberkante im Modell ==")
	for t in range(Map3D.TERRAIN_MODEL.size()):
		var name: String = Map3D.TERRAIN_MODEL[t]
		if not _view._meshes.has(name):
			continue
		var a: AABB = (_view._meshes[name] as Mesh).get_aabb()
		var top: float = a.position.y + a.size.y
		var want: float = float(Map3D.TERRAIN_TOP.get(t, 0.0))
		_check(absf(top - want) <= 0.02,
			"%s: Modell endet bei %+.3f, TERRAIN_TOP sagt %+.3f" % [name, top, want])
	_done.append("_test_terrain_tops_match")


# Was auf einer Kachel steht, darf nicht ueber sie hinausragen - sonst
# ist nicht mehr zu erkennen, auf welchem Feld es steht.
func _test_footprints_fit_tile() -> void:
	print("== Grundflaeche bleibt auf der Kachel ==")
	var over: Array = []
	for name in _view._meshes.keys():
		var a: AABB = (_view._meshes[String(name)] as Mesh).get_aabb()
		if a.size.x > Map3D.TILE + 0.01 or a.size.z > Map3D.TILE + 0.01:
			over.append("%s (%.2f x %.2f)" % [String(name), a.size.x, a.size.z])
	_check(over.is_empty(),
		"kein Modell breiter als eine Kachel (%.1f) - zu breit: %s"
			% [Map3D.TILE, str(over)])
	_done.append("_test_footprints_fit_tile")


# Ohne diesen Schalter kommt KEINE Instanzfarbe an. Das war in dieser
# Iteration der teuerste Fehler, weil er wie "funktioniert" aussah.
func _test_instance_colors_enabled() -> void:
	print("== Materialien nehmen die Instanzfarbe an ==")
	var off: Array = []
	for name in _view._meshes.keys():
		var m: Mesh = _view._meshes[String(name)] as Mesh
		for i in range(m.get_surface_count()):
			var mat := m.surface_get_material(i) as StandardMaterial3D
			if mat == null or not mat.vertex_color_use_as_albedo:
				off.append("%s[%d]" % [String(name), i])
	_check(off.is_empty(), "alle Materialien mit Instanzfarbe (aus: %s)" % str(off))
	_done.append("_test_instance_colors_enabled")


# Unerforschtes wird gar nicht gebaut - die Zahl der Aufstellungen muss
# der Zahl der sichtbaren Kacheln entsprechen.
func _test_fog_hides_tiles() -> void:
	print("== Nebel: unerforschte Kacheln werden nicht gebaut ==")
	var w := 8
	var h := 6
	var tiles: Array = []
	var fog: Array = []
	var seen := 0
	for y in range(h):
		for x in range(w):
			tiles.append(0)
			# Nur die linke Haelfte ist erforscht.
			var f: int = 2 if x < w / 2 else 0
			fog.append(f)
			if f > 0:
				seen += 1
	_view.refresh(_ctx(tiles, w, h, fog))
	_check(_terrain_instances() == seen,
		"%d von %d Kacheln gebaut" % [_terrain_instances(), w * h])

	# Alles sichtbar: dann sind es alle.
	for i in range(fog.size()):
		fog[i] = 2
	_view.refresh(_ctx(tiles, w, h, fog))
	_check(_terrain_instances() == w * h,
		"ohne Nebel alle %d Kacheln gebaut (%d)" % [w * h, _terrain_instances()])
	_done.append("_test_fog_hides_tiles")


# Der Tap muss dieselbe Kachel treffen, auf der die Kachel gezeichnet
# wird. Hin (unproject) und zurueck (tile_at) muessen sich aufheben.
func _test_tile_at_roundtrip() -> void:
	print("== Bildpunkt -> Kachel trifft die gezeichnete Kachel ==")
	var vp: Vector2 = Vector2(root.size)
	_view.look_at_map(Vector2(6.0, 6.0), 12.0)
	var bad: Array = []
	for y in range(3, 10):
		for x in range(3, 10):
			# Kachelmitte auf Hoehe 0 - dieselbe Ebene, die tile_at schneidet.
			var screen: Vector2 = _view._cam.unproject_position(
				Vector3(float(x) * Map3D.TILE, 0.0, float(y) * Map3D.TILE))
			var back: Vector2i = _view.tile_at(screen, vp)
			if back != Vector2i(x, y):
				bad.append("%s -> %s" % [str(Vector2i(x, y)), str(back)])
	_check(bad.is_empty(), "49 Kachelmitten treffen sich selbst (daneben: %s)"
		% str(bad))
	_done.append("_test_tile_at_roundtrip")


func _terrain_instances() -> int:
	var n := 0
	for name in _view._multi.keys():
		if String(name).begins_with("t_"):
			n += (_view._multi[name] as MultiMeshInstance3D).multimesh.instance_count
	return n


func _ctx(tiles: Array, w: int, h: int, fog: Array) -> Dictionary:
	return {"tiles": tiles, "width": w, "height": h, "fog": fog, "seed": 1,
		"cities": [], "objects": [], "monsters": [], "heroes": [], "enemies": [],
		"faction_dirs": UnitArt.FACTION_DIRS, "object_model": {}}
