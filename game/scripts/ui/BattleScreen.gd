extends Control

# Auto-Battle-Replay. GDScript-Port von BattleScreen.cs.
# Simuliert eine Schlacht aus DemoArmy und spielt das Event-Log im
# 0.4s-Takt ab, updated die Stack-Counter.

@export var side0_container_path: NodePath = ^"VBox/Side0Panel/Side0Stacks"
@export var side1_container_path: NodePath = ^"VBox/Side1Panel/Side1Stacks"
@export var side0_label_path: NodePath    = ^"VBox/Side0Panel/Side0Title"
@export var side1_label_path: NodePath    = ^"VBox/Side1Panel/Side1Title"
@export var log_list_path: NodePath        = ^"VBox/LogScroll/LogList"
@export var log_scroll_path: NodePath      = ^"VBox/LogScroll"
@export var status_label_path: NodePath    = ^"VBox/StatusLabel"
@export var rematch_button_path: NodePath  = ^"VBox/ButtonRow/RematchBtn"
@export var back_button_path: NodePath     = ^"VBox/ButtonRow/BackBtn"

const STEP_INTERVAL := 0.4

var _stack_labels: Dictionary = {}
var _events: Array = []
var _event_index: int = 0
var _accum: float = 0.0
var _seed: int = 42
var _side0: Array = []
var _side1: Array = []

func _set_status(s: String) -> void:
	var lbl := get_node_or_null(status_label_path) as Label
	if lbl != null:
		lbl.text = s
	print("[BattleScreen] " + s)

func _ready() -> void:
	_set_status("STEP 1: _ready")
	var rbtn := get_node_or_null(rematch_button_path) as Button
	if rbtn == null:
		_set_status("ERR: RematchBtn nicht gefunden unter " + str(rematch_button_path))
		return
	rbtn.pressed.connect(_on_rematch)
	var bbtn := get_node_or_null(back_button_path) as Button
	if bbtn == null:
		_set_status("ERR: BackBtn nicht gefunden unter " + str(back_button_path))
		return
	bbtn.pressed.connect(_on_back)
	_set_status("STEP 2: Buttons verdrahtet")
	_start_battle(_seed)

func _start_battle(seed: int) -> void:
	_set_status("STEP 3: start_battle seed=%d" % seed)
	_event_index = 0
	_accum = 0.0
	_clear_children(get_node(side0_container_path))
	_clear_children(get_node(side1_container_path))
	_clear_children(get_node(log_list_path))
	_stack_labels.clear()

	_set_status("STEP 4: lade units.json")
	var units_dict: Dictionary = {}
	var f := FileAccess.open("res://data/units.json", FileAccess.READ)
	if f == null:
		_set_status("ERR: units.json kann nicht geoeffnet werden. res:// Listing: " + str(DirAccess.get_files_at("res://data")))
		return
	var raw := f.get_as_text()
	f.close()
	_set_status("STEP 5: units.json gelesen (%d Zeichen)" % raw.length())
	var parsed: Variant = JSON.parse_string(raw)
	if not parsed is Dictionary:
		_set_status("ERR: JSON.parse_string Ergebnis ist " + str(typeof(parsed)))
		return
	var units_arr: Array = parsed["units"]
	_set_status("STEP 6: %d Units geparsed" % units_arr.size())
	for u in units_arr:
		units_dict[u["id"]] = u

	_set_status("STEP 7: baue Demo-Armee")
	_side0 = [
		BattleStack.new(units_dict["men_angel"],    2,  0),
		BattleStack.new(units_dict["men_cavalier"], 6,  0),
		BattleStack.new(units_dict["men_crusader"], 14, 0),
		BattleStack.new(units_dict["men_archer"],   20, 0),
		BattleStack.new(units_dict["men_spearman"], 40, 0),
	]
	_side1 = [
		BattleStack.new(units_dict["ork_behemoth"], 2,  1),
		BattleStack.new(units_dict["ork_cyclops"],  4,  1),
		BattleStack.new(units_dict["ork_ogre"],     8,  1),
		BattleStack.new(units_dict["ork_orc"],      20, 1),
		BattleStack.new(units_dict["ork_goblin"],   60, 1),
	]

	(get_node(side0_label_path) as Label).text = "Menschen"
	(get_node(side1_label_path) as Label).text = "Orkstaemme"
	_build_stack_row(_side0, get_node(side0_container_path))
	_build_stack_row(_side1, get_node(side1_container_path))

	_set_status("STEP 8: simuliere")
	var sim0 := _clone_stacks(_side0, 0)
	var sim1 := _clone_stacks(_side1, 1)
	var result := Battle.simulate(sim0, sim1, DeterministicRng.new(seed))
	_events = result["events"]

	_set_status("Seed %d  |  Runden %d  |  %s  |  Events %d" % [
		seed, result["turns"], _outcome_label(result["outcome"]), _events.size()
	])

