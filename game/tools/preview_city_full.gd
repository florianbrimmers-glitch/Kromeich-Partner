extends SceneTree

# Headless-Vollvorschau des Stadtbildschirms fuer ALLE VIER Fraktionen.
#
# Der echte CityScreen laesst sich headless nicht rendern (kein Display,
# siehe game/CLAUDE.md). Dieses Tool komponiert die Buehne als Bild: echter
# Hintergrund, echte Hotspot-Positionen aus data/city_layout.json, echte
# Sprite-Skalierung und echter Boden-Anker aus CityScreen.gd. Damit faellt
# auf, was Tests nicht sehen - dass Gebaeude ueber ihrer Raute schweben,
# dass ein Sprite fehlt, dass zwei Motive uebereinanderliegen.
#
#   godot --headless --path game/ --script tools/preview_city_full.gd
#
# Ergebnis: user://city-sheet.png (4 Fraktionen x 2 Zustaende, halbe Groesse)
#   plus user://city-<fraktion>.png in voller Groesse.

const W := 1080
const H := 1920
const HUD_TOP := 250     # spiegelt CityScreen.HUD_TOP
const HUD_BOTTOM := 180

# Spiegelt CityScreen.gd
const SPRITE_GROUND_FRAC := 0.56
const HW_MAX := 150.0
const STAGE_W_FRAC := 0.15

const FACTIONS := ["waldvolk", "menschen", "totenreich", "orks"]
# Fraktionsfarben nur fuer den Notfall-Platzhalter (sollte nie greifen).
const FACTION_TINT := [Color(0.45, 0.80, 0.40), Color(0.95, 0.85, 0.45),
	Color(0.70, 0.45, 0.90), Color(0.90, 0.45, 0.30)]

const SHEET_SCALE := 0.5


func _init() -> void:
	var panels: Array = []
	for i in range(FACTIONS.size()):
		var fac: String = FACTIONS[i]
		# Fertige Stadt (mit Mauer -> bg_walled) und Baustelle.
		var built: Image = _render(fac, i, true)
		var raw: Image = _render(fac, i, false)
		built.save_png("user://city-%s.png" % fac)
		panels.append(built)
		panels.append(raw)
	_sheet(panels)
	quit(0)


# Kontaktbogen: Spalte = Fraktion, Zeile 1 = fertig, Zeile 2 = im Bau.
func _sheet(panels: Array) -> void:
	var pw: int = int(W * SHEET_SCALE)
	var ph: int = int(H * SHEET_SCALE)
	var gap: int = 10
	var sheet := Image.create(pw * 4 + gap * 3, ph * 2 + gap, false, Image.FORMAT_RGBA8)
	sheet.fill(Color(0.02, 0.02, 0.03, 1.0))
	for i in range(panels.size()):
		var col: int = i / 2
		var row: int = i % 2
		var img: Image = (panels[i] as Image).duplicate()
		img.resize(pw, ph, Image.INTERPOLATE_LANCZOS)
		sheet.blit_rect(img, Rect2i(0, 0, pw, ph),
			Vector2i(col * (pw + gap), row * (ph + gap)))
	var err: int = sheet.save_png("user://city-sheet.png")
	print("save_err=%d -> %s" % [err,
		ProjectSettings.globalize_path("user://city-sheet.png")])


