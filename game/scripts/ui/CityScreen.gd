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
# Einheiten zwischen Held und Stadt-Garnison verschieben (M9b).
signal garrison_move_requested(unit_id: String, to_city: bool, all: bool)
# Zweiten (dritten) Helden anwerben (M13b). Der Screen zeigt nur den Knopf -
# Kosten, Obergrenze und Startarmee entscheidet der WorldMapScreen.
signal hire_hero_requested()
signal closed()

const LAYOUT_PATH := "res://data/city_layout.json"
const HUD_TOP := 250.0
# Kantenlaenge der Kreatur-Bilder in den Panels (It. 29). Die SVGs haben
# ViewBox 128 - darunter wird die Silhouette matschig, darueber sprengt
# die Zeile das Panel.
const RECRUIT_ICON_PX := 112
const GARRISON_ICON_PX := 72
const HUD_BOTTOM := 180.0

# Art-Pipeline: Pfade nach Konvention. Liegt ein PNG oder SVG dort, wird
# es am Hotspot statt des Platzhalter-Iso-Blocks gerendert; sonst Fallback
# auf Prozedural. SVG hat Vorrang vor PNG, damit selbstgeschriebene Iso-
# Sprites durch spaeter gelieferte gemalte PNGs einfach ueberschrieben
# werden koennen. Datei-Konvention siehe game/assets/city/ART_SPEC.md.
const ART_EXTENSIONS := [".svg", ".png"]

# Geraeusche (M11) ueber die statische Fassade, siehe SfxBus.gd.
const Sound := preload("res://scripts/core/SfxBus.gd")
# Kreatur-Sprites und Kreatur-Werte fuer Rekrutier- und Garnisons-Panel
# (It. 29). Dieselben 28 SVGs, die im Kampf auf dem Gitter stehen.
const UnitArt := preload("res://scripts/core/UnitArt.gd")
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
# Layout fuer Fraktionen OHNE gemalten Hintergrund: gleiche Plots, aber
# ueber die ganze Buehne verteilt. Das Haupt-Layout sitzt im Innenhof der
# gemalten Menschen-Ringmauer und laesst dort keinen Platz fuer zwei
# Textzeilen je Plot.
var _layout_plain: Dictionary = {}
var _plaza: Dictionary = {}
var _plots: Array = []   # zuletzt berechnete Hotspots fuer Treffer-Tests

# Cache fuer geladene Texturen: pfad -> Texture2D oder null (nicht gefunden,
# wird kein zweites Mal nachgeschlagen). Vermeidet ResourceLoader-Spam pro
# Frame und macht "leerer Ordner" zu einem No-Op.
var _tex_cache: Dictionary = {}

var _title: Label
var _gold: Label
var _trade_panel: Panel
var _trade_labels: Dictionary = {}
# Rekrut-Panel (M4 Teil 2): ein Panel, Zeilen werden je Gebaeude neu
# aufgebaut (1-2 Einheiten). Labels/Buttons pro uid fuer Refresh.
var _recruit_panel: Panel
var _recruit_title: Label
var _recruit_rows_box: VBoxContainer
var _recruit_labels: Dictionary = {}
var _recruit_buttons: Dictionary = {}
# Garnison-Panel (M9b): wird bei jedem Oeffnen neu aufgebaut, weil sich
# beide Seiten (Held/Stadt) staendig aendern.
var _gar_panel: Panel
var _gar_rows: VBoxContainer
var _gar_title: Label
var _hire_btn: Button
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
		_layout_plain = (raw as Dictionary).get("buildings_plain", _layout)
		_plaza = (raw as Dictionary).get("plaza", {}) as Dictionary
	else:
		push_warning("CityScreen: city_layout.json ohne 'buildings'")
		_layout = {}
		_layout_plain = {}
		_plaza = {}


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

	# Umschalter 2D/3D (It. 56). LINKS unter dem Goldstand, im HUD-Streifen
	# oben (der reicht bis HUD_TOP = 250) - nicht auf der Buehne: ein Knopf
	# ueber dem Hof frisst den Tipp auf einen Bauplatz.
	_view3d_btn = Button.new()
	_view3d_btn.text = "3D"
	_view3d_btn.add_theme_font_size_override("font_size", 26)
	_view3d_btn.position = Vector2(40, 146)
	_view3d_btn.custom_minimum_size = Vector2(130, 80)
	_view3d_btn.size = Vector2(130, 80)
	_view3d_btn.pressed.connect(_toggle_view3d)
	add_child(_view3d_btn)

	# Garnison-Button neben "Schliessen": Einheiten der Stadt ansehen und
	# mit dem Helden tauschen (M9b).
	var gar_btn := Button.new()
	gar_btn.text = "Garnison"
	gar_btn.add_theme_font_size_override("font_size", 28)
	gar_btn.custom_minimum_size = Vector2(200, 90)
	gar_btn.anchor_left = 1.0
	gar_btn.anchor_right = 1.0
	gar_btn.offset_left = -240
	gar_btn.offset_top = 140
	gar_btn.offset_right = -20
	gar_btn.pressed.connect(_open_garrison_panel)
	add_child(gar_btn)

	# Held anwerben (M13b). KEIN eigenes Gebaeude: ein zehnter Bauplatz
	# passt nur mit Verrenkungen in den Mauerring - `check_layout()` in
	# tools/gen_city_bg.py meldet die Schmiede als zu nah. Das waere eine
	# Art-Iteration (4 Fraktions-Sprites + Baustelle + Layout-Slot) und
	# haette mit dem Gameplay nichts zu tun. Dokumentierte Vereinfachung,
	# wie "keine Magiergilde" in M8.
	_hire_btn = Button.new()
	_hire_btn.text = "Held anwerben"
	_hire_btn.add_theme_font_size_override("font_size", 26)
	_hire_btn.custom_minimum_size = Vector2(280, 90)
	_hire_btn.anchor_left = 1.0
	_hire_btn.anchor_right = 1.0
	_hire_btn.offset_left = -320
	_hire_btn.offset_top = 250
	_hire_btn.offset_right = -20
	_hire_btn.pressed.connect(func() -> void: hire_hero_requested.emit())
	add_child(_hire_btn)

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
	_refresh_recruit_labels()
	if _gar_panel != null and _gar_panel.visible:
		_fill_garrison_rows()
	queue_redraw()


