extends "res://scripts/ui/Scene3D.gd"

# Raeumliche Ansicht der Weltkarte - im Stil der Heroes-4-Abenteuerkarte
# (It. 77; Grundlage It. 53).
#
# ZWEITE ANSICHT, KEIN ERSATZ. Beide lesen dasselbe Modell (`_map["tiles"]`,
# `_cities`, `_monsters`, `_objects`, `_fog_player`, `_costs`) - Wegfindung,
# Kampf, Balance und Spielstaende sind davon nicht beruehrt.
#
# KEINE LOGIK HIER. Alles kommt ueber `refresh(ctx)`.
#
# WAS SICH GEGENUEBER It. 53 GEAENDERT HAT: dort lag je Kachel eine Platte
# in ihrer Gelaendefarbe - die Karte sah aus wie ein Brettspiel. Die
# Abenteuerkarte von Heroes 4 hat KEINE Kachelkanten: Wiese laeuft in Wald
# und Sand ueber, Berge ragen auf, Wasser hat Ufer, Waelder sind dicht, und
# das Unerforschte liegt unter einem dunklen Schleier. Genau das baut diese
# Ansicht:
#
#   * EIN Gelaendenetz fuer die ganze Karte (`_build_land`), Hoehe aus
#     `ground_height` - Berge hoch, Wasser tief, alles Begehbare flach,
#     dazwischen weiche Uebergaenge. Farbe im Shader (world_land.gdshader)
#     aus Gewichten je Gelaendeart.
#   * WASSER als eigene Flaeche mit Ufersaum (world_water.gdshader).
#   * NEBEL als kleine Textur, eine Zelle je Kachel (`_fog_img`), gefiltert:
#     weicher Schleierrand, und unter dem Schleier wird das Gelaende flach.
#   * AUSSTATTUNG je Kachel aus nature.glb: dichte Waelder, Felsen und
#     Kiefern im Gebirge, Bueche und Gras auf der Wiese.
#   * STAEDTE, HELDEN, MONSTER aus den neuen Modellen: die Zitadelle der
#     Fraktion aus city.glb, der Held als Reiter, das Monster als seine
#     Kreatur aus creatures.glb.
#
# DER TIPP bleibt der Strahl auf y = 0 (Scene3D.cell_at). Das geht, weil
# alles BEGEHBARE flach bleibt (|h| <= WALK_MAX); hoch und tief sind nur
# Berge und Wasser, und die sind unpassierbar (Movement.base_cost).

const MODELS_PATH := "res://assets/models/world.glb"
const NATURE_PATH := "res://assets/models/nature.glb"
# Kartenobjekte im Heroes-4-Stil (tools/gen_mapobj3d.py). NACH world.glb
# geladen: gleiche Namen, die neuen ersetzen die alten Klotz-Modelle.
const MAPOBJ_PATH := "res://assets/models/mapobj.glb"
const CREATURES_PATH := "res://assets/models/creatures.glb"
const CITY_PATH := "res://assets/models/city.glb"
const LAND_SHADER := preload("res://scripts/ui/world_land.gdshader")
const WATER_SHADER := preload("res://scripts/ui/world_water.gdshader")
const DETAIL_TEX := "res://assets/textures/battle/detail_%s.png"

const TILE := 1.0

# Gelaendearten wie MapGen.TILE_*.
const T_GRASS := 0
const T_FOREST := 1
const T_WATER := 2
const T_MOUNTAIN := 3
const T_SAND := 4
const T_SWAMP := 5
const TERRAIN_NAMES := ["grass", "forest", "water", "mountain", "sand", "swamp"]

# Grundhoehe je Gelaendeart (Kachelmitte). Begehbares bleibt in WALK_MAX.
const BASE_HEIGHT := {0: 0.0, 1: 0.02, 2: -0.34, 3: 0.55, 4: -0.02, 5: -0.04}
const WALK_MAX := 0.05
const WATER_LEVEL := -0.08
# Zusaetzliche Zackenhoehe im Gebirge.
const MOUNTAIN_PEAK := 0.95

# Unerforschter Rand um die Karte, damit die Karte nicht im Leeren endet.
const MARGIN := 12
# Netzaufloesung: Unterteilungen je Kachel.
const SUBDIV := 4

