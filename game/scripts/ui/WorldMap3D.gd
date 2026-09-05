extends Node3D

# Raeumliche Ansicht der Weltkarte (It. 53).
#
# ZWEITE ANSICHT, KEIN ERSATZ. Das Spiel ist fertig und gruen; die
# 2D-Karte bleibt, bis diese hier gleichauf ist. Beide lesen dasselbe
# Modell (`_map["tiles"]`, `_cities`, `_monsters`, `_objects`,
# `_fog_player`, `_costs`) - Wegfindung, Kampf, Balance und Spielstaende
# sind davon nicht beruehrt.
#
# KEINE LOGIK HIER. Wie beim CityScreen kommt alles ueber `refresh(ctx)`
# herein. Diese Datei weiss nicht, was ein Monster ist - nur, wo etwas
# steht und welches Modell es traegt.
#
# WARUM MULTIMESH: eine 18x26-Karte sind 468 Kacheln plus Deko und
# Objekte. Als einzelne MeshInstance3D-Knoten waeren das ueber 600 Knoten
# mit je einem Zeichenaufruf. Ein MultiMesh je Modell macht daraus einen
# Aufruf pro Modell - auf dem Handy mit gl_compatibility ist das der
# Unterschied zwischen fluessig und ruckelnd.

const MODELS_PATH := "res://assets/models/world.glb"

# Kachelbreite in Weltmetern. Der Generator baut mit TILE = 1.0, also ist
# eine Kachel eine Einheit - jede andere Zahl hier waere eine zweite
# Wahrheit ueber dieselbe Groesse.
const TILE := 1.0

# Feste Kameraneigung (gewaehlte Variante: schraeg von oben, nicht
# drehbar). Flacher als 30 Grad kippt die Karte optisch weg und Felder
# hinter Bergen verschwinden; steiler als 40 sieht wieder aus wie 2D.
const CAM_PITCH_DEG := -34.0
# Hoehe der Kamera ueber der Ebene, in Kacheln. Der Abstand nach hinten
# wird daraus GERECHNET (siehe look_at_map) - zwei freie Zahlen waeren
# zwei Wahrheiten ueber denselben Blickpunkt.
const CAM_UP := 11.0

# Nebel: unerforscht wird gar nicht gezeichnet, erkundet abgedunkelt.
# Dieselben Stufen wie in der 2D-Karte (FOG_HIDDEN/EXPLORED/VISIBLE).
const FOG_DIM := Color(0.42, 0.45, 0.52)
# Sichtbar, aber diesen Zug nicht erreichbar. Die 2D-Karte legt dafuer ein
# schwarzes Alpha von 0.30 ueber die Kachel; hier ist es ein Faktor auf die
# Instanzfarbe. Erreichbar bleibt VOLL hell - genau dieser Unterschied ist
# die Reichweiten-Anzeige, nicht der Ring.
const OUT_OF_REACH := Color(0.62, 0.64, 0.68)
# Der duenne Ring auf erreichbaren Feldern, wie das weisse 0.25-Rechteck
# der 2D-Karte. Er ist die ZWEITE Aussage; ohne ihn wuerde man die Grenze
# der Reichweite auf gleichfarbigem Gelaende nicht genau sehen.
# Alpha 0.15, nicht 0.30: bei 0.30 lagen bis zu dreissig helle Reifen auf
# der erkundeten Flaeche und uebertoenten das Gelaende darunter - man sah
# die Reichweite und sonst nichts mehr.
const REACH_RING := Color(1.0, 1.0, 1.0, 0.15)

# Deko-Dichte je Gelaendeart: nicht jede Waldkachel bekommt einen Baum,
# sonst wird die Flaeche zur Mauer und man sieht die Kachelgrenzen nicht
# mehr. Zahl ist "von sechs".
const DECO_CHANCE := {"forest": 5, "mountain": 4, "swamp": 3}
const DECO_MODEL := {"forest": "deco_tree", "mountain": "deco_rock",
	"swamp": "deco_reed"}

# Gelaendeart -> Modellname. Reihenfolge ist MapGen.TILE_*.
const TERRAIN_MODEL := ["t_grass", "t_forest", "t_water", "t_mountain",
	"t_sand", "t_swamp"]
