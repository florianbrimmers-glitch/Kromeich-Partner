extends SceneTree

# Komponierte Kampf-Ansicht in ECHTER Geraetegroesse (It. 36).
#
#   godot --headless --path game/ --script tools/preview_battle_full.gd
#
# WARUM NEU, obwohl es preview_battle.gd gibt: das alte Werkzeug ist ein
# NACHBAU. Es haelt eigene Kopien von CELL, PAD_TOP, PAD_BOTTOM und
# TERRAIN_GROUND und stellt sich die Stacks selbst zusammen. Genau solche
# Kopien sind in It. 33 und 34 auseinandergelaufen. Hier kommt alles aus
# einem ECHTEN TacticalBattleScreen:
#   - Bildschirmgroesse aus den Projekt-Einstellungen
#   - Lage des Gitterfeldes aus den Anchors/Offsets des _grid_area-Knotens
#   - Zellgroesse und Ursprung aus bs._geom()
#   - Stacks, Hindernisse, Gelaende aus set_battle()
#   - Boden-Variante und Textur ueber bs._ground_variant / bs._battle_texture
#
# Was die Vorschau NICHT kann: Text. Image hat kein draw_string. Textzeilen
# werden deshalb als gemessene Kaesten dargestellt (Font.get_string_size),
# damit man sieht, wieviel Platz sie brauchen und ob sie kollidieren.
#
# Ausgabe: user://battle-full-<gelaende>.png

const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")
const UnitArt := preload("res://scripts/core/UnitArt.gd")

const CASES := [
	{"terrain": 0, "name": "gras",
		"player": [{"type": "men_spearman", "count": 24}, {"type": "men_archer", "count": 12}],
		"enemy": [{"type": "ork_goblin", "count": 30}, {"type": "ork_ogre", "count": 4}]},
	{"terrain": 5, "name": "sumpf",
		"player": [{"type": "elf_dwarf", "count": 18}, {"type": "elf_archer", "count": 9},
			{"type": "elf_goldwyrm", "count": 1}],
		"enemy": [{"type": "nec_skeleton", "count": 40}, {"type": "nec_lich", "count": 6},
			{"type": "nec_bonedragon", "count": 2}]},
]

var _cache: Dictionary = {}


func _init() -> void:
	var w: int = int(ProjectSettings.get_setting("display/window/size/viewport_width", 1080))
	var h: int = int(ProjectSettings.get_setting("display/window/size/viewport_height", 1920))
	print("Geraetegroesse aus den Projekt-Einstellungen: %dx%d" % [w, h])

	for case in CASES:
		var img: Image = await _render(case, w, h)
		var path: String = "user://battle-full-%s.png" % String(case["name"])
		var err: int = img.save_png(path)
		print("%s save_err=%d -> %s" % [path, err,
			ProjectSettings.globalize_path(path)])
	quit(0)


