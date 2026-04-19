extends Control

# Taktik-Kampf-Overlay (Phase B): interaktiver Zugkampf auf einem
# 10x8-Grid. Beide Seiten haben je einen Stack generischer Einheiten
# (Held-Armee vs. Gegner-Armee). Spieler zieht zuerst, dann KI.
# - Tap auf erreichbares leeres Feld: hinbewegen (beendet den Zug)
# - Tap auf Gegner-Feld in Reichweite: hinbewegen & angreifen
# - "Warten": Zug beenden ohne Aktion
# - "Fliehen": Kampf abbrechen (Outcome = flee)
# Gewinnt der Spieler, verliert er evtl. Einheiten (casualties); das
# Signal meldet outcome und casualties zurueck an den Host.
#
# Kommunikation: Host instanziert die Szene, setzt Parameter via
# set_battle(context) und verbindet battle_finished.
# context keys: player_name, player_army, player_bonus, enemy_name,
#   enemy_army, allow_flee (bool, default true), seed (int, default 42).
# result keys: outcome ("victory" | "defeat" | "flee"),
#   casualties (int, nur bei victory relevant).

signal battle_finished(result: Dictionary)

const GRID_COLS := 10
const GRID_ROWS := 8

# Einheiten-Profil. Beide Seiten identisch, damit die alte
# Kampfkraft-Formel (Armee + Bonus) reproduzierbar bleibt.
# Der Spieler-Bonus (Level+Wachturm) addiert sich auf Angriff und
# Verteidigung des Spieler-Stacks.
const UNIT_HP := 10
const UNIT_SPEED := 4
const UNIT_DMG_MIN := 1
const UNIT_DMG_MAX := 3
const UNIT_ATT := 5
const UNIT_DEF := 4

const PHASE_PLAYER := 0
const PHASE_ENEMY := 1
const PHASE_OVER := 2

var _player_name: String = "Held"
var _player_count_start: int = 0
var _player_bonus: int = 0
var _enemy_name: String = "Gegner"
var _enemy_count_start: int = 0
var _allow_flee: bool = true

var _p_pos: Vector2i
var _p_count: int
var _p_top_hp: int
var _p_retaliated: bool = false

var _e_pos: Vector2i
var _e_count: int
var _e_top_hp: int
var _e_retaliated: bool = false

var _phase: int = PHASE_PLAYER
var _round: int = 1
var _rng: RandomNumberGenerator
var _finished: bool = false
var _last_action_text: String = ""

var _grid_area: Control
var _title_label: Label
var _info_label: Label
var _action_label: Label
var _wait_btn: Button
var _flee_btn: Button

var _reachable: Dictionary = {}  # Vector2i -> step count


