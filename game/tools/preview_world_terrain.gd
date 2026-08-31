extends SceneTree

# Voll-Vorschau der Weltkarte: rendert eine Beispielkarte in Spiel-
# Aufloesung auf ein PNG, ohne APK-Build. Der echte WorldMapScreen laesst
# sich headless nicht rendern (kein Display, siehe game/CLAUDE.md).
#
#   godot --headless --path game/ --script tools/preview_world_terrain.gd
#
# Spiegelt bewusst die Zeichenreihenfolge aus WorldMapScreen._draw_map:
#   1. Nebelkachel wenn unerforscht
#   2. sonst Gelaende-Kachel in der Variante aus _tile_variant
#   3. darauf die Uebergangs-Fransen der abweichenden Nachbarn
# Nur so faellt auf, wenn Varianten oder Fransen im Feld falsch wirken -
# einzelne Kacheln nebeneinander sehen immer gut aus.
#
# Output: user://world-map-preview.png (links komplett erkundet,
#         rechts mit Kriegsnebel wie im Spiel)

const MAP_W := 18
const MAP_H := 26
const TILE := 64
const SEED := 42

# Muss zu WorldMapScreen passen.
const TERRAIN_VARIANTS := 6
const FOG_VARIANTS := 6
const FRINGE_ALPHA := 0.40
const FRINGE_SIDES := ["top", "right", "bottom", "left"]
const TERRAIN_NAMES := {
	MapGen.TILE_GRASS: "grass", MapGen.TILE_FOREST: "forest",
	MapGen.TILE_WATER: "water", MapGen.TILE_MOUNTAIN: "mountain",
	MapGen.TILE_SAND: "sand", MapGen.TILE_SWAMP: "swamp",
}
# Fallback-Farben wie WorldMapScreen._terrain_color - die Franse wird damit
# eingefaerbt.
const TERRAIN_COLORS := {
	MapGen.TILE_GRASS: Color(0.30, 0.48, 0.22),
	MapGen.TILE_FOREST: Color(0.18, 0.33, 0.15),
	MapGen.TILE_WATER: Color(0.16, 0.36, 0.52),
	MapGen.TILE_MOUNTAIN: Color(0.40, 0.38, 0.35),
	MapGen.TILE_SAND: Color(0.76, 0.66, 0.42),
	MapGen.TILE_SWAMP: Color(0.26, 0.32, 0.18),
}

var _cache: Dictionary = {}


func _init() -> void:
	var rng := DeterministicRng.new(SEED)
	var map: Dictionary = MapGen.generate(MAP_W, MAP_H, rng)
	var tiles: Array = map["tiles"]

	var gap: int = 16
	var pw: int = MAP_W * TILE
	var canvas := Image.create(pw * 2 + gap, MAP_H * TILE, false, Image.FORMAT_RGBA8)
	canvas.fill(Color(0.02, 0.02, 0.03, 1.0))

	# Linke Haelfte: alles erkundet. Rechte Haelfte: Nebel um einen Punkt,
	# damit der Uebergang erforscht/unerforscht beurteilbar ist.
	var hero := Vector2i(MAP_W / 2, MAP_H / 2 + 3)
	for pass_i in range(2):
		var ox: int = pass_i * (pw + gap)
		var fogged: bool = pass_i == 1
		for y in range(MAP_H):
			for x in range(MAP_W):
				var ti: int = int(tiles[y * MAP_W + x])
				var dist: int = absi(x - hero.x) + absi(y - hero.y)
				if fogged and dist > 7:
					_blit(canvas, "fog_%d" % _variant(x, y, FOG_VARIANTS),
						ox + x * TILE, y * TILE)
					continue
				var name: String = String(TERRAIN_NAMES.get(ti, "grass"))
				_blit(canvas, "%s_%d" % [name, _variant(x, y, TERRAIN_VARIANTS)],
					ox + x * TILE, y * TILE)
				_fringes(canvas, tiles, x, y, ti, ox)
				if fogged and dist > 4:
					# Erkundet aber nicht in Sicht: gedimmt wie im Screen.
					_dim(canvas, ox + x * TILE, y * TILE, 0.55)
	var err: int = canvas.save_png("user://world-map-preview.png")
	print("save_err=%d -> %s" % [err,
		ProjectSettings.globalize_path("user://world-map-preview.png")])
	quit(0)


# Muss identisch zu WorldMapScreen._tile_variant sein, sonst zeigt die
# Vorschau eine andere Karte als das Spiel.
func _variant(x: int, y: int, count: int) -> int:
	var h: int = (x * 73856093) ^ (y * 19349663) ^ (SEED * 83492791)
	h = (h ^ (h >> 13)) * 1274126177
	h = h ^ (h >> 16)
	return absi(h) % count


func _fringes(canvas: Image, tiles: Array, x: int, y: int, own: int, ox: int) -> void:
	var dirs := [Vector2i(0, -1), Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0)]
	for i in range(4):
		var nx: int = x + dirs[i].x
		var ny: int = y + dirs[i].y
		if nx < 0 or ny < 0 or nx >= MAP_W or ny >= MAP_H:
			continue
		var other: int = int(tiles[ny * MAP_W + nx])
		if other == own:
			continue
		var col: Color = TERRAIN_COLORS.get(other, Color(1, 1, 1))
		col.a = FRINGE_ALPHA
		_blit_tinted(canvas, "fringe_%s" % String(FRINGE_SIDES[i]),
			ox + x * TILE, y * TILE, col)


func _image(name: String) -> Image:
	if _cache.has(name):
		return _cache[name] as Image
	var path: String = "res://assets/world/terrain/%s.svg" % name
	var img: Image = null
	if ResourceLoader.exists(path):
		var tex: Texture2D = load(path) as Texture2D
		if tex != null:
			img = tex.get_image()
			if img.is_compressed():
				img.decompress()
			img.convert(Image.FORMAT_RGBA8)
			if img.get_width() != TILE:
				img.resize(TILE, TILE, Image.INTERPOLATE_LANCZOS)
	else:
		print("[FEHLT] %s" % path)
	_cache[name] = img
	return img


func _blit(canvas: Image, name: String, px: int, py: int) -> void:
	var img: Image = _image(name)
	if img == null:
		return
	canvas.blit_rect(img, Rect2i(0, 0, TILE, TILE), Vector2i(px, py))


# Franse mit Nachbarfarbe multiplizieren und alpha-blenden - entspricht
# draw_texture_rect(..., modulate) im Screen.
func _blit_tinted(canvas: Image, name: String, px: int, py: int, col: Color) -> void:
	var img: Image = _image(name)
	if img == null:
		return
	for j in range(TILE):
		for i in range(TILE):
			var src: Color = img.get_pixel(i, j)
			var a: float = src.a * col.a
			if a <= 0.004:
				continue
			var dst: Color = canvas.get_pixel(px + i, py + j)
			canvas.set_pixel(px + i, py + j, dst.lerp(
				Color(src.r * col.r, src.g * col.g, src.b * col.b), a))


func _dim(canvas: Image, px: int, py: int, amount: float) -> void:
	for j in range(TILE):
		for i in range(TILE):
			var dst: Color = canvas.get_pixel(px + i, py + j)
			canvas.set_pixel(px + i, py + j, dst.lerp(Color(0, 0, 0), amount))