func refresh(ctx: Dictionary) -> void:
	_ctx = ctx
	_update_hud()
	_refresh_trade_labels()
	_refresh_recruit_labels()
	if _gar_panel != null and _gar_panel.visible:
		_fill_garrison_rows()
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
	var purse: Wallet = _wallet()
	_gold.text = "Gold: " + str(purse.get_amount("gold")) if purse != null else "Gold: 0"
	# Anwerben (M13b): Text und Zustand kommen aus dem Kontext - der Screen
	# rechnet nichts selbst.
	if _hire_btn != null:
		var cost: Dictionary = _ctx.get("hire_cost", {}) as Dictionary
		var slots_left: int = int(_ctx.get("hire_slots_left", 0))
		var here: bool = bool(_ctx.get("hero_here", false))
		_hire_btn.text = "Held anwerben\n%s" % Wallet.cost_text(cost)
		var afford: bool = purse != null and purse.can_afford(cost)
		_hire_btn.disabled = slots_left <= 0 or not afford
		if slots_left <= 0:
			_hire_btn.text = "Held anwerben\n(Maximum erreicht)"
		_hire_btn.visible = bool(_ctx.get("own_city", true))
	# Kalender plus Wochenereignis (M12). Ruhige Wochen bleiben stumm,
	# sonst stuende dort in drei von vier Wochen "Ruhige Woche".
	var cal_text: String = String(_ctx.get("calendar", ""))
	if not bool(_ctx.get("week_quiet", true)):
		cal_text += "\n" + String(_ctx.get("week_event", ""))
	_cal.text = cal_text


# --- Rendering ---

# --- Raeumliche Ansicht (It. 56) ------------------------------------------
#
# ZWEITE ANSICHT, KEIN ERSATZ - wie Weltkarte (It. 53b) und Kampffeld
# (It. 55). Sie sitzt als SubViewport auf der Buehnenflaeche und liest
# dasselbe Modell ueber _city3d_ctx(); Bauregeln, Kosten und Anwerben sind
# nicht beruehrt.

const City3D := preload("res://scripts/ui/CityView3D.gd")

var _view3d_btn: Button
var _city3d = null
var _city3d_vp: SubViewport = null
var _city3d_on: bool = false


func _toggle_view3d() -> void:
	_city3d_on = not _city3d_on
	if _city3d_on and _city3d == null:
		_build_city3d()
	if _city3d_vp != null:
		(_city3d_vp.get_parent() as Control).visible = _city3d_on
	if _view3d_btn != null:
		_view3d_btn.text = "2D" if _city3d_on else "3D"
	queue_redraw()


