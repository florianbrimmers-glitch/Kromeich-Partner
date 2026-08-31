extends SceneTree

# Headless-Vorschau der Kampf-Effekte (Iteration 17).
#
# Der echte TacticalBattleScreen laesst sich headless NICHT rendern (kein
# Display, siehe game/CLAUDE.md). Dieses Tool baut darum drei Momente
# eines Angriffs als Bild-Komposition nach - dasselbe Muster wie
# preview_battle.gd und preview_city_full.gd. Genau dieses Vorgehen hat
# schon die unsichtbaren Gold-auf-Gold-Token und das leere Schlachtfeld
# gefunden; Effekte "sollten funktionieren" reicht nicht.
#
# Die Effekt-MATHEMATIK kommt aus BattleVfx - kein zweiter Satz Kurven,
# der auseinanderdriften kann. Nur das Zeichnen ist hier nachgebaut
# (Image kennt keine draw_*-Aufrufe).
#
#   /tmp/Godot_v4.6-stable_linux.x86_64 --headless --path game/ \
#     --script tools/preview_battle_fx.gd
#
# Ergebnis: user://battle-fx-preview.png (drei Panels nebeneinander)

const Vfx := preload("res://scripts/core/BattleVfx.gd")

const OUT_PATH := "user://battle-fx-preview.png"
const COLS := 10
const ROWS := 8
const CELL := 64
const GAP := 16
const FACTION_DIRS := ["waldvolk", "menschen", "totenreich", "orks"]

# Aufstellung fuer die Vorschau: Schuetze links, Ziel rechts.
const SHOOTER := "men_archer"
const TARGET := "nec_skeleton"
const SHOOTER_CELL := Vector2i(1, 4)
const TARGET_CELL := Vector2i(6, 4)

var _tex_cache: Dictionary = {}


func _init() -> void:
	var pw: int = COLS * CELL
	var ph: int = ROWS * CELL
	var canvas := Image.create(pw * 3 + GAP * 2, ph, false, Image.FORMAT_RGBA8)
	canvas.fill(Color(0.02, 0.02, 0.03, 1.0))

	# Drei Momente. Die Zeiten sind so gewaehlt, dass jeder Effekt in
	# seiner aussagekraeftigsten Phase steht.
	_panel(canvas, 0, "flug", 0.55)
	_panel(canvas, 1, "einschlag", 0.35)
	_panel(canvas, 2, "zerfall", 0.55)

	var err: int = canvas.save_png(OUT_PATH)
	print("save_err=%d -> %s" % [err, ProjectSettings.globalize_path(OUT_PATH)])
	quit(0)


# Baut ein Panel mit Boden, Gitter, Token und der Effekt-Queue im
# gewuenschten Zustand.
func _panel(canvas: Image, index: int, phase: String, t: float) -> void:
	var ox: int = index * (COLS * CELL + GAP)
	_ground(canvas, ox)
	_grid_lines(canvas, ox)

	# Queue wie im echten Kampf aufbauen, dann bis zum gewuenschten
	# Zeitpunkt vorspulen. Kein Handrechnen von Zwischenwerten.
	var q: Array = Vfx.new_queue()
	var flight: float = 0.0
	match phase:
		"flug":
			flight = Vfx.shot(q, SHOOTER_CELL, TARGET_CELL)
			Vfx.hit(q, TARGET_CELL, 34, Color(1.0, 0.94, 0.72), flight)
			Vfx.advance(q, flight * t)
		"einschlag":
			flight = Vfx.shot(q, SHOOTER_CELL, TARGET_CELL)
			Vfx.hit(q, TARGET_CELL, 34, Color(1.0, 0.94, 0.72), flight)
			Vfx.advance(q, flight + float(Vfx.DUR[Vfx.IMPACT]) * t)
		"zerfall":
			Vfx.died(q, TARGET_CELL, TARGET, 1)
			Vfx.popup(q, SHOOTER_CELL, "Glueck!", Color(1.0, 0.88, 0.35))
			Vfx.advance(q, float(Vfx.DUR[Vfx.DEATH]) * t)

	# Token. Im Zerfall-Panel steht das Ziel nicht mehr als Stack da -
	# es kommt aus dem DEATH-Effekt, genau wie im echten Screen.
	_token(canvas, ox, SHOOTER, SHOOTER_CELL, Color(0.95, 0.80, 0.25),
		Color(0.5, 0.35, 0.05))
	if phase != "zerfall":
		_token(canvas, ox, TARGET, TARGET_CELL, Color(0.5, 0.5, 0.55),
			Color(0.85, 0.25, 0.25))

	_effects(canvas, ox, q)
	print("[Panel %d] %s: %d Effekt(e) sichtbar" % [index, phase, q.size()])


