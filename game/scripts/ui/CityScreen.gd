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
signal plaza_tapped(stats: String)
signal market_trade_requested(res: String, buy: bool)
signal closed()

const LAYOUT_PATH := "res://data/city_layout.json"
const HUD_TOP := 150.0
const HUD_BOTTOM := 180.0

# Art-Pipeline: Pfade nach Konvention. Liegt ein PNG oder SVG dort, wird
# es am Hotspot statt des Platzhalter-Iso-Blocks gerendert; sonst Fallback
# auf Prozedural. SVG hat Vorrang vor PNG, damit selbstgeschriebene Iso-
# Sprites durch spaeter gelieferte gemalte PNGs einfach ueberschrieben
# werden koennen. Datei-Konvention siehe game/assets/city/ART_SPEC.md.
const ART_EXTENSIONS := [".svg", ".png"]
const ART_FACTION_DIR := "res://assets/city/%s/%s"            # %s=Fraktion, %s=building_id (ohne Ext)
const ART_BG := "res://assets/city/%s/bg"                     # %s=Fraktion
# Gemalter Hintergrund mit gebauter Stadtmauer. Wenn vorhanden UND
# "mauer" gebaut ist, ersetzt er bg komplett (statt Overlay-Schicht).
const ART_BG_WALLED := "res://assets/city/%s/bg_walled"       # %s=Fraktion
# Fallback fuer Fraktionen ohne bg_walled: Wall-Ring als Overlay-Layer.
const ART_WALL_OVERLAY := "res://assets/city/%s/wall_overlay" # %s=Fraktion
# Baustelle: zuerst gebaeude-spezifisch (construction-<bid>), dann generisch.
# So kann pro Gebaeudetyp eine "Vorahnung" des spaeteren Baus angedeutet
# werden, ohne dass jeder Slot zwingend eine eigene SVG braucht.
const ART_CONSTRUCTION_BID := "res://assets/city/_shared/construction-%s"
const ART_CONSTRUCTION := "res://assets/city/_shared/construction"
const FACTION_DIRS := ["waldvolk", "menschen", "totenreich", "orks"]

# ctx wird von WorldMapScreen.open()/refresh() befuellt, siehe dort.
var _ctx: Dictionary = {}
var _layout: Dictionary = {}
var _plots: Array = []   # zuletzt berechnete Hotspots fuer Treffer-Tests

# Cache fuer geladene Texturen: pfad -> Texture2D oder null (nicht gefunden,
# wird kein zweites Mal nachgeschlagen). Vermeidet ResourceLoader-Spam pro
# Frame und macht "leerer Ordner" zu einem No-Op.
var _tex_cache: Dictionary = {}

var _title: Label
var _gold: Label
var _trade_panel: Panel
var _trade_labels: Dictionary = {}
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
	# Achtung: KEIN Kind-ColorRect ueber die volle Flaeche als Hintergrund.
	# Children rendern ueber dem _draw() des Parents - ein Vollbild-Kind
	# wuerde alles Gemalte verdecken. Der Backdrop wird in _draw() selbst
	# gemalt, HUD-Streifen oben/unten ebenfalls. So bleiben Stage und HUD
	# in derselben Render-Schicht und stoeren sich nicht.

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
	_refresh_trade_labels()
	queue_redraw()