func _render(case: Dictionary, w: int, h: int) -> Image:
	var bs = TBS.new()
	bs.fx_speed = 0.0
	root.add_child(bs)
	await process_frame
	bs.set_battle({
		"player_stacks": case["player"],
		"enemy_stacks": case["enemy"],
		"seed": 31337, "terrain_id": int(case["terrain"]),
		"allow_flee": true, "player_att": 3, "player_def": 2,
	})
	await process_frame

	# Lage des Gitterfeldes aus dem KNOTEN, nicht aus einer Kopie: das
	# Gitterfeld haengt an PRESET_FULL_RECT, seine Groesse ist also
	# Bildschirm minus Offsets.
	var ga: Control = bs._grid_area
	var grect := Rect2(
		Vector2(ga.offset_left, ga.offset_top),
		Vector2(float(w) + ga.offset_right - ga.offset_left,
			float(h) + ga.offset_bottom - ga.offset_top))
	# Groesse setzen und SOFORT _geom() fragen (ohne Frame dazwischen, sonst
	# rechnet das Layout sie wieder auf die Fenstergroesse zurueck).
	ga.size = grect.size
	var g: Array = bs._geom()
	var o: Vector2 = grect.position + (g[0] as Vector2)
	var cell: float = float(g[1])
	print("[%s] Gitterfeld %s, Zelle %.1f px, Gitter %.0fx%.0f, Baender %.0f px (%.0f %%)"
		% [String(case["name"]), str(grect.size), cell,
			cell * bs.GRID_COLS, cell * bs.GRID_ROWS,
			grect.size.y - cell * bs.GRID_ROWS,
			100.0 * (grect.size.y - cell * bs.GRID_ROWS) / grect.size.y])

	var canvas := Image.create(w, h, false, Image.FORMAT_RGBA8)
	canvas.fill(Color(0.04, 0.05, 0.08))

	# --- Hintergrund des Gitterfeldes: Verlauf wie im Screen
	var ground: Color = bs._ground_color()
	var bands: int = 16
	for i in range(bands):
		var t: float = float(i) / float(bands - 1)
		var by: int = int(grect.position.y + grect.size.y * float(i) / float(bands))
		var bh: int = int(grect.size.y / float(bands)) + 1
		_fill(canvas, int(grect.position.x), by, int(grect.size.x), bh,
			ground.darkened(0.55).lerp(ground.darkened(0.25), t))

	# --- Kulisse oben, Bewuchs unten
	var art: String = bs._terrain_art_name()
	var back: Image = _img(bs, "backdrop/%s.svg" % art)
	if back != null and (g[0] as Vector2).y > 8.0:
		var bh2: int = int(min((g[0] as Vector2).y, grect.size.x * 0.34))
		_put(canvas, back, int(grect.position.x), int(o.y) - bh2,
			int(grect.size.x), bh2)
	var fore: Image = _img(bs, "fore/%s.svg" % art)
	var below: float = grect.size.y - ((g[0] as Vector2).y + cell * bs.GRID_ROWS)
	if fore != null and below > 8.0:
		var fh: int = int(min(below, grect.size.x * 0.22))
		_put(canvas, fore, int(grect.position.x),
			int(o.y + cell * bs.GRID_ROWS), int(grect.size.x), fh)

	# --- Boden-Kacheln
	for cx in range(bs.GRID_COLS):
		for cy in range(bs.GRID_ROWS):
			var v: int = int(bs._ground_variant(cx, cy))
			var gt: Image = _img(bs, "ground/%s_%d.svg" % [art, v])
			var px: int = int(o.x + float(cx) * cell)
			var py: int = int(o.y + float(cy) * cell)
			if gt != null:
				_put(canvas, gt, px, py, int(cell) + 1, int(cell) + 1)
			else:
				var shade: float = 0.04 if (cx + cy) % 2 == 0 else 0.0
				_fill(canvas, px, py, int(cell) + 1, int(cell) + 1,
					ground.lightened(shade))

	# --- Hindernisse
	for ob in bs._obstacles:
		var p: Vector2i = ob["pos"]
		var kind: int = int(ob["kind"])
		# Namen aus der Tabelle des Screens, nicht geraten (mein erster
		# Anlauf hatte "mud" statt "swamp" und meldete eine fehlende Datei,
		# die es nie gab).
		var rel: String = "obstacles/%s.svg" % String(bs.OBSTACLE_ART.get(kind, "stone"))
		var oi: Image = _img(bs, rel)
		var ox: int = int(o.x + float(p.x) * cell)
		var oy: int = int(o.y + float(p.y) * cell)
		if oi != null:
			_put(canvas, oi, ox, oy, int(cell), int(cell))
		else:
			_fill(canvas, ox + int(cell * 0.2), oy + int(cell * 0.2),
				int(cell * 0.6), int(cell * 0.6), Color(0.3, 0.3, 0.32, 0.8))

	# --- Token: Scheibe, Sprite, Beschriftungs-Kasten
	var font: Font = ThemeDB.fallback_font
	for side in [0, 1]:
		var stacks: Array = bs._p_stacks if side == 0 else bs._e_stacks
		for st in stacks:
			if int(st["count"]) <= 0:
				continue
			var sp: Vector2i = st["pos"]
			var ctr := Vector2(o.x + (float(sp.x) + 0.5) * cell,
				o.y + (float(sp.y) + 0.5) * cell)
			var r: float = cell * float(bs.TOKEN_DISC_FRAC)
			var ring: Color = Color(0.95, 0.80, 0.25) if side == 0 \
				else Color(0.85, 0.25, 0.25)
			_disc(canvas, ctr, r, ring.darkened(0.72), ring)
			var ui: Image = _unit_img(String(st["type"]))
			var usz: int = int(cell * float(bs.TOKEN_SPRITE_FRAC))
			_put(canvas, ui, int(ctr.x) - usz / 2,
				int(ctr.y - float(usz) * (0.5 + float(bs.TOKEN_SPRITE_LIFT))),
				usz, usz)
			# Beschriftung: gemessener Kasten (Image kann keinen Text).
			# ACHTUNG, hier lag mein erster Fehler: cell*0.52 ist im Screen
			# der ABSTAND unter der Mitte, nicht die Schriftgroesse. Die
			# ist max(15, cell*0.30). Mit 0.52 als Groesse zeigte die
			# Vorschau Textkaesten von 54 px und ich hielt die Beschriftung
			# fuer zu gross - das Werkzeug log, nicht das Spiel.
			var label: String = "%s%d" % [UnitType.short_of(String(st["type"])),
				int(st["count"])]
			var fsize: int = int(max(15.0, cell * 0.30))
			var ts: Vector2 = font.get_string_size(label,
				HORIZONTAL_ALIGNMENT_CENTER, -1, fsize)
			_fill(canvas, int(ctr.x - ts.x * 0.5), int(ctr.y + cell * 0.52),
				int(ts.x), int(ts.y), Color(0.95, 0.95, 1.0, 0.45))

	# --- UI-Baender: Kopfzeile, Log, Knopfzeile als Kaesten
	_fill(canvas, 0, 0, w, int(grect.position.y), Color(0.10, 0.11, 0.16, 0.9))
	_ui_text_box(canvas, font, w, 20, 50, 36, "KAMPF", Color(0.95, 0.85, 0.40, 0.5))
	_ui_text_box(canvas, font, w, 68, 50, 26,
		"Held 36 (Moral +1 Glueck +0)  vs  Gegner 34   Runde 1",
		Color(0.9, 0.92, 0.96, 0.5))
	var log_top: int = h - 300
	_fill(canvas, 40, log_top, w - 80, 120, Color(0.80, 0.88, 1.0, 0.16))
	for i in range(3):
		_ui_text_box(canvas, font, w, log_top + i * 40, 40, 22,
			"Held Sp greift Go an: 12 Schaden, 2 gefallen",
			Color(0.80, 0.88, 1.0, 0.45))
	_fill(canvas, 50, h - 170, 430, 120, Color(0.6, 0.6, 0.7, 0.35))
	_fill(canvas, 500, h - 170, w - 1000, 120, Color(0.6, 0.6, 0.7, 0.35))
	_fill(canvas, w - 480, h - 170, 430, 120, Color(0.6, 0.6, 0.7, 0.35))

	bs.queue_free()
	await process_frame
	return canvas