# Nebelstufen als Helligkeit in der Nebeltextur (siehe Shader).
const VIS_HIDDEN := 0.0
const VIS_EXPLORED := 0.5
const VIS_OUT_OF_REACH := 0.75
const VIS_REACH := 1.0

# Instanzfarbe der Ausstattung und Figuren je Nebelstufe.
const FOG_DIM := Color(0.48, 0.50, 0.56)
const OUT_OF_REACH := Color(0.70, 0.72, 0.76)

# Was auf einer Kachel steht, je Gelaendeart: [Praefix, Anzahl, Zielhoehe].
# Zielhoehe in Kacheln - die Modelle aus nature.glb haben verschiedene
# Groessen, also wird jedes auf seine Hoehe eingepasst (`_fit_scale`).
const SCATTER := {
	0: [["grass_", 3, 0.12], ["flower_", 1, 0.10], ["shrub_autumn_", 0.18, 0.30],
		["bush_plain_", 0.15, 0.28], ["boulder_", 0.06, 0.22], ["tree_leaf_", 0.08, 0.75]],
	1: [["tree_leaf_", 2.2, 0.80], ["tree_pine_", 1.4, 0.95], ["bush_plain_", 0.5, 0.30],
		["grass_", 1, 0.12]],
	3: [["boulder_", 0.7, 0.40], ["tree_pine_", 1.1, 0.75]],
	4: [["rock_", 0.3, 0.12], ["bare_", 0.10, 0.55]],
	5: [["grass_", 2.5, 0.16], ["bare_", 0.6, 0.65], ["shrub_green_", 0.4, 0.28]],
}

# Die Dinge auf der Karte.
const CITY_MODEL := "b_%s_zitadelle"
const CITY_SIZE := 1.15          # Breite der Stadt in Kacheln
const HERO_MODEL := "men_cavalier"
const FIGURE_SIZE := 0.80        # Raumdiagonale von Held und Monster
const OBJECT_SIZE := 0.75

# Fuer Werkzeuge und Tests: welche Modelle die Ansicht anfordert.
const RING_MODEL := "marker_ring"
const DISC_MODEL := "marker_disc"

var _built: bool = false
var _land: MeshInstance3D = null
var _water: MeshInstance3D = null
var _land_key: String = ""
var _w: int = 0
var _h: int = 0
var _tiles: Array = []
var _fog_img: Image = null
var _fog_tex: ImageTexture = null
var _noise := FastNoiseLite.new()
var _noise_tex: Texture2D = null
# Ausstattung je Kachel: index -> Array[{model, pos, rot, scale}].
var _scatter: Dictionary = {}
var _fit_cache: Dictionary = {}


func _init() -> void:
	model_paths = [MODELS_PATH, MAPOBJ_PATH, NATURE_PATH, CREATURES_PATH, CITY_PATH]
	pitch_deg = -34.0
	cam_up = 11.0
	_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	_noise.frequency = 0.35
	_noise.fractal_octaves = 3
	_noise.seed = 2027


func _ready() -> void:
	super()
	_soften_light()


# Licht wie auf dem Schlachtfeld (am Heroes-4-Bild gemessen, It. 72b).
func _soften_light() -> void:
	for c in get_children():
		if c is WorldEnvironment:
			var env: Environment = (c as WorldEnvironment).environment
			env.adjustment_enabled = true
			env.adjustment_saturation = 0.70
			env.tonemap_exposure = 0.85
			env.ambient_light_color = Color(0.78, 0.76, 0.70)
			env.ambient_light_energy = 0.42
			env.background_color = Color(0.05, 0.06, 0.08)
		elif c is DirectionalLight3D and (c as DirectionalLight3D).shadow_enabled:
			var sun := c as DirectionalLight3D
			sun.light_energy = 0.9
			sun.light_color = Color(1.0, 0.94, 0.82)


# --- Hoehe -------------------------------------------------------------------

func _tile_at(x: int, y: int) -> int:
	x = clampi(x, 0, _w - 1)
	y = clampi(y, 0, _h - 1)
	return int(_tiles[y * _w + x])


