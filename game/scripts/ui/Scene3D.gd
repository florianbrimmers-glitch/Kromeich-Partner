extends Node3D

# Gemeinsamer Unterbau der raeumlichen Ansichten (It. 54).
#
# WARUM ES IHN GIBT: Weltkarte, Kampffeld und Stadt zeigen voellig
# verschiedene Dinge, aber sie laden Modelle aus einem glb, schalten
# dieselben Materialschalter, stellen ueber MultiMesh auf, leuchten gleich
# und schauen unter derselben festen Neigung auf ein Gitter. Stuende das
# dreimal im Code, liefe es beim naechsten Umbau auseinander - dieselbe
# Falle wie die nachgebaute Nachbarschaft im Durchspiel-Test (It. 42).
#
# KEINE SPIELLOGIK. Wie beim CityScreen kommt alles ueber `refresh(ctx)`
# der Unterklasse herein. Dieser Unterbau weiss nicht, was ein Monster
# oder eine Einheit ist - nur, wo etwas steht und welches Modell es traegt.

# Zellbreite in Weltmetern. Die Generatoren bauen mit 1.0, also ist eine
# Zelle eine Einheit - jede andere Zahl waere eine zweite Wahrheit ueber
# dieselbe Groesse.
const CELL := 1.0

# Von der Unterklasse VOR dem Betreten des Baums zu setzen.
var model_paths: Array = []
# Feste Neigung (gewaehlte Variante: schraeg von oben, nicht drehbar).
# Flacher als 30 Grad kippt das Feld optisch weg, steiler als 45 sieht
# wieder aus wie 2D.
var pitch_deg: float = -34.0
# Hoehe der Kamera ueber der Ebene, in Zellen. Der Abstand nach hinten
# wird daraus GERECHNET (siehe look_at_cells) - zwei freie Zahlen waeren zwei
# Wahrheiten ueber denselben Blickpunkt.
var cam_up: float = 11.0
# Modelle, deren Instanzfarbe ein Alpha tragen darf (Markierungen).
var transparent_prefix: String = "marker_"

var _meshes: Dictionary = {}
var _multi: Dictionary = {}
var _cam: Camera3D = null


func _ready() -> void:
	load_models()
	_build_lighting()
	_build_camera()


func load_models() -> void:
	for path in model_paths:
		var packed := load(String(path)) as PackedScene
		if packed == null:
			push_error("Modelldatei fehlt: " + String(path))
			continue
		var src := packed.instantiate()
		for ch in src.get_children():
			if ch is MeshInstance3D:
				var m: Mesh = (ch as MeshInstance3D).mesh
				_enable_instance_color(m)
				if transparent_prefix != "" \
						and String(ch.name).begins_with(transparent_prefix):
					_enable_transparency(m)
				_meshes[String(ch.name)] = m
		src.queue_free()


# Die Farbe je Aufstellung wirkt NUR, wenn das Material sie auch benutzt.
#
# WIE DAS AUFFIEL (It. 53): auf dem ersten Bild schien der Nebel zu
# funktionieren - am Rand lagen dunklere Kacheln. Das waren aber Wald und
# Gebirge, die von Haus aus dunkler sind. Erst eine Messung
# (vertex_color_use_as_albedo je Material ausgeben) zeigte, dass der
# Schalter ueberall aus stand und damit KEINE Instanzfarbe ankam - kein
# Nebel, keine Besitzerfarbe, keine Bedrohungsfarbe. Sichtbar war davon
# eine weisse Scheibe, die rot sein sollte.
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
	if m == null:
		return
	for i in range(m.get_surface_count()):
		var mat := m.surface_get_material(i) as StandardMaterial3D
		if mat != null:
			mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA


func _build_lighting() -> void:
	# SONNE, HIMMEL, SCHATTEN (It. 62). Vorher: zwei Richtungslichter ohne
	# Schatten und ein festes graues Umgebungslicht - das ergibt flache
	# Farbflaechen ohne Volumen, egal wie gut die Modelle sind. Ein Koerper
	# wird erst raeumlich, wenn er etwas verdeckt.
	#
	# Der Himmel ist hier KEINE Kulisse, sondern die zweite Lichtquelle:
	# `AMBIENT_SOURCE_SKY` faerbt die Schattenseiten blaeulich, waehrend die
	# Sonne warm ist. Dieser Gegensatz macht den groessten Teil des
	# Eindrucks aus - mehr als jedes zusaetzliche Modelldetail.
	# SONNENSTAND: von vorn-links oben, nicht von hinten.
	#
	# ZWEI FEHLVERSUCHE, UND WARUM DIE MITTE STIMMT:
	#
	# (a) Azimut -130, Hoehe 52: Licht von hinten. Die Oberseiten brannten
	#     weiss aus, und genau die Flaechen, die die Kamera sieht, lagen im
	#     Dunkeln.
	# (b) Azimut -38, Hoehe 46: Licht von vorn. Die Flaechen stimmten - und
	#     der Schatten fiel nach HINTEN, also aus Sicht der Kamera direkt
	#     hinter die Figur, wo sie ihn selbst verdeckt. Auf dem Musterblatt
	#     war kein einziger Schatten zu sehen, obwohl alle eingeschaltet
	#     waren; ich habe erst an den Einstellungen gesucht und dann die
	#     Werte zur Laufzeit ausgelesen - sie stimmten alle.
	#
	# Jetzt von hinten-links, aber STEIL (58 Grad): der Schatten faellt
	# kurz nach vorn-rechts und bleibt sichtbar, und weil das Licht steil
	# steht, bekommen die senkrechten Flaechen genug ab.
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-58, -118, 0)
	sun.light_color = Color(1.0, 0.95, 0.86)
	sun.light_energy = 0.95
	sun.shadow_enabled = true
	# SCHATTENMODUS AUF STANDARD LASSEN.
	#
	# Hier stand SHADOW_ORTHOGONAL (ein einzelner Ausschnitt) zusammen mit
	# directional_shadow_max_distance = 45. Beides klang vernuenftig - die
	# Ansichten sind flach und begrenzt. Das Ergebnis war, dass ueberhaupt
	# kein Schatten mehr erschien, waehrend ein isolierter Testfall mit
	# denselben Lichtwerten und den STANDARD-Einstellungen sofort welche
	# zeigte. Mit einer orthogonalen Kamera passt Godot den Ausschnitt
	# offenbar anders an, als ich angenommen habe. Der Standard
	# (vier Teilausschnitte) tut hier das Richtige, also bleibt er.
	# KEIN shadow_normal_bias, KEIN shadow_blur, KEIN
	# light_angular_distance. Alle drei standen hier, um die Schattenkante
	# weicher zu machen - und zusammen haben sie den Schatten unter einer
	# 0.7 hohen Figur komplett wegg­eschoben. Ein isolierter Testfall mit
	# denselben Lichtwerten, aber Standard-Einstellungen zeigte den
	# Schatten sofort; das war der Unterschied. Weiche Kanten kann man
	# nachtraeglich suchen, wenn ueberhaupt ein Schatten da ist.
	add_child(sun)

	# Schwaches Gegenlicht von vorn-rechts: es rettet die der Sonne
	# abgewandten Silhouetten davor, im Schatten zu verschwinden. Ohne
	# Schatten (bis It. 61) war es das Hauptmittel, jetzt nur noch Beiwerk.
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-18, 55, 0)
	fill.light_energy = 0.22
	fill.light_color = Color(0.72, 0.84, 1.0)
	add_child(fill)

	var we := WorldEnvironment.new()
	we.environment = _make_environment()
	add_child(we)


