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
const UnitArt := preload("res://scripts/core/UnitArt.gd")
const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")

const OUT_PATH := "user://battle-fx-preview.png"
# It. 36: Gitter aus dem Screen, Zelle in ECHTER Geraetegroesse. Mit
# CELL = 64 zeigte diese Vorschau Effekte auf einer Zelle, die es auf dem
# Handy nicht gibt - dort sind es 104 px (1040 px Flaeche / 10 Spalten),
# und alle Effektradien sind relativ zur Zelle.
const COLS := TBS.GRID_COLS
const ROWS := TBS.GRID_ROWS
const CELL := 104
const GAP := 16

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
	# Faktoren aus dem Screen (It. 36): dort sind sie Konstanten, damit
	# Vorschau und Spiel dieselbe Tokengroesse zeigen.
	_disc(canvas, ox, ctr, float(CELL) * TBS.TOKEN_DISC_FRAC,
		fill.darkened(0.72), ring)
	_sprite(canvas, ox, uid, ctr - Vector2(0.0,
		float(CELL) * TBS.TOKEN_SPRITE_FRAC * TBS.TOKEN_SPRITE_LIFT),
		float(CELL) * TBS.TOKEN_SPRITE_FRAC, 1.0)


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
				# Pfeil als ausgerichteter Schaft mit Spitze - wie im
				# Screen seit It. 36. Richtung aus der BAHN (zwei Punkte
				# kurz hintereinander), nicht aus der Luftlinie.
				var pp: Vector2 = Vfx.arc_point(pa, pb, t, lift)
				var ahead: Vector2 = Vfx.arc_point(pa, pb, minf(1.0, t + 0.06), lift)
				var dir: Vector2 = ahead - pp
				if dir.length() < 0.001:
					dir = pb - pa
				dir = dir.normalized()
				var side: Vector2 = Vector2(-dir.y, dir.x)
				var shaft: float = c * 0.30
				_line(canvas, ox, pp - dir * shaft * 0.5, pp + dir * shaft * 0.5,
					maxf(2.0, c * 0.030), Color(0.92, 0.86, 0.66, 1.0))
				# Spitze als DREIECK, nicht als Punkt: der Screen zeichnet
				# draw_colored_polygon, und eine runde Kugel als Spitze
				# waere schon wieder ein anderer Pfeil als im Spiel.
				var tip: Vector2 = pp + dir * shaft * 0.5
				_tri(canvas, ox, tip + dir * c * 0.075,
					tip + side * c * 0.045, tip - side * c * 0.045,
					Color(1.0, 0.97, 0.82, 1.0))
				for sg in [-1.0, 1.0]:
					_line(canvas, ox,
						pp - dir * shaft * 0.5 + side * sg * c * 0.03,
						pp - dir * shaft * 0.5 - dir * c * 0.045,
						maxf(1.5, c * 0.018), Color(0.95, 0.90, 0.72, 0.9))
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
						ctr + dir * c * float(sp[1]), maxf(2.0, c * 0.022),
						Color(1, 1, 1, a * 0.8))
			Vfx.DEATH:
				var dc: Vector2 = _center(Vector2i(e["at"]))
				var fade: float = 1.0 - t
				var sink: float = c * 0.22 * Vfx.ease_out(t)
				_disc(canvas, ox, dc + Vector2(0.0, sink),
					c * TBS.TOKEN_DISC_FRAC * (1.0 - 0.3 * t),
					Color(0.05, 0.05, 0.06, fade * 0.7), Color(0, 0, 0, 0))
				_sprite(canvas, ox, String(e.get("uid", "")),
					dc + Vector2(0.0, sink),
					c * TBS.TOKEN_SPRITE_FRAC * (1.0 - 0.28 * t), fade)
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


func _line(canvas: Image, ox: int, a: Vector2, b: Vector2, w: float = 2.0,
		col: Color = Color.WHITE) -> void:
	var steps: int = int(maxf(2.0, a.distance_to(b)))
	var n: Vector2 = (b - a).normalized()
	var side := Vector2(-n.y, n.x)
	var half: int = int(maxf(1.0, w * 0.5))
	for i in range(steps + 1):
		var p: Vector2 = a.lerp(b, float(i) / float(steps))
		for k in range(-half, half + 1):
			var q: Vector2 = p + side * float(k)
			_blend(canvas, ox + int(q.x), int(q.y), col)


# Gefuelltes Dreieck ueber baryzentrische Koordinaten. Image kennt kein
# draw_colored_polygon, und der Pfeil braucht eine echte Spitze.
func _tri(canvas: Image, ox: int, a: Vector2, b: Vector2, cc: Vector2,
		col: Color) -> void:
	var x0: int = int(floor(min(a.x, min(b.x, cc.x))))
	var x1: int = int(ceil(max(a.x, max(b.x, cc.x))))
	var y0: int = int(floor(min(a.y, min(b.y, cc.y))))
	var y1: int = int(ceil(max(a.y, max(b.y, cc.y))))
	var d: float = (b.y - cc.y) * (a.x - cc.x) + (cc.x - b.x) * (a.y - cc.y)
	if absf(d) < 0.0001:
		return
	for y in range(y0, y1 + 1):
		for x in range(x0, x1 + 1):
			var px := Vector2(float(x), float(y))
			var w0: float = ((b.y - cc.y) * (px.x - cc.x)
				+ (cc.x - b.x) * (px.y - cc.y)) / d
			var w1: float = ((cc.y - a.y) * (px.x - cc.x)
				+ (a.x - cc.x) * (px.y - cc.y)) / d
			var w2: float = 1.0 - w0 - w1
			if w0 >= -0.02 and w1 >= -0.02 and w2 >= -0.02:
				_blend(canvas, ox + x, y, col)


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
	# Sprite-Pfad ueber core/UnitArt.gd (It. 36) - die eigene
	# FACTION_DIRS-Kopie hier war die dritte im Baum.
	var img: Image = null
	var tex: Texture2D = UnitArt.texture_for(uid)
	if tex != null:
		img = tex.get_image()
		if img.is_compressed():
			img.decompress()
		img.convert(Image.FORMAT_RGBA8)
	else:
		print("[FEHLT] Sprite fuer %s" % uid)
	_tex_cache[uid] = img
	return img