# Gewicht je Gelaendeart an einer Stelle: weiche Mischung der vier
# naechsten Kachelmitten. Die Glaettung (smoothstep auf dem Anteil) laesst
# jede Kachelmitte REIN stehen - nur zwischen den Kacheln wird gemischt.
func _weights(fx: float, fz: float) -> PackedFloat32Array:
	var out := PackedFloat32Array([0, 0, 0, 0, 0, 0])
	var x0: int = int(floor(fx))
	var z0: int = int(floor(fz))
	var tx: float = smoothstep(0.0, 1.0, fx - float(x0))
	var tz: float = smoothstep(0.0, 1.0, fz - float(z0))
	out[_tile_at(x0, z0)] += (1.0 - tx) * (1.0 - tz)
	out[_tile_at(x0 + 1, z0)] += tx * (1.0 - tz)
	out[_tile_at(x0, z0 + 1)] += (1.0 - tx) * tz
	out[_tile_at(x0 + 1, z0 + 1)] += tx * tz
	return out


# DIE EINE HOEHE. Netz, Ausstattung und Figuren lesen hier.
func ground_height(fx: float, fz: float) -> float:
	if _tiles.is_empty():
		return 0.0
	var wt := _weights(fx, fz)
	var h := 0.0
	for t in range(6):
		h += wt[t] * float(BASE_HEIGHT[t])
	# Zacken im Gebirge: Rauschen, nur wo Berg ist.
	var m: float = wt[T_MOUNTAIN]
	if m > 0.0:
		var r: float = 1.0 - absf(_noise.get_noise_2d(fx * 1.4, fz * 1.4))
		h += m * m * MOUNTAIN_PEAK * (r * r * 1.2 + 0.25 * _noise.get_noise_2d(fx * 3.1, fz * 3.1))
	# Wasser: Mulde zur Mitte hin tiefer.
	h += wt[T_WATER] * 0.05 * _noise.get_noise_2d(fx * 2.0, fz * 2.0)
	# Feine Unebenheit, auf Begehbarem kaum.
	h += 0.015 * _noise.get_noise_2d(fx * 4.0, fz * 4.0)
	return h


# --- Aufbau des Gelaendes ----------------------------------------------------

