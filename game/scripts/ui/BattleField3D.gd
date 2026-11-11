extends "res://scripts/ui/Scene3D.gd"

# Raeumliche Ansicht des Schlachtfelds (It. 54).
#
# ZWEITE ANSICHT, KEIN ERSATZ - wie bei der Weltkarte. Der 2D-Kampfschirm
# bleibt, bis diese hier gleichauf ist; Kampfmathematik, Zugreihenfolge und
# Balance sind davon nicht beruehrt.
#
# KEINE LOGIK HIER. Alles kommt ueber `refresh(ctx)`. Diese Datei weiss
# nicht, was ein Konterschlag ist - nur, wo etwas steht und welches Modell
# es traegt.
#
# HEROES-4-STIL (It. 73, Pilot It. 72, vom Nutzer abgenommen): durchgehender
# gemalter Boden statt Kacheln, kein sichtbares Raster ausser der
# Reichweite, das Feld voller Gruppen aus Felsen und Herbstbueschen, weiches
# Licht, grosse Figuren.

const CREATURES_PATH := "res://assets/models/creatures.glb"
const WORLD_PATH := "res://assets/models/world.glb"
# NACH creatures.glb geladen: ob_stone und ob_bush aus dieser Datei ersetzen
# die alten Hindernis-Kloetze, ohne dass sich die Zuordnung aendert.
const NATURE_PATH := "res://assets/models/nature.glb"
const GROUND_SHADER := preload("res://scripts/ui/battle_ground.gdshader")
const DETAIL_TEX := "res://assets/textures/battle/detail_%s.png"

# Gelaendeart -> Aussehen. Reihenfolge ist MapGen.TILE_*, wie in WorldMap3D.
# Wasser gibt es als Schlachtfeld nicht; dort wird auf Sand gekaempft
# (Kuestenkampf), sonst stuenden die Einheiten im Meer.
#
# Farben: Palette des Bodenshaders (dunkel, mittel, hell, trocken, Erde).
# Die Wiese ist am Heroes-4-Kampfbild gemessen (Median #4e6b3a, trocken
# #73603e), die anderen sind davon abgeleitet.
# Ausstattung: je Gruppe Wahrscheinlichkeit fuer einen Fels, Hoechstzahl
# Herbstbuesche, Wahrscheinlichkeit fuer einen gruenen Strauch; dazu kahle
# Baeumchen und Baeume hinter dem Brett.
const TERRAIN_LOOK := [
	{"name": "Wiese", "pal": [Color(0.25, 0.34, 0.19), Color(0.31, 0.42, 0.23),
		Color(0.34, 0.49, 0.23), Color(0.45, 0.40, 0.25), Color(0.47, 0.39, 0.25)],
		"dirt": 0.70, "rock": 0.7, "autumn": 3, "green": 0.5, "bare": 4, "trees": 0},
	{"name": "Wald", "pal": [Color(0.17, 0.27, 0.13), Color(0.22, 0.33, 0.16),
		Color(0.27, 0.38, 0.18), Color(0.33, 0.30, 0.18), Color(0.33, 0.26, 0.17)],
		"dirt": 0.72, "rock": 0.4, "autumn": 1, "green": 0.8, "bare": 2, "trees": 10},
	{"name": "Sand", "pal": [Color(0.55, 0.47, 0.31), Color(0.63, 0.55, 0.37),
		Color(0.70, 0.62, 0.43), Color(0.45, 0.45, 0.27), Color(0.50, 0.40, 0.27)],
		"dirt": 0.66, "rock": 0.9, "autumn": 0, "green": 0.2, "bare": 3, "trees": 0},
	{"name": "Gebirge", "pal": [Color(0.33, 0.33, 0.27), Color(0.40, 0.39, 0.32),
		Color(0.46, 0.45, 0.37), Color(0.38, 0.40, 0.25), Color(0.36, 0.33, 0.28)],
		"dirt": 0.62, "rock": 1.0, "autumn": 1, "green": 0.3, "bare": 2, "trees": 0},
	{"name": "Kueste", "pal": [Color(0.55, 0.47, 0.31), Color(0.63, 0.55, 0.37),
		Color(0.70, 0.62, 0.43), Color(0.45, 0.45, 0.27), Color(0.50, 0.40, 0.27)],
		"dirt": 0.66, "rock": 0.9, "autumn": 0, "green": 0.2, "bare": 3, "trees": 0},
	{"name": "Sumpf", "pal": [Color(0.17, 0.22, 0.13), Color(0.22, 0.28, 0.16),
		Color(0.28, 0.32, 0.18), Color(0.30, 0.32, 0.16), Color(0.22, 0.20, 0.14)],
		"dirt": 0.60, "rock": 0.3, "autumn": 0, "green": 0.6, "bare": 6, "trees": 0},
]

