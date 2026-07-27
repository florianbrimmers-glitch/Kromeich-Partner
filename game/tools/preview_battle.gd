extends SceneTree

# Headless-Preview des Kampf-Gitters. WICHTIG: der echte
# TacticalBattleScreen laesst sich headless NICHT rendern (kein Display,
# siehe game/CLAUDE.md) - dieses Tool baut das Gitter darum als
# Bild-Komposition nach, genau wie preview_city_full.gd es fuer die Stadt
# macht: Zellen als Rechtecke, Token per blend_rect, Seiten-Ring als
# gezeichneter Kreis. Layout und Groessenverhaeltnisse entsprechen dem
# Spiel (10x8 Gitter, Token 92 Prozent der Zelle).
#
#   /tmp/Godot_v4.6-stable_linux.x86_64 --headless --path game/ \
#     --script tools/preview_battle.gd
#
# Ergebnis: user://battle-preview.png

const OUT_PATH := "user://battle-preview.png"
const COLS := 10
const ROWS := 8
const CELL := 96
const FACTION_DIRS := ["waldvolk", "menschen", "totenreich", "orks"]
const Obst := preload("res://scripts/core/BattleObstacles.gd")

# Aufstellung wie im Spiel: Spieler Spalte 1, Gegner Spalte COLS-2.
const PLAYER := ["men_spearman", "men_archer", "men_griffin", "men_angel"]
const ENEMY := ["nec_skeleton", "nec_lich", "nec_blackknight", "nec_bonedragon"]


func _init() -> void:
	var canvas := Image.create(COLS * CELL, ROWS * CELL, false, Image.FORMAT_RGBA8)
	canvas.fill(Color(0.10, 0.12, 0.16, 1.0))
	_draw_grid_lines(canvas)
	# Belagerung (M9): Mauer-Reihe mit Tor-Luecke, ein Segment
	# angeschlagen - so sieht der Spieler die Bresche kommen.
	var walls: Array = Obst.siege_walls(COLS, ROWS)
	for i in range(walls.size()):
		var wp: Vector2i = Vector2i(walls[i]["pos"])
		_draw_wall(canvas, wp, i == 0)

	for i in range(PLAYER.size()):
		var y: int = _row(i, PLAYER.size())
		_place(canvas, String(PLAYER[i]), 1, y,
			Color(0.95, 0.80, 0.25), Color(0.5, 0.35, 0.05))
	for i in range(ENEMY.size()):
		var y2: int = _row(i, ENEMY.size())
		_place(canvas, String(ENEMY[i]), COLS - 2, y2,
			Color(0.5, 0.5, 0.55), Color(0.85, 0.25, 0.25))

	var err: int = canvas.save_png(OUT_PATH)
	print("save_err=%d -> %s" % [err, ProjectSettings.globalize_path(OUT_PATH)])
	quit(0)


func _row(i: int, n: int) -> int:
	if n <= 1:
		return ROWS / 2
	return (ROWS / (n + 1)) * (i + 1)


# Mauer-Segment wie im Screen: Quaderblock mit Zinnen, angeschlagen mit
# Rissen.
func _draw_wall(canvas: Image, cell: Vector2i, damaged: bool) -> void:
	var x0: int = cell.x * CELL
	var y0: int = cell.y * CELL
	var stone := Color(0.52, 0.50, 0.46, 1.0)
	var edge := Color(0.24, 0.23, 0.22, 1.0)
	for x in range(int(CELL * 0.06), int(CELL * 0.94)):
		for y in range(int(CELL * 0.16), int(CELL * 0.88)):
			canvas.set_pixel(x0 + x, y0 + y, stone)
	# Zinnen
	for z in range(3):
		var zx0: int = int(CELL * (0.08 + 0.30 * float(z)))
		for x2 in range(zx0, zx0 + int(CELL * 0.22)):
			for y2 in range(int(CELL * 0.04), int(CELL * 0.16)):
				canvas.set_pixel(x0 + x2, y0 + y2, Color(0.58, 0.56, 0.52, 1.0))
	# Rahmen
	for x3 in range(int(CELL * 0.06), int(CELL * 0.94)):
		canvas.set_pixel(x0 + x3, y0 + int(CELL * 0.16), edge)
		canvas.set_pixel(x0 + x3, y0 + int(CELL * 0.87), edge)
	if damaged:
		for t in range(int(CELL * 0.5)):
			var f: float = float(t) / float(CELL * 0.5)
			var cx: int = x0 + int(CELL * (0.30 + 0.16 * f))
			var cy: int = y0 + int(CELL * (0.20 + 0.64 * f))
			canvas.set_pixel(cx, cy, Color(0.15, 0.13, 0.12, 1.0))
			canvas.set_pixel(cx + 1, cy, Color(0.15, 0.13, 0.12, 1.0))


func _draw_grid_lines(canvas: Image) -> void:
	var lc := Color(0.22, 0.27, 0.35, 1.0)
	for col in range(COLS + 1):
		var x: int = mini(col * CELL, COLS * CELL - 1)
		for y in range(ROWS * CELL):
			canvas.set_pixel(x, y, lc)
	for row in range(ROWS + 1):
		var y2: int = mini(row * CELL, ROWS * CELL - 1)
		for x2 in range(COLS * CELL):
			canvas.set_pixel(x2, y2, lc)


# Seiten-Scheibe + Ring + Token, wie _draw_token im echten Screen.
func _place(canvas: Image, uid: String, cx: int, cy: int,
		fill: Color, ring: Color) -> void:
	var ctr := Vector2i(cx * CELL + CELL / 2, cy * CELL + CELL / 2)
	var r: float = float(CELL) * 0.40
	# Wie im Screen: dunkle Scheibe, Seite steckt im Ring.
	fill = fill.darkened(0.72)
	for dx in range(-int(r) - 3, int(r) + 4):
		for dy in range(-int(r) - 3, int(r) + 4):
			var px: int = ctr.x + dx
			var py: int = ctr.y + dy
			if px < 0 or py < 0 or px >= canvas.get_width() or py >= canvas.get_height():
				continue
			var d: float = sqrt(float(dx * dx + dy * dy))
			if d <= r - 1.5:
				canvas.set_pixel(px, py, fill)
			elif d <= r + 1.5:
				canvas.set_pixel(px, py, ring)
	var fid: int = UnitType.faction_of(uid)
	var path: String = "res://assets/units/%s/%s.svg" % [FACTION_DIRS[fid], uid]
	if not ResourceLoader.exists(path):
		print("[FEHLT] %s" % path)
		return
	var tex: Texture2D = load(path) as Texture2D
	if tex == null:
		print("[FEHLT] %s (load null)" % path)
		return
	var img: Image = tex.get_image()
	if img.is_compressed():
		img.decompress()
	img.convert(Image.FORMAT_RGBA8)
	var size: int = int(float(CELL) * 0.92)
	img.resize(size, size, Image.INTERPOLATE_LANCZOS)
	canvas.blend_rect(img, Rect2i(0, 0, size, size),
		Vector2i(ctr.x - size / 2, ctr.y - size / 2))
	print("[OK] %s auf (%d,%d)" % [uid, cx, cy])
