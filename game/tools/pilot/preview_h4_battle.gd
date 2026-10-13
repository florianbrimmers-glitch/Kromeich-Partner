extends SceneTree

# PILOT (It. 72): das Kampffeld im Stil von Heroes 4.
#
#   xvfb-run -a -s "-screen 0 1040x1485x24" godot --path game/ \
#       --resolution 1040x1485 --script tools/pilot/preview_h4_battle.gd
#
# Vorgabe des Nutzers: "aehnlich wie Heroes 4, nur nicht ganz so
# realistisch", alles in 3D, Speicher ist kein Thema. Der Vergleich mit
# Referenzbildern aus Heroes 4 zeigte als groessten Unterschied den BODEN:
# dort gibt es kein sichtbares Raster, sondern durchgehendes, gemaltes
# Gelaende mit hellen und dunklen Partien und Erdstellen; das Raster zeigt
# sich nur als durchscheinende Flaeche, wenn eine Einheit ihre Reichweite
# zeigt. Ausserdem steht das Feld voller natuerlicher Ausstattung.
#
# Dieses Werkzeug nimmt die ECHTE BattleField3D (Kamera, Licht, Figuren,
# Ringe), blendet deren Kachelboden und Klotz-Deko aus und legt darunter:
#   - eine durchgehende Bodenflaeche mit ground_h4.gdshader
#     (Poly-Haven-Texturen, CC0, Mischung ueber ein Rauschfeld),
#   - die Reichweite als durchscheinende Felder statt Ringen,
#   - Baeume, Bueche, Felsen und Blumen aus "Ultimate Stylized Nature"
#     (Quaternius, CC0), falls game/pilot_assets/nature.glb existiert.
#
# Nichts davon aendert das Spiel - es ist ein Pilot zur Entscheidung.

const Field := preload("res://scripts/ui/BattleField3D.gd")
const SHADER := preload("res://tools/pilot/ground_h4.gdshader")
const TEX := "res://pilot_assets/tex/%s.jpg"
const NATURE := "res://pilot_assets/nature.glb"
const CREATURES_CC0 := "res://pilot_assets/cc0.glb"

const STACKS := [
	{"pos": Vector2i(1, 2), "type": "men_spearman", "side": 0, "active": true},
	{"pos": Vector2i(1, 4), "type": "men_archer", "side": 0},
	{"pos": Vector2i(1, 6), "type": "men_cavalier", "side": 0},
	{"pos": Vector2i(6, 2), "type": "ork_goblin", "side": 1},
	{"pos": Vector2i(6, 4), "type": "ork_wolfrider", "side": 1},
	{"pos": Vector2i(6, 6), "type": "ork_behemoth", "side": 1},
]


func _noise_texture() -> Texture2D:
	var n := FastNoiseLite.new()
	n.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	n.frequency = 0.012
	n.fractal_octaves = 4
	n.seed = 4711
	var img: Image = n.get_seamless_image(512, 512)
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


# Strukturkarte aus einem Foto: Helligkeit je Pixel geteilt durch den
# Mittelwert, als Wert/2 gespeichert (0.5 = Mittel), mit Mipmaps. Im Shader
# ergibt das einen Faktor um 1.0 - unabhaengig davon, in welchem Farbraum
# Godot das Foto sonst liefern wuerde.
func _detail_map(name: String) -> Texture2D:
	var img := Image.load_from_file(ProjectSettings.globalize_path(TEX % name))
	img.convert(Image.FORMAT_RGB8)
	var w: int = img.get_width()
	var h: int = img.get_height()
	var lum := PackedFloat32Array()
	lum.resize(w * h)
	var sum := 0.0
	for y in range(h):
		for x in range(w):
			var c: Color = img.get_pixel(x, y)
			var l: float = c.r * 0.299 + c.g * 0.587 + c.b * 0.114
			lum[y * w + x] = l
			sum += l
	var mean: float = maxf(0.01, sum / float(w * h))
	var out := Image.create(w, h, false, Image.FORMAT_L8)
	for y in range(h):
		for x in range(w):
			var v: float = clampf(lum[y * w + x] / mean * 0.5, 0.0, 1.0)
			out.set_pixel(x, y, Color(v, v, v))
	out.generate_mipmaps()
	return ImageTexture.create_from_image(out)


func _ground(f: Node3D) -> void:
	var mat := ShaderMaterial.new()
	mat.shader = SHADER
	mat.set_shader_parameter("detail_a", _detail_map("leafy_grass"))
	mat.set_shader_parameter("detail_b", _detail_map("sparse_grass"))
	mat.set_shader_parameter("detail_dirt", _detail_map("dirt_aerial_02"))
	if OS.get_environment("PILOT_DETAIL") != "":
		mat.set_shader_parameter("detail", float(OS.get_environment("PILOT_DETAIL")))
	mat.set_shader_parameter("noise", _noise_texture())
	var pm := PlaneMesh.new()
	pm.size = Vector2(48, 48)
	pm.subdivide_width = 1
	pm.subdivide_depth = 1
	var mi := MeshInstance3D.new()
	mi.mesh = pm
	mi.material_override = mat
	mi.position = Vector3(3.5, -0.002, 3.5)
	f.add_child(mi)


