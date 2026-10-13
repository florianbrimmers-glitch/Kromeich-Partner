extends "res://scripts/ui/Scene3D.gd"

# Raeumliche Ansicht der Stadt - als PANORAMA wie in Heroes 4 (It. 75).
#
# Bis It. 74 war das ein Hof von oben: neun Gebaeude auf einer grauen
# Flaeche, orthogonale Kamera, nichts drumherum. Der Stadtschirm von
# Heroes 4 ist das Gegenteil - eine Landschaft mit Himmel, die Stadt steht
# auf Terrassen, deren Kanten als Fels abbrechen, die Burg oben hinten, ein
# Weg fuehrt hinauf, dahinter Berge. Genau das baut diese Ansicht:
#
#   * GELAENDE aus EINER Hoehenfunktion (`land_height`). Gebaeude, Wege,
#     Ausstattung und das Netz selbst fragen alle dieselbe Funktion - eine
#     zweite Hoehenangabe irgendwo waere ein Gebaeude, das schwebt.
#   * TERRASSEN nach der Tiefe des Bauplatzes: die hinterste Reihe (die
#     Zitadelle) steht am hoechsten. Das loest nebenbei das alte Problem,
#     dass vordere Gebaeude hintere verdecken (It. 69) - wer hoeher steht,
#     schaut drueber.
#   * PERSPEKTIVE und flacher Blick (rund 20 Grad), Himmel und Dunst. Die
#     Stadt wird nie gescrollt, also gibt es keinen Grund fuer die
#     orthogonale Kamera der anderen Ansichten (dort braucht jede Zelle
#     dieselbe Trefferflaeche).
#
# ZWEITE ANSICHT, KEIN ERSATZ - Bauregeln, Kosten und Anwerben sind nicht
# beruehrt; alles kommt ueber `refresh(ctx)`.
#
# DIE BAUPLAETZE KOMMEN WEITER AUS data/city_layout.json. Diese Ansicht
# legt nur fest, wie aus dem Anteil (x, y) ein Ort im Panorama wird.

const MODELS_PATH := "res://assets/models/city.glb"
const WORLD_PATH := "res://assets/models/world.glb"
const NATURE_PATH := "res://assets/models/nature.glb"
const LAND_SHADER := preload("res://scripts/ui/city_land.gdshader")
const SKY_SHADER := preload("res://scripts/ui/city_sky.gdshader")
const DETAIL_TEX := "res://assets/textures/battle/detail_%s.png"

# Was zwischen den Gebaeuden steht. Die Baeume und Felsen kommen aus
# nature.glb - dieselben wie auf dem Schlachtfeld, nicht ein zweiter Satz.
const PROPS := [
	{"model": "city_barrel", "n": 7, "scale": [1.0, 1.3]},
	{"model": "city_crate", "n": 6, "scale": [1.0, 1.3]},
	{"model": "city_cart", "n": 2, "scale": [1.1, 1.3]},
	{"model": "city_lamp", "n": 5, "scale": [1.0, 1.2]},
	{"model": "grass_0", "n": 40, "scale": [0.8, 1.4]},
	{"model": "grass_1", "n": 30, "scale": [0.8, 1.4]},
	{"model": "flower_yellow", "n": 10, "scale": [0.8, 1.2]},
	{"model": "flower_white", "n": 10, "scale": [0.8, 1.2]},
	{"model": "plants_0", "n": 8, "scale": [0.9, 1.3]},
]
# Abstand, den Gerumpel von einem Bauplatz und vom Weg haelt.
const PROP_CLEARANCE := 1.35

# Ungebaut: Baustelle je Bauplatz (It. 69), das Geruest ist nur Notausgang.
const SCAFFOLD := "city_scaffold"
const SITE_PREFIX := "city_site_"

# --- Panorama-Geometrie -----------------------------------------------------

# Breite der bebauten Flaeche: Anteil x 0..1 aus dem Layout -> Weltmeter.
const YARD_W := 11.0

