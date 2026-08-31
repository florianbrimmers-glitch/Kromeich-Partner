extends SceneTree

# Headless-Vorschau des Kampf-Gitters. Der echte TacticalBattleScreen
# laesst sich headless NICHT rendern (kein Display, siehe game/CLAUDE.md) -
# dieses Tool baut die Flaeche als Bild-Komposition nach und spiegelt dabei
# die Zeichenreihenfolge aus _draw_grid:
#
#   1. Verlauf ueber die ganze Flaeche
#   2. Kulisse OBERHALB des Gitters, Bewuchs UNTERHALB
#   3. Boden-Kachel je Feld (Variante aus _ground_variant)
#   4. Hindernis-Sprites
#   5. Token mit Seiten-Ring und Stufen-Punkten
#
# Nur so faellt auf, wenn die Baender leer bleiben oder Kacheln kacheln.
#
#   /tmp/Godot_v4.6-stable_linux.x86_64 --headless --path game/ \
#     --script tools/preview_battle.gd
#
# Ergebnis: user://battle-preview.png (zwei Gelaende nebeneinander)

const Obst := preload("res://scripts/core/BattleObstacles.gd")

const COLS := 10
const ROWS := 8
const CELL := 96
# Spiegelt die Flaeche auf dem Geraet: Gitter breitenbegrenzt, darueber und
# darunter bleibt Platz - genau die Baender, die gefuellt werden sollen.
const PAD_TOP := 300
const PAD_BOTTOM := 210
const SEED := 42

const FACTION_DIRS := ["waldvolk", "menschen", "totenreich", "orks"]
const TERRAIN_ART := ["grass", "forest", "coast", "mountain", "sand", "swamp"]
const GROUND_VARIANTS := 4
# Spiegelt TacticalBattleScreen.TERRAIN_GROUND.
const TERRAIN_GROUND := [
	Color(0.18, 0.28, 0.16), Color(0.13, 0.22, 0.14), Color(0.16, 0.23, 0.30),
	Color(0.26, 0.25, 0.24), Color(0.34, 0.30, 0.20), Color(0.20, 0.23, 0.16),
]

# Aufstellung: Spieler Spalte 1, Gegner Spalte COLS-2.
const PLAYER := ["men_spearman", "men_archer", "men_griffin", "men_angel"]
const ENEMY := ["nec_skeleton", "nec_lich", "nec_blackknight", "nec_bonedragon"]

var _cache: Dictionary = {}
var _w: int
var _h: int


func _init() -> void:
	_w = COLS * CELL
	_h = ROWS * CELL + PAD_TOP + PAD_BOTTOM
	# Zwei Gelaende nebeneinander: Gras (Standard) und Gebirge mit Mauer.
	var gap := 20
	var canvas := Image.create(_w * 2 + gap, _h, false, Image.FORMAT_RGBA8)
	canvas.fill(Color(0.02, 0.02, 0.03, 1.0))
	_panel(canvas, 0, 0, false)
	_panel(canvas, _w + gap, 3, true)
	var err: int = canvas.save_png("user://battle-preview.png")
	print("save_err=%d -> %s" % [err,
		ProjectSettings.globalize_path("user://battle-preview.png")])
	quit(0)


func _panel(canvas: Image, ox: int, terrain: int, siege: bool) -> void:
	var art: String = TERRAIN_ART[terrain]
	var ground: Color = TERRAIN_GROUND[terrain]
	var grid_y := PAD_TOP

	# 1) Verlauf ueber die ganze Flaeche.
	for y in range(_h):
		var t: float = float(y) / float(_h - 1)
		var col := ground.darkened(0.55).lerp(ground.darkened(0.25), t)
		for x in range(_w):
			canvas.set_pixel(ox + x, y, col)

	# 2) Kulisse oben, Bewuchs unten.
	var bh: int = int(min(float(PAD_TOP), float(_w) * 0.34))
	_stretch(canvas, "backdrop/%s.svg" % art, ox, grid_y - bh, _w, bh)
	var fh: int = int(min(float(PAD_BOTTOM), float(_w) * 0.22))
	_stretch(canvas, "fore/%s.svg" % art, ox, grid_y + ROWS * CELL, _w, fh)

	# 3) Boden-Kacheln.
	for cx in range(COLS):
		for cy in range(ROWS):
			_stretch(canvas, "ground/%s_%d.svg" % [art, _ground_variant(cx, cy)],
				ox + cx * CELL, grid_y + cy * CELL, CELL, CELL)

	_grid_lines(canvas, ox, grid_y)

	# 4) Hindernisse. Bei der Belagerung eine Mauerreihe mit Tor-Luecke,
	#    ein Segment angeschlagen.
	if siege:
		var walls: Array = Obst.siege_walls(COLS, ROWS)
		for i in range(walls.size()):
			var wp: Vector2i = Vector2i(walls[i]["pos"])
			var nm: String = "wall_cracked" if i == 0 else "wall"
			_stretch(canvas, "obstacles/%s.svg" % nm,
				ox + wp.x * CELL, grid_y + wp.y * CELL, CELL, CELL)
	else:
		var obs: Array = Obst.generate(terrain, SEED, COLS, ROWS)
		var names := {0: "stone", 1: "log", 2: "bush", 3: "swamp", 4: "wall"}
		for ob in obs:
			var p: Vector2i = Vector2i(ob["pos"])
			var nm2: String = String(names.get(int(ob["kind"]), "stone"))
			_stretch(canvas, "obstacles/%s.svg" % nm2,
				ox + p.x * CELL, grid_y + p.y * CELL, CELL, CELL)
		print("[%s] %d Hindernisse" % [art, obs.size()])

	# 5) Token.
	for i in range(PLAYER.size()):
		_token(canvas, ox, grid_y, String(PLAYER[i]), 1, _row(i, PLAYER.size()),
			Color(0.95, 0.80, 0.25), Color(0.5, 0.35, 0.05))
	for i in range(ENEMY.size()):
		_token(canvas, ox, grid_y, String(ENEMY[i]), COLS - 2, _row(i, ENEMY.size()),
			Color(0.5, 0.5, 0.55), Color(0.85, 0.25, 0.25))


