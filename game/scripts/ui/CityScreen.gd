class_name CityScreen
extends Control

# Isometrischer Stadt-Screen (Schritt 1 zur "echten" Heroes-Grafik).
#
# Aktuell rein prozedurale PLATZHALTER-Grafik: jede Gebaeude-Position aus
# data/city_layout.json wird als isometrischer Block gezeichnet (gebaut)
# bzw. als Baustellen-Raute (nicht gebaut). Sobald KI-generierte Sprites
# vorliegen, werden die Bloecke 1:1 durch Texturen an denselben Hotspots
# ersetzt - Layout, Tap-Logik und Signal-Anbindung bleiben unveraendert.
#
# Diese View enthaelt KEINE Spiel-Logik. Bauen/Rekrutieren wird per Signal
# an den WorldMapScreen zurueckgemeldet, der die bestehenden, autoritativen
# Funktionen _buy_building/_recruit_unit ausfuehrt und danach refresh()
# mit frischen Werten aufruft. So bleibt die Oekonomie an einer Stelle.

signal build_requested(building_id: String)
signal recruit_requested(unit_id: String)
signal closed()

const LAYOUT_PATH := "res://data/city_layout.json"
const HUD_TOP := 150.0
const HUD_BOTTOM := 180.0

# ctx wird von WorldMapScreen.open()/refresh() befuellt, siehe dort.
var _ctx: Dictionary = {}
var _layout: Dictionary = {}
var _plots: Array = []   # zuletzt berechnete Hotspots fuer Treffer-Tests

var _title: Label
var _gold: Label
var _cal: Label
var _status: Label
var _font: Font


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	anchor_right = 1.0
	anchor_bottom = 1.0
	_font = ThemeDB.fallback_font
	_load_layout()
	_build_hud()
	visible = false


func _load_layout() -> void:
	if not FileAccess.file_exists(LAYOUT_PATH):
		push_warning("CityScreen: %s fehlt - leeres Layout" % LAYOUT_PATH)
		_layout = {}
		return
	var f := FileAccess.open(LAYOUT_PATH, FileAccess.READ)
	var raw: Variant = JSON.parse_string(f.get_as_text())
	if typeof(raw) == TYPE_DICTIONARY and (raw as Dictionary).has("buildings"):
		_layout = (raw as Dictionary)["buildings"]
	else:
		push_warning("CityScreen: city_layout.json ohne 'buildings'")
		_layout = {}


func _build_hud() -> void:
	var bg := ColorRect.new()
	bg.color = Color(0.07, 0.08, 0.11, 1.0)
	bg.anchor_right = 1.0
	bg.anchor_bottom = 1.0
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bg)
	move_child(bg, 0)

	_title = Label.new()
	_title.add_theme_font_size_override("font_size", 44)
	_title.position = Vector2(40, 36)
	_title.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_title)

	_gold = Label.new()
	_gold.add_theme_font_size_override("font_size", 32)
	_gold.add_theme_color_override("font_color", Color(1.0, 0.85, 0.25))
	_gold.position = Vector2(40, 92)
	_gold.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_gold)

	_cal = Label.new()
	_cal.add_theme_font_size_override("font_size", 30)
	_cal.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_cal.anchor_left = 1.0
	_cal.anchor_right = 1.0
	_cal.offset_left = -460
	_cal.offset_top = 96
	_cal.offset_right = -260
	_cal.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_cal)

	var close_btn := Button.new()
	close_btn.text = "Schliessen"
	close_btn.add_theme_font_size_override("font_size", 30)
	close_btn.custom_minimum_size = Vector2(220, 90)
	close_btn.anchor_left = 1.0
	close_btn.anchor_right = 1.0
	close_btn.offset_left = -240
	close_btn.offset_top = 30
	close_btn.offset_right = -20
	close_btn.pressed.connect(func() -> void: closed.emit())
	add_child(close_btn)

	_status = Label.new()
	_status.add_theme_font_size_override("font_size", 30)
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_status.anchor_top = 1.0
	_status.anchor_right = 1.0
	_status.anchor_bottom = 1.0
	_status.offset_left = 20
	_status.offset_top = -150
	_status.offset_right = -20
	_status.offset_bottom = -90
	_status.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_status)