func _build_land() -> void:
	var nx: int = (_w - 1 + 2 * MARGIN) * SUBDIV + 1
	var nz: int = (_h - 1 + 2 * MARGIN) * SUBDIV + 1
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var cols := PackedColorArray()
	verts.resize(nx * nz)
	norms.resize(nx * nz)
	cols.resize(nx * nz)
	var step: float = 1.0 / float(SUBDIV)
	# Hoehen EINMAL ins Gitter, Normalen aus den Nachbarn. Fuenf Aufrufe
	# der Hoehenfunktion je Punkt (fuer die Normale) haetten beim ersten
	# Einschalten auf dem Handy spuerbar gedauert - die Karte hat rund
	# 30.000 Punkte.
	for j in range(nz):
		for i in range(nx):
			var x: float = -float(MARGIN) + float(i) * step
			var z: float = -float(MARGIN) + float(j) * step
			var k: int = j * nx + i
			verts[k] = Vector3(x, ground_height(x, z), z)
			var wt := _weights(x, z)
			cols[k] = Color(wt[T_FOREST], wt[T_SAND], wt[T_SWAMP], wt[T_MOUNTAIN])
	for j in range(nz):
		for i in range(nx):
			var l: float = verts[j * nx + maxi(i - 1, 0)].y
			var r: float = verts[j * nx + mini(i + 1, nx - 1)].y
			var u: float = verts[maxi(j - 1, 0) * nx + i].y
			var d: float = verts[mini(j + 1, nz - 1) * nx + i].y
			norms[j * nx + i] = Vector3(l - r, 2.0 * step, u - d).normalized()
	var idx := PackedInt32Array()
	idx.resize((nx - 1) * (nz - 1) * 6)
	var q := 0
	for j in range(nz - 1):
		for i in range(nx - 1):
			var a: int = j * nx + i
			idx[q] = a
			idx[q + 1] = a + 1
			idx[q + 2] = a + nx
			idx[q + 3] = a + 1
			idx[q + 4] = a + nx + 1
			idx[q + 5] = a + nx
			q += 6
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_NORMAL] = norms
	arr[Mesh.ARRAY_COLOR] = cols
	arr[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)

	if _noise_tex == null:
		var n := FastNoiseLite.new()
		n.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
		n.frequency = 0.012
		n.fractal_octaves = 4
		n.seed = 4711
		var img: Image = n.get_seamless_image(512, 512)
		img.generate_mipmaps()
		_noise_tex = ImageTexture.create_from_image(img)
	_fog_img = Image.create(_w, _h, false, Image.FORMAT_L8)
	_fog_tex = ImageTexture.create_from_image(_fog_img)
	var wimg := Image.create(_w, _h, false, Image.FORMAT_L8)
	for y in range(_h):
		for x in range(_w):
			wimg.set_pixel(x, y, Color.WHITE if _tile_at(x, y) == T_WATER else Color.BLACK)
	var wtex := ImageTexture.create_from_image(wimg)

	if _land == null:
		_land = MeshInstance3D.new()
		_land.name = "Gelaende"
		var mat := ShaderMaterial.new()
		mat.shader = LAND_SHADER
		mat.set_shader_parameter("detail_a", load(DETAIL_TEX % "grass_a"))
		mat.set_shader_parameter("detail_b", load(DETAIL_TEX % "grass_b"))
		mat.set_shader_parameter("detail_dirt", load(DETAIL_TEX % "dirt"))
		_land.material_override = mat
		add_child(_land)
		_water = MeshInstance3D.new()
		_water.name = "Wasser"
		var wm := ShaderMaterial.new()
		wm.shader = WATER_SHADER
		_water.material_override = wm
		_water.mesh = PlaneMesh.new()
		add_child(_water)
	_land.mesh = mesh
	var lm := _land.material_override as ShaderMaterial
	lm.set_shader_parameter("noise", _noise_tex)
	lm.set_shader_parameter("fog_tex", _fog_tex)
	lm.set_shader_parameter("map_size", Vector2(_w, _h))
	lm.set_shader_parameter("water_level", WATER_LEVEL)
	var wmat := _water.material_override as ShaderMaterial
	wmat.set_shader_parameter("noise", _noise_tex)
	wmat.set_shader_parameter("fog_tex", _fog_tex)
	wmat.set_shader_parameter("water_mask", wtex)
	wmat.set_shader_parameter("map_size", Vector2(_w, _h))
	(_water.mesh as PlaneMesh).size = Vector2(_w - 1 + 2 * MARGIN, _h - 1 + 2 * MARGIN)
	_water.position = Vector3((_w - 1) * 0.5, WATER_LEVEL, (_h - 1) * 0.5)
	_build_scatter()


# Modellgroesse einpassen: jedes Ausstattungsteil auf seine Zielhoehe.
func _fit_scale(model: String, target_h: float) -> float:
	if not _meshes.has(model):
		return 1.0
	if not _fit_cache.has(model):
		var a: AABB = (_meshes[model] as Mesh).get_aabb()
		_fit_cache[model] = maxf(0.01, a.size.y)
	return target_h / float(_fit_cache[model])


# Ausstattung je Kachel, EINMAL je Karte gewuerfelt (deterministisch aus
# Lage und Seed), danach nur noch nach Nebel ein- und ausgeblendet.
func _build_scatter() -> void:
	_scatter.clear()
	var pools: Dictionary = {}
	for k in _meshes.keys():
		for t in SCATTER.keys():
			for e in (SCATTER[t] as Array):
				var pre: String = String((e as Array)[0])
				if String(k).begins_with(pre):
					if not pools.has(pre):
						pools[pre] = []
					if not (pools[pre] as Array).has(k):
						(pools[pre] as Array).append(String(k))
	for pre in pools.keys():
		(pools[pre] as Array).sort()
	for y in range(_h):
		for x in range(_w):
			var t: int = _tile_at(x, y)
			if not SCATTER.has(t):
				continue
			var items: Array = []
			var salt := 0
			for e in (SCATTER[t] as Array):
				var ea: Array = e
				var pre: String = String(ea[0])
				if not pools.has(pre):
					continue
				var pool: Array = pools[pre]
				var want: float = float(ea[1])
				var n: int = int(floor(want))
				salt += 13
				if float(hash3(x, y, salt) % 1000) / 1000.0 < want - float(n):
					n += 1
				for i in range(n):
					var hh: int = hash3(x, y, salt + 101 + i * 37)
					var model: String = String(pool[hh % pool.size()])
					# Waelder stehen bis an den Kachelrand, sonst bleiben
					# Gassen, durch die man das Kachelraster wieder sieht.
					var spread: float = 0.92 if t == T_FOREST else 0.72
					var px: float = float(x) + (float((hh / 7) % 1000) / 1000.0 - 0.5) * spread
					var pz: float = float(y) + (float((hh / 7000) % 1000) / 1000.0 - 0.5) * spread
					var th: float = float(ea[2]) * (0.80 + float((hh / 70) % 40) * 0.01)
					var sc: float = _fit_scale(model, th)
					items.append({"model": model,
						"pos": Vector3(px, ground_height(px, pz) - 0.01, pz),
						"rot": float(hh % 360) * PI / 180.0,
						"scale": Vector3(sc, sc, sc)})
			_scatter[y * _w + x] = items