# Reichweite als durchscheinende FELDER statt Ringe - in Heroes 4 die
# einzige Stelle, an der man das Raster ueberhaupt sieht. Ringe gibt es nur
# noch unter Einheiten.
const MOVE_CELL := Color(0.95, 0.95, 0.80, 0.24)
const TARGET_CELL := Color(1.0, 0.35, 0.30, 0.38)
const ZONE_CELL := Color(0.40, 0.62, 0.95, 0.32)

# In Heroes 4 beherrschen die Einheiten das Feld; nach fit_to_tier sind
# unsere gut halb so gross. Nur die AUFSTELLUNG waechst - die Modelle und
# ihre Groessenregel bleiben, der Kontaktbogen bleibt vergleichbar.
#
# UM EINEN FESTEN BETRAG, NICHT UM EINEN FAKTOR. Im Pilot wuchs alles um
# 35 Prozent; im Spiel stehen die Stapel dicht an dicht, und ein um ein
# Drittel vergroesserter Knochendrache lag halb auf der Lich daneben.
# Jede Figur waechst jetzt um FIGURE_GROW in ihrer Raumdiagonale - kleine
# also um bis zu 35 Prozent, Stufe 7 um rund 20. Weil fuer alle derselbe
# Betrag dazukommt, bleibt die Reihenfolge der Groessen erhalten.
const FIGURE_GROW := 0.42
const FIGURE_SCALE_MAX := 1.35

# Licht, GEMESSEN am Vorbild (It. 72b): mit den Standardwerten aus Scene3D
# lag das Feld im Median 30 % zu hell und deutlich zu gesaettigt.
const LIGHT_EXPOSURE := 0.80
const LIGHT_SATURATION := 0.62

# Seitenfarben. Dieselbe Sprache wie auf der Weltkarte: das Modell zeigt
# WAS dort steht, der Ring darunter WEM es gehoert.
const SIDE_COLOR := [Color(1.0, 0.90, 0.45), Color(0.90, 0.30, 0.28)]
# Der Stack, der gerade zieht. Weiss statt der Seitenfarbe: die Frage "wer
# ist dran" ist eine andere als "wem gehoert das", und zwei Rottoene
# nebeneinander waeren nicht zu unterscheiden.
const ACTIVE_RING := Color(1.0, 1.0, 1.0, 0.95)
# Der Stapel, den man gerade umstellt.
const PICKED_RING := Color(0.55, 0.85, 1.0, 0.95)

# Hindernisart -> Modell. Die Zahlen sind Obstacles.KIND (0 Stein,
# 1 Baumstamm, 2 Busch, 3 Sumpfloch, 4 Mauer) und stehen wie im
# TacticalBattleScreen als Literale da: cross-class class_name-Referenzen
# sind im Android-Export unzuverlaessig.
const OBSTACLE_MODEL := {0: "ob_stone", 1: "ob_log", 2: "ob_bush",
	3: "ob_swamp", 4: "ob_wall"}

# Blickrichtung: die Modelle schauen im glb nach +Z (zur Kamera). Eine
# Drehung um Y bildet +Z auf (sin a, 0, cos a) ab - fuer +X also +90 Grad.
# Spieler steht links und schaut nach rechts, der Gegner umgekehrt.
const FACING := [PI * 0.5, -PI * 0.5]

# Steiler als die Weltkarte (-34): das Brett ist nur 8x8 und wird nie
# gescrollt. Steiler heisst dreierlei - weniger Verdeckung durch grosse
# Kreaturen, groessere Trefferflaeche je Zelle, und das Brett nutzt die
# Hoehe des Schirms besser: seine Bildhoehe waechst mit sin(Neigung), bei
# -46 Grad also um ein Achtel gegenueber -40. Noch steiler saehe wieder
# aus wie die 2D-Ansicht.
const PITCH := -46.0

