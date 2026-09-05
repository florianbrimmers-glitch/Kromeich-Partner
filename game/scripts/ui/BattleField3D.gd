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
const GROUND_MODEL := ["t_grass", "t_forest", "t_sand", "t_mountain",
	"t_sand", "t_swamp"]

# Seitenfarben. Dieselbe Sprache wie auf der Weltkarte: das Modell zeigt
# WAS dort steht, der Ring darunter WEM es gehoert.
const SIDE_COLOR := [Color(1.0, 0.90, 0.45), Color(0.90, 0.30, 0.28)]
# Der Stack, der gerade zieht. Weiss statt der Seitenfarbe: die Frage "wer
# ist dran" ist eine andere als "wem gehoert das", und zwei Rottoene
# nebeneinander waeren nicht zu unterscheiden.
const ACTIVE_RING := Color(1.0, 1.0, 1.0, 0.95)
# Erreichbare Felder und beschiessbare Ziele.
const MOVE_RING := Color(1.0, 1.0, 1.0, 0.18)
const TARGET_RING := Color(1.0, 0.35, 0.30, 0.55)

# Blickrichtung: die Modelle schauen im glb nach +Z (zur Kamera). Eine
# Drehung um Y bildet +Z auf (sin a, 0, cos a) ab - fuer +X also +90 Grad.
# Spieler steht links und schaut nach rechts, der Gegner umgekehrt.
const FACING := [PI * 0.5, -PI * 0.5]

# Steiler als die Weltkarte: das Brett ist nur 8x8, es muss nicht in die
# Tiefe gehen, und steiler heisst weniger Verdeckung durch grosse
# Kreaturen.
const PITCH := -40.0

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

	var ring: Array = []
	for m in (ctx.get("move", []) as Array):
		ring.append({"pos": _cell_pos(m as Vector2i), "color": MOVE_RING})
	for t in (ctx.get("targets", []) as Array):
		ring.append({"pos": _cell_pos(t as Vector2i), "color": TARGET_RING})

	for o in (ctx.get("obstacles", []) as Array):
		var od: Dictionary = o as Dictionary
		var cell: Vector2i = od["pos"]
		var model: String = "deco_rock" if String(od.get("kind", "rock")) == "rock" \
			else "deco_tree"
		add.call(model, cell, 0.0,
			float(hash3(cell.x, cell.y, sd) % 360) * PI / 180.0, Color.WHITE)

	for s in (ctx.get("stacks", []) as Array):
		var sd2: Dictionary = s as Dictionary
		var cell2: Vector2i = sd2["pos"]
		var side: int = clampi(int(sd2.get("side", 0)), 0, 1)
		add.call(String(sd2.get("type", "")), cell2, 0.0, FACING[side],
			Color.WHITE)
		ring.append({
			"pos": _cell_pos(cell2),
			"color": ACTIVE_RING if bool(sd2.get("active", false))
				else SIDE_COLOR[side],
		})
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
func frame_board(cols: int, rows: int) -> void:
	look_at_cells(Vector2(float(cols - 1) * 0.5, float(rows - 1) * 0.5),
		float(cols) + 1.0)


func is_built() -> bool:
	return _built