# --- Oeffentliche API (vom WorldMapScreen genutzt) ---

func open(ctx: Dictionary) -> void:
	if _layout.is_empty():
		_load_layout()
	_ctx = ctx
	visible = true
	_update_hud()
	queue_redraw()


func refresh(ctx: Dictionary) -> void:
	_ctx = ctx
	_update_hud()
	queue_redraw()


func set_status(s: String) -> void:
	if _status != null:
		_status.text = s


func _update_hud() -> void:
	if _title == null:
		return
	var fnames: Array = _ctx.get("faction_names", [])
	var fid: int = _faction_id()
	var fname: String = String(fnames[fid]) if fid >= 0 and fid < fnames.size() else "?"
	_title.text = "Stadt " + fname
	var hero: Object = _ctx.get("hero", null)
	_gold.text = "Gold: " + str(int(hero.gold)) if hero != null else "Gold: 0"
	_cal.text = String(_ctx.get("calendar", ""))


# --- Rendering ---

func _draw() -> void:
	var stage := _stage_rect()
	# Boden-Plateau als Andeutung (spaeter: KI-Hintergrund-Textur).
	draw_rect(Rect2(Vector2(0, HUD_TOP), Vector2(size.x, stage.size.y)), Color(0.12, 0.14, 0.13), true)
	_draw_ground_grid(stage)

	_plots = _compute_plots(stage)
	for p in _plots:
		_draw_plot(p)


func _draw_ground_grid(stage: Rect2) -> void:
	# Dezente isometrische Bodenlinien, damit die Perspektive lesbar ist.
	var col := Color(1, 1, 1, 0.05)
	var step := 90.0
	var cx := stage.position.x + stage.size.x * 0.5
	var top := stage.position.y
	var bot := stage.position.y + stage.size.y
	var x := -stage.size.x
	while x < stage.size.x * 2.0:
		draw_line(Vector2(cx + x, top), Vector2(cx + x + stage.size.y, bot), col, 1.0)
		draw_line(Vector2(cx + x, top), Vector2(cx + x - stage.size.y, bot), col, 1.0)
		x += step


func _draw_plot(p: Dictionary) -> void:
	var c: Vector2 = p["center"]
	var hw: float = p["hw"]
	var hh: float = p["hh"]
	var built: bool = p["built"]
	var col: Color = p["color"]

	# Schlagschatten als flache Ellipse (hier: gestauchte Raute).
	_draw_diamond(c + Vector2(0, hh * 0.18), hw * 1.05, hh * 1.05, Color(0, 0, 0, 0.25))

	if not built:
		# Baustelle: nur Boden-Raute mit Umriss.
		_draw_diamond(c, hw, hh, Color(col.r, col.g, col.b, 0.18))
		_draw_diamond_outline(c, hw, hh, Color(col.r, col.g, col.b, 0.55), 2.0)
		_plot_label(p, c + Vector2(0, hh + 18.0))
		return

	# Gebaut: extrudierter Iso-Block (Platzhalter fuer das spaetere Sprite).
	var height: float = hh * 2.0
	_draw_iso_block(c, hw, hh, height, col)
	_plot_label(p, c + Vector2(0, hh + 18.0))


