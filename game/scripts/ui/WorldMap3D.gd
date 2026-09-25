extends "res://scripts/ui/Scene3D.gd"

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
# Laden, Beleuchtung, Kamera, MultiMesh und die Umrechnung Bildpunkt ->
# Zelle stehen in Scene3D.gd - sie sind bei Karte, Kampf und Stadt
# dieselben.

const MODELS_PATH := "res://assets/models/world.glb"

# Kachelbreite. Scene3D.CELL ist die eine Wahrheit darueber; der Name
# TILE bleibt, weil die Weltkarte im ganzen Projekt von Kacheln spricht.
const TILE := 1.0

# Nebel: unerforscht wird gar nicht gezeichnet, erkundet abgedunkelt.
# Dieselben Stufen wie in der 2D-Karte (FOG_HIDDEN/EXPLORED/VISIBLE).
const FOG_DIM := Color(0.42, 0.45, 0.52)
# Sichtbar, aber diesen Zug nicht erreichbar. Die 2D-Karte legt dafuer ein
# schwarzes Alpha von 0.30 ueber die Kachel; hier ist es ein Faktor auf die
# Instanzfarbe. Erreichbar bleibt VOLL hell - genau dieser Unterschied ist
# die Reichweiten-Anzeige, nicht der Ring.
const OUT_OF_REACH := Color(0.52, 0.55, 0.60)
# KEIN RING MEHR AUF ERREICHBAREN FELDERN (It. 62).
#
# Bis It. 61 lag auf jedem erreichbaren Feld ein heller Reifen. Ohne Licht
# war das noetig - da unterschieden sich hell und dunkel kaum. Mit Sonne,
# Schatten und der staerkeren Abdunklung nicht erreichbarer Felder
# (OUT_OF_REACH von 0.62 auf 0.52) sagt die HELLIGKEIT die Reichweite, und
# dreissig Reifen darueber sahen aus wie Seifenblasen auf der Wiese. Die
# Konstante bleibt als Beleg, was hier frueher stand.
const REACH_RING := Color(1.0, 1.0, 1.0, 0.0)

# Deko-Dichte je Gelaendeart: nicht jede Waldkachel bekommt einen Baum,
# sonst wird die Flaeche zur Mauer und man sieht die Kachelgrenzen nicht
# mehr. Zahl ist "von sechs".
const DECO_CHANCE := {"forest": 5, "mountain": 4, "swamp": 3}

# BODENBEWUCHS (It. 62). Zahl der Streuteile je Kachel und Gelaendeart.
# Bis It. 61 war eine Wiese eine Flaeche in genau einem Gruen - das ist
# der Hauptgrund, warum die Karte nach 2010 aussah. Wasser bleibt leer,
# Gebirge hat schon seine Felsen.
const SCATTER_COUNT := {"grass": 3, "sand": 1, "swamp": 2, "forest": 2}
# Was gestreut wird, als Anteile von sechs. Gras ueberall, Blumen selten -
# eine Wiese voller Blumen liest sich als Beet, nicht als Wiese.
const SCATTER_MIX := ["deco_grass", "deco_grass", "deco_grass",
	"deco_grass", "deco_flower", "deco_stone"]
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

var _built: bool = false


func _init() -> void:
	model_paths = [MODELS_PATH]
	pitch_deg = -34.0
	cam_up = 11.0


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
	var by_scatter: Dictionary = {}
	for name in SCATTER_MIX:
		by_scatter[name] = []
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
				# Leichte Streuung auch hier: als exakt gleiche Platten
				# lasen sich die unerforschten Felder als Karopapier.
				var fs: float = 0.86 + float(hash3(x, y, sd + 53) % 22) * 0.01
				(by_terrain[FOG_MODEL] as Array).append({
					"pos": Vector3(float(x) * TILE, 0.0, float(y) * TILE),
					"color": Color(fs, fs, fs * 1.04),
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
			# EINE WIESE IST NICHT EINE FARBE. Ein Hauch Streuung je
			# Kachel (deterministisch, damit sie beim Neuzeichnen nicht
			# flimmert) nimmt der Flaeche das Gleichmaessige, noch bevor
			# irgendein Halm darauf steht.
			var shade: float = 0.94 + float(hash3(x, y, sd + 31) % 13) * 0.01
			col = Color(col.r * shade, col.g * shade, col.b * shade, col.a)
			(by_terrain[TERRAIN_MODEL[t]] as Array).append({
				"pos": Vector3(float(x) * TILE, 0.0, float(y) * TILE),
				"color": col,
			})
			var key: String = TERRAIN_MODEL[t].substr(2)
			_scatter(by_scatter, key, x, y, sd, top, col)
			if DECO_CHANCE.has(key) and hash3(x, y, sd) % 6 < int(DECO_CHANCE[key]):
				var hh: int = hash3(x, y, sd + 7)
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
	for name in by_scatter.keys():
		_fill(String(name), by_scatter[name])

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
	# Gelaende und Deko sind oben schon vollstaendig gesetzt.
	_clear_except(per_model, ["t_", "deco_"])


# Bodenbewuchs auf EINER Kachel. Ort, Drehung, Groesse und Art kommen aus
# demselben deterministischen Wuerfel wie die uebrige Deko - waechselte
# der Bewuchs bei jedem Neuzeichnen den Platz, waere die Karte unruhig und
# nicht wiedererkennbar (die Lehre aus _tile_variant in der 2D-Karte).
func _scatter(into: Dictionary, key: String, x: int, y: int, sd: int,
		top: float, col: Color) -> void:
	var n: int = int(SCATTER_COUNT.get(key, 0))
	for i in range(n):
		var h: int = hash3(x, y, sd + 101 + i * 17)
		var model: String = SCATTER_MIX[h % SCATTER_MIX.size()]
		if not into.has(model):
			into[model] = []
		# Nicht bis an die Kachelkante: sonst waechst der Halm halb auf der
		# Nachbarkachel und die Grenze franst aus.
		var dx: float = (float((h / 7) % 100) / 100.0 - 0.5) * 0.66
		var dz: float = (float((h / 700) % 100) / 100.0 - 0.5) * 0.66
		var sc: float = 0.75 + float((h / 70000) % 60) * 0.01
		(into[model] as Array).append({
			"pos": Vector3(float(x) * TILE + dx, top, float(y) * TILE + dz),
			"rot": float(h % 360) * PI / 180.0,
			"scale": Vector3(sc, sc, sc),
			"color": col,
		})


# Kamera auf denselben Ausschnitt wie die 2D-Karte: `center` ist die
# Kachel in der Bildmitte, `tiles_across` wie viele Kacheln in die Breite
# passen. Die Rechnung selbst steht in Scene3D.
func look_at_map(center: Vector2, tiles_across: float) -> void:
	look_at_cells(center, tiles_across)


# Bildpunkt -> Kachel. `viewport_size` wird nicht mehr gebraucht (die
# Kamera kennt ihren Viewport selbst), bleibt aber im Aufruf, weil der
# WorldMapScreen und die Suite damit lesbarer sind.
func tile_at(screen_pos: Vector2, _viewport_size: Vector2) -> Vector2i:
	return cell_at(screen_pos)


func is_built() -> bool:
	return _built
