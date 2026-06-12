extends SceneTree

# Voll-Preview der Weltkarten-Terrain-Tiles: rendert eine Beispiel-Karte
# (15x22 Tiles, wie das Spiel) auf ein PNG, sodass man die neuen Texturen
# in Spiel-Aufloesung sehen kann ohne APK-Build.
#
#   godot --headless --path game/ --script tools/preview_world_terrain.gd
#
# Output: user://world-terrain-preview.png

const MAP_W := 15
const MAP_H := 22
const TILE := 64
const SEED := 42


func _init() -> void:
	var rng := DeterministicRng.new(SEED)
	var map: Dictionary = MapGen.generate(MAP_W, MAP_H, rng)
	var tiles: Array = map["tiles"]

	# Lade alle Terrain-Texturen einmal.
	var tex_map: Dictionary = {}
	for ti in [MapGen.TILE_GRASS, MapGen.TILE_FOREST, MapGen.TILE_WATER,
	           MapGen.TILE_MOUNTAIN, MapGen.TILE_SAND, MapGen.TILE_SWAMP]:
		var name: String = ""
		match ti:
			MapGen.TILE_GRASS:    name = "grass"
			MapGen.TILE_FOREST:   name = "forest"
			MapGen.TILE_WATER:    name = "water"
			MapGen.TILE_MOUNTAIN: name = "mountain"
			MapGen.TILE_SAND:     name = "sand"
			MapGen.TILE_SWAMP:    name = "swamp"
		var path := "res://assets/world/terrain/%s.svg" % name
		if ResourceLoader.exists(path):
			var tex: Texture2D = load(path) as Texture2D
			tex_map[ti] = tex.get_image()
		else:
			print("MISSING: ", path)

	var w_px: int = MAP_W * TILE
	var h_px: int = MAP_H * TILE
	var canvas := Image.create(w_px, h_px, false, Image.FORMAT_RGBA8)
	canvas.fill(Color(0.04, 0.04, 0.06, 1.0))

	for y in range(MAP_H):
		for x in range(MAP_W):
			var ti: int = int(tiles[y * MAP_W + x])
			if not tex_map.has(ti):
				continue
			var src_img: Image = tex_map[ti]
			# Wenn die SVG nicht exakt TILE-Pixel gross ist, einmal resize.
			if src_img.get_width() != TILE or src_img.get_height() != TILE:
				var resized := Image.create(TILE, TILE, false, Image.FORMAT_RGBA8)
				resized.copy_from(src_img)
				resized.resize(TILE, TILE, Image.INTERPOLATE_LANCZOS)
				src_img = resized
			canvas.blend_rect(src_img,
				Rect2i(0, 0, TILE - 1, TILE - 1),
				Vector2i(x * TILE, y * TILE))

	# Demo-Overlay: 4 Staedte, 1 Held, 1 Gegner, 1 Truhe, 1 Mine - damit
	# man im PNG sieht, wie die neuen Welt-Sprites zusammen aussehen.
	_blit(canvas, "res://assets/world/cities/menschen.svg",   3,  2)
	_blit(canvas, "res://assets/world/cities/waldvolk.svg",  10,  3)
	_blit(canvas, "res://assets/world/cities/totenreich.svg", 2, 14)
	_blit(canvas, "res://assets/world/cities/orks.svg",      11, 18)
	_blit(canvas, "res://assets/world/units/hero.svg",        5,  5)
	_blit(canvas, "res://assets/world/units/enemy.svg",       9, 12)
	_blit(canvas, "res://assets/world/objects/chest.svg",     7,  8)
	_blit(canvas, "res://assets/world/objects/mine.svg",      6, 16)

	var save_err: int = canvas.save_png("user://world-terrain-preview.png")
	print("size=%dx%d save_err=%d -> %s" % [
		w_px, h_px, save_err,
		ProjectSettings.globalize_path("user://world-terrain-preview.png")])
	quit(0)


func _blit(canvas: Image, path: String, tx: int, ty: int) -> void:
	if not ResourceLoader.exists(path):
		print("MISSING blit: ", path)
		return
	var tex: Texture2D = load(path) as Texture2D
	var img: Image = tex.get_image()
	if img.get_width() != TILE or img.get_height() != TILE:
		var resized := Image.create(TILE, TILE, false, Image.FORMAT_RGBA8)
		resized.copy_from(img)
		resized.resize(TILE, TILE, Image.INTERPOLATE_LANCZOS)
		img = resized
	canvas.blend_rect(img, Rect2i(0, 0, TILE - 1, TILE - 1),
		Vector2i(tx * TILE, ty * TILE))