func _build_city3d() -> void:
	var cont := SubViewportContainer.new()
	cont.stretch = true
	# NUR die Buehne, nicht der ganze Schirm: oben und unten liegen die
	# HUD-Streifen, und ein Viewport darueber wuerde sie verdecken.
	var st: Rect2 = _stage_rect()
	cont.position = st.position
	cont.size = st.size
	cont.mouse_filter = Control.MOUSE_FILTER_IGNORE
	# HINTER die eigene Zeichnung: ein Control zeichnet erst sich selbst,
	# dann seine Kinder - ohne das laegen die Beschriftungen unter dem Bild
	# (der Befund aus It. 55).
	cont.show_behind_parent = true
	add_child(cont)
	_city3d_vp = SubViewport.new()
	# Eigene 3D-Welt - siehe WorldMapScreen._build_map3d. Ohne das lag der
	# Stadthof mitten im Kartengelaende.
	_city3d_vp.own_world_3d = true
	_city3d_vp.transparent_bg = false
	_city3d_vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	cont.add_child(_city3d_vp)
	_city3d = City3D.new()
	_city3d_vp.add_child(_city3d)


func _city3d_apply() -> void:
	if not _city3d_on or _city3d == null:
		return
	var st: Rect2 = _stage_rect()
	var cont := _city3d_vp.get_parent() as Control
	# Die Buehne folgt der Bildschirmgroesse - der Viewport muss mit.
	cont.position = st.position
	cont.size = st.size
	_city3d.refresh(_city3d_ctx())
	_city3d.frame_yard()


# Derselbe Zustand, den _compute_plots zeichnet, aus DENSELBEN Feldern.
func _city3d_ctx() -> Dictionary:
	var layout: Dictionary = _active_layout()
	var city: Dictionary = _ctx.get("city", {})
	var built: Array = city.get("buildings", [])
	var out: Array = []
	for def in (_ctx.get("buildings", []) as Array):
		var bid: String = String((def as Dictionary)["id"])
		if not layout.has(bid):
			continue
		var lp: Dictionary = layout[bid]
		out.append({"id": bid, "x": float(lp.get("x", 0.5)),
			"y": float(lp.get("y", 0.5)), "s": float(lp.get("s", 1.0)),
			"built": built.has(bid)})
	return {"faction": _faction_dir(), "buildings": out,
		"plaza": _plaza_def()}


func _draw() -> void:
	# Vollflaechiger Backdrop (frueher ein Kind-ColorRect - das hat die
	# Iso-Stage verdeckt, weil Children ueber dem Parent-_draw rendern).
	#
	# IN 3D BLEIBT DIE BUEHNE FREI. Der SubViewport liegt HINTER dieser
	# Zeichnung (sonst laegen die Beschriftungen unter dem Bild, It. 55) -
	# also deckt ein vollflaechiger Backdrop ihn zu. Beim ersten Versuch
	# war die Stadt deshalb einfach schwarz, mit sauber gesetzten
	# Beschriftungen darauf: alles gerechnet, nichts zu sehen.
	if not _city3d_on:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.07, 0.08, 0.11), true)
	# HUD-Streifen oben/unten, damit Labels lesbar bleiben.
	draw_rect(Rect2(Vector2.ZERO, Vector2(size.x, HUD_TOP)), Color(0.05, 0.06, 0.08), true)
	draw_rect(Rect2(Vector2(0.0, size.y - HUD_BOTTOM), Vector2(size.x, HUD_BOTTOM)), Color(0.05, 0.06, 0.08), true)

	var stage := _stage_rect()
	if _city3d_on:
		# In 3D zeichnet die Ansicht die Stadt. Was bleibt, sind die
		# BESCHRIFTUNGEN (Name und Zustand je Bauplatz): Schrift im Raum
		# waere entweder schraeg gestellt oder ein Schild, das seinen
		# Platz verlaesst.
		_city3d_apply()
		_plots = _compute_plots(stage)
		for p in _plots:
			var w3: Vector3 = _city3d.plot_pos(float(p["lx"]), float(p["ly"]))
			var sp: Vector2 = stage.position + _city3d.project_point(w3)
			_plot_label(p, sp + Vector2(0.0, 22.0))
		return
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
		_draw_placeholder_stage(stage)
	if has_wall and not walled_bg_used:
		var wall_tex: Texture2D = _texture_with_ext(ART_WALL_OVERLAY % _faction_dir())
		if wall_tex != null:
			draw_texture_rect(wall_tex, stage, false)

	_plots = _compute_plots(stage)
	for p in _plots:
		_draw_plot(p)