func _ground(canvas: Image, ox: int) -> void:
	# Gras, wie TERRAIN_GROUND[0] im Screen.
	var ground := Color(0.18, 0.28, 0.16, 1.0)
	var h: int = ROWS * CELL
	for y in range(h):
		var t: float = float(y) / float(h - 1)
		var col := ground.darkened(0.55).lerp(ground.darkened(0.25), t)
		for x in range(COLS * CELL):
			canvas.set_pixel(ox + x, y, col)
	for cx in range(COLS):
		for cy in range(ROWS):
			var shade: float = 0.04 if (cx + cy) % 2 == 0 else 0.0
			var cc := ground.lightened(shade)
			for px in range(CELL):
				for py in range(CELL):
					canvas.set_pixel(ox + cx * CELL + px, cy * CELL + py, cc)


func _grid_lines(canvas: Image, ox: int) -> void:
	var lc := Color(0.22, 0.27, 0.35, 1.0)
	for col in range(COLS + 1):
		var x: int = mini(col * CELL, COLS * CELL - 1)
		for y in range(ROWS * CELL):
			canvas.set_pixel(ox + x, y, lc)
	for row in range(ROWS + 1):
		var y2: int = mini(row * CELL, ROWS * CELL - 1)
		for x2 in range(COLS * CELL):
			canvas.set_pixel(ox + x2, y2, lc)


func _center(cell: Vector2i) -> Vector2:
	return Vector2((float(cell.x) + 0.5) * CELL, (float(cell.y) + 0.5) * CELL)


func _token(canvas: Image, ox: int, uid: String, cell: Vector2i,
		fill: Color, ring: Color) -> void:
	var ctr: Vector2 = _center(cell)
	_disc(canvas, ox, ctr, float(CELL) * 0.40, fill.darkened(0.72), ring)
	_sprite(canvas, ox, uid, ctr, float(CELL) * 0.92, 1.0)


func _effects(canvas: Image, ox: int, q: Array) -> void:
	var c: float = float(CELL)
	for e in q:
		if Vfx.pending(e):
			continue
		var kind: String = String(e.get("kind", ""))
		var t: float = Vfx.progress(e)
		match kind:
			Vfx.PROJECTILE:
				var pa: Vector2 = _center(Vector2i(e["from"]))
				var pb: Vector2 = _center(Vector2i(e["to"]))
				var lift: float = float(e.get("lift", 0.45)) * c
				for k in range(3):
					var tt: float = maxf(0.0, t - 0.07 * float(k + 1))
					_dot(canvas, ox, Vfx.arc_point(pa, pb, tt, lift),
						c * (0.055 - 0.014 * float(k)),
						Color(1.0, 0.92, 0.65, 0.45 - 0.12 * float(k)))
				_dot(canvas, ox, Vfx.arc_point(pa, pb, t, lift), c * 0.075,
					Color(1.0, 0.97, 0.82, 1.0))
			Vfx.IMPACT:
				var ctr: Vector2 = _center(Vector2i(e["at"]))
				var col: Color = e.get("col", Color(1, 1, 1))
				var a: float = 1.0 - t
				_ring(canvas, ox, ctr, c * Vfx.impact_radius(t),
					maxf(2.0, c * 0.05), Color(col.r, col.g, col.b, a * 0.9))
				var sp: Array = Vfx.impact_spoke(t)
				for k in range(Vfx.IMPACT_SPOKES):
					var ang: float = float(k) * TAU / float(Vfx.IMPACT_SPOKES) + 0.3
					var dir := Vector2(cos(ang), sin(ang))
					_line(canvas, ox, ctr + dir * c * float(sp[0]),
						ctr + dir * c * float(sp[1]),
						Color(1, 1, 1, a * 0.8))
			Vfx.DEATH:
				var dc: Vector2 = _center(Vector2i(e["at"]))
				var fade: float = 1.0 - t
				var sink: float = c * 0.22 * Vfx.ease_out(t)
				_disc(canvas, ox, dc + Vector2(0.0, sink),
					c * 0.40 * (1.0 - 0.3 * t),
					Color(0.05, 0.05, 0.06, fade * 0.7), Color(0, 0, 0, 0))
				_sprite(canvas, ox, String(e.get("uid", "")),
					dc + Vector2(0.0, sink), c * 0.92 * (1.0 - 0.28 * t), fade)
				for k2 in range(5):
					var ang2: float = float(k2) * TAU / 5.0 + 0.9
					var d2 := Vector2(cos(ang2), sin(ang2) * 0.45)
					_dot(canvas, ox, dc + d2 * c * 0.44 * Vfx.ease_out(t),
						c * 0.09 * (1.0 - t * 0.4),
						Color(0.55, 0.50, 0.44, fade * 0.5))
			Vfx.POPUP, Vfx.NUMBER:
				# Text laesst sich auf einem Image nicht setzen - ein
				# Balken an der richtigen Stelle beweist Position und
				# Ausblendung, mehr braucht die Vorschau nicht.
				var rf: Array = Vfx.rise_fade(t)
				var pc: Vector2 = _center(Vector2i(e["at"])) \
					- Vector2(0.0, c * 0.42 + float(rf[0]) * c)
				var pcol: Color = e.get("col", Color(1, 1, 1))
				_bar(canvas, ox, pc, c * 0.30, c * 0.06,
					Color(pcol.r, pcol.g, pcol.b, float(rf[1])))