# TIEFE JE LAYOUT-ZEILE, als Stuetzpunkte (Anteil y -> Welt z, kleiner =
# weiter hinten). Die Reihen des Layouts liegen bei y 0.47 bis 0.875 - fuer
# die 2D-Ansicht richtig, raeumlich zu eng: auf Terrassen braucht jede
# Reihe eine Stufe, und zwischen den Stufen eine Felskante. Die Punkte
# fallen genau auf die vier Gruppen des Layouts (Zitadelle; Kapelle und
# Wachturm; Schmiede und Reiterei; Markt, Kaserne und Spaeher; Mauer).
const DEPTH_CURVE := [[0.47, -7.4], [0.545, -3.5], [0.67, -0.3],
	[0.785, 3.3], [0.875, 6.0]]

# TERRASSEN: bis zu welchem Layout-y eine Reihe auf welcher Hoehe steht,
# und wo (Welt z) die Vorderkante der Stufe liegt. Die Kanten liegen
# zwischen den Reihen; jede Stufe ist hoeher als die davor. Vorne die
# unterste (Hoehe 0).
const TERRACES := [
	{"max_y": 0.50, "h": 3.1, "edge": -5.9},
	{"max_y": 0.60, "h": 2.0, "edge": -2.0},
	{"max_y": 0.72, "h": 1.0, "edge": 1.3},
]
# Halbe Breite einer Felskante (steil) und einer Rampe (flach).
const CLIFF_W := 0.13
const RAMP_W := 1.6
# Der Weg laeuft mittig den Hang hinauf; an dieser Stelle sind die Kanten
# Rampen statt Fels.
const ROAD_HALF := 0.55
const RAMP_HALF := 1.0
# Hinter dem Plateau steigen Berge an, seitlich Huegel.
const MOUNT_FROM := -15.0
const HILL_FROM := 7.0

# Gebaeude im Panorama groesser als im Hof von oben: der Blick ist flach
# und weiter, ein Bauplatz ist auf dem Schirm sonst ein Spielzeug.
const BUILDING_SCALE := 1.45
# Abstand zur Kamera, bei dem ein Gebaeude genau BUILDING_SCALE hat.
const DIST_REF := 13.0

# Kamera: Blickpunkt, Abstand, Hoehe und Bildwinkel (waagerecht).
const CAM_TARGET := Vector3(0.0, 1.6, -2.2)
const CAM_POS := Vector3(0.0, 6.6, 11.5)
const CAM_FOV := 54.0

# Stimmung je Fraktion. Wiese, Fels und Himmel; dazu, wie viele Baeume auf
# den Huegeln stehen. Menschen gemessen am Schlachtfeld (Heroes-4-Wiese),
# Totenreich nach dem Necropolis-Schirm des Vorbilds (grauer Fels, gluehend
# roter Himmel), Orks trocken, Waldvolk satt und bewaldet.
const FACTION_LOOK := {
	"menschen": {
		"grass": [Color("#405731"), Color("#4e6b3a"), Color("#557f3d"), Color("#73603e")],
		"rock": [Color("#5a5348"), Color("#968c7c")], "path": Color("#9a8662"),
		"peak": Color("#c9c6c0"),
		"sky": [Color("#4a78b8"), Color("#cfdbe2"), Color("#fbfaf6"), Color("#9aa6b8")],
		"shrubs": ["shrub_green_", "bush_plain_", "shrub_autumn_", "bush_flower_"],
		"trees": 46, "tree_prefix": "tree_leaf_", "cover": 0.50,
	},
	"waldvolk": {
		"grass": [Color("#33502a"), Color("#3f6331"), Color("#4c7838"), Color("#5f6a36")],
		"rock": [Color("#4a4c42"), Color("#7c8070"), ], "path": Color("#8a7a58"),
		"peak": Color("#b8bcb4"),
		"sky": [Color("#5a8cb0"), Color("#d8e4cc"), Color("#f6f8f0"), Color("#9cae9c")],
		"shrubs": ["shrub_green_", "bush_plain_", "bush_flower_"],
		"trees": 90, "tree_prefix": "tree_", "cover": 0.55,
	},
	"totenreich": {
		"grass": [Color("#3e3c3e"), Color("#4c4a4c"), Color("#5a5658"), Color("#5c5246")],
		"rock": [Color("#2c2a2e"), Color("#6a6670")], "path": Color("#6e6456"),
		"peak": Color("#4a4448"),
		"sky": [Color("#3a1a1e"), Color("#d8743a"), Color("#a8503a"), Color("#4a2224")],
		"shrubs": ["bare_", "boulder_"],
		"trees": 16, "tree_prefix": "bare_", "cover": 0.40,
	},
	"orks": {
		"grass": [Color("#6a5432"), Color("#7c6440"), Color("#8c7448"), Color("#8a5e3a")],
		"rock": [Color("#5a3a2a"), Color("#9a6a4a")], "path": Color("#a48460"),
		"peak": Color("#b08a6a"),
		"sky": [Color("#5e7aa0"), Color("#e6c08a"), Color("#f4e6cc"), Color("#b08a70")],
		"shrubs": ["bare_", "boulder_", "shrub_autumn_"],
		"trees": 14, "tree_prefix": "bare_", "cover": 0.44,
	},
}