func set_battle(context: Dictionary) -> void:
	_player_name = String(context.get("player_name", "Held"))
	_player_count_start = int(context.get("player_army", 0))
	_player_bonus = int(context.get("player_bonus", 0))
	_enemy_name = String(context.get("enemy_name", "Gegner"))
	_enemy_count_start = int(context.get("enemy_army", 0))
	_allow_flee = bool(context.get("allow_flee", true))
	_p_count = _player_count_start
	_p_top_hp = UNIT_HP
	_e_count = _enemy_count_start
	_e_top_hp = UNIT_HP
	_p_pos = Vector2i(1, int(GRID_ROWS / 2))
	_e_pos = Vector2i(GRID_COLS - 2, int(GRID_ROWS / 2))
	_rng = RandomNumberGenerator.new()
	_rng.seed = int(context.get("seed", 42))
	_phase = PHASE_PLAYER
	_round = 1
	_p_retaliated = false
	_e_retaliated = false
	_finished = false
	_last_action_text = "Dein Zug."
	_refresh_reachable()
	_refresh_texts()
	if _flee_btn != null:
		_flee_btn.visible = _allow_flee
	if _grid_area != null:
		_grid_area.queue_redraw()


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build_ui()
	_refresh_reachable()
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
	_title_label.offset_top = 30.0
	_title_label.offset_bottom = 110.0
	_title_label.add_theme_font_size_override("font_size", 56)
	_title_label.add_theme_color_override("font_color", Color(0.95, 0.85, 0.40))
	add_child(_title_label)

	_info_label = Label.new()
	_info_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_info_label.set_anchors_preset(Control.PRESET_TOP_WIDE)
	_info_label.offset_top = 120.0
	_info_label.offset_bottom = 190.0
	_info_label.add_theme_font_size_override("font_size", 30)
	_info_label.add_theme_color_override("font_color", Color(0.90, 0.92, 0.96))
	add_child(_info_label)

	_action_label = Label.new()
	_action_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_action_label.set_anchors_preset(Control.PRESET_TOP_WIDE)
	_action_label.offset_top = 190.0
	_action_label.offset_bottom = 260.0
	_action_label.add_theme_font_size_override("font_size", 28)
	_action_label.add_theme_color_override("font_color", Color(0.80, 0.85, 0.95))
	add_child(_action_label)

	_grid_area = Control.new()
	_grid_area.set_anchors_preset(Control.PRESET_FULL_RECT)
	_grid_area.offset_left = 40.0
	_grid_area.offset_right = -40.0
	_grid_area.offset_top = 280.0
	_grid_area.offset_bottom = -240.0
	_grid_area.mouse_filter = Control.MOUSE_FILTER_STOP
	_grid_area.draw.connect(_draw_grid)
	_grid_area.resized.connect(_on_grid_resized)
	_grid_area.gui_input.connect(_on_grid_input)
	add_child(_grid_area)

	_wait_btn = Button.new()
	_wait_btn.text = "Warten"
	_wait_btn.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	_wait_btn.offset_left = 60.0
	_wait_btn.offset_top = -180.0
	_wait_btn.offset_right = 500.0
	_wait_btn.offset_bottom = -60.0
	_wait_btn.add_theme_font_size_override("font_size", 40)
	_wait_btn.pressed.connect(_on_wait_pressed)
	add_child(_wait_btn)

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
	if _info_label == null or _action_label == null:
		return
	_info_label.text = "%s  A=%d (Bonus +%d)   vs.   %s  A=%d  |  Runde %d" % [
		_player_name, _p_count, _player_bonus,
		_enemy_name, _e_count, _round]
	_action_label.text = _last_action_text


func _on_grid_resized() -> void:
	if _grid_area != null:
		_grid_area.queue_redraw()


# --- Grid-Geometrie ---

func _grid_origin_and_cell() -> Array:
	var size: Vector2 = _grid_area.size
	if size.x <= 0.0 or size.y <= 0.0:
		return [Vector2.ZERO, 0.0]
	var cell_w: float = size.x / float(GRID_COLS)
	var cell_h: float = size.y / float(GRID_ROWS)
	var cell: float = min(cell_w, cell_h)
	var grid_w: float = cell * GRID_COLS
	var grid_h: float = cell * GRID_ROWS
	var ox: float = (size.x - grid_w) * 0.5
	var oy: float = (size.y - grid_h) * 0.5
	return [Vector2(ox, oy), cell]


func _cell_from_pos(p: Vector2) -> Vector2i:
	var geom: Array = _grid_origin_and_cell()
	var origin: Vector2 = geom[0]
	var cell: float = geom[1]
	if cell <= 0.0:
		return Vector2i(-1, -1)
	var cx: int = int(floor((p.x - origin.x) / cell))
	var cy: int = int(floor((p.y - origin.y) / cell))
	if cx < 0 or cx >= GRID_COLS or cy < 0 or cy >= GRID_ROWS:
		return Vector2i(-1, -1)
	return Vector2i(cx, cy)


# --- BFS fuer Reichweite ---

func _refresh_reachable() -> void:
	_reachable.clear()
	if _phase != PHASE_PLAYER or _finished:
		return
	var start: Vector2i = _p_pos
	_reachable[start] = 0
	var frontier: Array = [start]
	var limit: int = UNIT_SPEED
	while not frontier.is_empty():
		var cur: Vector2i = frontier.pop_front()
		var d: int = int(_reachable[cur])
		if d >= limit:
			continue
		for dx in [-1, 0, 1]:
			for dy in [-1, 0, 1]:
				if dx == 0 and dy == 0:
					continue
				if dx != 0 and dy != 0:
					continue  # 4-Nachbarschaft
				var n := Vector2i(cur.x + dx, cur.y + dy)
				if n.x < 0 or n.x >= GRID_COLS or n.y < 0 or n.y >= GRID_ROWS:
					continue
				if n == _e_pos:
					continue
				if _reachable.has(n):
					continue
				_reachable[n] = d + 1
				frontier.append(n)


func _is_adjacent(a: Vector2i, b: Vector2i) -> bool:
	var dx: int = abs(a.x - b.x)
	var dy: int = abs(a.y - b.y)
	return dx + dy == 1


