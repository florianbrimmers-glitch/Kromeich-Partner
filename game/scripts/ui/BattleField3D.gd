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
# DER BODEN KOMMT AUS DER WELTKARTE. Gekaempft wird auf dem Gelaende, auf
# dem man sich trifft, und dieselben Platten zu benutzen ist nicht nur
# billiger: haette das Schlachtfeld eigene Gruentoene, saehe der Wald im
# Kampf anders aus als der Wald, in den man hineingelaufen ist.

const CREATURES_PATH := "res://assets/models/creatures.glb"
const WORLD_PATH := "res://assets/models/world.glb"

# Gelaendeart -> Bodenmodell. Reihenfolge ist MapGen.TILE_*, wie in
# WorldMap3D. Wasser gibt es als Schlachtfeld nicht; dort wird auf Sand
# gekaempft (Kuestenkampf), sonst stuenden die Einheiten im Meer.
# FLACHE Boeden (bt_), nicht die Gelaendequader der Weltkarte (t_). Die
# Quader haben deckungsgleiche Seitenflaechen und erzeugten dunkle
# Z-Fighting-Linien quer ueber das Brett - derselbe Fehler wie im Nebel
# (It. 62), dieselbe Loesung: eine Flaeche ohne Seitenflaechen.
const GROUND_MODEL := ["bt_grass", "bt_forest", "bt_sand", "bt_mountain",
	"bt_sand", "bt_swamp"]

# Seitenfarben. Dieselbe Sprache wie auf der Weltkarte: das Modell zeigt
# WAS dort steht, der Ring darunter WEM es gehoert.
const SIDE_COLOR := [Color(1.0, 0.90, 0.45), Color(0.90, 0.30, 0.28)]
# Der Stack, der gerade zieht. Weiss statt der Seitenfarbe: die Frage "wer
# ist dran" ist eine andere als "wem gehoert das", und zwei Rottoene
# nebeneinander waeren nicht zu unterscheiden.
const ACTIVE_RING := Color(1.0, 1.0, 1.0, 0.95)
# Erreichbare Felder und beschiessbare Ziele. GRUEN wie in 2D, wo die
# Reichweite als gruene Flaeche liegt - ein weisser Ring hiess auf dem
# Brett dasselbe wie der weisse Ring um den ziehenden Stapel.
const MOVE_RING := Color(0.45, 0.95, 0.52, 0.30)
# Aufstellungsphase: die erlaubte Flaeche, in derselben Farbe wie das
# blaue Feld der 2D-Ansicht. Ohne sie ist die Taktikphase in 3D nicht
# bedienbar - man saehe nicht, wohin man einen Stapel setzen darf.
const ZONE_RING := Color(0.40, 0.62, 0.95, 0.32)
# Der Stapel, den man gerade umstellt.
const PICKED_RING := Color(0.55, 0.85, 1.0, 0.95)
const TARGET_RING := Color(1.0, 0.35, 0.30, 0.55)

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

# DER RAND UM DAS BRETT (It. 69).
#
# Gemessen an der echten Gitterflaeche (1040 x 1485 px): die Kamera zeigt
# 9 Zellen ueber die BREITE (KEEP_WIDTH), das sind bei 46 Grad Neigung
# 17.9 Zellreihen in der Tiefe - das Brett ist 8 tief. 55 Prozent der
# Flaeche waren damit reine Hintergrundfarbe, also schwarz. Die 2D-Ansicht
# fuellt denselben Platz seit It. 21 mit Kulisse und Vordergrund; raeumlich
# stand das Brett im Nichts.
#
# Der Rand ist DEUTLICH DUNKLER als das Brett. Er muss als "ausserhalb"
# lesbar bleiben - sonst zaehlt man Felder ab, die es nicht gibt.
const APRON_SHADE := 0.58
const APRON_MIX := ["deco_grass", "deco_grass", "deco_grass", "deco_stone",
	"deco_tree", "deco_flower"]