func refresh(ctx: Dictionary) -> void:
	_ctx = ctx
	_update_hud()
	_refresh_trade_labels()
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
	# Vollflaechiger Backdrop (frueher ein Kind-ColorRect - das hat die
	# Iso-Stage verdeckt, weil Children ueber dem Parent-_draw rendern).
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.07, 0.08, 0.11), true)
	# HUD-Streifen oben/unten, damit Labels lesbar bleiben.
	draw_rect(Rect2(Vector2.ZERO, Vector2(size.x, HUD_TOP)), Color(0.05, 0.06, 0.08), true)
	draw_rect(Rect2(Vector2(0.0, size.y - HUD_BOTTOM), Vector2(size.x, HUD_BOTTOM)), Color(0.05, 0.06, 0.08), true)

	var stage := _stage_rect()
	# Stadt-Hintergrund in drei Stufen:
	#   1. Mauer gebaut + bg_walled vorhanden -> gemaltes Mauer-Bild
	#   2. sonst bg (+ ggf. wall_overlay wenn Mauer gebaut, Fallback fuer
	#      Fraktionen ohne eigenes bg_walled)
	#   3. gar kein Bild -> Boden-Plateau + Iso-Grid
	var city: Dictionary = _ctx.get("city", {})
	var built_arr: Array = city.get("buildings", [])
	var has_wall: bool = built_arr.has("mauer")
	var bg_tex: Texture2D = null
	if has_wall:
		bg_tex = _texture_with_ext(ART_BG_WALLED % _faction_dir())
	var walled_bg_used: bool = bg_tex != null
	if bg_tex == null:
		bg_tex = _texture_with_ext(ART_BG % _faction_dir())
	if bg_tex != null:
		draw_texture_rect(bg_tex, stage, false)
	else:
		draw_rect(stage, Color(0.12, 0.14, 0.13), true)
		_draw_ground_grid(stage)
	if has_wall and not walled_bg_used:
		var wall_tex: Texture2D = _texture_with_ext(ART_WALL_OVERLAY % _faction_dir())
		if wall_tex != null:
			draw_texture_rect(wall_tex, stage, false)

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
	var bid: String = String(p["id"])

	# Schlagschatten als flache Ellipse (hier: gestauchte Raute).
	_draw_diamond(c + Vector2(0, hh * 0.18), hw * 1.05, hh * 1.05, Color(0, 0, 0, 0.25))

	# Versuche zuerst eine Sprite-Textur (SVG bevorzugt, PNG als Fallback).
	# Bei ungebauten Gebaeuden: erst gebaeude-spezifisch, dann generisch.
	var tex: Texture2D = null
	if built:
		tex = _texture_with_ext(ART_FACTION_DIR % [_faction_dir(), bid])
	else:
		tex = _texture_with_ext(ART_CONSTRUCTION_BID % bid)
		if tex == null:
			tex = _texture_with_ext(ART_CONSTRUCTION)
	if tex != null:
		_draw_sprite_at(tex, c, hw, hh, built)
		_plot_label(p, c + Vector2(0, hh + 18.0))
		return

	# Kein Sprite vorhanden -> Platzhalter wie bisher.
	if not built:
		_draw_diamond(c, hw, hh, Color(col.r, col.g, col.b, 0.18))
		_draw_diamond_outline(c, hw, hh, Color(col.r, col.g, col.b, 0.55), 2.0)
		_plot_label(p, c + Vector2(0, hh + 18.0))
		return

	var height: float = hh * 2.0
	_draw_iso_block(c, hw, hh, height, col)
	_plot_label(p, c + Vector2(0, hh + 18.0))