# Eigene Funktion, damit die Vorschauwerkzeuge und spaetere Ansichten
# dieselbe Stimmung bekommen und nicht jede ihre eigene baut.
func _make_environment() -> Environment:
	var env := Environment.new()

	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Color(0.32, 0.52, 0.80)
	sky_mat.sky_horizon_color = Color(0.72, 0.80, 0.86)
	sky_mat.ground_bottom_color = Color(0.26, 0.24, 0.20)
	sky_mat.ground_horizon_color = Color(0.60, 0.58, 0.50)
	sky_mat.sun_angle_max = 24.0
	sky_mat.sun_curve = 0.12
	var sky := Sky.new()
	sky.sky_material = sky_mat
	env.sky = sky
	# DER HIMMEL IST LICHT, NICHT KULISSE. Als Hintergrund (BG_SKY) stand
	# im ersten Anlauf ein blaues Rechteck ueber der Karte und ein braunes
	# darunter, mit harter Kante dazwischen - die Karte schwamm in einer
	# Landschaft, die es gar nicht gibt. Der Hintergrund bleibt dunkel und
	# neutral wie bisher; die Sky-Ressource dient nur noch als Quelle fuer
	# das Umgebungslicht.
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.07, 0.09, 0.12)
	# UMGEBUNGSLICHT ALS FARBE, nicht aus dem Himmel.
	#
	# Mit AMBIENT_SOURCE_SKY war die Fuellhelligkeit so hoch, dass die
	# Schattenseite fast so hell blieb wie die Sonnenseite - die Schatten
	# waren gerechnet, gerendert und trotzdem unsichtbar. Ein Schatten
	# entsteht nicht durch die Lichtquelle, sondern durch den UNTERSCHIED
	# zu ihr. Ein kuehler, kontrollierter Farbwert macht denselben Dienst
	# (blaeuliche Schattenseiten neben warmer Sonne) und laesst sich
	# einstellen.
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	# Kuehl, aber nicht BLAU. Mit (0.52, 0.62, 0.80) faerbte das
	# Umgebungslicht die nach oben schauenden Flaechen so stark ein, dass
	# aus dem dunklen Nebelfeld ein Meer wurde.
	env.ambient_light_color = Color(0.64, 0.68, 0.76)
	env.ambient_light_energy = 0.34
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	# TONWERTKORREKTUR. Ohne sie brennen helle Flaechen (Sand, Knochen,
	# Dachschnee) einfach auf Weiss aus und alles Dunkle saeuft ab -
	# genau der Eindruck von "flach". Filmic haelt beide Enden.
	# ACES statt Filmic, und Weisspunkt 1.6 statt 4.0. Mit 4.0 lag alles im
	# unteren Drittel der Kurve: die Wiese wurde blass, das Wasser stumpf,
	# und der Gewinn an Schatten ging als Verlust an Farbe wieder heraus.
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	# Weisspunkt 1.7: Sonne (0.95) und Umgebungslicht (0.34) ergeben auf
	# einer nach oben schauenden Flaeche zusammen rund 1.3. Liegt der
	# Weisspunkt darunter, clippt genau das - und der Hof, die Wiese und
	# der Sand wurden pastellig. Das war der Grund, warum die ersten
	# Versuche "blass" aussahen, nicht die Farben der Modelle.
	env.tonemap_white = 1.7
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.22
	env.adjustment_contrast = 1.04
	return env


func _build_camera() -> void:
	_cam = Camera3D.new()
	# ORTHOGONAL, nicht perspektivisch: eine Zelle ist dann ueberall gleich
	# gross. Mit Perspektive waeren Felder am oberen Rand kleiner, und die
	# Trefferflaeche fuer den Finger dort kleiner als unten.
	_cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	# `size` soll die BREITE in Zellen sein. Godot legt sie sonst auf die
	# Hoehe, und auf einem 720x1280-Schirm hiesse "15" dann 8.4 Zellen quer
	# - der Name der Zahl haette das Gegenteil ihrer Wirkung gesagt.
	_cam.keep_aspect = Camera3D.KEEP_WIDTH
	_cam.rotation_degrees = Vector3(pitch_deg, 0, 0)
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
		# Farbe je Aufstellung: so faerbt ein Nebel eine einzelne Zelle ab,
		# ohne dass es ein zweites Modell braucht.
		mmi.multimesh.use_colors = true
		mmi.multimesh.mesh = _meshes[model]
		add_child(mmi)
		_multi[model] = mmi
	var mm: MultiMesh = mmi.multimesh
	mm.instance_count = items.size()
	for i in range(items.size()):
		var it: Dictionary = items[i]
		var b := Basis(Vector3.UP, float(it.get("rot", 0.0)))
		# Massstab je Aufstellung: so kann ein Modell von 1x1 auf die
		# tatsaechliche Groesse gezogen werden, statt seine Masse ein
		# zweites Mal im Generator zu hinterlegen (der Hofboden ist genau
		# dieser Fall).
		if it.has("scale"):
			b = b.scaled(it["scale"] as Vector3)
		var t := Transform3D(b, it["pos"] as Vector3)
		mm.set_instance_transform(i, t)
		mm.set_instance_color(i, it.get("color", Color.WHITE))


# Alle Aufstellungen ausser den genannten leeren. Ohne das bleiben Reste
# der letzten Runde stehen - ein gefallener Held zum Beispiel.
func _clear_except(keep: Dictionary, keep_prefixes: Array) -> void:
	for name in _multi.keys():
		if keep.has(name):
			continue
		var skip := false
		for pre in keep_prefixes:
			if String(name).begins_with(String(pre)):
				skip = true
				break
		if not skip:
			(_multi[name] as MultiMeshInstance3D).multimesh.instance_count = 0