func _render(fac: String, fid: int, all_built: bool) -> Image:
	var canvas := Image.create(W, H, false, Image.FORMAT_RGBA8)
	canvas.fill(Color(0.07, 0.08, 0.11, 1.0))
	_fill_rect(canvas, 0, 0, W, HUD_TOP, Color(0.05, 0.06, 0.08))
	_fill_rect(canvas, 0, H - HUD_BOTTOM, W, HUD_BOTTOM, Color(0.05, 0.06, 0.08))

	var stage_h: int = H - HUD_TOP - HUD_BOTTOM
	# Spiegelt CityScreen._draw: mit gebauter Mauer bg_walled, sonst bg.
	var bg_path := ""
	if all_built:
		bg_path = _first_existing(["res://assets/city/%s/bg_walled.svg" % fac,
			"res://assets/city/%s/bg_walled.png" % fac])
	if bg_path == "":
		bg_path = _first_existing(["res://assets/city/%s/bg.svg" % fac,
			"res://assets/city/%s/bg.png" % fac])
	if bg_path != "":
		var bg_img: Image = _image_of(bg_path)
		bg_img.resize(W, stage_h, Image.INTERPOLATE_LANCZOS)
		canvas.blend_rect(bg_img, Rect2i(0, 0, W, stage_h), Vector2i(0, HUD_TOP))
	else:
		print("[FEHLT] Hintergrund fuer %s" % fac)
		var accent: Color = FACTION_TINT[fid]
		for yy in range(stage_h):
			var tt: float = float(yy) / float(stage_h - 1)
			_fill_rect(canvas, 0, HUD_TOP + yy, W, 1,
				Color(0.10, 0.12, 0.17).lerp(accent, 0.10).lerp(
					Color(0.15, 0.16, 0.13).lerp(accent, 0.05), tt))

	var layout: Dictionary = _load_layout(bg_path == "")
	var hw: float = min(float(W) * STAGE_W_FRAC, HW_MAX)

	# Sortierung wie im Screen: kleineres y zuerst, damit vordere Gebaeude
	# vorne liegen.
	var ordered: Array = layout.keys()
	ordered.sort_custom(func(a, b):
		return float(layout[a].get("y", 0.5)) < float(layout[b].get("y", 0.5)))

	var missing: int = 0
	for bid in ordered:
		var lp: Dictionary = layout[bid]
		var cx: float = float(lp.get("x", 0.5)) * float(W)
		var cy: float = float(HUD_TOP) + float(lp.get("y", 0.5)) * float(stage_h)
		var tex_path := ""
		if all_built:
			tex_path = "res://assets/city/%s/%s.svg" % [fac, bid]
		else:
			var specific := "res://assets/city/_shared/construction-%s.svg" % bid
			tex_path = specific if ResourceLoader.exists(specific) \
				else "res://assets/city/_shared/construction.svg"
		if not ResourceLoader.exists(tex_path):
			print("[FEHLT] %s" % tex_path)
			missing += 1
			continue
		var img: Image = _image_of(tex_path)
		# Muss zu CityScreen._draw_sprite_at passen.
		var sprite_w: int = int(hw * (2.0 if all_built else 1.5))
		var sprite_h: int = int(float(sprite_w) * (float(img.get_height()) / float(img.get_width())))
		img.resize(sprite_w, sprite_h, Image.INTERPOLATE_LANCZOS)
		_blend_clipped(canvas, img, int(cx - float(sprite_w) * 0.5),
			int(cy - float(sprite_h) * SPRITE_GROUND_FRAC))
	print("[%s] %s: %d Plots, %d fehlend" % [
		fac, "fertig" if all_built else "im Bau", ordered.size(), missing])
	return canvas


func _image_of(path: String) -> Image:
	var tex: Texture2D = load(path) as Texture2D
	var img: Image = tex.get_image()
	# PNGs kommen VRAM-komprimiert aus dem Import; resize/blend brauchen RGBA8.
	if img.is_compressed():
		img.decompress()
	img.convert(Image.FORMAT_RGBA8)
	return img


func _load_layout(plain: bool) -> Dictionary:
	var f := FileAccess.open("res://data/city_layout.json", FileAccess.READ)
	var raw: Variant = JSON.parse_string(f.get_as_text())
	if typeof(raw) != TYPE_DICTIONARY:
		return {}
	var d: Dictionary = raw as Dictionary
	if plain and d.has("buildings_plain"):
		return d["buildings_plain"]
	return d["buildings"]


func _fill_rect(img: Image, x: int, y: int, w: int, h: int, c: Color) -> void:
	for j in range(max(0, y), min(img.get_height(), y + h)):
		for i in range(max(0, x), min(img.get_width(), x + w)):
			img.set_pixel(i, j, c)


func _blend_clipped(dst: Image, src: Image, dst_x: int, dst_y: int) -> void:
	var src_off_x: int = max(0, -dst_x)
	var src_off_y: int = max(0, -dst_y)
	var w: int = min(src.get_width() - src_off_x, dst.get_width() - max(0, dst_x))
	var h: int = min(src.get_height() - src_off_y, dst.get_height() - max(0, dst_y))
	if w <= 0 or h <= 0:
		return
	dst.blend_rect(src, Rect2i(src_off_x, src_off_y, w, h),
		Vector2i(max(0, dst_x), max(0, dst_y)))


func _first_existing(paths: Array) -> String:
	for p in paths:
		if ResourceLoader.exists(String(p)):
			return String(p)
	return ""