# Zeichnet ein Sprite an einem Hotspot, breitenproportional skaliert.
# Anker ist die Boden-Mitte des Plots (selbe Position wie der Iso-Block),
# damit Texturen ohne Layout-Anpassung 1:1 in die Slots fallen.
func _draw_sprite_at(tex: Texture2D, ground_center: Vector2, hw: float, hh: float, built: bool) -> void:
	var src: Vector2 = tex.get_size()
	if src.x <= 0.0 or src.y <= 0.0:
		return
	# Sprite-Breite skaliert mit Plot-Raute. Werte sind in Vielfachen der
	# Plot-Halbbreite (hw). 2.0/1.5 entspricht einer "Stadt mit Details"-
	# Skalierung: Gebaeude wirken nicht mehr wie 7 dominante Kloetze, sondern
	# lassen Raum fuer Wege, Plaza und Hintergrund-Deko (Huetten, Brunnen
	# etc. in bg.svg).
	var sprite_w: float = hw * (2.0 if built else 1.5)
	var sprite_h: float = sprite_w * (src.y / src.x)
	# Anker: SVGs sind so geschnitten, dass die Bodenraute des Gebaeudes
	# vertikal bei ~56% der Bildhoehe sitzt (ViewBox 0..512, Bodenmitte
	# bei y=288). Sprite so platzieren, dass dieser Anker auf das Plot-
	# Zentrum trifft, dann sitzen die Gebaeude wirklich auf ihrer Raute,
	# statt "ueber" ihr zu schweben.
	const SPRITE_GROUND_FRAC := 0.56
	var rect := Rect2(
		ground_center - Vector2(sprite_w * 0.5, sprite_h * SPRITE_GROUND_FRAC),
		Vector2(sprite_w, sprite_h))
	draw_texture_rect(tex, rect, false)


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
	# Drei Zeilen pro Plot:
	#   1) Gebaeude-Name
	#   2) Zustand: Kosten / Voraussetzung / Vorrat / "fertig"
	#   3) Effekt-Beschreibung (was tut das Gebaeude?) - klein und dezent,
	#      aber immer sichtbar, damit man auch ungebaute Gebaeude einschaetzen
	#      kann. War im alten Button-Panel automatisch im Button-Text drin.
	var line1: String = String(p["name"])
	var line2: String = String(p["sub"])
	var line3: String = String(p["effect"])
	_centered_text(line1, at, 26, Color(0.95, 0.95, 0.98))
	var y_off := 30.0
	if line2 != "":
		_centered_text(line2, at + Vector2(0, y_off), 22, p["sub_col"])
		y_off += 26.0
	if line3 != "":
		_centered_text(line3, at + Vector2(0, y_off), 20, Color(0.78, 0.82, 0.90, 0.85))


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
			"effect": String(def.get("effect", "")),
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
		var cost: Dictionary = def.get("cost", {})
		var req: String = String(def.get("requires", ""))
		if req != "" and not _city_has(req):
			return "braucht " + req.capitalize()
		return Wallet.cost_text(cost) + " bauen"
	# Gebaut: Militaergebaeude zeigen Rekrut-Vorrat, Rest "fertig".
	if uid != "":
		var pools: Dictionary = _city_pools()
		var have: int = int(pools.get(uid, 0))
		var rate: int = UnitType.growth_of(uid)
		return "%s: %d (+%d/Wo)" % [UnitType.short_of(uid), have, rate]
	return "fertig"


func _plot_sub_color(def: Dictionary, is_built: bool, fid: int) -> Color:
	var bid: String = String(def["id"])
	if not is_built:
		var req: String = String(def.get("requires", ""))
		if req != "" and not _city_has(req):
			return Color(0.9, 0.5, 0.5)
		var hero: Object = _ctx.get("hero", null)
		if hero != null and (hero.wallet as Wallet).can_afford(def.get("cost", {})):
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
	# Plaza-Hit zuerst (Vordergrund-Element ueber den Wegen): wenn der Tap
	# in den Brunnen-Plaza-Bereich faellt, Stadt-Statistik in der Status-
	# zeile zeigen, ohne dass danach noch ein Gebaeude-Hit ausgewertet wird.
	if _hit_plaza(pos):
		_show_plaza_stats()
		return
	# Vorne (groesseres y) hat Vorrang -> rueckwaerts durch die Zeichenliste.
	for i in range(_plots.size() - 1, -1, -1):
		var p: Dictionary = _plots[i]
		if _in_diamond(pos, p["center"], p["hw"], p["hh"]):
			_act_on_plot(p)
			return


# Plaza/Brunnen-Treffer: passt zur Lage in den gemalten bg.png/bg_walled.png
# (Brunnen-Plaza bei ~60 % Stage-Hoehe, mittig). Werte hier weil in den
# Bildern fix.
const PLAZA_NORM_X := 0.50
const PLAZA_NORM_Y := 0.60
const PLAZA_NORM_RX := 0.14
const PLAZA_NORM_RY := 0.06