func _process(delta: float) -> void:
	if _event_index >= _events.size():
		return
	_accum += delta
	while _accum >= STEP_INTERVAL and _event_index < _events.size():
		_accum -= STEP_INTERVAL
		_play_event(_events[_event_index])
		_event_index += 1

func _play_event(ev: Dictionary) -> void:
	_update_stack_count(ev["target_id"], ev["target_count_after"])
	var line := "R%d  %s  ->  %s   -%d (%d)" % [
		ev["turn"], ev["attacker_id"], ev["target_id"], ev["damage"], ev["target_count_after"]
	]
	_append_log_line(line)

func _append_log_line(text: String) -> void:
	var list := get_node(log_list_path)
	var lbl := Label.new()
	lbl.text = text
	lbl.add_theme_color_override("font_color", Color(0.85, 0.85, 0.9))
	list.add_child(lbl)
	var scroll := get_node_or_null(log_scroll_path) as ScrollContainer
	if scroll != null:
		scroll.set_deferred("scroll_vertical", 2147483647)

func _update_stack_count(unit_id: String, new_count: int) -> void:
	if not _stack_labels.has(unit_id):
		return
	var lbl: Label = _stack_labels[unit_id]
	lbl.text = "%s  x%d" % [_short_id(unit_id), new_count]
	if new_count <= 0:
		lbl.add_theme_color_override("font_color", Color(0.4, 0.2, 0.2))

func _build_stack_row(stacks: Array, host: Node) -> void:
	for s in stacks:
		var box := PanelContainer.new()
		box.custom_minimum_size = Vector2(180, 90)
		var inner := VBoxContainer.new()
		var name_lbl := Label.new()
		name_lbl.text = "%s  x%d" % [_short_id(s.unit["id"]), s.count]
		var meta_lbl := Label.new()
		meta_lbl.text = "Tier %d  HP %d" % [int(s.unit["tier"]), int(s.unit["stats"]["hp"])]
		meta_lbl.add_theme_color_override("font_color", Color(0.7, 0.7, 0.75))
		inner.add_child(name_lbl)
		inner.add_child(meta_lbl)
		box.add_child(inner)
		host.add_child(box)
		_stack_labels[s.unit["id"]] = name_lbl

func _clone_stacks(src: Array, side: int) -> Array:
	var out: Array = []
	for s in src:
		out.append(BattleStack.new(s.unit, s.count, side))
	return out

func _clear_children(n: Node) -> void:
	for c in n.get_children():
		c.queue_free()

func _short_id(id: String) -> String:
	var idx := id.find("_")
	return id if idx < 0 else id.substr(idx + 1)

func _outcome_label(o: int) -> String:
	match o:
		Battle.OUTCOME_SIDE0: return "Menschen gewinnen"
		Battle.OUTCOME_SIDE1: return "Orkstaemme gewinnen"
		_:                    return "Unentschieden"

func _on_rematch() -> void:
	_seed += 1
	_start_battle(_seed)

func _on_back() -> void:
	get_tree().change_scene_to_file("res://scenes/Main.tscn")
