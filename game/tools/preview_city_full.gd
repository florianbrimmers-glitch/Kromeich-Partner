extends SceneTree

# Headless Voll-Preview fuer den CityScreen: komponiert die Sprites in
# ein 1080x1920-Bild an den realen Hotspot-Positionen aus
# data/city_layout.json mit der realen Skalierung aus CityScreen.gd.
# Approximiert das Phone-Display ohne SubViewport (das braucht Display).
#
#   godot --headless --path game/ --script tools/preview_city_full.gd
#
# Output: user://city-full-preview.png

const W := 1080
const H := 1920
const HUD_TOP := 150
const HUD_BOTTOM := 180

# Spiegelt CityScreen.gd Konstanten
const SPRITE_GROUND_FRAC := 0.56
const HW_MAX := 150.0
const STAGE_W_FRAC := 0.15


func _init() -> void:
	var canvas := Image.create(W, H, false, Image.FORMAT_RGBA8)
	canvas.fill(Color(0.07, 0.08, 0.11, 1.0))
	# HUD-Streifen oben/unten
	_fill_rect(canvas, 0, 0, W, HUD_TOP, Color(0.05, 0.06, 0.08))
	_fill_rect(canvas, 0, H - HUD_BOTTOM, W, HUD_BOTTOM, Color(0.05, 0.06, 0.08))
	# Stage-Backdrop: bg.svg falls vorhanden, sonst Plateau-Farbe.
	var bg_path := "res://assets/city/menschen/bg.svg"
	if ResourceLoader.exists(bg_path):
		var bg_tex: Texture2D = load(bg_path) as Texture2D
		var bg_img: Image = bg_tex.get_image()
		bg_img.resize(W, H - HUD_TOP - HUD_BOTTOM, Image.INTERPOLATE_LANCZOS)
		canvas.blend_rect(bg_img, Rect2i(0, 0, W, H - HUD_TOP - HUD_BOTTOM), Vector2i(0, HUD_TOP))
	else:
		_fill_rect(canvas, 0, HUD_TOP, W, H - HUD_TOP - HUD_BOTTOM, Color(0.12, 0.14, 0.13))

	var layout: Dictionary = _load_layout()
	var stage_x: float = 0.0
	var stage_y: float = float(HUD_TOP)
	var stage_w: float = float(W)
	var stage_h: float = float(H - HUD_TOP - HUD_BOTTOM)
	var hw: float = min(stage_w * STAGE_W_FRAC, HW_MAX)
	# var hh: float = hw * 0.5  # reserviert fuer ggf. spaeter

	# Sortierung: kleineres y zuerst, damit vordere Gebaeude vorne sind.
	var ordered: Array = layout.keys()
	ordered.sort_custom(func(a, b):
		return float(layout[a].get("y", 0.5)) < float(layout[b].get("y", 0.5)))

	for bid in ordered:
		var lp: Dictionary = layout[bid]
		var cx: float = stage_x + float(lp.get("x", 0.5)) * stage_w
		var cy: float = stage_y + float(lp.get("y", 0.5)) * stage_h
		var tex_path := "res://assets/city/menschen/%s.svg" % bid
		if not ResourceLoader.exists(tex_path):
			continue
		var tex: Texture2D = load(tex_path) as Texture2D
		var img: Image = tex.get_image()
		var sprite_w: int = int(hw * 2.4)
		var sprite_h: int = int(sprite_w * (float(img.get_height()) / float(img.get_width())))
		var img_scaled := Image.create(sprite_w, sprite_h, false, Image.FORMAT_RGBA8)
		img_scaled.copy_from(img)
		img_scaled.resize(sprite_w, sprite_h, Image.INTERPOLATE_LANCZOS)
		var dst_x: int = int(cx - sprite_w * 0.5)
		var dst_y: int = int(cy - sprite_h * SPRITE_GROUND_FRAC)
		_blend_clipped(canvas, img_scaled, dst_x, dst_y)
		print("[OK] %s @ (%d,%d) size=%dx%d" % [bid, cx, cy, sprite_w, sprite_h])

	var save_err: int = canvas.save_png("user://city-full-preview.png")
	print("save_err=%d -> %s" % [save_err, ProjectSettings.globalize_path("user://city-full-preview.png")])
	quit(0)


func _load_layout() -> Dictionary:
	var f := FileAccess.open("res://data/city_layout.json", FileAccess.READ)
	var raw: Variant = JSON.parse_string(f.get_as_text())
	if typeof(raw) == TYPE_DICTIONARY:
		return (raw as Dictionary)["buildings"]
	return {}


func _fill_rect(img: Image, x: int, y: int, w: int, h: int, c: Color) -> void:
	for j in range(max(0, y), min(img.get_height(), y + h)):
		for i in range(max(0, x), min(img.get_width(), x + w)):
			img.set_pixel(i, j, c)


func _blend_clipped(dst: Image, src: Image, dst_x: int, dst_y: int) -> void:
	var sw: int = src.get_width()
	var sh: int = src.get_height()
	var clip_w: int = min(sw, dst.get_width() - dst_x)
	var clip_h: int = min(sh, dst.get_height() - dst_y)
	if clip_w <= 0 or clip_h <= 0:
		return
	var src_off_x: int = max(0, -dst_x)
	var src_off_y: int = max(0, -dst_y)
	var dst_off_x: int = max(0, dst_x)
	var dst_off_y: int = max(0, dst_y)
	var w: int = clip_w - src_off_x
	var h: int = clip_h - src_off_y
	if w <= 0 or h <= 0:
		return
	dst.blend_rect(src, Rect2i(src_off_x, src_off_y, w, h),
		Vector2i(dst_off_x, dst_off_y))
