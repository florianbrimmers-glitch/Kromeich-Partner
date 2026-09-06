extends "res://scripts/ui/Scene3D.gd"

# Raeumliche Ansicht der Stadt (It. 56).
#
# ZWEITE ANSICHT, KEIN ERSATZ - wie Weltkarte und Kampffeld. Der
# 2D-Stadtschirm bleibt, bis diese hier gleichauf ist; Bauregeln, Kosten
# und Anwerben sind davon nicht beruehrt.
#
# KEINE LOGIK HIER. Alles kommt ueber `refresh(ctx)`.
#
# DIE BAUPLAETZE KOMMEN AUS data/city_layout.json - derselben Datei, aus
# der die 2D-Ansicht und tools/gen_city_bg.py lesen. Eigene Koordinaten
# waeren eine dritte Wahrheit ueber dieselbe Stadt.

const MODELS_PATH := "res://assets/models/city.glb"
# Der Bodenbewuchs kommt aus der WELTKARTE - dieselben Grasbuschel,
# Blumen und Steine, die dort seit It. 62 stehen. Zwei Saetze davon waeren
# zwei Wahrheiten darueber, wie Gras in diesem Spiel aussieht.
const WORLD_PATH := "res://assets/models/world.glb"

# Was im Hof herumsteht, und wie oft. Die Zahlen sind auf einen Hof von
# 6 x 13 Einheiten gemuenzt; sie ergeben rund achtzig Teile, also gut ein
# Teil pro Quadrateinheit freier Flaeche.
const PROPS := [
	{"model": "deco_grass", "n": 54, "scale": [0.8, 1.6]},
	{"model": "deco_stone", "n": 16, "scale": [0.7, 1.4]},
	{"model": "deco_flower", "n": 12, "scale": [0.8, 1.3]},
	{"model": "city_barrel", "n": 7, "scale": [0.9, 1.2]},
	{"model": "city_crate", "n": 6, "scale": [0.9, 1.3]},
	{"model": "city_cart", "n": 2, "scale": [1.0, 1.2]},
	{"model": "city_lamp", "n": 4, "scale": [0.9, 1.1]},
	{"model": "city_tree", "n": 5, "scale": [0.8, 1.4]},
]
# Abstand, den Gerumpel von einem Bauplatz haelt. Darunter steht das Fass
# im Gebaeude - und ein Baum vor der Tuer verdeckt die Beschriftung.
const PROP_CLEARANCE := 1.15

# Der Hof in Weltmetern. Die Datei gibt x und y als Anteil von 0 bis 1;
# hier wird daraus eine Flaeche. 300 px Gebaeudebreite sind 2.0 Einheiten
# (siehe UNIT in tools/gen_city3d.py), also rund ein Drittel der Hofbreite
# - dasselbe Verhaeltnis wie auf dem 2D-Schirm.
#
# DER HOF IST HOCH UND SCHMAL, nicht quadratisch: das Layout
# `buildings_plain` stellt die neun Plaetze in ZWEI Spalten und fuenf
# Reihen auf, und der Stadtschirm ist ein Hochformat. Der erste Anlauf war
# 7 breit und 6 tief - damit standen die Gebaeude Schulter an Schulter,
# die Beschriftungen lagen auf den Daechern der naechsten Reihe, und die
# untere Haelfte des Schirms blieb leer.
const YARD_W := 6.0
const YARD_D := 13.0

# Breite des Wegs, als Anteil der Hofbreite.
const ROAD_FRAC := 0.13

# STEILER als Weltkarte und Kampffeld, obwohl die Stadt von Silhouetten
# lebt - weil sie die hoechsten Modelle des Spiels hat. Ein Gebaeude der
# Hoehe h verdeckt h / tan(Neigung) Einheiten Hof dahinter: bei -32 Grad
# das 1.6-fache, bei einer 2.5 hohen Zitadelle also vier Einheiten, und
# damit zwei ganze Bauplatz-Reihen. Bei -44 Grad ist es noch das
# 1.04-fache. Flacher sah der Hof aus wie eine Reihe uebereinander
# geschobener Daecher.
const PITCH := -44.0

