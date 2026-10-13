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
#  * Begehbares muss flach sein, sonst trifft der Tipp (Strahl auf y = 0)
#    das falsche Feld. Seit It. 77 gibt es EINE Hoehenfunktion fuer das
#    ganze Gelaende; geprueft wird sie selbst.
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
	await _test_walkable_is_flat()
	await _test_footprints_fit_tile()
	await _test_instance_colors_enabled()
	await _test_fog_hides_tiles()
	await _test_tile_at_roundtrip()
	await _test_screen_integration()
	await _test_guard_labels()
	await _test_views_do_not_share_a_world()

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


# Jeder Name, den die Ansicht anfordert, muss geladen sein. Ein fehlendes
# Modell faellt sonst stumm aus (_fill kehrt einfach um).
func _test_models_present() -> void:
	print("== Alle angeforderten Modelle sind geladen ==")
	var want: Array = []
	for v in WMS.MAP3D_OBJECT_MODEL.values():
		want.append(String(v))
	for f in UnitArt.FACTION_DIRS:
		want.append(Map3D.CITY_MODEL % String(f))
	want.append_array([Map3D.HERO_MODEL, Map3D.RING_MODEL, Map3D.DISC_MODEL])
	# Jede Kreatur kann als Monster auf der Karte stehen.
	var f := FileAccess.open("res://data/units.json", FileAccess.READ)
	var units: Array = (JSON.parse_string(f.get_as_text()) as Dictionary)["units"]
	for u in units:
		want.append(String((u as Dictionary)["id"]))
	var missing: Array = []
	for n in want:
		if not _view._meshes.has(String(n)):
			missing.append(String(n))
	_check(missing.is_empty(),
		"%d Modelle angefordert, keines fehlt (fehlend: %s)" % [want.size(), str(missing)])
	# Jede Ausstattungsart findet mindestens ein Modell (sonst fehlt der
	# Wald, und niemand wuerde nach einem Praefix suchen).
	var empty: Array = []
	for t in Map3D.SCATTER.keys():
		for e in (Map3D.SCATTER[t] as Array):
			var pre: String = String((e as Array)[0])
			var found := false
			for k in _view._meshes.keys():
				if String(k).begins_with(pre):
					found = true
					break
			if not found:
				empty.append(pre)
	_check(empty.is_empty(), "jede Ausstattungsart hat Modelle (leer: %s)" % str(empty))
	# Die Kartenobjekte kommen aus mapobj.glb, nicht mehr aus den alten
	# Klotz-Modellen in world.glb: das neue Windrad hat Fluegel.
	var mill: Mesh = _view._meshes.get("obj_windmill")
	_check(mill != null and mill.get_aabb().size.x > 0.5,
		"Kartenobjekte im neuen Stil geladen (Windmuehle %.2f breit)"
			% (mill.get_aabb().size.x if mill != null else 0.0))
	_done.append("_test_models_present")


# DER TIPP TRIFFT, WEIL ALLES BEGEHBARE FLACH IST. Scene3D.cell_at schneidet
# den Strahl mit y = 0; auf einem Huegel laege der Tipp eine Reihe daneben
# (h / tan(34 Grad), It. 53). Hoch und tief duerfen nur Berg und Wasser
# sein - beide unpassierbar. Diese Regel steht hier als Eigenschaft der
# EINEN Hoehenfunktion, die auch das Netz baut.
func _test_walkable_is_flat() -> void:
	print("== Begehbares Gelaende ist flach, Berg hoch, Wasser tief ==")
	var w := 12
	var h := 12
	var tiles: Array = []
	for y in range(h):
		for x in range(w):
			# Bloecke je Gelaendeart, damit auch Uebergaenge vorkommen.
			tiles.append(((x / 4) + (y / 4) * 3) % 6)
	var fog: Array = []
	for i in range(w * h):
		fog.append(2)
	_view.refresh(_ctx(tiles, w, h, fog))
	var bad: Array = []
	var peak := 0.0
	var deep := 0.0
	for y in range(h):
		for x in range(w):
			var t: int = int(tiles[y * w + x])
			var gy: float = _view.ground_height(float(x), float(y))
			if t == Map3D.T_MOUNTAIN:
				peak = maxf(peak, gy)
			elif t == Map3D.T_WATER:
				deep = minf(deep, gy)
			elif absf(gy) > Map3D.WALK_MAX:
				bad.append("%s %s %.3f" % [Map3D.TERRAIN_NAMES[t], str(Vector2i(x, y)), gy])
	_check(bad.is_empty(), "jede begehbare Kachelmitte innerhalb +-%.2f (%s)"
		% [Map3D.WALK_MAX, str(bad.slice(0, 5))])
	_check(peak > 0.3, "Gebirge ragt auf (hoechste Kachelmitte %.2f)" % peak)
	_check(deep < Map3D.WATER_LEVEL, "Wasser liegt unter dem Spiegel (%.2f)" % deep)
	_check(_view.land_node() != null and _view.water_node() != null,
		"Gelaende und Wasser sind gebaut")
	_done.append("_test_walkable_is_flat")