func _best_adjacent_reachable(target: Vector2i) -> Vector2i:
	# waehlt das zu target adjazente Feld mit geringster Distanz,
	# das in _reachable liegt. Gibt (-1,-1) wenn keins erreichbar.
	var best := Vector2i(-1, -1)
	var best_d := 9999
	for dx in [-1, 0, 1]:
		for dy in [-1, 0, 1]:
			if dx == 0 and dy == 0:
				continue
			if dx != 0 and dy != 0:
				continue
			var n := Vector2i(target.x + dx, target.y + dy)
			if n == _p_pos:
				return n  # schon benachbart
			if _reachable.has(n):
				var d: int = int(_reachable[n])
				if d < best_d:
					best_d = d
					best = n
	return best


# --- Rendering ---

func _draw_grid() -> void:
	if _grid_area == null:
		return
	var geom: Array = _grid_origin_and_cell()
	var origin: Vector2 = geom[0]
	var cell: float = geom[1]
	if cell <= 0.0:
		return
	var grid_size := Vector2(cell * GRID_COLS, cell * GRID_ROWS)

	_grid_area.draw_rect(Rect2(origin, grid_size), Color(0.12, 0.14, 0.18), true)

	# Reichweiten-Felder hervorheben (gruenlich), Attack-Cells (roetlich)
	if _phase == PHASE_PLAYER and not _finished:
		for k in _reachable.keys():
			var c: Vector2i = k
			if c == _p_pos:
				continue
			var r := Rect2(origin + Vector2(float(c.x) * cell, float(c.y) * cell),
				Vector2(cell, cell))
			_grid_area.draw_rect(r, Color(0.25, 0.45, 0.30, 0.55), true)
		# Gegner-Zelle einfaerben, falls angreifbar
		if _can_attack_enemy():
			var r2 := Rect2(origin + Vector2(float(_e_pos.x) * cell, float(_e_pos.y) * cell),
				Vector2(cell, cell))
			_grid_area.draw_rect(r2, Color(0.60, 0.25, 0.25, 0.65), true)

	# Gitterlinien
	var line_col := Color(0.25, 0.30, 0.38)
	for c in range(GRID_COLS + 1):
		var x: float = origin.x + float(c) * cell
		_grid_area.draw_line(Vector2(x, origin.y), Vector2(x, origin.y + grid_size.y), line_col, 1.5)
	for r in range(GRID_ROWS + 1):
		var y: float = origin.y + float(r) * cell
		_grid_area.draw_line(Vector2(origin.x, y), Vector2(origin.x + grid_size.x, y), line_col, 1.5)

	var radius: float = cell * 0.40

	if _p_count > 0:
		var p_center := origin + Vector2((float(_p_pos.x) + 0.5) * cell, (float(_p_pos.y) + 0.5) * cell)
		_grid_area.draw_circle(p_center, radius, Color(0.95, 0.80, 0.25))
		_grid_area.draw_arc(p_center, radius, 0.0, TAU, 32, Color(0.60, 0.45, 0.10), 3.0)
		_draw_stack_label(p_center, str(_p_count), radius)

	if _e_count > 0:
		var e_center := origin + Vector2((float(_e_pos.x) + 0.5) * cell, (float(_e_pos.y) + 0.5) * cell)
		_grid_area.draw_circle(e_center, radius, Color(0.55, 0.55, 0.60))
		_grid_area.draw_arc(e_center, radius, 0.0, TAU, 32, Color(0.90, 0.25, 0.25), 3.0)
		_draw_stack_label(e_center, str(_e_count), radius)


func _draw_stack_label(center: Vector2, text: String, radius: float) -> void:
	var font: Font = get_theme_default_font()
	if font == null:
		return
	var fs: int = int(max(18.0, radius * 0.9))
	var tsize: Vector2 = font.get_string_size(text, HORIZONTAL_ALIGNMENT_CENTER, -1.0, fs)
	var pos := Vector2(center.x - tsize.x * 0.5, center.y + tsize.y * 0.3)
	_grid_area.draw_string(font, pos, text, HORIZONTAL_ALIGNMENT_CENTER, -1.0, fs, Color(0.06, 0.06, 0.08))


func _can_attack_enemy() -> bool:
	if _e_count <= 0:
		return false
	# Angreifbar, wenn entweder bereits adjazent oder ein adjazentes
	# Feld erreichbar ist.
	if _is_adjacent(_p_pos, _e_pos):
		return true
	return _best_adjacent_reachable(_e_pos).x >= 0


# --- Spieler-Input ---

