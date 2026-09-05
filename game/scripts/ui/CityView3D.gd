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
const ROAD_FRAC := 0.16

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
	model_paths = [MODELS_PATH]
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
	# Boden und Weg sind 1x1 gebaut und werden hier auf den Hof gezogen -
	# so steht die Hofgroesse nur an EINER Stelle.
	add.call("city_ground", Vector3.ZERO, Vector3(YARD_W, 1.0, YARD_D))
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

	for name in per_model.keys():
		_fill(String(name), per_model[name])
	_clear_except(per_model, [])
	_built = true


# Den ganzen Hof ins Bild. Die Stadt wird nie gescrollt.
func frame_yard() -> void:
	look_at_cells(Vector2(0.0, 0.6), YARD_W + 1.2)


func is_built() -> bool:
	return _built