var _built: bool = false
var _land: MeshInstance3D = null
var _land_fac: String = ""
var _sky_mat: ShaderMaterial = null
var _noise := FastNoiseLite.new()
var _noise_tex: Texture2D = null
var _props_key: String = ""
var _props: Dictionary = {}


func _init() -> void:
	model_paths = [MODELS_PATH, WORLD_PATH, NATURE_PATH]
	transparent_prefix = ""
	_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	_noise.frequency = 0.08
	_noise.fractal_octaves = 3
	_noise.seed = 1717


func _ready() -> void:
	super()
	_setup_panorama()


# Perspektive, Himmel als Kulisse, Dunst. Der Unterbau baut eine
# orthogonale Kamera und einen neutralen Hintergrund - beides ist fuer die
# Karte und das Brett richtig, fuer ein Panorama nicht.
func _setup_panorama() -> void:
	_cam.projection = Camera3D.PROJECTION_PERSPECTIVE
	_cam.keep_aspect = Camera3D.KEEP_WIDTH
	_cam.fov = CAM_FOV
	_cam.near = 0.2
	_cam.far = 200.0
	_noise_tex = _make_noise_texture()
	_sky_mat = ShaderMaterial.new()
	_sky_mat.shader = SKY_SHADER
	_sky_mat.set_shader_parameter("noise", _noise_tex)
	for c in get_children():
		if c is WorldEnvironment:
			var env: Environment = (c as WorldEnvironment).environment
			var sky := Sky.new()
			sky.sky_material = _sky_mat
			env.sky = sky
			env.background_mode = Environment.BG_SKY
			# Dunst: entfernte Berge werden heller und nehmen die Farbe des
			# Horizonts an - ohne das klebt der Hintergrund am Vordergrund.
			env.fog_enabled = true
			env.fog_density = 0.0045
			env.fog_sky_affect = 0.0
			env.fog_aerial_perspective = 0.25
			env.tonemap_exposure = 0.85
			env.adjustment_saturation = 0.85
			env.ambient_light_color = Color(0.78, 0.76, 0.72)
			env.ambient_light_energy = 0.42
		elif c is DirectionalLight3D and (c as DirectionalLight3D).shadow_enabled:
			var sun := c as DirectionalLight3D
			# Sonne von links, flacher als ueber dem Brett: die Felskanten
			# der Terrassen bekommen Licht und Schatten.
			sun.rotation_degrees = Vector3(-42, -62, 0)
			sun.light_energy = 0.95
			sun.directional_shadow_max_distance = 60.0
	frame_yard()


func _make_noise_texture() -> Texture2D:
	var n := FastNoiseLite.new()
	n.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	n.frequency = 0.012
	n.fractal_octaves = 4
	n.seed = 4711
	var img: Image = n.get_seamless_image(512, 512)
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


# --- Hoehenfunktion ---------------------------------------------------------