func _row(i: int, n: int) -> int:
	if n <= 1:
		return ROWS / 2
	return (ROWS / (n + 1)) * (i + 1)


# Muss identisch zu TacticalBattleScreen._ground_variant sein.
func _ground_variant(cx: int, cy: int) -> int:
	var h: int = (cx * 73856093) ^ (cy * 19349663) ^ (SEED * 83492791)
	h = (h ^ (h >> 13)) * 1274126177
	h = h ^ (h >> 16)
	return absi(h) % GROUND_VARIANTS


func _grid_lines(canvas: Image, ox: int, gy: int) -> void:
	var lc := Color(0.22, 0.27, 0.35, 0.55)
	for col in range(COLS + 1):
		var x: int = mini(col * CELL, COLS * CELL - 1)
		for y in range(ROWS * CELL):
			_blend(canvas, ox + x, gy + y, lc)
	for row in range(ROWS + 1):
		var y2: int = mini(row * CELL, ROWS * CELL - 1)
		for x2 in range(COLS * CELL):
			_blend(canvas, ox + x2, gy + y2, lc)


func _token(canvas: Image, ox: int, gy: int, uid: String, cx: int, cy: int,
		fill: Color, ring: Color) -> void:
	var ctr := Vector2i(ox + cx * CELL + CELL / 2, gy + cy * CELL + CELL / 2)
	var r: float = float(CELL) * 0.40
	# Wie im Screen: dunkle Scheibe, Seite steckt im Ring.
	var disc: Color = fill.darkened(0.72)
	var ri: int = int(r) + 3
	for dx in range(-ri, ri + 1):
		for dy in range(-ri, ri + 1):
			var d: float = sqrt(float(dx * dx + dy * dy))
			if d <= r - 1.5:
				_blend(canvas, ctr.x + dx, ctr.y + dy, disc)
			elif d <= r + 1.5:
				_blend(canvas, ctr.x + dx, ctr.y + dy, ring)
	var fid: int = UnitType.faction_of(uid)
	var size: int = int(float(CELL) * 0.92)
	_stretch(canvas, "", ctr.x - size / 2, ctr.y - size / 2, size, size,
		"res://assets/units/%s/%s.svg" % [FACTION_DIRS[fid], uid])


# Skaliert ein SVG in ein Rechteck und blendet es alpha-korrekt ein.
# `rel` ist relativ zu assets/battle/, `abs_path` schlaegt das aus.
func _stretch(canvas: Image, rel: String, px: int, py: int, w: int, h: int,
		abs_path: String = "") -> void:
	var key: String = abs_path if abs_path != "" else rel
	if w <= 0 or h <= 0:
		return
	var img: Image = _image(key, abs_path == "")
	if img == null:
		return
	var scaled := Image.create(w, h, false, Image.FORMAT_RGBA8)
	scaled.copy_from(img)
	scaled.resize(w, h, Image.INTERPOLATE_LANCZOS)
	for j in range(h):
		var ty: int = py + j
		if ty < 0 or ty >= canvas.get_height():
			continue
		for i in range(w):
			var tx: int = px + i
			if tx < 0 or tx >= canvas.get_width():
				continue
			var src: Color = scaled.get_pixel(i, j)
			if src.a <= 0.004:
				continue
			_blend(canvas, tx, ty, src)


func _image(key: String, is_battle: bool) -> Image:
	if _cache.has(key):
		return _cache[key] as Image
	var path: String = ("res://assets/battle/%s" % key) if is_battle else key
	var img: Image = null
	if ResourceLoader.exists(path):
		var tex: Texture2D = load(path) as Texture2D
		if tex != null:
			img = tex.get_image()
			if img.is_compressed():
				img.decompress()
			img.convert(Image.FORMAT_RGBA8)
	else:
		print("[FEHLT] %s" % path)
	_cache[key] = img
	return img


func _blend(canvas: Image, x: int, y: int, col: Color) -> void:
	if x < 0 or y < 0 or x >= canvas.get_width() or y >= canvas.get_height():
		return
	if col.a >= 0.999:
		canvas.set_pixel(x, y, col)
		return
	var dst: Color = canvas.get_pixel(x, y)
	canvas.set_pixel(x, y, dst.lerp(col, col.a))