# Unerforscht. Siehe make_fog() im Generator: eine Leerstelle sagt nicht
# "unbekannt", sie sagt gar nichts - und die Ausdehnung der Karte war ohne
# diese Platte nicht mehr abzulesen.
const FOG_MODEL := "t_fog"
# Oberkante je Gelaendeart, damit Deko und Figuren nicht in der Platte
# stecken. Muss zu TERRAIN in tools/gen_models.py passen.
const TERRAIN_TOP := {0: 0.0, 1: 0.10, 2: -0.22, 3: 0.40, 4: -0.02, 5: -0.08}

var _meshes: Dictionary = {}
var _multi: Dictionary = {}
var _cam: Camera3D = null
var _built: bool = false


func _ready() -> void:
	_load_models()
	_build_lighting()
	_build_camera()


func _load_models() -> void:
	var packed := load(MODELS_PATH) as PackedScene
	if packed == null:
		push_error("world.glb fehlt: " + MODELS_PATH)
		return
	var src := packed.instantiate()
	for ch in src.get_children():
		if ch is MeshInstance3D:
			var m: Mesh = (ch as MeshInstance3D).mesh
			_enable_instance_color(m)
			# Die Markierungen brauchen zusaetzlich Durchsichtigkeit: der
			# Reichweiten-Ring liegt bei Alpha 0.30 auf JEDEM erreichbaren
			# Feld, und bei voller Deckung waeren das bis zu dreissig
			# leuchtende Reifen - lauter als die Karte darunter.
			if String(ch.name).begins_with("marker_"):
				_enable_transparency(m)
			_meshes[String(ch.name)] = m
	src.queue_free()


# Die Farbe je Aufstellung wirkt NUR, wenn das Material sie auch benutzt.
#
# WIE DAS AUFFIEL: auf dem ersten Bild schien der Nebel zu funktionieren -
# am Rand lagen dunklere Kacheln. Das waren aber Wald und Gebirge, die von
# Haus aus dunkler sind. Erst eine Messung (vertex_color_use_as_albedo je
# Material ausgeben) zeigte, dass der Schalter ueberall aus stand und
# damit KEINE einzige Instanzfarbe ankam - Nebel nicht, Besitzerfarbe
# nicht, Bedrohungsfarbe nicht. Die weisse Scheibe, die eigentlich rot
# sein sollte, war das einzige sichtbare Symptom.
#
# glTF kennt den Schalter nicht, also wird er hier gesetzt. Godot faerbt
# dann albedo * Instanzfarbe - weiss laesst das Modell wie gebaut, alles
# andere toent es.
func _enable_instance_color(m: Mesh) -> void:
	if m == null:
		return
	for i in range(m.get_surface_count()):
		var mat := m.surface_get_material(i) as StandardMaterial3D
		if mat != null:
			mat.vertex_color_use_as_albedo = true


func _enable_transparency(m: Mesh) -> void:
	for i in range(m.get_surface_count()):
		var mat := m.surface_get_material(i) as StandardMaterial3D
		if mat != null:
			mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA


func _build_lighting() -> void:
	# Ein Hauptlicht fuer die Form, ein kaltes Gegenlicht, damit die
	# Schattenseiten nicht absaufen. Keine Schattenkarten: auf dem Handy
	# mit gl_compatibility kosten sie mehr, als sie hier zeigen.
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-48, -125, 0)
	key.light_energy = 1.15
	add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-25, 60, 0)
	fill.light_energy = 0.35
	fill.light_color = Color(0.75, 0.85, 1.0)
	add_child(fill)

	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.07, 0.09, 0.12)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.55, 0.62, 0.75)
	env.ambient_light_energy = 0.45
	we.environment = env
	add_child(we)


func _build_camera() -> void:
	_cam = Camera3D.new()
	# ORTHOGONAL, nicht perspektivisch: eine Kachel ist dann ueberall
	# gleich gross. Mit Perspektive waeren Felder am oberen Rand kleiner,
	# und die Reichweiten-Anzeige haette dort weniger Trefferflaeche.
	_cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	# `size` soll die BREITE in Kacheln sein. Godot legt sie sonst auf die
	# Hoehe, und auf einem 720x1280-Schirm hiesse "15" dann 8.4 Kacheln
	# quer - der Name der Zahl haette das Gegenteil ihrer Wirkung gesagt.
	# Die 2D-Karte rechnet ebenfalls in Kacheln pro Breite.
	_cam.keep_aspect = Camera3D.KEEP_WIDTH
	_cam.rotation_degrees = Vector3(CAM_PITCH_DEG, 0, 0)
	add_child(_cam)
	_cam.make_current()