# Anteil y (Layout) -> Welt z, stueckweise linear durch DEPTH_CURVE.
func plot_depth(y: float) -> float:
	var c: Array = DEPTH_CURVE
	if y <= float(c[0][0]):
		return float(c[0][1])
	for i in range(1, c.size()):
		var a: Array = c[i - 1]
		var b: Array = c[i]
		if y <= float(b[0]):
			var t: float = (y - float(a[0])) / (float(b[0]) - float(a[0]))
			return lerpf(float(a[1]), float(b[1]), t)
	return float(c[c.size() - 1][1])


# Mittlere Kantenlinie einer Terrasse bei x - leicht gewellt, damit die
# Kante wie gewachsener Fels aussieht und nicht wie eine Mauer.
func _edge_z(i: int, x: float) -> float:
	var e: float = float(TERRACES[i]["edge"])
	return e + 0.30 * sin(x * 0.85 + float(i) * 1.7) \
		+ 0.14 * sin(x * 2.3 + float(i) * 0.6)


func _road_x(z: float) -> float:
	return 0.35 * sin(z * 0.45)


# DIE EINE HOEHE. Netz, Gebaeude, Weg und Ausstattung lesen alle hier.
func land_height(x: float, z: float) -> float:
	var h := 0.0
	# Terrassen: jede Stufe hebt alles HINTER ihrer Kante an. An der
	# Wegstelle laeuft die Stufe als Rampe aus statt als Fels.
	var prev := 0.0
	var on_road: float = 1.0 - smoothstep(RAMP_HALF, RAMP_HALF + 0.9,
		absf(x - _road_x(z)))
	for i in range(TERRACES.size() - 1, -1, -1):
		var th: float = float(TERRACES[i]["h"])
		var dh: float = th - prev
		prev = th
		var w: float = lerpf(CLIFF_W, RAMP_W, on_road)
		var ez: float = _edge_z(i, x)
		h += dh * smoothstep(ez + w, ez - w, z)
	# Seitlich Huegel, hinten Berge - beides mit Rauschen.
	var ax: float = absf(x)
	var hill: float = smoothstep(HILL_FROM, HILL_FROM + 8.0, ax)
	h += hill * (2.2 + 2.6 * (_noise.get_noise_2d(x * 0.6, z * 0.6) * 0.5 + 0.5))
	var mt: float = smoothstep(MOUNT_FROM, MOUNT_FROM - 12.0, z)
	var ridge: float = _noise.get_noise_2d(x * 0.35 + 40.0, 7.0) * 0.5 + 0.5
	h += mt * (3.5 + 7.0 * ridge + 2.5 * _noise.get_noise_2d(x * 1.1, z * 1.1))
	# Vorn faellt das Land leicht ab, in ein Tal.
	h -= smoothstep(8.0, 16.0, z) * 0.6
	# Feine Unebenheit, auf dem Plateau schwach.
	h += _noise.get_noise_2d(x * 2.0, z * 2.0) * lerpf(0.05, 0.35, maxf(hill, mt))
	return h


# Wo der Weg ist (0..1) - fuer die Farbe im Netz.
func _path_mask(x: float, z: float, plots: Array) -> float:
	var m := 0.0
	if z > -7.0 and z < 9.5:
		m = 1.0 - smoothstep(ROAD_HALF * 0.6, ROAD_HALF, absf(x - _road_x(z)))
	# Stichwege vom Hauptweg zu jedem Bauplatz.
	for pp in plots:
		var p: Vector3 = pp
		var x0: float = minf(p.x, _road_x(p.z))
		var x1: float = maxf(p.x, _road_x(p.z))
		if x >= x0 - 0.2 and x <= x1 + 0.2:
			var d: float = absf(z - (p.z + 0.85))
			m = maxf(m, 1.0 - smoothstep(0.22, 0.42, d))
	# Platz vor der Burg und am Tor.
	m = maxf(m, 1.0 - smoothstep(1.2, 1.7, Vector2(x, z - 6.6).length()))
	return m


func plot_pos(x: float, y: float) -> Vector3:
	var px: float = (x - 0.5) * YARD_W
	var pz: float = plot_depth(y)
	return Vector3(px, land_height(px, pz), pz)


# --- Gelaendenetz -----------------------------------------------------------

