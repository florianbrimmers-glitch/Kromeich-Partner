extends SceneTree

# Headless-Tests fuer die raeumliche Stadt (It. 56):
#
#   godot --headless --path game/ --script tools/test_city3d.gd
#
# WIE DIE STADT AUSSIEHT, entscheidet nur ein Bild - dafuer gibt es
# tools/preview_city3d.gd. Diese Suite haelt fest, was schiefgehen kann,
# ohne dass ein Bild es verraet:
#
#  * Ein fehlendes Gebaeudemodell faellt stumm auf das Geruest zurueck -
#    die Stadt saehe dann nur "noch nicht gebaut" aus.
#  * Ein Bauplatz ohne Rezept fehlt einfach.
#  * Der Tipp muss denselben Bauplatz treffen, an dem die Ansicht das
#    Gebaeude zeichnet.
#  * Ungebaut zeigt das GERUEST, nicht nichts.

const City3D := preload("res://scripts/ui/CityView3D.gd")
const CityScreen := preload("res://scripts/ui/CityScreen.gd")

const DEVICE_W := 1080
const DEVICE_H := 1920

const FAC_DIRS := ["waldvolk", "menschen", "totenreich", "orks"]

var _fails: int = 0
var _done: Array = []
var _v = null


func _init() -> void:
	_v = City3D.new()
	root.add_child(_v)
	await process_frame

	await _test_every_plot_has_a_model()
	await _test_unbuilt_shows_scaffold()
	await _test_screen_integration()

	var missing: Array = []
	for m in get_method_list():
		var mn: String = String(m["name"])
		if mn.begins_with("_test") and not _done.has(mn):
			missing.append(mn)
	_check(missing.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)" % str(missing))

	print("")
	if _fails == 0:
		print("Stadt-3D-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Stadt-3D-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _layout_ids() -> Array:
	var f := FileAccess.open("res://data/city_layout.json", FileAccess.READ)
	var d: Dictionary = JSON.parse_string(f.get_as_text()) as Dictionary
	return (d["buildings"] as Dictionary).keys()


# Neun Bauplaetze mal vier Fraktionen. Fehlt eines, faellt die Ansicht auf
# das Geruest zurueck - eine fertige Stadt saehe dann teilweise unfertig
# aus, und niemand wuerde nach einem fehlenden Modell suchen.
func _test_every_plot_has_a_model() -> void:
	print("== Jeder Bauplatz hat ein Modell, in jeder Fraktion ==")
	var ids: Array = _layout_ids()
	var missing: Array = []
	for fac in FAC_DIRS:
		for bid in ids:
			var n: String = "b_%s_%s" % [String(fac), String(bid)]
			if not _v._meshes.has(n):
				missing.append(n)
	_check(missing.is_empty(), "%d Modelle (%d Plaetze x %d Fraktionen), keines fehlt (%s)"
		% [ids.size() * FAC_DIRS.size(), ids.size(), FAC_DIRS.size(), str(missing)])
	for n in ["city_ground", "city_road", "city_plaza", "city_cobble",
			City3D.SCAFFOLD]:
		_check(_v._meshes.has(n), "Hofteil %s vorhanden" % n)
	# Das Gerumpel im Hof (It. 63). Fehlt eines dieser Modelle, faellt es
	# stumm aus, und der Hof waere wieder die leere Flaeche, die er bis
	# dahin war.
	var no_prop: Array = []
	for entry in City3D.PROPS:
		var m: String = String((entry as Dictionary)["model"])
		if not _v._meshes.has(m):
			no_prop.append(m)
	_check(no_prop.is_empty(), "jedes Hof-Requisit hat ein Modell (%s)"
		% str(no_prop))
	_done.append("_test_every_plot_has_a_model")


func _test_unbuilt_shows_scaffold() -> void:
	print("== Ungebaut zeigt das Geruest ==")
	var ids: Array = _layout_ids()
	var bs: Array = []
	for i in range(ids.size()):
		bs.append({"id": String(ids[i]), "x": 0.3 + 0.4 * float(i % 2),
			"y": 0.1 + 0.1 * float(i), "built": i < 3})
	_v.refresh({"faction": "menschen", "buildings": bs, "plaza": {}})
	_check(_count(City3D.SCAFFOLD) == ids.size() - 3,
		"%d Geruestee fuer %d ungebaute Plaetze"
			% [_count(City3D.SCAFFOLD), ids.size() - 3])
	var built := 0
	for i in range(3):
		built += _count("b_menschen_%s" % String(ids[i]))
	_check(built == 3, "drei gebaute Gebaeude stehen (%d)" % built)

	# Alles gebaut: kein Geruest mehr, und keins bleibt als Rest stehen.
	for b in bs:
		(b as Dictionary)["built"] = true
	_v.refresh({"faction": "orks", "buildings": bs, "plaza": {}})
	_check(_count(City3D.SCAFFOLD) == 0,
		"nach dem Ausbau kein Geruest mehr (%d)" % _count(City3D.SCAFFOLD))
	_check(_count("b_menschen_%s" % String(ids[0])) == 0,
		"und kein Gebaeude der alten Fraktion (%d)"
			% _count("b_menschen_%s" % String(ids[0])))
	_done.append("_test_unbuilt_shows_scaffold")


# Der Tipp muss den Bauplatz treffen, an dem die Ansicht zeichnet - am
# ECHTEN Schirm, nicht an einer nachgebauten Rechnung.
func _test_screen_integration() -> void:
	print("== Einbettung in den Stadtschirm ==")
	var cs = CityScreen.new()
	root.add_child(cs)
	await process_frame
	cs.set_anchors_preset(Control.PRESET_TOP_LEFT)
	cs.size = Vector2(DEVICE_W, DEVICE_H)
	await process_frame
	var ids: Array = _layout_ids()
	var defs: Array = []
	for bid in ids:
		defs.append({"id": String(bid), "name": String(bid).capitalize(),
			"cost": {"gold": 100}, "effect": "x"})
	cs.open({
		"city": {"faction": 1, "buildings": [String(ids[0]), String(ids[1])],
			"garrison": []},
		"buildings": defs,
		"faction_names": ["Waldvolk", "Menschen", "Totenreich", "Orks"],
		"faction_colors": [Color.GREEN, Color.YELLOW, Color.PURPLE, Color.RED],
		"wallet": Wallet.new(), "own_city": true,
	})
	await process_frame

	_check(not bool(cs.get("_city3d_on")), "startet in der 2D-Ansicht")
	cs.call("_toggle_view3d")
	await process_frame
	await process_frame
	_check(bool(cs.get("_city3d_on")), "Umschalter aktiviert die 3D-Ansicht")
	var v = cs.get("_city3d")
	_check(v != null and v.is_built(), "der Hof ist aufgebaut")

	# Hin und zurueck: vom Bauplatz auf den Bildpunkt und wieder auf den
	# Bauplatz. Getroffen werden muss derselbe.
	var got: Array = []
	var want: Array = []
	cs.get("_plots").sort_custom(func(a, b): return String(a["id"]) < String(b["id"]))
	for p in (cs.get("_plots") as Array):
		want.append(String(p["id"]))
		var w3: Vector3 = v.plot_pos(float(p["lx"]), float(p["ly"]))
		var sp: Vector2 = (cs.call("_stage_rect") as Rect2).position \
			+ v.project_point(w3)
		var hit: Vector3 = v.ground_at(sp - (cs.call("_stage_rect") as Rect2).position)
		var best: String = ""
		var best_d: float = 99.0
		for q in (cs.get("_plots") as Array):
			var qw: Vector3 = v.plot_pos(float(q["lx"]), float(q["ly"]))
			var d: float = Vector2(hit.x - qw.x, hit.z - qw.z).length()
			if d < best_d:
				best_d = d
				best = String(q["id"])
		got.append(best)
	_check(got == want, "jeder Bauplatz trifft sich selbst (%s vs %s)"
		% [str(got), str(want)])

	cs.call("_toggle_view3d")
	await process_frame
	_check(not bool(cs.get("_city3d_on")), "Umschalter fuehrt zurueck nach 2D")
	cs.queue_free()
	await process_frame
	_done.append("_test_screen_integration")


func _count(model: String) -> int:
	var mmi = _v._multi.get(model)
	return 0 if mmi == null else (mmi as MultiMeshInstance3D).multimesh.instance_count