# Ungebaut: das Geruest steht an derselben Stelle wie das Gebaeude spaeter.
const SCAFFOLD := "city_scaffold"

var _built: bool = false


func _init() -> void:
	model_paths = [MODELS_PATH, WORLD_PATH]
	pitch_deg = PITCH
	cam_up = 7.0
	# Die Stadt hat keine Markierungsringe - nichts hier braucht Alpha.
	transparent_prefix = ""


# Anteil (0..1) aus city_layout.json -> Ort im Hof.
func plot_pos(x: float, y: float) -> Vector3:
	return Vector3((x - 0.5) * YARD_W, 0.0, (y - 0.5) * YARD_D)


# ctx:
#   faction    String                    Verzeichnisname (menschen, ...)
#   buildings  Array[{id, x, y, built}]
#   plaza      Dictionary {x, y}         optional
func refresh(ctx: Dictionary) -> void:
	if _meshes.is_empty():
		return
	var fac: String = String(ctx.get("faction", "menschen"))
	var per_model: Dictionary = {}
	var add := func(model: String, pos: Vector3, sc: Vector3) -> void:
		if not per_model.has(model):
			per_model[model] = []
		(per_model[model] as Array).append({"pos": pos, "color": Color.WHITE,
			"scale": sc})

	var one := Vector3.ONE
	# DER HOF WIRD GEKACHELT, nicht als eine Flaeche gezogen.
	#
	# Zuerst lag hier eine einzige grosse Platte, und um ihr das
	# Gleichmaessige zu nehmen, habe ich flache "Flicken" darauf gestreut.
	# Als gedrehte Quadrate lasen sie sich als Blatt Papier, als Siebenecke
	# als Fliesenmuster - beides schlechter als vorher. Der Fehler war die
	# Idee: ein Flicken mit harter Kante sieht immer nach Form aus.
	#
	# Die Weltkarte loest dasselbe Problem seit It. 62 anders und besser:
	# sie streut die FARBE JE KACHEL. Weil die Kacheln ohnehin aneinander
	# stossen, hat die Streuung keine Kanten. Genau das hier auch - 6 x 13
	# Bodenkacheln, jede eine Nuance anders.
	for gz in range(int(YARD_D)):
		for gx in range(int(YARD_W)):
			# SPANNE 0.96 bis 1.035, nicht 0.90 bis 1.10. Eine Hofkachel
			# ist auf dem Schirm gut doppelt so gross wie eine Kachel der
			# Weltkarte - dieselbe Streuung liest sich hier als
			# Schachbrett statt als Boden.
			var sh: float = 0.96 + float(hash3(gx, gz, 17) % 16) * 0.005
			if not per_model.has("city_ground"):
				per_model["city_ground"] = []
			(per_model["city_ground"] as Array).append({
				"pos": Vector3(float(gx) - YARD_W * 0.5 + 0.5, 0.0,
					float(gz) - YARD_D * 0.5 + 0.5),
				"color": Color(sh, sh, sh * 0.98),
				"scale": one,
			})
	add.call("city_road", Vector3.ZERO,
		Vector3(YARD_W * ROAD_FRAC, 1.0, YARD_D))
	var pz: Dictionary = ctx.get("plaza", {}) as Dictionary
	if not pz.is_empty():
		add.call("city_plaza", plot_pos(float(pz.get("x", 0.5)),
			float(pz.get("y", 0.85))), one)

	for b in (ctx.get("buildings", []) as Array):
		var bd: Dictionary = b as Dictionary
		var pos: Vector3 = plot_pos(float(bd.get("x", 0.5)),
			float(bd.get("y", 0.5)))
		# UNGEBAUT ZEIGT DAS GERUEST, nicht nichts. Ein leerer Platz saehe
		# aus wie ein Fehler; genauso macht es die 2D-Ansicht mit
		# construction.svg.
		if not bool(bd.get("built", false)):
			add.call(SCAFFOLD, pos, one)
			continue
		var model: String = "b_%s_%s" % [fac, String(bd.get("id", ""))]
		if not _meshes.has(model):
			add.call(SCAFFOLD, pos, one)
			continue
		add.call(model, pos, one)

	_scatter_props(per_model, ctx, int(ctx.get("seed", 7)))

	_scatter_road(per_model, int(ctx.get("seed", 7)))

	for name in per_model.keys():
		_fill(String(name), per_model[name])
	_clear_except(per_model, [])
	_built = true