# --- Die eine Schnittstelle nach aussen -----------------------------------

# ctx:
#   tiles       Array[int]        Gelaendearten, width * height
#   width/height int
#   fog         Array[int]        FOG_HIDDEN / EXPLORED / VISIBLE
#   seed        int
#   cities      Array[{pos, faction, color}]
#   faction_dirs Array[String]    Fraktions-Index -> Verzeichnisname
#   monsters    Array[{pos, unit, color}]
#   objects     Array[{pos, kind}]
#   heroes      Array[{pos, color}]
#   enemies     Array[{pos, color}]
#   object_model Dictionary       kind -> Modellname
#   reach       Array[Vector2i]   Felder in Zugreichweite; LEER heisst
#                                 "keine Angabe" und dunkelt nichts ab
func refresh(ctx: Dictionary) -> void:
	if _meshes.is_empty():
		return
	var w: int = int(ctx.get("width", 0))
	var h: int = int(ctx.get("height", 0))
	var tiles: Array = ctx.get("tiles", []) as Array
	var fog: Array = ctx.get("fog", []) as Array
	if w <= 0 or h <= 0 or tiles.size() < w * h:
		return
	var key: String = "%d|%d|%d|%d" % [w, h, int(ctx.get("seed", 0)), hash(tiles)]
	if key != _land_key:
		_w = w
		_h = h
		_tiles = tiles.duplicate()
		_build_land()
		_land_key = key

	var reach: Dictionary = {}
	for r in (ctx.get("reach", []) as Array):
		reach[r] = true
	var has_reach: bool = not reach.is_empty()

	# Nebeltextur und Ausstattung nach Nebel.
	var per_model: Dictionary = {}
	for y in range(h):
		for x in range(w):
			var i: int = y * w + x
			var f: int = int(fog[i]) if i < fog.size() else 2
			var v: float = VIS_HIDDEN
			var col := Color.WHITE
			if f == 1:
				v = VIS_EXPLORED
				col = FOG_DIM
			elif f == 2:
				v = VIS_OUT_OF_REACH if (has_reach and not reach.has(Vector2i(x, y))) \
					else VIS_REACH
				col = OUT_OF_REACH if v < VIS_REACH else Color.WHITE
			_fog_img.set_pixel(x, y, Color(v, v, v))
			if f == 0:
				continue
			for it in (_scatter.get(i, []) as Array):
				var d: Dictionary = it
				var m: String = String(d["model"])
				if not per_model.has(m):
					per_model[m] = []
				(per_model[m] as Array).append({"pos": d["pos"], "rot": d["rot"],
					"scale": d["scale"], "color": col})
	_fog_tex.update(_fog_img)

	_place_things(ctx, fog, w, per_model)
	for name in per_model.keys():
		_fill(String(name), per_model[name])
	_clear_except(per_model, [])
	_built = true


