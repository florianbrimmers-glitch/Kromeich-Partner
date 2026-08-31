extends SceneTree

# Komponierte Weltkarten-Ansicht mit ECHTEM Spielzustand (It. 34).
#
#   godot --headless --path game/ --script tools/preview_world_full.gd
#
# WARUM NICHT preview_world_terrain.gd: das zeigt nur Kacheln, Fransen und
# Nebel. Auf dem Gerät liegen darüber Objekte, Städte, Monster und der
# Held - und genau in dieser Mischung entscheidet sich, ob die Karte
# lesbar ist. Einzelne Kacheln nebeneinander sehen immer gut aus (Lehrgeld
# aus It. 19 und It. 30).
#
# Die Positionen kommen NICHT aus einer Nachbildung, sondern aus einem
# echten WorldMapScreen: _start() laeuft headless, danach werden _map,
# _objects, _cities, _monsters, _hero und _fog_player ausgelesen und die
# Bildschirm-Methoden (_tile_variant, _fog_get) direkt aufgerufen. So kann
# die Vorschau nicht von der Wahrheit abweichen.
#
# Ausgabe:
#   user://world-full.png      ganze Karte, alles erkundet
#   user://world-viewport.png  der Ausschnitt, den das Handy zeigt
#                              (1080 x 1490 um den Helden), MIT Nebel

const TILE := 64
const VIEW_W := 1080
const VIEW_H := 1490
const SEED := 4711
const FACTION := 1

const FRINGE_ALPHA := 0.62
const FRINGE_SIDES := ["top", "right", "bottom", "left"]

var _wm = null
var _tex_cache: Dictionary = {}


func _init() -> void:
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	_wm = scene.instantiate()
	root.add_child(_wm)
	await process_frame
	_wm.call("_start", SEED, FACTION)
	await process_frame

	var map: Dictionary = _wm.get("_map")
	var mw: int = int(_wm.get("MAP_WIDTH"))
	var mh: int = int(_wm.get("MAP_HEIGHT"))
	print("Karte %dx%d, Seed %d" % [mw, mh, SEED])

	var full: Image = _compose(mw, mh, false)
	var e1: int = full.save_png("user://world-full.png")
	print("world-full.png save_err=%d -> %s" % [e1,
		ProjectSettings.globalize_path("user://world-full.png")])

	var fogged: Image = _compose(mw, mh, true)
	var hero = _wm.get("_hero")
	var hp: Vector2i = hero.position
	var cx: int = hp.x * TILE + TILE / 2
	var cy: int = hp.y * TILE + TILE / 2
	var vx: int = clampi(cx - VIEW_W / 2, 0, max(0, mw * TILE - VIEW_W))
	var vy: int = clampi(cy - VIEW_H / 2, 0, max(0, mh * TILE - VIEW_H))
	var view := Image.create(VIEW_W, VIEW_H, false, Image.FORMAT_RGBA8)
	view.fill(Color(0.04, 0.05, 0.07))
	view.blit_rect(fogged, Rect2i(vx, vy, min(VIEW_W, mw * TILE - vx),
		min(VIEW_H, mh * TILE - vy)), Vector2i.ZERO)
	var e2: int = view.save_png("user://world-viewport.png")
	print("world-viewport.png save_err=%d (Held auf %s) -> %s" % [e2, str(hp),
		ProjectSettings.globalize_path("user://world-viewport.png")])

	_wm.queue_free()
	await process_frame
	quit(0)


func _tex(rel: String) -> Image:
	if _tex_cache.has(rel):
		return _tex_cache[rel] as Image
	var path: String = "res://assets/world/" + rel
	var img: Image = null
	if ResourceLoader.exists(path):
		var t: Texture2D = load(path) as Texture2D
		if t != null:
			img = t.get_image()
			if img.is_compressed():
				img.decompress()
			img.convert(Image.FORMAT_RGBA8)
	else:
		print("[FEHLT] %s" % path)
	_tex_cache[rel] = img
	return img


func _terrain_name(t: int) -> String:
	match t:
		0: return "grass"
		1: return "forest"
		2: return "water"
		3: return "mountain"
		4: return "sand"
		5: return "swamp"
	return "grass"