# Pflaster auf dem Weg. Es liegt IN der Wegbreite, nicht darueber hinaus -
# sonst franst der Weg aus, statt gepflastert zu wirken.
func _scatter_road(per_model: Dictionary, sd: int) -> void:
	if not _meshes.has("city_cobble"):
		return
	var half: float = YARD_W * ROAD_FRAC * 0.5 - 0.12
	for i in range(46):
		var h: int = hash3(i, 3, sd + 4201)
		var px: float = (float(h % 1000) / 1000.0 - 0.5) * half * 2.0
		var pz: float = (float((h / 1000) % 1000) / 1000.0 - 0.5) * YARD_D * 0.96
		var sc: float = 0.75 + float((h / 100000) % 70) * 0.01
		if not per_model.has("city_cobble"):
			per_model["city_cobble"] = []
		(per_model["city_cobble"] as Array).append({
			"pos": Vector3(px, 0.0, pz),
			"rot": float(h % 360) * PI / 180.0,
			"scale": Vector3(sc, sc, sc),
			"color": Color.WHITE,
		})


# Gerumpel im Hof. Deterministisch aus dem Seed, damit es beim
# Neuzeichnen nicht springt - dieselbe Regel wie beim Bodenbewuchs der
# Weltkarte. Was zu nah an einem Bauplatz landet, faellt weg: sonst steht
# das Fass im Gebaeude oder der Baum vor der Beschriftung.
func _scatter_props(per_model: Dictionary, ctx: Dictionary, sd: int) -> void:
	var plots: Array = []
	for b in (ctx.get("buildings", []) as Array):
		var bd: Dictionary = b as Dictionary
		plots.append(plot_pos(float(bd.get("x", 0.5)), float(bd.get("y", 0.5))))
	var idx: int = 0
	for entry in PROPS:
		var e: Dictionary = entry
		var model: String = String(e["model"])
		if not _meshes.has(model):
			continue
		for i in range(int(e["n"])):
			idx += 1
			var h: int = hash3(idx, int(e["n"]), sd + 811)
			# 0.84 statt 0.94: ein gedrehtes Quadrat ragt an den Ecken
			# ueber seine Kantenlaenge hinaus, und Flicken am Hofrand
			# standen deshalb halb im Nichts.
			var px: float = (float(h % 1000) / 1000.0 - 0.5) * YARD_W * 0.84
			var pz: float = (float((h / 1000) % 1000) / 1000.0 - 0.5) \
				* YARD_D * 0.9
			var too_close := false
			for pp in plots:
				if Vector2(px - (pp as Vector3).x, pz - (pp as Vector3).z) \
						.length() < PROP_CLEARANCE:
					too_close = true
					break
			if too_close:
				continue
			var rng: Array = e["scale"]
			var sc: float = float(rng[0]) + float((h / 100000) % 100) * 0.01 \
				* (float(rng[1]) - float(rng[0]))
			if not per_model.has(model):
				per_model[model] = []
			(per_model[model] as Array).append({
				"pos": Vector3(px, 0.0, pz),
				"rot": float(h % 360) * PI / 180.0,
				"scale": Vector3(sc, sc, sc),
				"color": Color.WHITE,
			})


# Den ganzen Hof ins Bild. Die Stadt wird nie gescrollt.
func frame_yard() -> void:
	look_at_cells(Vector2(0.0, 0.6), YARD_W + 1.2)


func is_built() -> bool:
	return _built
