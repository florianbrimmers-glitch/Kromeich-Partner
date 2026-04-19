extends Control

# Taktik-Kampf-Overlay (Phase A): zeigt ein Schlachtfeld mit beiden
# Armeen als Stacks auf einem 10x8-Grid. In dieser Phase passiert auf
# dem Grid noch kein interaktiver Kampf - "Kaempfen" loest den Kampf
# sofort mathematisch auf (wie bisher auf der Weltkarte), "Fliehen"
# bricht ab. Phase B wird daraus einen echten Zugkampf machen.
#
# Kommunikation: der Host (WorldMapScreen) instanziert die Szene als
# Kind, setzt die Parameter ueber set_battle(...) und verbindet das
# Signal battle_finished. Das Signal liefert ein Dictionary mit
# Schluessel "outcome" ("fight" oder "flee").

signal battle_finished(result: Dictionary)

const GRID_COLS := 10
const GRID_ROWS := 8

var _player_name: String = "Held"
var _player_army: int = 0
var _player_bonus: int = 0
var _enemy_name: String = "Monster"
var _enemy_army: int = 0

var _grid_area: Control
var _title_label: Label
var _info_label: Label
var _prediction_label: Label
var _fight_btn: Button
var _flee_btn: Button
var _finished: bool = false


func set_battle(player_name: String, player_army: int, player_bonus: int,
		enemy_name: String, enemy_army: int) -> void:
	_player_name = player_name
	_player_army = player_army
	_player_bonus = player_bonus
	_enemy_name = enemy_name
	_enemy_army = enemy_army
	_refresh_texts()
	if _grid_area != null:
		_grid_area.queue_redraw()


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build_ui()
	_refresh_texts()


func _build_ui() -> void:
	var bg := ColorRect.new()
	bg.color = Color(0.04, 0.05, 0.08, 1.0)
	bg.mouse_filter = Control.MOUSE_FILTER_STOP
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(bg)

	_title_label = Label.new()
	_title_label.text = "KAMPF"
	_title_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_title_label.set_anchors_preset(Control.PRESET_TOP_WIDE)
	_title_label.offset_top = 40.0
	_title_label.offset_bottom = 120.0
	_title_label.add_theme_font_size_override("font_size", 56)
	_title_label.add_theme_color_override("font_color", Color(0.95, 0.85, 0.40))
	add_child(_title_label)

	_info_label = Label.new()
	_info_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_info_label.set_anchors_preset(Control.PRESET_TOP_WIDE)
	_info_label.offset_top = 140.0
	_info_label.offset_bottom = 220.0
	_info_label.add_theme_font_size_override("font_size", 36)
	_info_label.add_theme_color_override("font_color", Color(0.90, 0.92, 0.96))
	add_child(_info_label)

	_prediction_label = Label.new()
	_prediction_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_prediction_label.set_anchors_preset(Control.PRESET_TOP_WIDE)
	_prediction_label.offset_top = 220.0
	_prediction_label.offset_bottom = 290.0
	_prediction_label.add_theme_font_size_override("font_size", 32)
	add_child(_prediction_label)

	_grid_area = Control.new()
	_grid_area.set_anchors_preset(Control.PRESET_FULL_RECT)
	_grid_area.offset_left = 40.0
	_grid_area.offset_right = -40.0
	_grid_area.offset_top = 320.0
	_grid_area.offset_bottom = -240.0
	_grid_area.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_grid_area.draw.connect(_draw_grid)
	_grid_area.resized.connect(_on_grid_resized)
	add_child(_grid_area)

	_fight_btn = Button.new()
	_fight_btn.text = "Kaempfen"
	_fight_btn.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	_fight_btn.offset_left = 60.0
	_fight_btn.offset_top = -180.0
	_fight_btn.offset_right = 500.0
	_fight_btn.offset_bottom = -60.0
	_fight_btn.add_theme_font_size_override("font_size", 40)
	_fight_btn.pressed.connect(_on_fight_pressed)
	add_child(_fight_btn)

	_flee_btn = Button.new()
	_flee_btn.text = "Fliehen"
	_flee_btn.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	_flee_btn.offset_left = -500.0
	_flee_btn.offset_top = -180.0
	_flee_btn.offset_right = -60.0
	_flee_btn.offset_bottom = -60.0
	_flee_btn.add_theme_font_size_override("font_size", 40)
	_flee_btn.pressed.connect(_on_flee_pressed)
	add_child(_flee_btn)