# Zeichnet ein Bild ins Ziel, auf TILE skaliert, mit Alpha-Blending.
func _put(dst: Image, src: Image, x: int, y: int, w: int, h: int,
		tint: Color = Color.WHITE, dim: float = 0.0) -> void:
	if src == null:
		return
	var img: Image = src.duplicate()
	img.resize(w, h, Image.INTERPOLATE_LANCZOS)
	for iy in range(h):
		var ty: int = y + iy
		if ty < 0 or ty >= dst.get_height():
			continue
		for ix in range(w):
			var tx: int = x + ix
			if tx < 0 or tx >= dst.get_width():
				continue
			var c: Color = img.get_pixel(ix, iy)
			if c.a <= 0.004:
				continue
			c = Color(c.r * tint.r, c.g * tint.g, c.b * tint.b, c.a * tint.a)
			if dim > 0.0:
				c = c.darkened(dim)
			var b: Color = dst.get_pixel(tx, ty)
			dst.set_pixel(tx, ty, b.lerp(Color(c.r, c.g, c.b, 1.0), c.a))
	return


func _fill_rect(dst: Image, x: int, y: int, w: int, h: int, col: Color) -> void:
	for iy in range(max(0, y), min(dst.get_height(), y + h)):
		for ix in range(max(0, x), min(dst.get_width(), x + w)):
			var b: Color = dst.get_pixel(ix, iy)
			dst.set_pixel(ix, iy, b.lerp(Color(col.r, col.g, col.b, 1.0), col.a))


func _outline(dst: Image, x: int, y: int, w: int, h: int, col: Color, th: int) -> void:
	_fill_rect(dst, x, y, w, th, col)
	_fill_rect(dst, x, y + h - th, w, th, col)
	_fill_rect(dst, x, y, th, h, col)
	_fill_rect(dst, x + w - th, y, th, h, col)