# DER RAND UM DAS BRETT (It. 69): der Boden reicht bis an den Bildrand,
# sonst waeren 55 Prozent des Kampfschirms schwarz. Seit It. 73 ist der
# Boden EINE Flaeche; apron_rect sagt, wie gross sie sein muss und wo die
# Ausstattung steht.
#
# Notbremse: bei einem entarteten Seitenverhaeltnis (Viewport noch 0 hoch)
# darf der Rand nicht ins Unendliche wachsen.
const APRON_MAX := 26

var _built: bool = false
var _ground: MeshInstance3D = null
var _ground_terrain: int = -1
# Ausstattung je (Gelaende, Seed, Brett) einmal gerechnet: refresh laeuft bei
# jedem Neuzeichnen, waehrend Animationen also dutzendfach je Sekunde.
var _props_key: String = ""
var _props: Dictionary = {}


func _init() -> void:
	model_paths = [WORLD_PATH, CREATURES_PATH, NATURE_PATH]
	pitch_deg = PITCH
	cam_up = 9.0


func _ready() -> void:
	super()
	_register_cell_marker()
	_soften_light()


# Durchscheinendes Feld fuer die Reichweite, als eigenes "Modell", damit es
# wie alles andere ueber _fill und MultiMesh laeuft.
func _register_cell_marker() -> void:
	var pm := PlaneMesh.new()
	pm.size = Vector2(0.93, 0.93) * CELL
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.vertex_color_use_as_albedo = true
	pm.material = mat
	_meshes["marker_cell"] = pm


func _soften_light() -> void:
	for c in get_children():
		if c is WorldEnvironment:
			var env: Environment = (c as WorldEnvironment).environment
			if env == null:
				continue
			env.adjustment_enabled = true
			env.adjustment_saturation = LIGHT_SATURATION
			env.tonemap_exposure = LIGHT_EXPOSURE
			env.ambient_light_color = Color(0.78, 0.76, 0.70)
			env.ambient_light_energy = 0.42
		elif c is DirectionalLight3D and (c as DirectionalLight3D).shadow_enabled:
			var sun := c as DirectionalLight3D
			sun.light_energy = 0.85
			sun.light_color = Color(1.0, 0.94, 0.82)
			sun.shadow_blur = 1.6


# Rauschen fuer Flecken und Wolkenschatten - einmal je Ansicht, nativ
# gerechnet (FastNoiseLite), nicht pixelweise in GDScript.
func _noise_texture() -> Texture2D:
	var n := FastNoiseLite.new()
	n.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	n.frequency = 0.012
	n.fractal_octaves = 4
	n.seed = 4711
	var img: Image = n.get_seamless_image(512, 512)
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


func _ensure_ground(terrain: int, cols: int, rows: int) -> void:
	if _ground == null:
		var mat := ShaderMaterial.new()
		mat.shader = GROUND_SHADER
		mat.set_shader_parameter("detail_a", load(DETAIL_TEX % "grass_a"))
		mat.set_shader_parameter("detail_b", load(DETAIL_TEX % "grass_b"))
		mat.set_shader_parameter("detail_dirt", load(DETAIL_TEX % "dirt"))
		mat.set_shader_parameter("noise", _noise_texture())
		_ground = MeshInstance3D.new()
		_ground.name = "Boden"
		_ground.mesh = PlaneMesh.new()
		_ground.material_override = mat
		add_child(_ground)
	if terrain != _ground_terrain:
		var look: Dictionary = TERRAIN_LOOK[terrain]
		var pal: Array = look["pal"]
		var m := _ground.material_override as ShaderMaterial
		var keys := ["grass_dark", "grass_mid", "grass_light", "grass_dry",
			"dirt_col"]
		for i in range(keys.size()):
			m.set_shader_parameter(keys[i], pal[i])
		m.set_shader_parameter("dirt_amount", float(look["dirt"]))
		_ground_terrain = terrain
	# Groesse aus derselben Rechnung wie die Ausstattung, plus Rand.
	var r: Rect2i = apron_rect(cols, rows)
	(_ground.mesh as PlaneMesh).size = Vector2(r.size.x + 2, r.size.y + 2) * CELL
	_ground.position = Vector3((r.position.x + r.size.x * 0.5 - 0.5) * CELL,
		-0.002, (r.position.y + r.size.y * 0.5 - 0.5) * CELL)


# Wie viele Bodenflaechen es gibt - fuer den Test, der headless keine
# Positionen lesen kann.
func ground_node() -> MeshInstance3D:
	return _ground