func _refresh_texts() -> void:
	if _info_label == null or _prediction_label == null:
		return
	var eff: int = _player_army + _player_bonus
	_info_label.text = "%s (A %d + Bonus %d = %d)   vs.   %s (A %d)" % [
		_player_name, _player_army, _player_bonus, eff, _enemy_name, _enemy_army]
	if eff >= _enemy_army:
		var loss: int = max(0, _enemy_army - _player_bonus)
		_prediction_label.text = "Prognose: Sieg  (Verlust %d Armee)" % loss
		_prediction_label.add_theme_color_override("font_color", Color(0.55, 0.90, 0.55))
	else:
		_prediction_label.text = "Prognose: NIEDERLAGE  (Flucht empfohlen)"
		_prediction_label.add_theme_color_override("font_color", Color(1.0, 0.45, 0.40))


func _on_grid_resized() -> void:
	if _grid_area != null:
		_grid_area.queue_redraw()


func _draw_grid() -> void:
	if _grid_area == null:
		return
	var size: Vector2 = _grid_area.size
	if size.x <= 0.0 or size.y <= 0.0:
		return
	var cell_w: float = size.x / float(GRID_COLS)
	var cell_h: float = size.y / float(GRID_ROWS)
	var cell: float = min(cell_w, cell_h)
	var grid_w: float = cell * GRID_COLS
	var grid_h: float = cell * GRID_ROWS
	var ox: float = (size.x - grid_w) * 0.5
	var oy: float = (size.y - grid_h) * 0.5

	var bg := Rect2(Vector2(ox, oy), Vector2(grid_w, grid_h))
	_grid_area.draw_rect(bg, Color(0.12, 0.14, 0.18), true)

	var line_col := Color(0.25, 0.30, 0.38)
	for c in range(GRID_COLS + 1):
		var x: float = ox + float(c) * cell
		_grid_area.draw_line(Vector2(x, oy), Vector2(x, oy + grid_h), line_col, 1.5)
	for r in range(GRID_ROWS + 1):
		var y: float = oy + float(r) * cell
		_grid_area.draw_line(Vector2(ox, y), Vector2(ox + grid_w, y), line_col, 1.5)

	# Spieler-Stack links Mitte
	var p_col: int = 1
	var p_row: int = int(GRID_ROWS / 2)
	var p_center := Vector2(ox + (float(p_col) + 0.5) * cell, oy + (float(p_row) + 0.5) * cell)
	var radius: float = cell * 0.40
	_grid_area.draw_circle(p_center, radius, Color(0.95, 0.80, 0.25))
	_grid_area.draw_arc(p_center, radius, 0.0, TAU, 32, Color(0.60, 0.45, 0.10), 3.0)
	_draw_stack_label(p_center, str(_player_army), radius)

	# Gegner-Stack rechts Mitte
	var e_col: int = GRID_COLS - 2
	var e_row: int = int(GRID_ROWS / 2)
	var e_center := Vector2(ox + (float(e_col) + 0.5) * cell, oy + (float(e_row) + 0.5) * cell)
	_grid_area.draw_circle(e_center, radius, Color(0.55, 0.55, 0.60))
	_grid_area.draw_arc(e_center, radius, 0.0, TAU, 32, Color(0.90, 0.25, 0.25), 3.0)
	_draw_stack_label(e_center, str(_enemy_army), radius)


func _draw_stack_label(center: Vector2, text: String, radius: float) -> void:
	var font: Font = get_theme_default_font()
	if font == null:
		return
	var fs: int = int(max(18.0, radius * 0.9))
	var tsize: Vector2 = font.get_string_size(text, HORIZONTAL_ALIGNMENT_CENTER, -1.0, fs)
	var pos := Vector2(center.x - tsize.x * 0.5, center.y + tsize.y * 0.3)
	_grid_area.draw_string(font, pos, text, HORIZONTAL_ALIGNMENT_CENTER, -1.0, fs, Color(0.06, 0.06, 0.08))


func _on_fight_pressed() -> void:
	if _finished:
		return
	_finished = true
	battle_finished.emit({"outcome": "fight"})


func _on_flee_pressed() -> void:
	if _finished:
		return
	_finished = true
	battle_finished.emit({"outcome": "flee"})