func _draw_iso_block(c: Vector2, hw: float, hh: float, h: float, base: Color) -> void:
	# Boden-Raute (Grundriss).
	var n := c + Vector2(0, -hh)
	var e := c + Vector2(hw, 0)
	var s := c + Vector2(0, hh)
	var w := c + Vector2(-hw, 0)
	# Dach-Raute (um h nach oben versetzt).
	var up := Vector2(0, -h)
	var n2 := n + up
	var e2 := e + up
	var s2 := s + up
	var w2 := w + up
	# Licht von oben-links: linke Wand heller, rechte dunkler.
	var left_col := base.lightened(0.05)
	var right_col := base.darkened(0.30)
	var roof_col := base.lightened(0.25)
	draw_colored_polygon(PackedVector2Array([w, s, s2, w2]), left_col)
	draw_colored_polygon(PackedVector2Array([s, e, e2, s2]), right_col)
	draw_colored_polygon(PackedVector2Array([n2, e2, s2, w2]), roof_col)
	# Kanten fuer Lesbarkeit.
	var edge := Color(0, 0, 0, 0.35)
	draw_polyline(PackedVector2Array([w, s, e, e2, s2, w2, w]), edge, 1.5)
	draw_polyline(PackedVector2Array([n2, e2, s2, w2, n2]), edge, 1.5)
	draw_line(s, s2, edge, 1.5)


func _draw_diamond(c: Vector2, hw: float, hh: float, col: Color) -> void:
	draw_colored_polygon(PackedVector2Array([
		c + Vector2(0, -hh), c + Vector2(hw, 0),
		c + Vector2(0, hh), c + Vector2(-hw, 0),
	]), col)


func _draw_diamond_outline(c: Vector2, hw: float, hh: float, col: Color, wdt: float) -> void:
	draw_polyline(PackedVector2Array([
		c + Vector2(0, -hh), c + Vector2(hw, 0),
		c + Vector2(0, hh), c + Vector2(-hw, 0), c + Vector2(0, -hh),
	]), col, wdt)


func _plot_label(p: Dictionary, at: Vector2) -> void:
	var line1: String = String(p["name"])
	var line2: String = String(p["sub"])
	_centered_text(line1, at, 26, Color(0.95, 0.95, 0.98))
	if line2 != "":
		_centered_text(line2, at + Vector2(0, 30), 22, p["sub_col"])


func _centered_text(txt: String, at: Vector2, fsize: int, col: Color) -> void:
	var w := _font.get_string_size(txt, HORIZONTAL_ALIGNMENT_LEFT, -1, fsize).x
	var pos := Vector2(at.x - w * 0.5, at.y)
	draw_string(_font, pos + Vector2(1.5, 1.5), txt, HORIZONTAL_ALIGNMENT_LEFT, -1, fsize, Color(0, 0, 0, 0.8))
	draw_string(_font, pos, txt, HORIZONTAL_ALIGNMENT_LEFT, -1, fsize, col)


# --- Hotspot-Berechnung (geteilt von _draw und _gui_input) ---

func _compute_plots(stage: Rect2) -> Array:
	var out: Array = []
	if _layout.is_empty():
		_load_layout()
	var city: Dictionary = _ctx.get("city", {})
	if city.is_empty():
		return out
	var fid: int = _faction_id()
	var built: Array = city.get("buildings", [])
	var defs: Array = _ctx.get("buildings", [])
	var fcolors: Array = _ctx.get("faction_colors", [])
	var base_col: Color = fcolors[fid] if fid >= 0 and fid < fcolors.size() else Color(0.6, 0.6, 0.6)
	var hw: float = min(stage.size.x * 0.15, 150.0)
	var hh: float = hw * 0.5

	for def in defs:
		var bid: String = String(def["id"])
		if not _layout.has(bid):
			continue
		var lp: Dictionary = _layout[bid]
		var center := stage.position + Vector2(
			float(lp.get("x", 0.5)) * stage.size.x,
			float(lp.get("y", 0.5)) * stage.size.y)
		var is_built: bool = built.has(bid)
		out.append({
			"id": bid,
			"name": String(def.get("name", bid)),
			"center": center,
			"hw": hw,
			"hh": hh,
			"built": is_built,
			"color": base_col,
			"z": int(lp.get("z", 0)),
			"sub": _plot_subline(def, is_built, fid),
			"sub_col": _plot_sub_color(def, is_built, fid),
		})

	# Hinten-nach-vorne: kleineres y zuerst, z als Tiebreaker.
	out.sort_custom(func(a, b):
		if int(a["z"]) != int(b["z"]):
			return int(a["z"]) < int(b["z"])
		return float(a["center"].y) < float(b["center"].y))
	return out