# PLATZHALTER-Buehne fuer Fraktionen ohne gemalten Hintergrund.
# Bewusst schlicht und in Code statt als Asset: sobald gemalte
# Hintergruende (bg.png je Fraktion, siehe assets/city/ART_SPEC.md)
# vorliegen, faellt dieser Zweig weg. Vorher war hier eine einzelne
# Volltonflaeche - der Grund fuer die "leere schwarze Stadt".
func _draw_placeholder_stage(stage: Rect2) -> void:
	var fcolors: Array = _ctx.get("faction_colors", [])
	var fid: int = _faction_id()
	var accent: Color = fcolors[fid] if fid >= 0 and fid < fcolors.size() else Color(0.6, 0.6, 0.6)
	# Vertikaler Verlauf Himmel -> Boden, leicht in Fraktionsfarbe getoent.
	var sky := Color(0.10, 0.12, 0.17).lerp(accent, 0.10)
	var ground := Color(0.15, 0.16, 0.13).lerp(accent, 0.05)
	var bands: int = 24
	for i in range(bands):
		var t: float = float(i) / float(bands - 1)
		var band := Rect2(
			stage.position + Vector2(0.0, stage.size.y * float(i) / float(bands)),
			Vector2(stage.size.x, stage.size.y / float(bands) + 1.0))
		draw_rect(band, sky.lerp(ground, t), true)
	# Horizont-Linie auf ~38 % Hoehe, damit die Buehne Tiefe bekommt.
	var hy: float = stage.position.y + stage.size.y * 0.38
	draw_line(Vector2(stage.position.x, hy),
		Vector2(stage.position.x + stage.size.x, hy),
		Color(accent.r, accent.g, accent.b, 0.18), 2.0)
	_draw_ground_grid(stage)


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

	# Letzte Rettung: fehlt das Sprite fuer ein GEBAUTES Gebaeude, stand hier
	# ein Volltonquader in Fraktionsfarbe - auf dem Geraet ein violetter
	# Wuerfel mitten in der Stadt. Seit Iteration 18 sind alle 36 Sprites da
	# und tools/test_city_screen.gd haelt das fest; der Quader bleibt nur als
	# Notausgang und ist bewusst entsaettigt, damit er nach Platzhalter
	# aussieht und nicht nach Absicht.
	var height: float = hh * 1.5
	var placeholder: Color = col.lerp(Color(0.42, 0.42, 0.44), 0.72)
	_draw_iso_block(c, hw, hh, height, placeholder)
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


# Hoehe des Beschriftungs-Blocks je Plot. Zwei Zeilen - die dritte
# (Effekt-Text) stand frueher hier und lief regelmaessig in den Namen des
# naechsten Plots; sie erscheint jetzt beim Antippen in der Statuszeile
# (siehe _act_on_plot). Die Konstante nutzt auch der Kollisions-Test.
const LABEL_LINE1_SIZE := 26
const LABEL_LINE2_SIZE := 22
const LABEL_BLOCK_H := 56.0


func _plot_label(p: Dictionary, at: Vector2) -> void:
	# Zwei Zeilen pro Plot:
	#   1) Gebaeude-Name
	#   2) Zustand: Kosten / Voraussetzung / Vorrat / "fertig"
	# Der Effekt-Text kommt beim Tap in die Statuszeile, damit die Bauplaetze
	# sich nicht gegenseitig ueberschreiben.
	var max_w: float = float(p["hw"]) * 1.9
	_centered_text(String(p["name"]), at, LABEL_LINE1_SIZE, Color(0.95, 0.95, 0.98), max_w)
	var line2: String = String(p["sub"])
	if line2 != "":
		_centered_text(line2, at + Vector2(0, 30.0), LABEL_LINE2_SIZE, p["sub_col"], max_w)


# Zeichnet zentrierten Text mit Schlagschatten. max_w > 0 kuerzt zu lange
# Zeilen mit "..." statt sie in den Nachbar-Plot laufen zu lassen.
func _centered_text(txt: String, at: Vector2, fsize: int, col: Color,
		max_w: float = 0.0) -> void:
	var shown: String = txt
	var w := _font.get_string_size(shown, HORIZONTAL_ALIGNMENT_LEFT, -1, fsize).x
	if max_w > 0.0 and w > max_w:
		while shown.length() > 1 and w > max_w:
			shown = shown.substr(0, shown.length() - 1)
			w = _font.get_string_size(shown + "...", HORIZONTAL_ALIGNMENT_LEFT, -1, fsize).x
		shown += "..."
		w = _font.get_string_size(shown, HORIZONTAL_ALIGNMENT_LEFT, -1, fsize).x
	var pos := Vector2(at.x - w * 0.5, at.y)
	draw_string(_font, pos + Vector2(1.5, 1.5), shown, HORIZONTAL_ALIGNMENT_LEFT, -1, fsize, Color(0, 0, 0, 0.8))
	draw_string(_font, pos, shown, HORIZONTAL_ALIGNMENT_LEFT, -1, fsize, col)