# Kamera auf einen Ausschnitt setzen: `center` ist die Zelle in der
# Bildmitte, `cells_across` wie viele Zellen in die Breite passen.
# NICHT `look_at` nennen: Node3D hat schon eines mit anderer Signatur, und
# Godot lehnt die Ueberdeckung zurecht ab - der eigene Aufruf waere nie
# gelaufen.
func look_at_cells(center: Vector2, cells_across: float) -> void:
	if _cam == null:
		return
	_cam.size = maxf(4.0, cells_across)
	# Der ABSTAND nach hinten folgt aus Hoehe und Neigung, er ist keine
	# freie Zahl: der Mittelstrahl der Kamera muss genau auf `center`
	# treffen. Mit einem festen Wert lag der Blickpunkt vier Zellen vor dem
	# Ziel - die Figur sass unterhalb der Bildmitte, und je nach Neigung
	# waere der Fehler anders gross.
	var pitch: float = deg_to_rad(absf(pitch_deg))
	var back: float = cam_up / tan(pitch)
	_cam.position = Vector3(center.x * CELL, cam_up * CELL,
		(center.y + back) * CELL)
	_cam.rotation_degrees = Vector3(pitch_deg, 0, 0)


# Bildpunkt -> Zelle. Der Strahl der Kamera wird mit der Ebene y = 0
# geschnitten.
#
# BEKANNTE UNGENAUIGKEIT: erhoehtes Gelaende wird an seinem FUSS getroffen,
# nicht an der sichtbaren Oberflaeche - ein Tipp auf eine Bergspitze landet
# eine Zelle dahinter. Das ist dieselbe Vereinfachung, die HoMM3 macht, und
# sie haelt Tipp und Wegfindung konsistent: gelaufen wird auf der Ebene.
func cell_at(screen_pos: Vector2) -> Vector2i:
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
	return Vector2i(int(round(hit.x / CELL)), int(round(hit.z / CELL)))


# Zelle -> Bildpunkt. Die Gegenrichtung zu cell_at, fuer alles, was als
# FLACHE SCHRIFT ueber der raeumlichen Ansicht liegen muss: Stapelgroessen
# zum Beispiel. Text im Raum waere entweder schraeg gestellt (schlecht
# lesbar) oder ein Billboard, das seine Zelle verlaesst.
func project_cell(cell: Vector2i, y: float = 0.0) -> Vector2:
	return project_point(Vector3(float(cell.x) * CELL, y, float(cell.y) * CELL))


func project_point(world: Vector3) -> Vector2:
	if _cam == null:
		return Vector2.ZERO
	return _cam.unproject_position(world)


# Bildpunkt -> Punkt auf der Ebene y = 0, ungerundet. cell_at rundet das
# auf eine Zelle; wo es kein Zellgitter gibt (die Stadt hat Bauplaetze,
# kein Raster), braucht man den Punkt selbst.
func ground_at(screen_pos: Vector2) -> Vector3:
	if _cam == null:
		return Vector3.ZERO
	var from: Vector3 = _cam.project_ray_origin(screen_pos)
	var dir: Vector3 = _cam.project_ray_normal(screen_pos)
	if absf(dir.y) < 0.0001:
		return Vector3.ZERO
	return from + dir * (-from.y / dir.y)


# Wie viele Bildpunkte eine Zelle breit ist - das Mass, an dem sich
# Schriftgroessen und Abstaende der Ueberlagerung ausrichten.
func cell_pixels() -> float:
	if _cam == null or _cam.size <= 0.0:
		return 1.0
	var vp := _cam.get_viewport()
	if vp == null:
		return 1.0
	return float(vp.get_visible_rect().size.x) / _cam.size


# Deterministische Streuung - dieselbe Begruendung wie bei _tile_variant in
# der 2D-Karte: waechselte die Deko bei jedem Neuzeichnen ihren Platz,
# waere das Bild unruhig und nicht wiedererkennbar.
func hash3(x: int, y: int, salt: int) -> int:
	var h: int = (x * 73856093) ^ (y * 19349663) ^ (salt * 83492791)
	h = (h ^ (h >> 13)) * 1274126177
	return absi(h ^ (h >> 16))