# Ein MultiMesh je Modell, gefuellt aus einer Liste von Aufstellungen.
# `items` ist ein Array aus { "pos": Vector3, "rot": float, "color": Color }.
func _fill(model: String, items: Array) -> void:
	if not _meshes.has(model):
		return
	var mmi: MultiMeshInstance3D = _multi.get(model)
	if mmi == null:
		mmi = MultiMeshInstance3D.new()
		mmi.multimesh = MultiMesh.new()
		mmi.multimesh.transform_format = MultiMesh.TRANSFORM_3D
		# Farbe je Aufstellung: so faerbt der Nebel eine einzelne Kachel
		# ab, ohne dass es ein zweites Modell braucht.
		mmi.multimesh.use_colors = true
		mmi.multimesh.mesh = _meshes[model]
		add_child(mmi)
		_multi[model] = mmi
	var mm: MultiMesh = mmi.multimesh
	mm.instance_count = items.size()
	for i in range(items.size()):
		var it: Dictionary = items[i]
		var t := Transform3D(Basis(Vector3.UP, float(it.get("rot", 0.0))),
			it["pos"] as Vector3)
		mm.set_instance_transform(i, t)
		mm.set_instance_color(i, it.get("color", Color.WHITE))


# Deterministische Streuung - dieselbe Begruendung wie bei _tile_variant in
# der 2D-Karte: waechselte die Deko bei jedem Neuzeichnen ihren Platz,
# waere die Karte unruhig und nicht wiedererkennbar.
func _hash(x: int, y: int, salt: int) -> int:
	var h: int = (x * 73856093) ^ (y * 19349663) ^ (salt * 83492791)
	h = (h ^ (h >> 13)) * 1274126177
	return absi(h ^ (h >> 16))


# --- Die eine Schnittstelle nach aussen -----------------------------------

# ctx:
#   tiles       Array[int]        Gelaendearten, MAP_WIDTH * MAP_HEIGHT
#   width/height int
#   fog         Array[int]        FOG_HIDDEN / EXPLORED / VISIBLE
#   seed        int
#   cities      Array[{pos, faction, owner}]
#   monsters    Array[{pos}]
#   objects     Array[{pos, kind}]
#   heroes      Array[{pos, active}]
#   enemies     Array[{pos}]
#   object_model Dictionary       kind -> Modellname
#   reach       Array[Vector2i]   Felder in Zugreichweite; LEER heisst
#                                 "keine Angabe" und dunkelt nichts ab -
#                                 die Vorschauwerkzeuge liefern sie nicht
func refresh(ctx: Dictionary) -> void:
	if _meshes.is_empty():
		return
	var w: int = int(ctx.get("width", 0))
	var h: int = int(ctx.get("height", 0))
	var tiles: Array = ctx.get("tiles", []) as Array
	var fog: Array = ctx.get("fog", []) as Array
	var sd: int = int(ctx.get("seed", 0))
	if w <= 0 or h <= 0 or tiles.size() < w * h:
		return

	var reach: Dictionary = {}
	for r in (ctx.get("reach", []) as Array):
		reach[r] = true
	var has_reach: bool = not reach.is_empty()

	var by_terrain: Dictionary = {}
	var by_deco: Dictionary = {}
	var rings: Array = []
	for name in TERRAIN_MODEL:
		by_terrain[name] = []
	by_terrain[FOG_MODEL] = []
	for name in DECO_MODEL.values():
		by_deco[name] = []

	for y in range(h):
		for x in range(w):
			var i: int = y * w + x
			var f: int = int(fog[i]) if i < fog.size() else 2
			# Unerforscht bekommt eine neutrale Platte: sie verraet die
			# Gelaendeart nicht, zeigt aber, dass dort ueberhaupt Karte
			# ist. Der erste Entwurf hat hier gar nichts gebaut - siehe
			# make_fog() im Generator.
			if f == 0:
				(by_terrain[FOG_MODEL] as Array).append({
					"pos": Vector3(float(x) * TILE, 0.0, float(y) * TILE),
					"color": Color.WHITE,
				})
				continue
			var t: int = int(tiles[i])
			if t < 0 or t >= TERRAIN_MODEL.size():
				continue
			var cell := Vector2i(x, y)
			var in_reach: bool = has_reach and reach.has(cell)
			# Drei Helligkeiten, dieselbe Aussage wie in 2D: erkundet aber
			# nicht einsehbar (FOG_DIM), einsehbar aber diesen Zug nicht
			# erreichbar (OUT_OF_REACH), erreichbar (voll).
			var col: Color = Color.WHITE
			if f != 2:
				col = FOG_DIM
			elif has_reach and not in_reach:
				col = OUT_OF_REACH
			var top: float = float(TERRAIN_TOP.get(t, 0.0))
			if in_reach:
				rings.append({
					"pos": Vector3(float(x) * TILE, top, float(y) * TILE),
					"color": REACH_RING,
				})
			(by_terrain[TERRAIN_MODEL[t]] as Array).append({
				"pos": Vector3(float(x) * TILE, 0.0, float(y) * TILE),
				"color": col,
			})
			var key: String = TERRAIN_MODEL[t].substr(2)
			if DECO_CHANCE.has(key) and _hash(x, y, sd) % 6 < int(DECO_CHANCE[key]):
				var hh: int = _hash(x, y, sd + 7)
				(by_deco[DECO_MODEL[key]] as Array).append({
					"pos": Vector3(float(x) * TILE
							+ (float(hh % 100) / 100.0 - 0.5) * 0.36,
						top,
						float(y) * TILE
							+ (float((hh / 100) % 100) / 100.0 - 0.5) * 0.36),
					"rot": float(hh % 360) * PI / 180.0,
					"color": col,
				})
	for name in by_terrain.keys():
		_fill(String(name), by_terrain[name])
	for name in by_deco.keys():
		_fill(String(name), by_deco[name])

	# Die Reichweiten-Ringe gehen in DENSELBEN Topf wie die Besitzer-Ringe:
	# ein Modell, ein MultiMesh. Zwei Toepfe waeren zwei Zeichenaufrufe fuer
	# dieselbe Scheibe, und der zweite wuerde beim naechsten Durchlauf
	# vergessen zu leeren.
	_place_things(ctx, tiles, fog, w, rings)
	_built = true