# --- Zeichen-Helfer auf Image --------------------------------------------

func _blend(canvas: Image, x: int, y: int, col: Color) -> void:
	if x < 0 or y < 0 or x >= canvas.get_width() or y >= canvas.get_height():
		return
	if col.a <= 0.0:
		return
	var dst: Color = canvas.get_pixel(x, y)
	canvas.set_pixel(x, y, dst.lerp(col, clampf(col.a, 0.0, 1.0)))


func _disc(canvas: Image, ox: int, ctr: Vector2, r: float,
		fill: Color, ring: Color) -> void:
	var ri: int = int(r) + 3
	for dx in range(-ri, ri + 1):
		for dy in range(-ri, ri + 1):
			var d: float = sqrt(float(dx * dx + dy * dy))
			if d <= r - 1.5:
				_blend(canvas, ox + int(ctr.x) + dx, int(ctr.y) + dy, fill)
			elif d <= r + 1.5:
				_blend(canvas, ox + int(ctr.x) + dx, int(ctr.y) + dy, ring)


func _dot(canvas: Image, ox: int, ctr: Vector2, r: float, col: Color) -> void:
	_disc(canvas, ox, ctr, r, col, col)


func _ring(canvas: Image, ox: int, ctr: Vector2, r: float, w: float,
		col: Color) -> void:
	var ri: int = int(r + w) + 2
	for dx in range(-ri, ri + 1):
		for dy in range(-ri, ri + 1):
			var d: float = sqrt(float(dx * dx + dy * dy))
			if absf(d - r) <= w * 0.5:
				_blend(canvas, ox + int(ctr.x) + dx, int(ctr.y) + dy, col)


func _line(canvas: Image, ox: int, a: Vector2, b: Vector2, col: Color) -> void:
	var steps: int = int(maxf(2.0, a.distance_to(b)))
	for i in range(steps + 1):
		var p: Vector2 = a.lerp(b, float(i) / float(steps))
		_blend(canvas, ox + int(p.x), int(p.y), col)
		_blend(canvas, ox + int(p.x) + 1, int(p.y), col)


func _bar(canvas: Image, ox: int, ctr: Vector2, w: float, h: float,
		col: Color) -> void:
	for dx in range(-int(w * 0.5), int(w * 0.5) + 1):
		for dy in range(-int(h * 0.5), int(h * 0.5) + 1):
			_blend(canvas, ox + int(ctr.x) + dx, int(ctr.y) + dy, col)


func _sprite(canvas: Image, ox: int, uid: String, ctr: Vector2, size: float,
		alpha: float) -> void:
	if uid == "":
		return
	var img: Image = _unit_image(uid)
	if img == null:
		return
	var s: int = int(size)
	if s < 2:
		return
	var scaled := Image.create(s, s, false, Image.FORMAT_RGBA8)
	scaled.copy_from(img)
	scaled.resize(s, s, Image.INTERPOLATE_LANCZOS)
	var x0: int = ox + int(ctr.x) - s / 2
	var y0: int = int(ctr.y) - s / 2
	for x in range(s):
		for y in range(s):
			var px: Color = scaled.get_pixel(x, y)
			if px.a <= 0.0:
				continue
			px.a *= alpha
			_blend(canvas, x0 + x, y0 + y, px)


func _unit_image(uid: String) -> Image:
	if _tex_cache.has(uid):
		return _tex_cache[uid] as Image
	var fid: int = UnitType.faction_of(uid)
	var img: Image = null
	if fid >= 0 and fid < FACTION_DIRS.size():
		var path: String = "res://assets/units/%s/%s.svg" % [FACTION_DIRS[fid], uid]
		if ResourceLoader.exists(path):
			var tex: Texture2D = load(path) as Texture2D
			if tex != null:
				img = tex.get_image()
				if img.is_compressed():
					img.decompress()
				img.convert(Image.FORMAT_RGBA8)
	if img == null:
		print("[FEHLT] Sprite fuer %s" % uid)
	_tex_cache[uid] = img
	return img