# Was auf einer Kachel steht, bleibt auf ihr - im AUFGESTELLTEN Massstab.
func _test_footprints_fit_tile() -> void:
	print("== Dinge auf der Karte bleiben auf ihrer Kachel ==")
	var over: Array = []
	var check := func(model: String, size: float, limit: float) -> void:
		if not _view._meshes.has(model):
			return
		var a: AABB = (_view._meshes[model] as Mesh).get_aabb()
		var sc: float = _view.model_scale(model, size)
		var wmax: float = maxf(a.size.x, a.size.z) * sc
		if wmax > limit + 0.01:
			over.append("%s (%.2f)" % [model, wmax])
	for v in WMS.MAP3D_OBJECT_MODEL.values():
		check.call(String(v), 0.0, Map3D.TILE)
	for f in UnitArt.FACTION_DIRS:
		# Die Stadt darf etwas ueberstehen - eine Burg, die in ihr Feld
		# passt, ist ein Haus.
		check.call(Map3D.CITY_MODEL % String(f), -Map3D.CITY_SIZE, Map3D.CITY_SIZE)
	check.call(Map3D.HERO_MODEL, Map3D.FIGURE_SIZE, Map3D.TILE)
	var fl := FileAccess.open("res://data/units.json", FileAccess.READ)
	for u in ((JSON.parse_string(fl.get_as_text()) as Dictionary)["units"] as Array):
		check.call(String((u as Dictionary)["id"]), Map3D.FIGURE_SIZE, Map3D.TILE)
	_check(over.is_empty(), "kein Ding breiter als erlaubt (zu breit: %s)" % str(over))
	_done.append("_test_footprints_fit_tile")


# Ohne diesen Schalter kommt KEINE Instanzfarbe an (It. 53) - und damit
# kein Abdunkeln im Nebel und keine Besitzer- oder Bedrohungsfarbe.
func _test_instance_colors_enabled() -> void:
	print("== Materialien nehmen die Instanzfarbe an ==")
	var off: Array = []
	for name in _view._meshes.keys():
		var m: Mesh = _view._meshes[String(name)] as Mesh
		for i in range(m.get_surface_count()):
			var mat := m.surface_get_material(i) as StandardMaterial3D
			if mat == null or not mat.vertex_color_use_as_albedo:
				off.append("%s[%d]" % [String(name), i])
	_check(off.is_empty(), "alle Materialien mit Instanzfarbe (aus: %s)" % str(off.slice(0, 5)))
	_done.append("_test_instance_colors_enabled")