# AUSSTATTUNG IN GRUPPEN wie im Vorbild: ein heller Fels, ein paar
# Herbstbuesche, ein gruener Strauch, Bodenpflanzen; dazu kahle Baeumchen
# hinter dem Brett und vereinzelte Grasbueschel.
#
# AUF DEM BRETT NUR GRAS. Alles, was hoeher ist, saehe aus wie ein
# Hindernis - und Hindernisse kommen ausschliesslich aus der Kampflogik.
# VOR DEM BRETT NICHTS HOHES: bei 46 Grad verdeckt die Hoehe h genau
# h / tan(46) Reihen ueber sich - ein Busch direkt unter dem Brett laege mit
# seiner Krone auf den Figuren der untersten Reihe (It. 53, It. 72).
# Unabhaengig von den Einheiten, damit nichts springt, wenn jemand zieht.
func _scatter_props(cols: int, rows: int, terrain: int, sd: int) -> Dictionary:
	var key: String = "%d/%d/%d/%d" % [cols, rows, terrain, sd]
	if key == _props_key:
		return _props
	var look: Dictionary = TERRAIN_LOOK[terrain]
	var out: Dictionary = {}
	var rng := RandomNumberGenerator.new()
	rng.seed = sd * 7919 + terrain * 104729 + 17
	var of := func(prefix: String) -> Array:
		var a: Array = []
		for k in _meshes.keys():
			if String(k).begins_with(prefix):
				a.append(k)
		a.sort()
		return a
	var rocks: Array = of.call("boulder_")
	var autumn: Array = of.call("shrub_autumn_")
	var green: Array = of.call("shrub_green_")
	var bare: Array = of.call("bare_")
	var plants: Array = of.call("plants_")
	var grass: Array = of.call("grass_")
	var trees: Array = of.call("tree_")
	var put := func(pool: Array, pos: Vector3, sc: float) -> void:
		if pool.is_empty():
			return
		var name: String = String(pool[rng.randi() % pool.size()])
		# DIE SPERRE GILT JE TEIL, NICHT JE GRUPPE. Zuerst stand sie nur an
		# der Gruppenmitte - Buesche und Pflanzen werden aber um bis zu eine
		# Zelle versetzt und landeten auf Randfeldern (der Test hat es
		# gemeldet, im Bild sah es nach einem Hindernis aus).
		if not name.begins_with("grass_") and pos.x > -0.6 \
				and pos.x < cols - 0.4 and pos.z > -0.6 and pos.z < rows - 0.4:
			return
		if not out.has(name):
			out[name] = []
		(out[name] as Array).append({"pos": pos, "rot": rng.randf() * TAU,
			"scale": Vector3(sc, sc, sc), "color": Color.WHITE})
	var r: Rect2i = apron_rect(cols, rows)
	var x0: float = r.position.x
	var x1: float = r.position.x + r.size.x
	var z0: float = r.position.y
	var z1: float = r.position.y + r.size.y
	var front0: float = rows - 0.4
	var front1: float = rows + 2.6
	var gz: float = z0
	while gz < z1:
		var gx: float = x0
		while gx < x1:
			var c := Vector2(gx + rng.randf_range(-1.0, 1.0),
				gz + rng.randf_range(-1.0, 1.0))
			gx += 3.0
			var on_board: bool = c.x > -0.7 and c.x < cols - 0.3 \
				and c.y > -0.7 and c.y < rows - 0.3
			if on_board:
				continue
			var in_front: bool = c.y > front0 and c.y < front1
			if rng.randf() < float(look["rock"]) and not in_front:
				put.call(rocks, Vector3(c.x, 0, c.y), rng.randf_range(0.8, 1.3))
			var n_autumn: int = 0 if in_front else rng.randi_range(0, int(look["autumn"]))
			for k in range(n_autumn):
				var a: float = rng.randf() * TAU
				put.call(autumn, Vector3(c.x + cos(a) * 0.7, 0, c.y + sin(a) * 0.6),
					rng.randf_range(0.85, 1.25))
			if rng.randf() < float(look["green"]) and not in_front:
				var a2: float = rng.randf() * TAU
				put.call(green, Vector3(c.x + cos(a2) * 0.6, 0, c.y + sin(a2) * 0.6),
					rng.randf_range(0.8, 1.1))
			for k in range(rng.randi_range(1, 3)):
				put.call(plants, Vector3(c.x + rng.randf_range(-1, 1), 0,
					c.y + rng.randf_range(-1, 1)), rng.randf_range(0.8, 1.2))
		gz += 3.0
	# Kahle Baeumchen und (im Wald) Baeume nur HINTER dem Brett.
	for k in range(int(look["bare"])):
		put.call(bare, Vector3(rng.randf_range(x0, x1), 0,
			rng.randf_range(z0, -1.2)), rng.randf_range(0.9, 1.3))
	for k in range(int(look["trees"])):
		put.call(trees, Vector3(rng.randf_range(x0, x1), 0,
			rng.randf_range(z0, -1.6)), rng.randf_range(0.85, 1.15))
	# Grasbueschel ueberall, auch auf dem Brett - sie sind niedrig genug.
	for k in range(int((x1 - x0) * (z1 - z0) * 0.22)):
		put.call(grass, Vector3(rng.randf_range(x0, x1), 0,
			rng.randf_range(z0, z1)), rng.randf_range(0.8, 1.2))
	_props_key = key
	_props = out
	return out