# Notbremse: bei einem entarteten Seitenverhaeltnis (Viewport noch 0 hoch)
# darf der Rand nicht ins Unendliche wachsen.
const APRON_MAX := 26

var _built: bool = false


func _init() -> void:
	model_paths = [WORLD_PATH, CREATURES_PATH]
	pitch_deg = PITCH
	cam_up = 9.0


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
		GROUND_MODEL.size() - 1)
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

	var ground: String = GROUND_MODEL[terrain]
	for y in range(rows):
		for x in range(cols):
			# Zwei Helligkeiten im Schachbrett: ohne sie verschwimmen die
			# Zellgrenzen auf einfarbigem Gras, und man kann nicht mehr
			# abzaehlen, wie weit eine Einheit noch kommt.
			var shade: float = 1.0 if (x + y) % 2 == 0 else 0.90
			add.call(ground, Vector2i(x, y), 0.0, 0.0,
				Color(shade, shade, shade))
	_apron(per_model, ground, cols, rows, sd)

	var picked: Vector2i = ctx.get("picked", Vector2i(-1, -1))
	var ring: Array = []
	for m in (ctx.get("move", []) as Array):
		ring.append({"pos": _cell_pos(m as Vector2i), "color": MOVE_RING})
	for t in (ctx.get("targets", []) as Array):
		ring.append({"pos": _cell_pos(t as Vector2i), "color": TARGET_RING})
	for z in (ctx.get("zone", []) as Array):
		ring.append({"pos": _cell_pos(z as Vector2i), "color": ZONE_RING})

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


# Gelaende ausserhalb des Bretts, bis der Bildrand erreicht ist.
func _apron(per_model: Dictionary, ground: String, cols: int, rows: int,
		sd: int) -> void:
	var r: Rect2i = apron_rect(cols, rows)
	var x0: int = r.position.x
	var x1: int = r.position.x + r.size.x - 1
	var z0: int = r.position.y
	var z1: int = r.position.y + r.size.y - 1
	if not per_model.has(ground):
		per_model[ground] = []
	var tiles: Array = per_model[ground]
	for z in range(z0, z1 + 1):
		for x in range(x0, x1 + 1):
			if x >= 0 and x < cols and z >= 0 and z < rows:
				continue
			# Unregelmaessige Helligkeit statt Schachbrett: das Muster ist
			# die Ablesehilfe des SPIELFELDS und darf draussen nicht
			# auftauchen.
			var h: int = hash3(x, z, sd + 991)
			var sh: float = APRON_SHADE + float(h % 12) * 0.006
			tiles.append({
				"pos": Vector3(float(x) * CELL, 0.0, float(z) * CELL),
				"rot": 0.0, "color": Color(sh, sh, sh),
			})
			# Bewuchs, aber nicht dicht am Brett - ein Baum direkt an der
			# Kante sieht aus, als stuende er auf einem Spielfeld.
			var near_edge: bool = (x >= -1 and x <= cols and z >= -1
				and z <= rows)
			if near_edge or (h / 16) % 5 == 0:
				continue
			var model: String = APRON_MIX[(h / 128) % APRON_MIX.size()]
			if not _meshes.has(model):
				continue
			if not per_model.has(model):
				per_model[model] = []
			var jx: float = (float((h / 32) % 100) / 100.0 - 0.5) * 0.7
			var jz: float = (float((h / 2048) % 100) / 100.0 - 0.5) * 0.7
			var gs: float = 0.85 + float((h / 65536) % 90) * 0.012
			(per_model[model] as Array).append({
				"pos": Vector3((float(x) + jx) * CELL, 0.0,
					(float(z) + jz) * CELL),
				"rot": float(h % 360) * PI / 180.0,
				"scale": Vector3(gs, gs, gs),
				"color": Color(0.70, 0.73, 0.68),
			})


func frame_board(cols: int, rows: int) -> void:
	look_at_cells(Vector2(float(cols - 1) * 0.5, float(rows - 1) * 0.5),
		float(cols) + 1.0)


func is_built() -> bool:
	return _built