# DAS MODELL SAGT WAS, DER RING SAGT WEM.
#
# Erster Anlauf: das Modell selbst wurde mit der Besitzer- oder
# Bedrohungsfarbe getoent. Das kostet zweimal. Eine rot getoente Burg ist
# keine rote Burg mehr, sondern eine schlecht gefaerbte - die Fraktion war
# nicht mehr zu erkennen. Und ein gruen getoentes Monster sah aus wie eine
# andere Kreatur, nicht wie ein schwacher Gegner.
#
# Jetzt steht das Modell in seinen eigenen Farben, und die Zugehoerigkeit
# liegt als flache Scheibe (Monster: Bedrohung) oder als Ring (Stadt,
# Held) darunter. Das ist dieselbe Sprache wie auf der 2D-Karte, wo der
# Ring um das Feld die Farbe traegt und nicht das Sinnbild.
func _place_things(ctx: Dictionary, tiles: Array, fog: Array, w: int,
		rings: Array) -> void:
	var per_model: Dictionary = {}
	if not rings.is_empty():
		per_model["marker_ring"] = rings
	# `col` faerbt das Modell (weiss = wie gebaut, FOG_DIM im Nebel),
	# `mark` ist die Farbe der Scheibe/des Rings darunter - oder leer.
	var add := func(model: String, cell: Vector2i, mark: String,
			mark_col: Color) -> void:
		var i: int = cell.y * w + cell.x
		if i < 0 or i >= tiles.size():
			return
		var f: int = int(fog[i]) if i < fog.size() else 2
		if f == 0:
			return
		var t: int = int(tiles[i])
		var top: float = float(TERRAIN_TOP.get(t, 0.0))
		var pos := Vector3(float(cell.x) * TILE, top, float(cell.y) * TILE)
		var dim: Color = Color.WHITE if f == 2 else FOG_DIM
		if not per_model.has(model):
			per_model[model] = []
		(per_model[model] as Array).append({"pos": pos, "color": dim})
		if mark == "":
			return
		if not per_model.has(mark):
			per_model[mark] = []
		(per_model[mark] as Array).append({
			"pos": pos,
			"color": mark_col if f == 2 else mark_col * FOG_DIM,
		})

	var fac_names: Array = ctx.get("faction_dirs", [])
	for c in (ctx.get("cities", []) as Array):
		var cd: Dictionary = c as Dictionary
		var fi: int = int(cd.get("faction", 1))
		var fname: String = String(fac_names[fi]) if fi < fac_names.size() else "menschen"
		add.call("city_" + fname, Vector2i(cd["pos"]), "marker_ring",
			cd.get("color", Color.WHITE) as Color)
	var omap: Dictionary = ctx.get("object_model", {}) as Dictionary
	for o in (ctx.get("objects", []) as Array):
		var od: Dictionary = o as Dictionary
		var model: String = String(omap.get(int(od.get("kind", -1)), ""))
		if model != "":
			add.call(model, Vector2i(od["pos"]), "", Color.WHITE)
	for m in (ctx.get("monsters", []) as Array):
		add.call("monster", Vector2i((m as Dictionary)["pos"]), "marker_disc",
			(m as Dictionary).get("color", Color(0.9, 0.35, 0.3)) as Color)
	for e in (ctx.get("enemies", []) as Array):
		add.call("hero", Vector2i((e as Dictionary)["pos"]), "marker_ring",
			(e as Dictionary).get("color", Color(0.9, 0.3, 0.3)) as Color)
	for hh in (ctx.get("heroes", []) as Array):
		add.call("hero", Vector2i((hh as Dictionary)["pos"]), "marker_ring",
			(hh as Dictionary).get("color", Color.WHITE) as Color)
	for name in per_model.keys():
		_fill(String(name), per_model[name])
	# Modelle ohne Aufstellung in diesem Durchlauf leeren, sonst bleiben
	# Reste der letzten Runde stehen (ein gefallener Held zum Beispiel).
	for name in _multi.keys():
		if not per_model.has(name) and not String(name).begins_with("t_") \
				and not String(name).begins_with("deco_"):
			(_multi[name] as MultiMeshInstance3D).multimesh.instance_count = 0