# ctx:
#   cols/rows   int
#   terrain     int               Gelaendeart des Bodens (MapGen.TILE_*)
#   seed        int               fuer die Streuung der Bodendeko
#   stacks      Array[{pos, type, side, active}]
#   obstacles   Array[{pos, kind}]  kind: "rock" | "tree"
#   move        Array[Vector2i]   Felder, die der aktive Stack erreicht
#   targets     Array[Vector2i]   Felder, die er angreifen kann
#   zone        Array[Vector2i]   erlaubte Flaeche der Aufstellungsphase
#   picked      Vector2i          Stapel, der gerade umgestellt wird (oder -1)
func refresh(ctx: Dictionary) -> void:
	if _meshes.is_empty():
		return
	var cols: int = int(ctx.get("cols", 8))
	var rows: int = int(ctx.get("rows", 8))
	if cols <= 0 or rows <= 0:
		return
	var terrain: int = clampi(int(ctx.get("terrain", 0)), 0,
		TERRAIN_LOOK.size() - 1)
	var sd: int = int(ctx.get("seed", 0))

	var per_model: Dictionary = {}
	var add := func(model: String, cell: Vector2i, y: float, rot: float,
			col: Color) -> void:
		if not per_model.has(model):
			per_model[model] = []
		(per_model[model] as Array).append({
			"pos": Vector3(float(cell.x) * CELL, y, float(cell.y) * CELL),
			"rot": rot, "color": col,
		})

	_ensure_ground(terrain, cols, rows)
	var props: Dictionary = _scatter_props(cols, rows, terrain, sd)
	for name in props.keys():
		per_model[name] = (props[name] as Array).duplicate()

	var picked: Vector2i = ctx.get("picked", Vector2i(-1, -1))
	var ring: Array = []
	var cells: Array = []
	var lift := Vector3(0.0, 0.012, 0.0)
	for m in (ctx.get("move", []) as Array):
		cells.append({"pos": _cell_pos(m as Vector2i) + lift, "color": MOVE_CELL})
	for t in (ctx.get("targets", []) as Array):
		cells.append({"pos": _cell_pos(t as Vector2i) + lift, "color": TARGET_CELL})
	for z in (ctx.get("zone", []) as Array):
		cells.append({"pos": _cell_pos(z as Vector2i) + lift, "color": ZONE_CELL})
	if not cells.is_empty():
		per_model["marker_cell"] = cells

	for o in (ctx.get("obstacles", []) as Array):
		var od: Dictionary = o as Dictionary
		var cell: Vector2i = od["pos"]
		var kind: int = int(od.get("kind", 0))
		var model: String = String(OBSTACLE_MODEL.get(kind, "ob_stone"))
		if kind == 4 and bool(od.get("cracked", false)):
			model = "ob_wall_cracked"
		# Mauern stehen in Reih und Glied - eine gedrehte Mauer waere ein
		# Loch in der Belagerung. Alles andere wird gestreut, damit die
		# Hindernisse nicht wie ein Muster aussehen.
		var rot: float = 0.0 if kind == 4 \
			else float(hash3(cell.x, cell.y, sd) % 360) * PI / 180.0
		add.call(model, cell, 0.0, rot, Color.WHITE)

	for s in (ctx.get("stacks", []) as Array):
		var sd2: Dictionary = s as Dictionary
		var cell2: Vector2i = sd2["pos"]
		var side: int = clampi(int(sd2.get("side", 0)), 0, 1)
		# Ausfallschritt und Gleiten: der Stapel steht datenseitig schon auf
		# seinem Zielfeld, der Effekt zieht ihn optisch zurueck. Der Ring
		# darunter bleibt auf dem FELD - er sagt, wo der Stapel steht, nicht
		# wo seine Figur gerade ist.
		var off: Vector2 = sd2.get("offset", Vector2.ZERO)
		if not per_model.has(String(sd2.get("type", ""))):
			per_model[String(sd2.get("type", ""))] = []
		(per_model[String(sd2.get("type", ""))] as Array).append({
			"pos": _cell_pos(cell2) + Vector3(off.x * CELL, 0.0, off.y * CELL),
			"rot": FACING[side], "color": Color.WHITE,
			"scale": Vector3.ONE * figure_scale(String(sd2.get("type", ""))),
		})
		var rc: Color = SIDE_COLOR[side]
		if bool(sd2.get("active", false)):
			rc = ACTIVE_RING
		if cell2 == picked:
			rc = PICKED_RING
		ring.append({"pos": _cell_pos(cell2), "color": rc})
	if not ring.is_empty():
		per_model["marker_ring"] = ring

	for name in per_model.keys():
		_fill(String(name), per_model[name])
	_clear_except(per_model, [])
	_built = true