# NEBEL: die Nebeltextur traegt je Kachel ihre Stufe, und auf unerforschten
# Kacheln steht keine Ausstattung (sie verriete Wald oder Gebirge).
func _test_fog_hides_tiles() -> void:
	print("== Nebel: Schleier und keine Ausstattung im Unerforschten ==")
	var w := 8
	var h := 6
	var tiles: Array = []
	var fog: Array = []
	for y in range(h):
		for x in range(w):
			tiles.append(Map3D.T_FOREST)
			fog.append(2 if x < w / 2 else 0)
	_view.refresh(_ctx(tiles, w, h, fog))
	var img: Image = _view.fog_image()
	_check(img != null and img.get_width() == w and img.get_height() == h,
		"Nebeltextur hat eine Zelle je Kachel")
	var wrong: Array = []
	for y in range(h):
		for x in range(w):
			var v: float = img.get_pixel(x, y).r
			var want: float = Map3D.VIS_REACH if x < w / 2 else Map3D.VIS_HIDDEN
			if absf(v - want) > 0.02:
				wrong.append(Vector2i(x, y))
	_check(wrong.is_empty(), "Nebelstufe je Kachel stimmt (falsch: %s)" % str(wrong.slice(0, 5)))
	var expect := 0
	for y in range(h):
		for x in range(w / 2):
			expect += (_view._scatter.get(y * w + x, []) as Array).size()
	var shown := _scatter_instances()
	_check(expect > 0 and shown == expect,
		"Wald nur im Erforschten: %d Teile aufgestellt, erwartet %d" % [shown, expect])
	for i in range(fog.size()):
		fog[i] = 2
	_view.refresh(_ctx(tiles, w, h, fog))
	_check(_scatter_instances() == _view.scatter_count(),
		"ohne Nebel steht die ganze Ausstattung (%d von %d)"
			% [_scatter_instances(), _view.scatter_count()])
	_done.append("_test_fog_hides_tiles")


func _scatter_instances() -> int:
	var pres: Array = []
	for t in Map3D.SCATTER.keys():
		for e in (Map3D.SCATTER[t] as Array):
			pres.append(String((e as Array)[0]))
	var n := 0
	for name in _view._multi.keys():
		for pre in pres:
			if String(name).begins_with(String(pre)):
				n += (_view._multi[name] as MultiMeshInstance3D).multimesh.instance_count
				break
	return n


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