func _on_grid_input(event: InputEvent) -> void:
	if _finished or _phase != PHASE_PLAYER:
		return
	if not (event is InputEventMouseButton):
		return
	var mb: InputEventMouseButton = event
	if not mb.pressed or mb.button_index != MOUSE_BUTTON_LEFT:
		return
	var cell: Vector2i = _cell_from_pos(mb.position)
	if cell.x < 0:
		return
	if cell == _e_pos:
		_try_attack_enemy()
		return
	if cell == _p_pos:
		return
	if _reachable.has(cell):
		_p_pos = cell
		_last_action_text = "Du bewegst dich."
		_end_player_turn()


func _try_attack_enemy() -> void:
	if _e_count <= 0:
		return
	if _is_adjacent(_p_pos, _e_pos):
		_resolve_attack(true)
		_end_player_turn()
		return
	var spot: Vector2i = _best_adjacent_reachable(_e_pos)
	if spot.x < 0:
		_last_action_text = "Gegner ist ausser Reichweite."
		_refresh_texts()
		return
	_p_pos = spot
	_resolve_attack(true)
	_end_player_turn()


func _on_wait_pressed() -> void:
	if _finished or _phase != PHASE_PLAYER:
		return
	_last_action_text = "Du wartest."
	_end_player_turn()


func _on_flee_pressed() -> void:
	if _finished:
		return
	if not _allow_flee:
		return
	_finished = true
	battle_finished.emit({"outcome": "flee", "casualties": 0})


# --- Zug-Ablauf ---

func _end_player_turn() -> void:
	_refresh_texts()
	if _grid_area != null:
		_grid_area.queue_redraw()
	if _check_end():
		return
	_phase = PHASE_ENEMY
	_reachable.clear()
	if _grid_area != null:
		_grid_area.queue_redraw()
	# kleine Pause, damit Spieler sieht was passiert
	get_tree().create_timer(0.35).timeout.connect(_run_enemy_turn)


func _run_enemy_turn() -> void:
	if _finished:
		return
	if _e_count <= 0:
		_check_end()
		return
	# BFS vom Gegner aus (Spieler blockiert nicht das Ziel).
	var dist: Dictionary = {}
	dist[_e_pos] = 0
	var frontier: Array = [_e_pos]
	while not frontier.is_empty():
		var cur: Vector2i = frontier.pop_front()
		for dx in [-1, 0, 1]:
			for dy in [-1, 0, 1]:
				if dx == 0 and dy == 0:
					continue
				if dx != 0 and dy != 0:
					continue
				var n := Vector2i(cur.x + dx, cur.y + dy)
				if n.x < 0 or n.x >= GRID_COLS or n.y < 0 or n.y >= GRID_ROWS:
					continue
				if n == _p_pos:
					continue
				if dist.has(n):
					continue
				dist[n] = int(dist[cur]) + 1
				frontier.append(n)
	# Zielsuche: adjazentes Feld zum Spieler mit min dist
	var best := Vector2i(-1, -1)
	var best_d := 9999
	for dx in [-1, 0, 1]:
		for dy in [-1, 0, 1]:
			if dx == 0 and dy == 0:
				continue
			if dx != 0 and dy != 0:
				continue
			var n := Vector2i(_p_pos.x + dx, _p_pos.y + dy)
			if n == _e_pos:
				best = n
				best_d = 0
				break
			if dist.has(n):
				var d: int = int(dist[n])
				if d <= UNIT_SPEED and d < best_d:
					best_d = d
					best = n
	if best.x >= 0:
		_e_pos = best
		if _is_adjacent(_e_pos, _p_pos):
			_resolve_attack(false)
	else:
		# Nicht in Reichweite -> einen Schritt Richtung Spieler
		var step := _e_pos
		var step_d: int = 9999
		for dx in [-1, 0, 1]:
			for dy in [-1, 0, 1]:
				if dx == 0 and dy == 0:
					continue
				if dx != 0 and dy != 0:
					continue
				var n := Vector2i(_e_pos.x + dx, _e_pos.y + dy)
				if n.x < 0 or n.x >= GRID_COLS or n.y < 0 or n.y >= GRID_ROWS:
					continue
				if n == _p_pos:
					continue
				var d: int = abs(n.x - _p_pos.x) + abs(n.y - _p_pos.y)
				if d < step_d:
					step_d = d
					step = n
		_e_pos = step
	_end_enemy_turn()