# Rechteckgitter mit feiner Mitte und grobem Rand: die Felskanten brauchen
# feine Schritte, die Berge nicht.
func _axis(lo: float, hi: float, fine_lo: float, fine_hi: float,
		fine: float, coarse: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	var v: float = lo
	while v < hi:
		out.append(v)
		v += fine if (v >= fine_lo and v < fine_hi) else coarse
	out.append(hi)
	return out


func _build_land(fac: String, plots: Array) -> void:
	var xs := _axis(-40.0, 40.0, -11.0, 11.0, 0.22, 1.1)
	var zs := _axis(-45.0, 20.0, -12.0, 10.0, 0.11, 1.1)
	var nx: int = xs.size()
	var nz: int = zs.size()
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var cols := PackedColorArray()
	verts.resize(nx * nz)
	norms.resize(nx * nz)
	cols.resize(nx * nz)
	var e := 0.08
	for j in range(nz):
		for i in range(nx):
			var x: float = xs[i]
			var z: float = zs[j]
			var k: int = j * nx + i
			verts[k] = Vector3(x, land_height(x, z), z)
			var dx: float = land_height(x + e, z) - land_height(x - e, z)
			var dz: float = land_height(x, z + e) - land_height(x, z - e)
			norms[k] = Vector3(-dx, 2.0 * e, -dz).normalized()
			cols[k] = Color(_path_mask(x, z, plots), 0, 0)
	var idx := PackedInt32Array()
	for j in range(nz - 1):
		for i in range(nx - 1):
			var a: int = j * nx + i
			var b: int = a + 1
			var c: int = a + nx
			var d: int = c + 1
			idx.append_array([a, b, c, b, d, c])
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_NORMAL] = norms
	arr[Mesh.ARRAY_COLOR] = cols
	arr[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	if _land == null:
		_land = MeshInstance3D.new()
		_land.name = "Gelaende"
		var mat := ShaderMaterial.new()
		mat.shader = LAND_SHADER
		mat.set_shader_parameter("detail_a", load(DETAIL_TEX % "grass_a"))
		mat.set_shader_parameter("detail_b", load(DETAIL_TEX % "grass_b"))
		mat.set_shader_parameter("detail_dirt", load(DETAIL_TEX % "dirt"))
		mat.set_shader_parameter("noise", _noise_tex)
		_land.material_override = mat
		add_child(_land)
	_land.mesh = mesh
	_apply_look(fac)
	_land_fac = fac


func _apply_look(fac: String) -> void:
	var look: Dictionary = FACTION_LOOK.get(fac, FACTION_LOOK["menschen"])
	var m := _land.material_override as ShaderMaterial
	var g: Array = look["grass"]
	m.set_shader_parameter("grass_dark", g[0])
	m.set_shader_parameter("grass_mid", g[1])
	m.set_shader_parameter("grass_light", g[2])
	m.set_shader_parameter("grass_dry", g[3])
	var r: Array = look["rock"]
	m.set_shader_parameter("rock_dark", r[0])
	m.set_shader_parameter("rock_light", r[1])
	m.set_shader_parameter("path_col", look["path"])
	m.set_shader_parameter("peak_col", look["peak"])
	var s: Array = look["sky"]
	_sky_mat.set_shader_parameter("top_col", s[0])
	_sky_mat.set_shader_parameter("horizon_col", s[1])
	_sky_mat.set_shader_parameter("cloud_col", s[2])
	_sky_mat.set_shader_parameter("cloud_shade", s[3])
	_sky_mat.set_shader_parameter("ground_col", (g[0] as Color).darkened(0.3))
	_sky_mat.set_shader_parameter("cover", float(look["cover"]))
	for c in get_children():
		if c is WorldEnvironment:
			(c as WorldEnvironment).environment.fog_light_color = s[1]


func land_node() -> MeshInstance3D:
	return _land


# --- Aufbau -----------------------------------------------------------------

# ctx:
#   faction    String                    Verzeichnisname (menschen, ...)
#   buildings  Array[{id, x, y, s, built}]
func refresh(ctx: Dictionary) -> void:
	if _meshes.is_empty():
		return
	var fac: String = String(ctx.get("faction", "menschen"))
	var plots: Array = []
	for b in (ctx.get("buildings", []) as Array):
		var bd: Dictionary = b as Dictionary
		plots.append(plot_pos(float(bd.get("x", 0.5)), float(bd.get("y", 0.5))))
	var key: String = "%s|%s" % [fac, str(plots)]
	if _land == null or key != _props_key:
		_build_land(fac, plots)
		_props = _scatter(fac, plots, int(ctx.get("seed", 7)))
		_props_key = key

	var per_model: Dictionary = {}
	for k in _props.keys():
		per_model[k] = (_props[k] as Array).duplicate()
	var add := func(model: String, pos: Vector3, sc: Vector3) -> void:
		if not per_model.has(model):
			per_model[model] = []
		(per_model[model] as Array).append({"pos": pos, "color": Color.WHITE,
			"scale": sc})
	for b in (ctx.get("buildings", []) as Array):
		var bd: Dictionary = b as Dictionary
		var pos: Vector3 = plot_pos(float(bd.get("x", 0.5)), float(bd.get("y", 0.5)))
		var bid: String = String(bd.get("id", ""))
		# Der Groessenfaktor aus dem Layout (Zitadelle 1.05, Kapelle 0.84).
		var sc: float = float(bd.get("s", 1.0)) * building_scale_at(pos)
		var siz := Vector3(sc, sc, sc)
		# Ein Haar tiefer setzen: auf leicht unebenem Grund schwebt sonst
		# eine Ecke.
		pos.y -= 0.04
		if not bool(bd.get("built", false)):
			var site: String = SITE_PREFIX + bid
			add.call(site if _meshes.has(site) else SCAFFOLD, pos, siz)
			continue
		var model: String = "b_%s_%s" % [fac, bid]
		add.call(model if _meshes.has(model) else SCAFFOLD, pos, siz)

	for name in per_model.keys():
		_fill(String(name), per_model[name])
	_clear_except(per_model, [])
	_built = true


# Ausstattung: Baeume auf den Huegeln und am Plateaurand, Felsen am Fuss
# der Terrassenkanten, Gerumpel und Bewuchs zwischen den Gebaeuden.
# Deterministisch und gecacht - refresh laeuft bei jedem Neuzeichnen.
func _scatter(fac: String, plots: Array, sd: int) -> Dictionary:
	var look: Dictionary = FACTION_LOOK.get(fac, FACTION_LOOK["menschen"])
	var out: Dictionary = {}
	var rng := RandomNumberGenerator.new()
	rng.seed = sd * 7919 + hash(fac) + 23
	var put := func(model: String, x: float, z: float, sc: float) -> void:
		if not _meshes.has(model):
			return
		if not out.has(model):
			out[model] = []
		(out[model] as Array).append({
			"pos": Vector3(x, land_height(x, z) - 0.03, z),
			"rot": rng.randf() * TAU, "scale": Vector3(sc, sc, sc),
			"color": Color.WHITE})
	var of := func(prefix: String) -> Array:
		var a: Array = []
		for k in _meshes.keys():
			if String(k).begins_with(prefix):
				a.append(String(k))
		a.sort()
		return a
	var free := func(x: float, z: float, clearance: float) -> bool:
		for pp in plots:
			var p: Vector3 = pp
			if Vector2(x - p.x, z - p.z).length() < clearance:
				return false
		if absf(x - _road_x(z)) < ROAD_HALF + 0.5 and z > -8.0 and z < 10.0:
			return false
		return true

	# Baeume: seitlich auf den Huegeln und hinter dem Plateau, nie mitten
	# in der Stadt.
	var trees: Array = of.call(String(look["tree_prefix"]))
	if trees.is_empty():
		trees = of.call("tree_")
	for i in range(int(look["trees"])):
		var side: float = -1.0 if rng.randf() < 0.5 else 1.0
		# Nicht nah an der Kamera: dort waeren sie riesige Ballen, die das
		# halbe Bild zudecken.
		var x: float = side * rng.randf_range(7.5, 18.0)
		var z: float = rng.randf_range(-18.0, 3.0)
		if not free.call(x, z, 1.8):
			continue
		put.call(String(trees[rng.randi() % trees.size()]), x, z,
			rng.randf_range(1.3, 2.1))
	# Felsbrocken am Fuss jeder Terrassenkante.
	var rocks: Array = of.call("boulder_")
	for t in range(TERRACES.size()):
		for k in range(7):
			var x: float = rng.randf_range(-9.0, 9.0)
			var z: float = _edge_z(t, x) + 0.55
			if not free.call(x, z, 1.4):
				continue
			put.call(String(rocks[rng.randi() % rocks.size()]), x, z,
				rng.randf_range(0.7, 1.3))
	# Buesche am Plateaurand.
	var shrubs: Array = []
	for pre in (look["shrubs"] as Array):
		shrubs += of.call(String(pre))
	for k in range(26):
		var x: float = (-1.0 if rng.randf() < 0.5 else 1.0) * rng.randf_range(5.0, 8.0)
		var z: float = rng.randf_range(-8.0, 8.0)
		if free.call(x, z, 1.3):
			put.call(String(shrubs[rng.randi() % shrubs.size()]), x, z,
				rng.randf_range(1.0, 1.6))
	# Gerumpel und Bewuchs zwischen den Gebaeuden.
	for entry in PROPS:
		var e: Dictionary = entry
		var model: String = String(e["model"])
		var rg: Array = e["scale"]
		for i in range(int(e["n"])):
			var x: float = rng.randf_range(-YARD_W * 0.55, YARD_W * 0.55)
			var z: float = rng.randf_range(-7.0, 8.0)
			if not free.call(x, z, PROP_CLEARANCE):
				continue
			put.call(model, x, z, rng.randf_range(float(rg[0]), float(rg[1])))
	return out


# Die ganze Stadt ins Bild. Die Stadt wird nie gescrollt.
func frame_yard() -> void:
	if _cam == null:
		return
	_cam.position = CAM_POS
	_cam.look_at(CAM_TARGET, Vector3.UP)


# TIPP AUF EINEN BAUPLATZ, im BILD gemessen statt auf dem Boden.
#
# Bis It. 74 schnitt der Strahl die Ebene y = 0 und nahm den naechsten
# Bauplatz. Auf Terrassen und mit Perspektive stimmt das nicht mehr: der
# Strahl auf die Zitadelle trifft y = 0 weit hinter ihr. Jetzt wird jeder
# Bauplatz (Mitte in halber Gebaeudehoehe) ins Bild projiziert, und
# getroffen ist der naechste innerhalb eines Radius, der mit dem Bild
# skaliert.
func plot_at(local: Vector2, plots: Array, radius_frac: float = 0.10) -> Dictionary:
	var best: Dictionary = {}
	var vw: float = float(get_viewport().get_visible_rect().size.x)
	var best_d: float = vw * radius_frac
	for pp in plots:
		var p: Dictionary = pp
		var sp: Vector2 = project_point(plot_anchor(float(p["lx"]), float(p["ly"])))
		var d: float = sp.distance_to(local)
		if d < best_d:
			best_d = d
			best = p
	return best


# Wo ein Bauplatz im Bild "ist": seine Mitte, etwas ueber dem Boden.
func plot_anchor(x: float, y: float) -> Vector3:
	var p: Vector3 = plot_pos(x, y)
	return p + Vector3(0.0, 0.7 * building_scale_at(p), 0.0)


# GROESSE NACH ABSTAND ausgleichen. Mit Perspektive war die Mauer in der
# vordersten Reihe dreimal so gross wie die Zitadelle hinten - genau
# umgekehrt wie gewollt, die Burg ist das wichtigste Gebaeude der Stadt.
# Gebaeude weiter hinten wachsen deshalb mit ihrem Abstand zur Kamera,
# vordere schrumpfen; gekappt, damit die Tiefe sichtbar bleibt.
func building_scale_at(pos: Vector3) -> float:
	var d: float = CAM_POS.distance_to(pos)
	return BUILDING_SCALE * clampf(d / DIST_REF, 0.72, 1.45)


func is_built() -> bool:
	return _built