# --- Hotspot-Berechnung (geteilt von _draw und _gui_input) ---

# Hat diese Fraktion ueberhaupt einen gemalten Hintergrund? Danach
# richtet sich sowohl der Buehnen-Hintergrund als auch die Plot-Verteilung.
func _has_painted_bg() -> bool:
	return _texture_with_ext(ART_BG % _faction_dir()) != null \
		or _texture_with_ext(ART_BG_WALLED % _faction_dir()) != null


# Aktives Layout: der gemalte Innenhof nur dort, wo es auch ein Bild gibt.
func _active_layout() -> Dictionary:
	if _has_painted_bg():
		return _layout
	return _layout_plain if not _layout_plain.is_empty() else _layout


func _compute_plots(stage: Rect2) -> Array:
	var out: Array = []
	if _layout.is_empty():
		_load_layout()
	var layout: Dictionary = _active_layout()
	var city: Dictionary = _ctx.get("city", {})
	if city.is_empty():
		return out
	var fid: int = _faction_id()
	var built: Array = city.get("buildings", [])
	var defs: Array = _ctx.get("buildings", [])
	var fcolors: Array = _ctx.get("faction_colors", [])
	var base_col: Color = fcolors[fid] if fid >= 0 and fid < fcolors.size() else Color(0.6, 0.6, 0.6)
	# Grundgroesse eines Bauplatzes; "s" im Layout skaliert sie je Plot.
	# Damit stehen hintere Reihen kleiner und vordere groesser - ohne das
	# wirkt der Hof flach (It. 33).
	var hw_base: float = min(stage.size.x * 0.15, 150.0)

	for def in defs:
		var bid: String = String(def["id"])
		if not layout.has(bid):
			continue
		var lp: Dictionary = layout[bid]
		var center := stage.position + Vector2(
			float(lp.get("x", 0.5)) * stage.size.x,
			float(lp.get("y", 0.5)) * stage.size.y)
		var is_built: bool = built.has(bid)
		var hw: float = hw_base * float(lp.get("s", 1.0))
		var hh: float = hw * 0.5
		out.append({
			"id": bid,
			"name": String(def.get("name", bid)),
			"center": center,
			# Der Platz als ANTEIL, wie er in city_layout.json steht - die
			# raeumliche Ansicht rechnet daraus ihren eigenen Ort, statt
			# aus einem Bildschirmpunkt zurueckzurechnen.
			"lx": float(lp.get("x", 0.5)),
			"ly": float(lp.get("y", 0.5)),
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
	if not is_built:
		var cost: Dictionary = def.get("cost", {})
		var missing: Array = _missing_requires(def)
		if not missing.is_empty():
			return "braucht " + " + ".join(missing)
		return Wallet.cost_text(cost) + " bauen"
	# Gebaut: Militaergebaeude zeigen Rekrut-Vorrat je Einheit, Rest "fertig".
	var units: Array = UnitType.units_for_building(fid, bid)
	if not units.is_empty():
		var pools: Dictionary = _city_pools()
		var parts: Array = []
		for u in units:
			parts.append("%s:%d" % [UnitType.short_of(String(u)), int(pools.get(u, 0))])
		return " ".join(parts)
	return "fertig"


# "requires" tolerant lesen (String ODER Array, z.B. Zitadelle braucht
# Reiterei UND Mauer) und die noch fehlenden als Anzeige-Namen liefern.
func _missing_requires(def: Dictionary) -> Array:
	var raw: Variant = def.get("requires", null)
	if raw == null:
		return []
	var reqs: Array = (raw as Array) if raw is Array else [raw]
	var missing: Array = []
	for r in reqs:
		if not _city_has(String(r)):
			missing.append(String(r).capitalize())
	return missing


func _plot_sub_color(def: Dictionary, is_built: bool, fid: int) -> Color:
	var bid: String = String(def["id"])
	if not is_built:
		if not _missing_requires(def).is_empty():
			return Color(0.9, 0.5, 0.5)
		var purse: Wallet = _wallet()
		if purse != null and purse.can_afford(def.get("cost", {})):
			return Color(0.6, 0.95, 0.6)
		return Color(0.95, 0.85, 0.5)
	if not UnitType.units_for_building(fid, bid).is_empty():
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
	# In 3D gibt es keine Rauten: der Strahl der Kamera trifft den Hofboden,
	# und getroffen ist der Bauplatz, der diesem Punkt am naechsten liegt.
	# Ein Bauplatz ist rund zwei Einheiten breit, DIST_MAX also grosszuegig
	# genug, dass man nicht genau treffen muss, und eng genug, dass ein
	# Tipp auf leeren Hof nichts ausloest.
	if _city3d_on and _city3d != null:
		const DIST_MAX := 1.3
		var local: Vector2 = pos - _stage_rect().position
		var hit: Vector3 = _city3d.ground_at(local)
		var best: Dictionary = {}
		var best_d: float = DIST_MAX
		for p in _plots:
			var w3: Vector3 = _city3d.plot_pos(float(p["lx"]), float(p["ly"]))
			var d: float = Vector2(hit.x - w3.x, hit.z - w3.z).length()
			if d < best_d:
				best_d = d
				best = p
		if not best.is_empty():
			_act_on_plot(best)
		return
	# Vorne (groesseres y) hat Vorrang -> rueckwaerts durch die Zeichenliste.
	for i in range(_plots.size() - 1, -1, -1):
		var p: Dictionary = _plots[i]
		if _in_diamond(pos, p["center"], p["hw"], p["hh"]):
			_act_on_plot(p)
			return


# Plaza/Brunnen-Treffer. Die Werte stehen seit It. 33 in
# data/city_layout.json unter "plaza" - dieselbe Datei, aus der auch
# tools/gen_city_bg.py den Platz ZEICHNET. Vorher waren es Konstanten hier
# und Koordinaten dort: nach dem Umbau der Komposition lag die Grafik an
# einer Stelle und die Trefferflaeche an einer anderen.
# Die Konstanten bleiben als Rueckfall, wenn die Datei den Eintrag nicht
# hat (alte Layout-Datei).
const PLAZA_FALLBACK := {"x": 0.63, "y": 0.885, "rx": 0.115, "ry": 0.05}


# Geldbeutel des Spielers (M13a). Er steckt seit dem Umbau als "wallet" im
# Kontext, weil er dem SPIELER gehoert und nicht dem Helden - mit mehreren
# Helden waere "welcher Held haelt das Gold" sofort ein Fehler.
#
# Rueckfall auf `hero.wallet`, wenn der Aufrufer nur einen Helden reicht:
# so bleiben Alt-Aufrufer und die Tests gueltig, die den Screen einzeln
# aufsetzen. Gibt null zurueck, wenn beides fehlt - jeder Aufrufer prueft.
func _wallet() -> Wallet:
	var w = _ctx.get("wallet", null)
	if w is Wallet:
		return w as Wallet
	var hero: Object = _ctx.get("hero", null)
	if hero != null:
		return hero.wallet as Wallet
	return null


func _plaza_def() -> Dictionary:
	if _layout.is_empty():
		_load_layout()
	if _plaza.is_empty():
		return PLAZA_FALLBACK
	return _plaza


func _hit_plaza(pos: Vector2) -> bool:
	var stage := _stage_rect()
	var pd: Dictionary = _plaza_def()
	var cx: float = stage.position.x + float(pd["x"]) * stage.size.x
	var cy: float = stage.position.y + float(pd["y"]) * stage.size.y
	var rx: float = float(pd["rx"]) * stage.size.x
	var ry: float = float(pd["ry"]) * stage.size.y
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
	# Wochenrate aufaddieren: pro Militaergebaeude das weekly_growth aller
	# freigeschalteten Einheiten, fuer andere Gebaeude den Effekt-Text.
	var growth: int = 0
	var effects: Array = []
	for def in defs:
		var bid: String = String(def["id"])
		if not built.has(bid):
			continue
		var units: Array = UnitType.units_for_building(fid, bid)
		if not units.is_empty():
			for u in units:
				growth += UnitType.growth_of(String(u))
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
	# Ein Klick auf jeden Bauplatz-Tap. Das eigentliche Bauen bzw.
	# Rekrutieren macht sein eigenes Geraeusch im WorldMapScreen.
	Sound.play("ui_tap")
	var bid: String = String(p["id"])
	var fid: int = _faction_id()
	if not bool(p["built"]):
		build_requested.emit(bid)
		return
	if not UnitType.units_for_building(fid, bid).is_empty():
		_open_recruit_panel(bid)
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
	var purse: Wallet = _wallet()
	if purse == null:
		return
	for rid in _trade_labels.keys():
		var amt: int = purse.get_amount(String(rid))
		(_trade_labels[rid] as Label).text = "%s: %d" % [Wallet.display_name(String(rid)), amt]


# --- Rekrut-Panel (M4 Teil 2) ---
# Ein Militaergebaeude schaltet 1-2 Einheiten frei. Tap oeffnet dieses
# Panel; jede Zeile zeigt Vorrat/Wochenrate/Preis und emittiert beim
# Kauf recruit_requested(uid) - die Oekonomie bleibt im WorldMapScreen,
# der danach ueber open() refresht (Labels ziehen aus _ctx nach).

func _open_recruit_panel(bid: String) -> void:
	if _recruit_panel == null:
		_build_recruit_panel()
	# Titel + Zeilen fuer genau dieses Gebaeude neu aufbauen.
	var bname: String = bid.capitalize()
	for def in _ctx.get("buildings", []):
		if String(def["id"]) == bid:
			bname = String(def["name"])
			break
	_recruit_title.text = "%s - Rekrutierung" % bname
	for c in _recruit_rows_box.get_children():
		c.queue_free()
	_recruit_labels.clear()
	_recruit_buttons.clear()
	var fid: int = _faction_id()
	for uid in UnitType.units_for_building(fid, bid):
		var u: String = String(uid)
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 14)
		_recruit_rows_box.add_child(row)

		# Kreatur zeigen, nicht nur ihren Namen. Fehlt das Sprite, bleibt
		# die Zeile wie vorher - kein leerer Platzhalter.
		var icon: TextureRect = UnitArt.icon(u, RECRUIT_ICON_PX)
		if icon != null:
			row.add_child(icon)

		var lbl := Label.new()
		lbl.custom_minimum_size = Vector2(420, 0)
		lbl.add_theme_font_size_override("font_size", 24)
		lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(lbl)
		_recruit_labels[u] = lbl

		var btn := Button.new()
		btn.text = "+1  (%s)" % Wallet.cost_text(UnitType.cost_dict_of(u))
		btn.custom_minimum_size = Vector2(300, 90)
		btn.add_theme_font_size_override("font_size", 26)
		btn.pressed.connect(func() -> void: recruit_requested.emit(u))
		row.add_child(btn)
		_recruit_buttons[u] = btn
	_recruit_panel.visible = true
	_refresh_recruit_labels()


func _build_recruit_panel() -> void:
	var panel := Panel.new()
	panel.visible = false
	panel.anchor_left = 0.5
	panel.anchor_top = 0.5
	panel.anchor_right = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -440
	panel.offset_top = -320
	panel.offset_right = 440
	panel.offset_bottom = 320
	add_child(panel)
	_recruit_panel = panel

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

	_recruit_title = Label.new()
	_recruit_title.add_theme_font_size_override("font_size", 36)
	vb.add_child(_recruit_title)

	_recruit_rows_box = VBoxContainer.new()
	_recruit_rows_box.add_theme_constant_override("separation", 14)
	vb.add_child(_recruit_rows_box)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(spacer)

	var close_btn := Button.new()
	close_btn.text = "Schliessen"
	close_btn.custom_minimum_size = Vector2(0, 96)
	close_btn.add_theme_font_size_override("font_size", 30)
	close_btn.pressed.connect(func() -> void: _recruit_panel.visible = false)
	vb.add_child(close_btn)


# --- Garnison-Panel (M9b) ---
# Links die Heldenarmee, rechts die Garnison. Pro Einheit eine Zeile mit
# Verschiebe-Buttons; ohne Held vor Ort zeigt es nur den Bestand, weil
# Tauschen dann nicht geht.

func _open_garrison_panel() -> void:
	if _gar_panel == null:
		_build_garrison_panel()
	_fill_garrison_rows()
	_gar_panel.visible = true


func _build_garrison_panel() -> void:
	var panel := Panel.new()
	panel.visible = false
	panel.anchor_left = 0.5
	panel.anchor_top = 0.5
	panel.anchor_right = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -460
	panel.offset_top = -540
	panel.offset_right = 460
	panel.offset_bottom = 540
	add_child(panel)
	_gar_panel = panel

	var bg := ColorRect.new()
	bg.color = Color(0.08, 0.09, 0.12, 1.0)
	bg.anchor_right = 1.0
	bg.anchor_bottom = 1.0
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(bg)

	var vb := VBoxContainer.new()
	vb.anchor_right = 1.0
	vb.anchor_bottom = 1.0
	vb.offset_left = 28
	vb.offset_top = 28
	vb.offset_right = -28
	vb.offset_bottom = -28
	vb.add_theme_constant_override("separation", 14)
	panel.add_child(vb)

	_gar_title = Label.new()
	_gar_title.add_theme_font_size_override("font_size", 36)
	vb.add_child(_gar_title)

	_gar_rows = VBoxContainer.new()
	_gar_rows.add_theme_constant_override("separation", 10)
	vb.add_child(_gar_rows)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(spacer)

	var close_btn := Button.new()
	close_btn.text = "Schliessen"
	close_btn.custom_minimum_size = Vector2(0, 96)
	close_btn.add_theme_font_size_override("font_size", 30)
	close_btn.pressed.connect(func() -> void: _gar_panel.visible = false)
	vb.add_child(close_btn)


func _fill_garrison_rows() -> void:
	if _gar_rows == null:
		return
	for c in _gar_rows.get_children():
		c.queue_free()
	var city: Dictionary = _ctx.get("city", {})
	var gar: Dictionary = city.get("garrison_army", {}) as Dictionary
	var hero: Object = _ctx.get("hero", null)
	var here: bool = bool(_ctx.get("hero_here", false))
	_gar_title.text = "Garnison %s" % Garrison.summary(gar)
	if not here:
		var hint := Label.new()
		hint.text = "Held ist nicht in der Stadt - Tauschen nicht moeglich.\nRekruten wandern direkt in die Garnison."
		hint.add_theme_font_size_override("font_size", 26)
		_gar_rows.add_child(hint)
	# Alle Einheiten, die auf einer der beiden Seiten vorkommen.
	var ids: Array = []
	for uid in UnitType.all_ids():
		var in_hero: int = int((hero.army as Dictionary).get(uid, 0)) if hero != null else 0
		if in_hero > 0 or int(gar.get(uid, 0)) > 0:
			ids.append(String(uid))
	if ids.is_empty():
		var empty := Label.new()
		empty.text = "Keine Einheiten vorhanden."
		empty.add_theme_font_size_override("font_size", 26)
		_gar_rows.add_child(empty)
		return
	for uid in ids:
		var u: String = String(uid)
		var in_hero2: int = int((hero.army as Dictionary).get(u, 0)) if hero != null else 0
		var in_city: int = int(gar.get(u, 0))
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 10)
		_gar_rows.add_child(row)

		var icon2: TextureRect = UnitArt.icon(u, GARRISON_ICON_PX)
		if icon2 != null:
			row.add_child(icon2)

		var lbl := Label.new()
		lbl.text = "%s  Held %d / Stadt %d" % [UnitType.name_of(u), in_hero2, in_city]
		lbl.custom_minimum_size = Vector2(380, 0)
		lbl.add_theme_font_size_override("font_size", 24)
		lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(lbl)

		if here:
			_add_move_button(row, "-> Stadt", u, true, false, in_hero2 > 0)
			_add_move_button(row, "alle >>", u, true, true, in_hero2 > 0)
			_add_move_button(row, "-> Held", u, false, false, in_city > 0)
			_add_move_button(row, "<< alle", u, false, true, in_city > 0)


