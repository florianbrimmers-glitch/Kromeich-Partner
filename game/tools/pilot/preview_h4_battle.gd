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
# In Heroes 4 dominieren die Einheiten das Feld; unsere sind rund halb so
# gross. Nur im Pilot vergroessert - die Spielregel (fit_to_tier) bleibt.
const FIGURE_SCALE := 1.35

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
	# GRUPPEN WIE IM VORBILD (It. 72, zweite Runde). Heroes 4 hat keinen
	# Waldrand ums Feld, sondern lockere Gruppen: ein heller Fels, zwei, drei
	# rote Herbstbuesche, ein gruener Strauch, dazwischen Bodenpflanzen; hier
	# und da ein kahles Baeumchen. Der erste Anlauf mit dichtem Laubwald
	# rundherum sah nach Maerchenwald aus, nicht nach Heroes.
	var of := func(prefix: String) -> Array:
		return kinds.filter(func(k): return String(k).begins_with(prefix))
	var autumn: Array = of.call("shrub_autumn")
	var green: Array = of.call("shrub_green")
	var rocks: Array = of.call("boulder")
	var bare: Array = of.call("bare")
	var plants: Array = of.call("plants")
	var grass: Array = of.call("grass")
	# Zaehler als Array: ein Lambda faengt eine lokale Zahl nur als KOPIE
	# (Falle aus It. 23) - der erste Lauf meldete deshalb 0 Teile.
	var placed := [0]
	var put := func(pool: Array, pos: Vector3, sc: float) -> void:
		if pool.is_empty():
			return
		var proto: MeshInstance3D = protos[pool[rng.randi() % pool.size()]]
		var mi := MeshInstance3D.new()
		mi.mesh = proto.mesh
		mi.position = pos
		mi.rotation.y = rng.randf() * TAU
		mi.scale = Vector3(sc, sc, sc)
		f.add_child(mi)
		placed[0] += 1
	# Gruppen-Mittelpunkte: ausserhalb des Bretts reichlich, auf dem Brett
	# nur zwei als echte Hindernisse (Felder 3,1 und 4,5 bleiben frei von
	# Einheiten).
	var centers: Array = [Vector2(3.0, 1.0), Vector2(4.2, 5.2)]
	for z in range(-8, 16, 3):
		for x in range(-2, 11, 3):
			var c := Vector2(x + rng.randf_range(-1.0, 1.0), z + rng.randf_range(-1.0, 1.0))
			var on_board: bool = c.x > -0.6 and c.x < 7.6 and c.y > -0.6 and c.y < 7.6
			if on_board:
				continue
			# Vor dem Brett nichts Hohes - h / tan(46) verdeckt die Figuren.
			if c.y > 7.6 and c.y < 10.5 and rng.randf() < 0.5:
				continue
			centers.append(c)
	for c in centers:
		var in_front: bool = c.y > 7.6 and c.y < 10.5
		if rng.randf() < 0.7:
			put.call(rocks, Vector3(c.x, 0, c.y), rng.randf_range(0.8, 1.3))
		var n_autumn: int = 0 if in_front else rng.randi_range(1, 3)
		for k in range(n_autumn):
			var a: float = rng.randf() * TAU
			put.call(autumn, Vector3(c.x + cos(a) * 0.7, 0, c.y + sin(a) * 0.6),
				rng.randf_range(0.85, 1.25))
		if rng.randf() < 0.5 and not in_front:
			var a2: float = rng.randf() * TAU
			put.call(green, Vector3(c.x + cos(a2) * 0.6, 0, c.y + sin(a2) * 0.6),
				rng.randf_range(0.8, 1.1))
		for k in range(rng.randi_range(1, 3)):
			put.call(plants, Vector3(c.x + rng.randf_range(-1, 1), 0,
				c.y + rng.randf_range(-1, 1)), rng.randf_range(0.8, 1.2))
	# Vereinzelte kahle Baeumchen, nur hinter dem Brett.
	for k in range(4):
		put.call(bare, Vector3(rng.randf_range(-1.5, 9.0), 0,
			rng.randf_range(-6.0, -1.0)), rng.randf_range(0.9, 1.3))
	# Grasbueschel ueberall, auch auf dem Brett - aber nicht unter Einheiten.
	for k in range(70):
		var gx: float = rng.randf_range(-2.0, 10.0)
		var gz: float = rng.randf_range(-8.0, 15.0)
		if occupied.has(Vector2i(roundi(gx), roundi(gz))):
			continue
		put.call(grass, Vector3(gx, 0, gz), rng.randf_range(0.8, 1.2))
	scene.free()
	return placed[0]


# Weicheres, waermeres Licht als im Spiel - im Vorbild gibt es keine harten
# Glanzflaechen ausser auf den Felsen, und die Farben sind gedeckt.
# Figuren je Instanz um ihren Fusspunkt vergroessern. Die Instanzlage
# bleibt, nur die Basis waechst - so bleibt jede Figur auf ihrem Feld.
func _enlarge_figures(f: Node3D, k: float) -> void:
	for s in STACKS:
		var name: String = String(s["type"])
		if not f._multi.has(name):
			continue
		var mm: MultiMesh = (f._multi[name] as MultiMeshInstance3D).multimesh
		for i in range(mm.instance_count):
			var t: Transform3D = mm.get_instance_transform(i)
			t.basis = t.basis * Basis().scaled(Vector3(k, k, k))
			mm.set_instance_transform(i, t)


func _soften_light(f: Node3D) -> void:
	for c in f.get_children():
		if c is WorldEnvironment:
			var env: Environment = (c as WorldEnvironment).environment
			# GEMESSEN statt geschaetzt: der vorige Lauf lag im Median 30 %
			# zu hell (v 0.55 statt 0.42) und zu gesaettigt (s 0.60 statt
			# 0.46) - quer durch Boden, Fels und Busch, also eine Sache des
			# Lichts, nicht einzelner Farben.
			env.adjustment_enabled = true
			env.adjustment_saturation = OS.get_environment("PILOT_SAT").to_float() if OS.get_environment("PILOT_SAT") != "" else 0.62
			env.tonemap_exposure = OS.get_environment("PILOT_EXP").to_float() if OS.get_environment("PILOT_EXP") != "" else 0.80
			env.ambient_light_color = Color(0.78, 0.76, 0.70)
			env.ambient_light_energy = 0.42
		elif c is DirectionalLight3D and (c as DirectionalLight3D).shadow_enabled:
			var sun := c as DirectionalLight3D
			sun.light_energy = 0.85
			sun.light_color = Color(1.0, 0.94, 0.82)
			sun.shadow_blur = 1.6


func _init() -> void:
	var f = Field.new()
	var paths: Array = [Field.WORLD_PATH, Field.CREATURES_PATH]
	# Eigener Satz zuerst, CC0 darueber: der Goblin fehlt in den freien
	# CC0-Paketen und kommt so aus dem selbst gebauten Satz statt als roter
	# Klotz aus dem Spiel.
	for extra in ["res://pilot_assets/own.glb", CREATURES_CC0]:
		if ResourceLoader.exists(extra):
			paths.append(extra)
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
	_soften_light(f)
	_enlarge_figures(f, FIGURE_SCALE)
	_reach(f, reach)
	var n: int = _props(f)
	for i in range(5):
		await process_frame
	var out := "user://h4-kampf.png"
	var err: int = root.get_texture().get_image().save_png(out)
	print("Kampffeld H4-Pilot: %d Ausstattungsteile, err=%d -> %s"
		% [n, err, ProjectSettings.globalize_path(out)])
	quit(0)