func _end_enemy_turn() -> void:
	if _check_end():
		return
	_phase = PHASE_PLAYER
	_round += 1
	_p_retaliated = false
	_e_retaliated = false
	_last_action_text = "Dein Zug."
	_refresh_reachable()
	_refresh_texts()
	if _grid_area != null:
		_grid_area.queue_redraw()


# --- Kampfmechanik ---

func _resolve_attack(player_attacks: bool) -> void:
	var att_count: int
	var att_att: int
	var def_def: int
	var att_name: String
	var def_name: String
	if player_attacks:
		att_count = _p_count
		att_att = UNIT_ATT + _player_bonus
		def_def = UNIT_DEF
		att_name = _player_name
		def_name = _enemy_name
	else:
		att_count = _e_count
		att_att = UNIT_ATT
		def_def = UNIT_DEF + _player_bonus
		att_name = _enemy_name
		def_name = _player_name
	var dmg: int = _compute_damage(att_count, att_att, def_def)
	var killed_before: int
	if player_attacks:
		killed_before = _e_count
		_apply_damage_to_enemy(dmg)
		_last_action_text = "%s greift %s an: %d Schaden, %d getoetet." % [
			att_name, def_name, dmg, killed_before - _e_count]
	else:
		killed_before = _p_count
		_apply_damage_to_player(dmg)
		_last_action_text = "%s greift %s an: %d Schaden, %d getoetet." % [
			att_name, def_name, dmg, killed_before - _p_count]

	# Retaliation: Verteidiger schlaegt einmal pro Runde zurueck (halb).
	if player_attacks:
		if _e_count > 0 and not _e_retaliated:
			_e_retaliated = true
			var rdmg: int = int(_compute_damage(_e_count, UNIT_ATT, UNIT_DEF + _player_bonus) / 2)
			if rdmg > 0:
				var kb: int = _p_count
				_apply_damage_to_player(rdmg)
				_last_action_text += "  Konter: %d Schaden, %d gefallen." % [rdmg, kb - _p_count]
	else:
		if _p_count > 0 and not _p_retaliated:
			_p_retaliated = true
			var rdmg2: int = int(_compute_damage(_p_count, UNIT_ATT + _player_bonus, UNIT_DEF) / 2)
			if rdmg2 > 0:
				var kb2: int = _e_count
				_apply_damage_to_enemy(rdmg2)
				_last_action_text += "  Konter: %d Schaden, %d gefallen." % [rdmg2, kb2 - _e_count]


func _compute_damage(count: int, att: int, def_val: int) -> int:
	if count <= 0:
		return 0
	var base: int = _rng.randi_range(UNIT_DMG_MIN, UNIT_DMG_MAX)
	var stack_dmg: float = float(base * count)
	var diff: int = att - def_val
	var mod: float = 1.0
	if diff > 0:
		mod = 1.0 + min(3.0, 0.05 * float(diff))
	elif diff < 0:
		mod = max(0.3, 1.0 + 0.025 * float(diff))
	return int(max(1.0, stack_dmg * mod))


func _apply_damage_to_enemy(dmg: int) -> void:
	if dmg <= 0 or _e_count <= 0:
		return
	var total: int = (_e_count - 1) * UNIT_HP + _e_top_hp - dmg
	if total <= 0:
		_e_count = 0
		_e_top_hp = 0
		return
	_e_count = int((total - 1) / UNIT_HP) + 1
	var rem: int = total % UNIT_HP
	_e_top_hp = UNIT_HP if rem == 0 else rem


func _apply_damage_to_player(dmg: int) -> void:
	if dmg <= 0 or _p_count <= 0:
		return
	var total: int = (_p_count - 1) * UNIT_HP + _p_top_hp - dmg
	if total <= 0:
		_p_count = 0
		_p_top_hp = 0
		return
	_p_count = int((total - 1) / UNIT_HP) + 1
	var rem: int = total % UNIT_HP
	_p_top_hp = UNIT_HP if rem == 0 else rem


func _check_end() -> bool:
	if _finished:
		return true
	if _p_count <= 0 and _e_count <= 0:
		_finished = true
		_phase = PHASE_OVER
		battle_finished.emit({"outcome": "defeat", "casualties": _player_count_start})
		return true
	if _p_count <= 0:
		_finished = true
		_phase = PHASE_OVER
		battle_finished.emit({"outcome": "defeat", "casualties": _player_count_start})
		return true
	if _e_count <= 0:
		_finished = true
		_phase = PHASE_OVER
		var cas: int = max(0, _player_count_start - _p_count)
		battle_finished.emit({"outcome": "victory", "casualties": cas})
		return true
	return false