func _hit_plaza(pos: Vector2) -> bool:
	var stage := _stage_rect()
	var cx: float = stage.position.x + PLAZA_NORM_X * stage.size.x
	var cy: float = stage.position.y + PLAZA_NORM_Y * stage.size.y
	var rx: float = PLAZA_NORM_RX * stage.size.x
	var ry: float = PLAZA_NORM_RY * stage.size.y
	if rx <= 0.0 or ry <= 0.0:
		return false
	var dx: float = (pos.x - cx) / rx
	var dy: float = (pos.y - cy) / ry
	return dx * dx + dy * dy <= 1.0


func _show_plaza_stats() -> void:
	var city: Dictionary = _ctx.get("city", {})
	var fid: int = _faction_id()
	var built: Array = city.get("buildings", [])
	var defs: Array = _ctx.get("buildings", [])
	var built_count: int = built.size()
	var total: int = defs.size()
	# Wochenrate aufaddieren: pro Militaergebaeude die fraktionsspezifische
	# WEEKLY_GROWTH-Rate, fuer nicht-militaerische Gebaeude den Effekt-Text.
	var growth: int = 0
	var effects: Array = []
	var weekly: Dictionary = _ctx.get("weekly_growth", {})
	for def in defs:
		var bid: String = String(def["id"])
		if not built.has(bid):
			continue
		var uid: String = UnitType.unit_for_building(fid, bid)
		if uid != "":
			growth += int(weekly.get(bid, 0))
		else:
			var eff: String = String(def.get("effect", ""))
			if eff != "":
				effects.append(eff)
	var fnames: Array = _ctx.get("faction_names", [])
	var fname: String = String(fnames[fid]) if fid >= 0 and fid < fnames.size() else "?"
	var parts: Array = ["Stadt %s: %d/%d gebaut" % [fname, built_count, total]]
	if growth > 0:
		parts.append("+%d Einheiten/Wo" % growth)
	if not effects.is_empty():
		parts.append(", ".join(effects))
	var msg: String = " - ".join(parts)
	plaza_tapped.emit(msg)
	set_status(msg)


func _act_on_plot(p: Dictionary) -> void:
	var bid: String = String(p["id"])
	var fid: int = _faction_id()
	if not bool(p["built"]):
		build_requested.emit(bid)
		return
	var uid: String = UnitType.unit_for_building(fid, bid)
	if uid != "":
		recruit_requested.emit(uid)
	elif bid == "markt":
		_open_trade_panel()
	else:
		# Kein Militaergebaeude -> Effekt aus dem Plot-Dict zeigen, damit
		# der Tap zumindest die Wirkung in der Statuszeile spiegelt.
		var eff: String = String(p["effect"])
		if eff != "":
			set_status("%s: %s" % [String(p["name"]), eff])
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


# Fraktions-Index -> Verzeichnisname unter assets/city/. Liste muss zur
# FACTION_NAMES-Konvention in WorldMapScreen passen.
func _faction_dir() -> String:
	var fid: int = _faction_id()
	if fid >= 0 and fid < FACTION_DIRS.size():
		return String(FACTION_DIRS[fid])
	return "menschen"


# Texture-Loader mit Cache. ResourceLoader gibt bei nicht-existierendem
# Pfad null zurueck, das speichern wir auch -> kein zweiter Versuch pro
# Frame. So bleibt der Render-Loop guenstig, auch wenn die meisten Slots
# noch keine Bilder haben.
func _texture(path: String) -> Texture2D:
	if _tex_cache.has(path):
		return _tex_cache[path] as Texture2D
	var tex: Texture2D = null
	if ResourceLoader.exists(path):
		tex = load(path) as Texture2D
	_tex_cache[path] = tex
	return tex