# Reichweite als durchscheinende Felder - in Heroes 4 die einzige Stelle,
# an der man das Raster ueberhaupt sieht.
func _reach(f: Node3D, cells: Array) -> void:
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_color = Color(0.95, 0.95, 0.80, 0.22)
	var pm := PlaneMesh.new()
	pm.size = Vector2(0.93, 0.93)
	for c in cells:
		var mi := MeshInstance3D.new()
		mi.mesh = pm
		mi.material_override = mat
		mi.position = Vector3(float(c.x), 0.01, float(c.y))
		f.add_child(mi)


# Ausstattung aus dem Natur-Paket: deterministisch gestreut, nie auf einem
# Feld mit Einheit, und am Brettrand dichter als in der Mitte - so steht
# Heroes 4 auch aus.
func _props(f: Node3D) -> int:
	if not ResourceLoader.exists(NATURE):
		return 0
	var scene := (load(NATURE) as PackedScene).instantiate()
	var protos: Dictionary = {}
	for c in scene.get_children():
		if c is MeshInstance3D:
			protos[String(c.name)] = c
	var occupied: Dictionary = {}
	for s in STACKS:
		occupied[s["pos"]] = true
	var rng := RandomNumberGenerator.new()
	rng.seed = 90210
	var kinds: Array = protos.keys()
	kinds.sort()
	var big: Array = kinds.filter(func(k): return String(k).begins_with("tree"))
	var mid: Array = kinds.filter(func(k): return String(k).begins_with("bush") or String(k).begins_with("rock"))
	var small: Array = kinds.filter(func(k): return String(k).begins_with("flower") or String(k).begins_with("grass") or String(k).begins_with("fern"))
	var placed := 0
	# HINDERNISSE AUF DEM BRETT: wie in Heroes 4 stehen ein paar Felsen und
	# Bueche als echte Hindernisse im Feld.
	var obstacle_cells := {Vector2i(3, 1): "rock", Vector2i(4, 5): "bush",
		Vector2i(4, 2): "rock"}
	for z in range(-8, 16):
		for x in range(-2, 10):
			var cell := Vector2i(x, z)
			var on_board: bool = x >= 0 and x < 8 and z >= 0 and z < 8
			if on_board and occupied.has(cell):
				continue
			var pool: Array = []
			var chance: float = 0.0
			if obstacle_cells.has(cell):
				pool = mid.filter(func(k): return String(k).begins_with(obstacle_cells[cell]))
				chance = 1.0
			elif on_board:
				pool = small
				chance = 0.35
			elif z < 0:
				# Hinter dem Brett: Waldrand. Hoch darf es hier sein - es
				# ragt im Bild nach OBEN, vom Brett weg.
				var r: float = rng.randf()
				pool = big if r < 0.55 else (mid if r < 0.85 else small)
				chance = 0.9
			elif z < 12:
				# DAVOR NUR NIEDRIGES. Bei 46 Grad verdeckt ein Baum von 3
				# Zellen Hoehe h / tan(46) = 2.9 Reihen ueber sich - stuende er
				# direkt unter dem Brett, laege seine Krone auf den Figuren.
				# Die Regel aus It. 53, die der erste Anlauf wieder vergessen
				# hatte: Reiter und Behemoth verschwanden unter dem Laub.
				pool = mid if rng.randf() < 0.45 else small
				chance = 0.7
			else:
				pool = big if rng.randf() < 0.6 else mid
				chance = 0.9
			if pool.is_empty() or rng.randf() > chance:
				continue
			var proto: MeshInstance3D = protos[pool[rng.randi() % pool.size()]]
			var mi := MeshInstance3D.new()
			mi.mesh = proto.mesh
			var jitter: float = 0.0 if obstacle_cells.has(cell) else 0.35
			mi.position = Vector3(float(x) + rng.randf_range(-jitter, jitter), 0.0,
				float(z) + rng.randf_range(-jitter, jitter))
			mi.rotation.y = rng.randf() * TAU
			var sc: float = rng.randf_range(0.85, 1.2)
			mi.scale = Vector3(sc, sc, sc)
			f.add_child(mi)
			placed += 1
	scene.free()
	return placed


func _init() -> void:
	var f = Field.new()
	var paths: Array = [Field.WORLD_PATH, Field.CREATURES_PATH]
	if ResourceLoader.exists(CREATURES_CC0):
		paths.append(CREATURES_CC0)
	f.model_paths = paths
	root.add_child(f)
	await process_frame
	var reach: Array = []
	for x in range(0, 4):
		for z in range(0, 6):
			if absi(x - 1) + absi(z - 2) <= 3 and Vector2i(x, z) != Vector2i(1, 2):
				reach.append(Vector2i(x, z))
	f.refresh({"cols": 8, "rows": 8, "terrain": 0, "seed": 7,
		"stacks": STACKS, "obstacles": [], "move": [], "targets": []})
	f.frame_board(8, 8)
	# Kachelboden und Klotz-Deko ausblenden - der neue Boden liegt darunter.
	for k in f._multi.keys():
		var name: String = String(k)
		if name.begins_with("bt_") or name.begins_with("t_") \
				or name.begins_with("deco_"):
			(f._multi[k] as Node3D).visible = false
	_ground(f)
	_reach(f, reach)
	var n: int = _props(f)
	for i in range(5):
		await process_frame
	var out := "user://h4-kampf.png"
	var err: int = root.get_texture().get_image().save_png(out)
	print("Kampffeld H4-Pilot: %d Ausstattungsteile, err=%d -> %s"
		% [n, err, ProjectSettings.globalize_path(out)])
	quit(0)