# Vergroesserung einer Figur im Kampf (siehe FIGURE_GROW). Oeffentlich, damit
# der Test dieselbe Regel prueft statt sie nachzubauen.
func figure_scale(model: String) -> float:
	if not _meshes.has(model):
		return 1.0
	var d: float = (_meshes[model] as Mesh).get_aabb().size.length()
	if d <= 0.001:
		return 1.0
	return clampf(1.0 + FIGURE_GROW / d, 1.0, FIGURE_SCALE_MAX)


func _cell_pos(cell: Vector2i) -> Vector3:
	return Vector3(float(cell.x) * CELL, 0.0, float(cell.y) * CELL)


# Kamera so, dass das ganze Brett im Bild ist - das Schlachtfeld wird nie
# gescrollt, anders als die Weltkarte.
# Wie viele Zellreihen die Kamera ueber die Hoehe zeigt. Aus DENSELBEN
# Zahlen, mit denen frame_board die Kamera setzt - eine zweite Kopie waere
# die Doppelung, an der It. 36/37 und It. 42 gescheitert sind.
func _visible_half_depth(cols: int) -> float:
	var vp := get_viewport()
	if vp == null:
		return float(cols)
	var vs: Vector2 = Vector2(vp.get_visible_rect().size)
	if vs.x <= 0.0 or vs.y <= 0.0:
		return float(cols)
	var aspect: float = vs.x / vs.y
	var half_screen: float = (float(cols) + 1.0) * 0.5 / maxf(0.05, aspect)
	return half_screen / sin(deg_to_rad(absf(PITCH)))


# Welcher Zellbereich mit Boden belegt wird - Brett UND Rand. Oeffentlich,
# damit tools/test_creatures3d.gd dieselbe Rechnung benutzt statt einer
# zweiten Kopie: headless sind die MultiMesh-Transformationen nicht
# auslesbar (sie liefern alle den Ursprung, wie get_instance_color seit
# It. 58), also ist die ANZAHL das Einzige, was ein Test sehen kann.
func apron_rect(cols: int, rows: int) -> Rect2i:
	var half_w: float = (float(cols) + 1.0) * 0.5
	var half_d: float = _visible_half_depth(cols)
	var cx: float = float(cols - 1) * 0.5
	var cz: float = float(rows - 1) * 0.5
	var x0: int = maxi(int(floor(cx - half_w)) - 1, -APRON_MAX)
	var x1: int = mini(int(ceil(cx + half_w)) + 1, cols + APRON_MAX)
	var z0: int = maxi(int(floor(cz - half_d)) - 1, -APRON_MAX)
	var z1: int = mini(int(ceil(cz + half_d)) + 1, rows + APRON_MAX)
	return Rect2i(x0, z0, x1 - x0 + 1, z1 - z0 + 1)


func frame_board(cols: int, rows: int) -> void:
	look_at_cells(Vector2(float(cols - 1) * 0.5, float(rows - 1) * 0.5),
		float(cols) + 1.0)


func is_built() -> bool:
	return _built