# DAS MODELL SAGT WAS, DER RING SAGT WEM (It. 53): das Modell steht in
# seinen eigenen Farben, die Zugehoerigkeit liegt als Ring (Stadt, Held)
# oder Scheibe (Monster: Bedrohung) darunter.
func _place_things(ctx: Dictionary, fog: Array, w: int, per_model: Dictionary) -> void:
	var add := func(model: String, cell: Vector2i, size: float, mark: String,
			mark_col: Color, mark_scale: float = 1.0) -> void:
		var i: int = cell.y * w + cell.x
		if i < 0 or i >= _tiles.size() or not _meshes.has(model):
			return
		var f: int = int(fog[i]) if i < fog.size() else 2
		if f == 0:
			return
		var pos := Vector3(float(cell.x), ground_height(cell.x, cell.y), float(cell.y))
		var dim: Color = Color.WHITE if f == 2 else FOG_DIM
		var sc: float = model_scale(model, size)
		if not per_model.has(model):
			per_model[model] = []
		(per_model[model] as Array).append({"pos": pos, "color": dim,
			"scale": Vector3(sc, sc, sc), "rot": PI * 0.12})
		if mark == "" or not _meshes.has(mark):
			return
		if not per_model.has(mark):
			per_model[mark] = []
		(per_model[mark] as Array).append({"pos": pos + Vector3(0, 0.01, 0),
			"scale": Vector3(mark_scale, 1.0, mark_scale),
			"color": mark_col if f == 2 else mark_col * FOG_DIM})

	var fac_names: Array = ctx.get("faction_dirs", [])
	for c in (ctx.get("cities", []) as Array):
		var cd: Dictionary = c as Dictionary
		var fi: int = int(cd.get("faction", 1))
		var fname: String = String(fac_names[fi]) if fi < fac_names.size() else "menschen"
		var model: String = CITY_MODEL % fname
		if not _meshes.has(model):
			model = "city_" + fname
		add.call(model, Vector2i(cd["pos"]), -CITY_SIZE, RING_MODEL,
			cd.get("color", Color.WHITE) as Color, 1.35)
	var omap: Dictionary = ctx.get("object_model", {}) as Dictionary
	for o in (ctx.get("objects", []) as Array):
		var od: Dictionary = o as Dictionary
		var model: String = String(omap.get(int(od.get("kind", -1)), ""))
		if model != "":
			add.call(model, Vector2i(od["pos"]), 0.0, "", Color.WHITE)
	for m in (ctx.get("monsters", []) as Array):
		var md: Dictionary = m as Dictionary
		var unit: String = String(md.get("unit", ""))
		var model: String = unit if _meshes.has(unit) else "monster"
		add.call(model, Vector2i(md["pos"]), FIGURE_SIZE if model == unit else 0.0,
			DISC_MODEL, md.get("color", Color(0.9, 0.35, 0.3)) as Color)
	for e in (ctx.get("enemies", []) as Array):
		add.call(HERO_MODEL, Vector2i((e as Dictionary)["pos"]), FIGURE_SIZE,
			RING_MODEL, (e as Dictionary).get("color", Color(0.9, 0.3, 0.3)) as Color)
	for hh in (ctx.get("heroes", []) as Array):
		add.call(HERO_MODEL, Vector2i((hh as Dictionary)["pos"]), FIGURE_SIZE,
			RING_MODEL, (hh as Dictionary).get("color", Color.WHITE) as Color)


# Massstab eines Dings auf der Karte.
#   size > 0: Raumdiagonale (Figuren - dieselbe Groessenregel wie
#             fit_to_tier, damit ein Drache groesser bleibt als ein Goblin,
#             aber jedes Ding auf seine Kachel passt).
#   size < 0: Breite in Kacheln (Stadt).
#   size = 0: wie gebaut (die Kartenobjekte aus world.glb).
func model_scale(model: String, size: float) -> float:
	if size == 0.0 or not _meshes.has(model):
		return 1.0
	var a: AABB = (_meshes[model] as Mesh).get_aabb()
	if size < 0.0:
		return -size / maxf(0.01, maxf(a.size.x, a.size.z))
	# Figuren: Diagonale, aber nie breiter als eine Kachel.
	var k: float = size / maxf(0.01, a.size.length()) * 1.6
	return minf(k, 0.95 / maxf(0.01, maxf(a.size.x, a.size.z)))


# Kamera auf denselben Ausschnitt wie die 2D-Karte.
func look_at_map(center: Vector2, tiles_across: float) -> void:
	look_at_cells(center, tiles_across)


func tile_at(screen_pos: Vector2, _viewport_size: Vector2) -> Vector2i:
	return cell_at(screen_pos)


func land_node() -> MeshInstance3D:
	return _land


func water_node() -> MeshInstance3D:
	return _water


func fog_image() -> Image:
	return _fog_img


func scatter_count() -> int:
	var n := 0
	for k in _scatter.keys():
		n += (_scatter[k] as Array).size()
	return n


func is_built() -> bool:
	return _built