func _add_move_button(row: HBoxContainer, text: String, uid: String,
		to_city: bool, all: bool, enabled: bool) -> void:
	var b := Button.new()
	b.text = text
	b.disabled = not enabled
	b.custom_minimum_size = Vector2(150, 76)
	b.add_theme_font_size_override("font_size", 22)
	b.pressed.connect(func() -> void: garrison_move_requested.emit(uid, to_city, all))
	row.add_child(b)


func _refresh_recruit_labels() -> void:
	if _recruit_panel == null or not _recruit_panel.visible:
		return
	var pools: Dictionary = _city_pools()
	var hero: Object = _ctx.get("hero", null)
	var here: bool = bool(_ctx.get("hero_here", false))
	for uid in _recruit_labels.keys():
		var u: String = String(uid)
		var have: int = int(pools.get(u, 0))
		# Zweite Zeile mit den Kampfwerten: vorher kaufte der Spieler eine
		# Einheit, ohne zu sehen, was sie kann.
		(_recruit_labels[u] as Label).text = "%s (T%d): %d da, +%d/Wo\n%s" % [
			UnitType.name_of(u), UnitType.tier_of(u), have, UnitType.growth_of(u),
			UnitArt.stat_line(u)]
		var purse: Wallet = _wallet()
		var afford: bool = purse != null \
			and purse.can_afford(UnitType.cost_dict_of(u))
		(_recruit_buttons[u] as Button).disabled = have <= 0 or not afford or not here