func _img(bs, rel: String) -> Image:
	if _cache.has(rel):
		return _cache[rel] as Image
	var img: Image = null
	var tex: Texture2D = bs._battle_texture(rel)
	if tex != null:
		img = tex.get_image()
		if img.is_compressed():
			img.decompress()
		img.convert(Image.FORMAT_RGBA8)
	else:
		print("[FEHLT] battle/%s" % rel)
	_cache[rel] = img
	return img


func _unit_img(uid: String) -> Image:
	var key: String = "unit:" + uid
	if _cache.has(key):
		return _cache[key] as Image
	var img: Image = null
	var tex: Texture2D = UnitArt.texture_for(uid)
	if tex != null:
		img = tex.get_image()
		if img.is_compressed():
			img.decompress()
		img.convert(Image.FORMAT_RGBA8)
	_cache[key] = img
	return img


func _ui_text_box(dst: Image, font: Font, w: int, y: int, x: int, fsize: int,
		text: String, col: Color) -> void:
	var ts: Vector2 = font.get_string_size(text, HORIZONTAL_ALIGNMENT_CENTER,
		-1, fsize)
	var cx: int = int((float(w) - ts.x) * 0.5) if x < 0 else x
	_fill(dst, cx, y, int(ts.x), int(ts.y), col)


func _fill(dst: Image, x: int, y: int, w: int, h: int, col: Color) -> void:
	for iy in range(max(0, y), min(dst.get_height(), y + h)):
		for ix in range(max(0, x), min(dst.get_width(), x + w)):
			var b: Color = dst.get_pixel(ix, iy)
			dst.set_pixel(ix, iy, b.lerp(Color(col.r, col.g, col.b, 1.0), col.a))


func _disc(dst: Image, ctr: Vector2, r: float, fill: Color, ring: Color) -> void:
	var r0: int = int(r)
	for iy in range(int(ctr.y) - r0 - 3, int(ctr.y) + r0 + 4):
		for ix in range(int(ctr.x) - r0 - 3, int(ctr.x) + r0 + 4):
			if ix < 0 or iy < 0 or ix >= dst.get_width() or iy >= dst.get_height():
				continue
			var d: float = Vector2(float(ix), float(iy)).distance_to(ctr)
			if d <= r - 1.0:
				dst.set_pixel(ix, iy, fill)
			elif d <= r + 2.0:
				dst.set_pixel(ix, iy, ring)


func _put(dst: Image, src: Image, x: int, y: int, w: int, h: int) -> void:
	if src == null or w <= 0 or h <= 0:
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
			var b: Color = dst.get_pixel(tx, ty)
			dst.set_pixel(tx, ty, b.lerp(Color(c.r, c.g, c.b, 1.0), c.a))