# Der Umschalter, die Kamera und der Tap AM ECHTEN SCHIRM. Ohne diesen
# Test wuerde die Suite nur die Ansicht fuer sich pruefen - genau der
# Fehler, den die Vorschau-Werkzeuge in It. 36/37 gemacht haben.
func _test_screen_integration() -> void:
	print("== Einbettung in den Weltkarten-Schirm ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 4711, 1)
	await process_frame

	_check(not bool(wm.get("_map3d_on")), "startet in der 2D-Ansicht")
	_check(wm.get("_map3d") == null, "die 3D-Ansicht wird erst beim Einschalten gebaut")

	wm.call("_toggle_view3d")
	await process_frame
	await process_frame
	_check(bool(wm.get("_map3d_on")), "Umschalter aktiviert die 3D-Ansicht")
	_check(wm.get("_map3d") != null, "die 3D-Ansicht existiert nach dem Einschalten")
	var btn := wm.get_node_or_null(wm.get("view3d_toggle_path")) as Button
	_check(btn != null and btn.text == "2D",
		"der Knopf bietet jetzt den Rueckweg an (%s)"
			% ("fehlt" if btn == null else btn.text))

	# DER AUSSCHNITT MUSS DERSELBE SEIN. Springt das Bild beim Umschalten,
	# ist die Umrechnung aus _view_offset/_tile_size falsch - und weil
	# beide Ansichten dieselbe Karte zeigen, faellt genau das im Bild am
	# schwersten auf.
	var area: Control = wm.get("_map_area")
	var view = wm.get("_map3d")
	var ts: float = float(wm.get("_tile_size"))
	var off: Vector2 = wm.get("_view_offset")
	var mid: Vector2 = area.size * 0.5
	var mid2d := Vector2i(int(floor((mid.x - off.x) / ts)),
		int(floor((mid.y - off.y) / ts)))
	var mid3d: Vector2i = view.tile_at(mid, area.size)
	_check(mid2d == mid3d,
		"Bildmitte zeigt in beiden Ansichten dasselbe Feld (2D %s, 3D %s)"
			% [str(mid2d), str(mid3d)])

	# Der Tap laeuft ueber _tile_at_pixel und muss in 3D denselben Weg
	# nehmen wie die Kamera - hin und zurueck ueber die echte Funktion.
	var bad: Array = []
	for d in [Vector2(0, 0), Vector2(120, 90), Vector2(-140, 60),
			Vector2(200, -110), Vector2(-90, -140)]:
		var p: Vector2 = mid + d
		var cell: Vector2i = view.tile_at(p, area.size)
		if cell.x < 0 or cell.x >= 18 or cell.y < 0 or cell.y >= 26:
			continue
		var got: Vector2i = wm.call("_tile_at_pixel", p)
		if got != cell:
			bad.append("%s: Kamera %s, Tap %s" % [str(p), str(cell), str(got)])
	_check(bad.is_empty(), "_tile_at_pixel folgt in 3D der Kamera (%s)" % str(bad))

	# Und zurueck: die 2D-Karte muss wieder zeichnen.
	wm.call("_toggle_view3d")
	await process_frame
	_check(not bool(wm.get("_map3d_on")), "Umschalter fuehrt zurueck nach 2D")
	var back: Vector2i = wm.call("_tile_at_pixel", mid)
	_check(back == mid2d, "nach dem Zurueckschalten wieder die Pixel-Rechnung (%s)"
		% str(back))

	wm.queue_free()
	await process_frame
	_done.append("_test_screen_integration")


# Die Wachzahlen an Staedten, Monstern und Objekten standen bis It. 56
# DREIMAL fast gleich im Zeichencode, und die raeumliche Ansicht haette
# eine vierte Kopie gebraucht. Jetzt liefert `_guard_labels()` sie einmal;
# dieser Test haelt die REGELN fest, nach denen sie entstehen - sonst
# faellt beim naechsten Umbau nur auf, dass irgendwo eine Zahl fehlt.
func _test_guard_labels() -> void:
	print("== Wachzahlen: eine Quelle, klare Regeln ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 4711, 1)
	await process_frame

	var labels: Dictionary = wm.call("_guard_labels")
	var fog: Array = wm.get("_fog_player")
	var w: int = int(wm.get("MAP_WIDTH"))
	# NACHFRAGEN, OB DIE BREITE ANKAM: `get()` auf eine Konstante liefert
	# in manchen Godot-Fassungen null, und daraus wuerde still 0 - dann
	# zeigte `fog[y * 0 + x]` auf lauter gueltige, aber falsche Felder, und
	# die drei Pruefungen darunter waeren gruen, ohne etwas zu pruefen.
	_check(w == 18, "MAP_WIDTH ist lesbar und plausibel (%d)" % w)

	# Ein Monster auf einer nicht mehr verborgenen Kachel MUSS eine Zahl
	# haben - im Nebel steht sie als "?" da, aber sie fehlt nie.
	var missing: Array = []
	for m in (wm.get("_monsters") as Array):
		var mp: Vector2i = (m as Dictionary)["pos"]
		var f: int = int(fog[mp.y * w + mp.x])
		if f != 0 and not labels.has(mp):
			missing.append(str(mp))
	_check(missing.is_empty(), "jedes sichtbare Monster traegt eine Zahl (%s)"
		% str(missing))

	# Die eigene Stadt zeigt keine Wachzahl - sie ist keine Bedrohung.
	var own: Array = []
	for c in (wm.get("_cities") as Array):
		var cd: Dictionary = c as Dictionary
		if int(cd.get("owner", -1)) == int(wm.get("OWNER_HERO")) \
				and labels.has(Vector2i(cd["pos"])):
			own.append(str(cd["pos"]))
	_check(own.is_empty(), "eigene Staedte tragen keine Wachzahl (%s)" % str(own))

	# Nichts auf einer VERBORGENEN Kachel.
	var leaked: Array = []
	for cell in labels.keys():
		var cv: Vector2i = cell
		if int(fog[cv.y * w + cv.x]) == 0:
			leaked.append(str(cv))
	_check(leaked.is_empty(), "keine Zahl auf unerforschtem Feld (%s)" % str(leaked))

	# Jede Zahl ist entweder eine Ziffernfolge oder das Fragezeichen -
	# nichts dazwischen, und nie leer.
	var bad: Array = []
	for cell in labels.keys():
		var t: String = String((labels[cell] as Dictionary)["text"])
		if t != "?" and not t.is_valid_int():
			bad.append(t)
	_check(bad.is_empty(), "jede Zahl ist Ziffer oder \"?\" (%s)" % str(bad))
	_check(not labels.is_empty(),
		"Seed 4711 zeigt in Zug 1 ueberhaupt Wachzahlen (%d)" % labels.size())

	wm.queue_free()
	await process_frame
	_done.append("_test_guard_labels")


# DREI ANSICHTEN, DREI WELTEN.
#
# Gefunden auf dem GERAET, nicht hier: auf den Bildschirmfotos des Nutzers
# lag unter dem Kampfbrett die Weltkarte, im Stadthof das Kartengelaende,
# und auf der Karte ein Stueck Stadt. Ursache: ein `SubViewport` bekommt
# NICHT von selbst eine eigene 3D-Welt - ohne `own_world_3d` teilen sich
# alle drei Ansichten die Welt des Hauptviewports. Jede Kamera sieht dann
# die Geometrie der anderen, und jede Ansicht bringt zwei eigene Lichter
# mit: bei drei offenen Schirmen brennen sechs Richtungslichter auf allem,
# was auch das flaue, zu helle Bild auf dem Geraet erklaert.
#
# WARUM ES KEIN WERKZEUG GESEHEN HAT: jede Vorschau baut genau EINEN
# Schirm. Im Spiel bleibt die Weltkarte bestehen, waehrend Stadt oder
# Kampf aufgehen. Ein Fehler ZWISCHEN zwei Schirmen ist fuer ein Werkzeug,
# das immer nur einen baut, unsichtbar. Dieser Test baut deshalb zwei.
func _test_views_do_not_share_a_world() -> void:
	print("== Jede raeumliche Ansicht hat ihre eigene Welt ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 4711, 1)
	await process_frame
	wm.call("_toggle_view3d")
	await process_frame
	await process_frame

	var cs = load("res://scripts/ui/CityScreen.gd").new()
	root.add_child(cs)
	await process_frame
	cs.open({
		"city": {"faction": 1, "buildings": ["markt"], "garrison": []},
		"buildings": [{"id": "markt", "name": "Markt", "cost": {"gold": 1},
			"effect": "x"}],
		"faction_names": ["Waldvolk", "Menschen", "Totenreich", "Orks"],
		"faction_colors": [Color.GREEN, Color.YELLOW, Color.PURPLE, Color.RED],
		"wallet": Wallet.new(), "own_city": true,
	})
	await process_frame
	cs.call("_toggle_view3d")
	await process_frame
	await process_frame

	var mv = wm.get("_map3d")
	var cv = cs.get("_city3d")
	_check(mv != null and cv != null, "beide Ansichten sind gebaut")
	if mv != null and cv != null:
		var mw: World3D = (mv as Node3D).get_world_3d()
		var cw: World3D = (cv as Node3D).get_world_3d()
		_check(mw != cw,
			"Karte und Stadt liegen NICHT in derselben 3D-Welt")
		# Und die URSACHE beim Namen nennen. Der erste Anlauf hat statt
		# dessen die Modellnamen beider Ansichten verglichen - das war
		# selbst falsch: Stadt und Karte benutzen ABSICHTLICH dieselben
		# Modelle (Gras, Steine, Blumen aus world.glb), der Test waere also
		# auch nach der Reparatur rot geblieben.
		var vps: Array = []
		for pair in [[mv, "Karte"], [cv, "Stadt"]]:
			var vp := (pair[0] as Node).get_viewport() as SubViewport
			if vp == null or not vp.own_world_3d:
				vps.append(String(pair[1]))
		_check(vps.is_empty(),
			"jeder SubViewport hat own_world_3d gesetzt (fehlt: %s)" % str(vps))

	cs.queue_free()
	wm.queue_free()
	await process_frame
	_done.append("_test_views_do_not_share_a_world")


func _ctx(tiles: Array, w: int, h: int, fog: Array) -> Dictionary:
	return {"tiles": tiles, "width": w, "height": h, "fog": fog, "seed": 1,
		"cities": [], "objects": [], "monsters": [], "heroes": [], "enemies": [],
		"faction_dirs": UnitArt.FACTION_DIRS, "object_model": {}}