func _plot_subline(def: Dictionary, is_built: bool, fid: int) -> String:
	var bid: String = String(def["id"])
	var uid: String = UnitType.unit_for_building(fid, bid)
	if not is_built:
		var cost: int = int(def.get("cost", 0))
		var req: String = String(def.get("requires", ""))
		if req != "" and not _city_has(req):
			return "braucht " + req.capitalize()
		return str(cost) + " G bauen"
	# Gebaut: Militaergebaeude zeigen Rekrut-Vorrat, Rest "fertig".
	if uid != "":
		var pools: Dictionary = _city_pools()
		var have: int = int(pools.get(uid, 0))
		var wg: Dictionary = _ctx.get("weekly_growth", {})
		var rate: int = int(wg.get(bid, 0))
		return "%s: %d (+%d/Wo)" % [UnitType.short_of(uid), have, rate]
	return "fertig"


func _plot_sub_color(def: Dictionary, is_built: bool, fid: int) -> Color:
	var bid: String = String(def["id"])
	if not is_built:
		var req: String = String(def.get("requires", ""))
		if req != "" and not _city_has(req):
			return Color(0.9, 0.5, 0.5)
		var hero: Object = _ctx.get("hero", null)
		if hero != null and int(hero.gold) >= int(def.get("cost", 0)):
			return Color(0.6, 0.95, 0.6)
		return Color(0.95, 0.85, 0.5)
	if UnitType.unit_for_building(fid, bid) != "":
		return Color(0.7, 0.9, 1.0)
	return Color(0.7, 0.7, 0.75)


# --- Eingabe ---

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			_handle_tap(mb.position)
	elif event is InputEventScreenTouch:
		var st := event as InputEventScreenTouch
		if st.pressed:
			_handle_tap(st.position)


func _handle_tap(pos: Vector2) -> void:
	# Vorne (groesseres y) hat Vorrang -> rueckwaerts durch die Zeichenliste.
	for i in range(_plots.size() - 1, -1, -1):
		var p: Dictionary = _plots[i]
		if _in_diamond(pos, p["center"], p["hw"], p["hh"]):
			_act_on_plot(p)
			return


func _act_on_plot(p: Dictionary) -> void:
	var bid: String = String(p["id"])
	var fid: int = _faction_id()
	if not bool(p["built"]):
		build_requested.emit(bid)
		return
	var uid: String = UnitType.unit_for_building(fid, bid)
	if uid != "":
		recruit_requested.emit(uid)
	else:
		set_status("%s steht bereits." % String(p["name"]))


func _in_diamond(pt: Vector2, c: Vector2, hw: float, hh: float) -> bool:
	if hw <= 0.0 or hh <= 0.0:
		return false
	var d := pt - c
	return absf(d.x) / hw + absf(d.y) / hh <= 1.0


# --- kleine Helfer ---

func _stage_rect() -> Rect2:
	var h: float = max(0.0, size.y - HUD_TOP - HUD_BOTTOM)
	return Rect2(Vector2(0.0, HUD_TOP), Vector2(size.x, h))


func _faction_id() -> int:
	var city: Dictionary = _ctx.get("city", {})
	return int(city.get("faction", 1))


func _city_has(bid: String) -> bool:
	var city: Dictionary = _ctx.get("city", {})
	return (city.get("buildings", []) as Array).has(bid)


func _city_pools() -> Dictionary:
	var city: Dictionary = _ctx.get("city", {})
	return city.get("pools", {}) as Dictionary