# Kamera auf denselben Ausschnitt setzen, den die 2D-Karte zeigt:
# `center` ist die Kachel in der Bildmitte, `tiles_across` wie viele
# Kacheln in die Breite passen.
func look_at_map(center: Vector2, tiles_across: float) -> void:
	if _cam == null:
		return
	_cam.size = maxf(4.0, tiles_across)
	# Der ABSTAND nach hinten folgt aus Hoehe und Neigung, er ist keine
	# freie Zahl: der Mittelstrahl der Kamera muss genau auf `center`
	# treffen. Mit einem festen Wert (CAM_BACK) lag der Blickpunkt 4
	# Kacheln vor dem Ziel - der Held sass unterhalb der Bildmitte, und je
	# nach Neigung waere der Fehler anders gross.
	var pitch: float = deg_to_rad(absf(CAM_PITCH_DEG))
	var back: float = CAM_UP / tan(pitch)
	_cam.position = Vector3(center.x * TILE, CAM_UP * TILE,
		(center.y + back) * TILE)
	_cam.rotation_degrees = Vector3(CAM_PITCH_DEG, 0, 0)


# Bildschirmpunkt -> Kachel. Der Strahl der Kamera wird mit der Ebene y = 0
# geschnitten.
#
# BEKANNTE UNGENAUIGKEIT: erhoehtes Gelaende (Gebirge steht 1.1 hoch) wird
# an seinem FUSS getroffen, nicht an der sichtbaren Oberflaeche - ein Tap
# auf die Bergspitze landet eine Kachel dahinter. Das ist dieselbe
# Vereinfachung, die HoMM3 macht, und sie haelt Tap und Wegfindung
# konsistent: gelaufen wird ohnehin auf der Ebene.
func tile_at(screen_pos: Vector2, viewport_size: Vector2) -> Vector2i:
	if _cam == null:
		return Vector2i(-1, -1)
	var from: Vector3 = _cam.project_ray_origin(screen_pos)
	var dir: Vector3 = _cam.project_ray_normal(screen_pos)
	if absf(dir.y) < 0.0001:
		return Vector2i(-1, -1)
	var t: float = -from.y / dir.y
	if t < 0.0:
		return Vector2i(-1, -1)
	var hit: Vector3 = from + dir * t
	return Vector2i(int(round(hit.x / TILE)), int(round(hit.z / TILE)))


func is_built() -> bool:
	return _built