func _compose(mw: int, mh: int, with_fog: bool) -> Image:
	var canvas := Image.create(mw * TILE, mh * TILE, false, Image.FORMAT_RGBA8)
	canvas.fill(Color(0.05, 0.06, 0.08))
	var map: Dictionary = _wm.get("_map")
	var tiles: Array = map["tiles"]
	var fog: Array = _wm.get("_fog_player")
	var variants: int = int(_wm.get("TERRAIN_VARIANTS"))
	var fog_variants: int = int(_wm.get("FOG_VARIANTS"))
	var hidden: int = int(_wm.get("FOG_HIDDEN"))
	var explored: int = int(_wm.get("FOG_EXPLORED"))

	# 1. Gelaende + Fransen (oder Nebel)
	for y in range(mh):
		for x in range(mw):
			var px: int = x * TILE
			var py: int = y * TILE
			var f: int = int(_wm.call("_fog_get", fog, Vector2i(x, y))) if with_fog else 2
			if with_fog and f == hidden:
				var v: int = int(_wm.call("_tile_variant", x, y, fog_variants))
				_put(canvas, _tex("terrain/fog_%d.svg" % v), px, py, TILE, TILE)
				continue
			var t: int = int(tiles[y * mw + x])
			var tv: int = int(_wm.call("_tile_variant", x, y, variants))
			var timg: Image = _tex("terrain/%s_%d.svg" % [_terrain_name(t), tv])
			if timg == null:
				timg = _tex("terrain/%s.svg" % _terrain_name(t))
			_put(canvas, timg, px, py, TILE, TILE, Color.WHITE,
				0.45 if (with_fog and f == explored) else 0.0)

	# 2. Fransen zu abweichenden Nachbarn - zweiter Durchgang, damit sie
	#    auf fertigem Gelaende liegen.
	var offs := {"top": Vector2i(0, -1), "right": Vector2i(1, 0),
		"bottom": Vector2i(0, 1), "left": Vector2i(-1, 0)}
	for y in range(mh):
		for x in range(mw):
			if with_fog and int(_wm.call("_fog_get", fog, Vector2i(x, y))) == hidden:
				continue
			var t: int = int(tiles[y * mw + x])
			for side in FRINGE_SIDES:
				var d: Vector2i = offs[side]
				var nx: int = x + d.x
				var ny: int = y + d.y
				if nx < 0 or nx >= mw or ny < 0 or ny >= mh:
					continue
				var nt: int = int(tiles[ny * mw + nx])
				if nt == t:
					continue
				var col: Color = _wm.call("_terrain_color", nt)
				col.a = FRINGE_ALPHA
				_put(canvas, _tex("terrain/fringe_%s.svg" % side),
					x * TILE, y * TILE, TILE, TILE, col)

	# 3. Objekte
	var sprites: Dictionary = _wm.get("OBJECT_SPRITES")
	var res_cols: Dictionary = _wm.get("RESOURCE_COLORS")
	for obj in (_wm.get("_objects") as Array):
		var op: Vector2i = obj["pos"]
		if with_fog and int(_wm.call("_fog_get", fog, op)) == hidden:
			continue
		var kind: int = int(obj["kind"])
		var name: String = "chest"
		var tint: Color = Color.WHITE
		if kind == int(_wm.get("OBJECT_MINE")):
			name = "mine"
		elif kind == int(_wm.get("OBJECT_PILE")):
			name = "pile"
			tint = res_cols.get(String(obj.get("resource", "gold")), Color.WHITE)
		elif sprites.has(kind):
			name = String(sprites[kind])
		var inset: int = int(TILE * 0.10)
		_put(canvas, _tex("objects/%s.svg" % name),
			op.x * TILE + inset, op.y * TILE + inset,
			TILE - 2 * inset, TILE - 2 * inset, tint)

	# 4. Staedte
	var fdirs: Array = _wm.get("FACTION_DIRS")
	for city in (_wm.get("_cities") as Array):
		var cp: Vector2i = city["pos"]
		if with_fog and int(_wm.call("_fog_get", fog, cp)) == hidden:
			continue
		var fid: int = int(city["faction"])
		var inset2: int = int(TILE * 0.06)
		_put(canvas, _tex("cities/%s.svg" % String(fdirs[fid])),
			cp.x * TILE + inset2, cp.y * TILE + inset2,
			TILE - 2 * inset2, TILE - 2 * inset2)
		var owner: int = int(city["owner"])
		if owner == int(_wm.get("OWNER_HERO")):
			_outline(canvas, cp.x * TILE + inset2, cp.y * TILE + inset2,
				TILE - 2 * inset2, TILE - 2 * inset2, Color(1.0, 0.85, 0.2, 1.0), 4)
		elif owner >= int(_wm.get("OWNER_AI_MIN")):
			_outline(canvas, cp.x * TILE + inset2, cp.y * TILE + inset2,
				TILE - 2 * inset2, TILE - 2 * inset2, Color(0.85, 0.15, 0.15, 1.0), 4)

	# 5. Monster als dunkle Scheibe mit Rand (wie im Screen)
	for m in (_wm.get("_monsters") as Array):
		var mp: Vector2i = m["pos"]
		if with_fog and int(_wm.call("_fog_get", fog, mp)) == hidden:
			continue
		var r: int = int(TILE * 0.30)
		var ccx: int = mp.x * TILE + TILE / 2
		var ccy: int = mp.y * TILE + TILE / 2
		for iy in range(ccy - r, ccy + r):
			for ix in range(ccx - r, ccx + r):
				if ix < 0 or iy < 0 or ix >= canvas.get_width() or iy >= canvas.get_height():
					continue
				var dd: float = Vector2(ix - ccx, iy - ccy).length()
				if dd <= float(r) - 3.0:
					canvas.set_pixel(ix, iy, Color(0.20, 0.20, 0.22))
				elif dd <= float(r):
					canvas.set_pixel(ix, iy, Color(0.85, 0.35, 0.35))

	# 6. Held und Gegner-Helden
	var hero = _wm.get("_hero")
	_put(canvas, _tex("units/hero.svg"),
		hero.position.x * TILE + 4, hero.position.y * TILE + 4, TILE - 8, TILE - 8)
	for e in (_wm.get("_enemies") as Array):
		var eh = e["hero"]
		if eh == null:
			continue
		if with_fog and int(_wm.call("_fog_get", fog, eh.position)) == hidden:
			continue
		_put(canvas, _tex("units/enemy.svg"),
			eh.position.x * TILE + 4, eh.position.y * TILE + 4, TILE - 8, TILE - 8)
	return canvas