# Variante ohne Extension: probiert .svg, .png. So koennen
# selbstgeschriebene SVG-Sprites spaeter durch gemalte PNGs ueberschrieben
# werden, ohne Code-Change.
func _texture_with_ext(path_no_ext: String) -> Texture2D:
	for ext in ART_EXTENSIONS:
		var t: Texture2D = _texture(path_no_ext + String(ext))
		if t != null:
			return t
	return null


# --- Markt-Tausch-Panel (M3 Teil 2) ---
# Reine Anzeige: Kurse und Bestaende kommen aus _ctx, jede Aktion geht
# als market_trade_requested-Signal an den WorldMapScreen (Oekonomie).

func _open_trade_panel() -> void:
	if _trade_panel == null:
		_build_trade_panel()
	_refresh_trade_labels()
	_trade_panel.visible = true


func _build_trade_panel() -> void:
	var panel := Panel.new()
	panel.visible = false
	panel.anchor_left = 0.5
	panel.anchor_top = 0.5
	panel.anchor_right = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -440
	panel.offset_top = -560
	panel.offset_right = 440
	panel.offset_bottom = 560
	add_child(panel)
	_trade_panel = panel

	var bg := ColorRect.new()
	bg.color = Color(0.08, 0.09, 0.12, 1.0)
	bg.anchor_right = 1.0
	bg.anchor_bottom = 1.0
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(bg)

	var vb := VBoxContainer.new()
	vb.anchor_right = 1.0
	vb.anchor_bottom = 1.0
	vb.offset_left = 32
	vb.offset_top = 32
	vb.offset_right = -32
	vb.offset_bottom = -32
	vb.add_theme_constant_override("separation", 18)
	panel.add_child(vb)

	var title := Label.new()
	title.text = "Markt - Tauschhandel"
	title.add_theme_font_size_override("font_size", 40)
	vb.add_child(title)

	var buy_rates: Dictionary = _ctx.get("market_buy", {})
	var sell_rates: Dictionary = _ctx.get("market_sell", {})
	for rid in Wallet.RESOURCE_IDS:
		if rid == "gold" or not buy_rates.has(rid):
			continue
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 14)
		vb.add_child(row)

		var lbl := Label.new()
		lbl.custom_minimum_size = Vector2(280, 0)
		lbl.add_theme_font_size_override("font_size", 28)
		row.add_child(lbl)
		_trade_labels[rid] = lbl

		var buy_btn := Button.new()
		buy_btn.text = "Kauf %dG" % int(buy_rates.get(rid, 0))
		buy_btn.custom_minimum_size = Vector2(220, 90)
		buy_btn.add_theme_font_size_override("font_size", 26)
		buy_btn.pressed.connect(func() -> void: market_trade_requested.emit(rid, true))
		row.add_child(buy_btn)

		var sell_btn := Button.new()
		sell_btn.text = "Verkauf +%dG" % int(sell_rates.get(rid, 0))
		sell_btn.custom_minimum_size = Vector2(240, 90)
		sell_btn.add_theme_font_size_override("font_size", 26)
		sell_btn.pressed.connect(func() -> void: market_trade_requested.emit(rid, false))
		row.add_child(sell_btn)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(spacer)

	var close_btn := Button.new()
	close_btn.text = "Schliessen"
	close_btn.custom_minimum_size = Vector2(0, 96)
	close_btn.add_theme_font_size_override("font_size", 30)
	close_btn.pressed.connect(func() -> void: _trade_panel.visible = false)
	vb.add_child(close_btn)


func _refresh_trade_labels() -> void:
	if _trade_panel == null or not _trade_panel.visible and _trade_labels.is_empty():
		return
	var hero: Object = _ctx.get("hero", null)
	if hero == null:
		return
	for rid in _trade_labels.keys():
		var amt: int = (hero.wallet as Wallet).get_amount(String(rid))
		(_trade_labels[rid] as Label).text = "%s: %d" % [Wallet.display_name(String(rid)), amt]
