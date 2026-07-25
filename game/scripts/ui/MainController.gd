extends Control

# Titel-Screen. Einstiegspunkte:
# - Fortsetzen: laedt den Autosave (nur sichtbar, wenn einer existiert)
# - Weltkarte: neues Spiel
# - Kampf-Test: Auto-Battle-Replay zur Verifikation der Battle-Engine

const SaveLib := preload("res://scripts/core/SaveManager.gd")

# Muss zur Reihenfolge in WorldMapScreen.FACTION_NAMES passen.
const FACTIONS := ["Waldvolk", "Menschen", "Totenreich", "Orks"]
const FACTION_COLORS := [
	Color(0.45, 0.85, 0.45),
	Color(0.95, 0.85, 0.35),
	Color(0.70, 0.45, 0.90),
	Color(0.95, 0.35, 0.30),
]

@export var worldmap_button_path: NodePath = ^"WorldMapBtn"
@export var battle_button_path: NodePath   = ^"BattleBtn"

var _new_game_panel: Panel
var _seed_edit: LineEdit

func _ready() -> void:
	var wbtn := get_node_or_null(worldmap_button_path) as Button
	if wbtn != null:
		wbtn.pressed.connect(_on_worldmap_pressed)
	var bbtn := get_node_or_null(battle_button_path) as Button
	if bbtn != null:
		bbtn.pressed.connect(_on_battle_pressed)
	var sub := get_node_or_null(^"Subtitle") as Label
	if sub != null:
		sub.text = "MVP - %s / %s" % [OS.get_name(), OS.get_model_name()]
	# "Fortsetzen" dynamisch ueber dem Weltkarte-Button einfuegen, damit
	# die .tscn unveraendert bleibt. Nur zeigen, wenn ein Autosave existiert.
	if SaveLib.has_autosave() and wbtn != null:
		var cont := Button.new()
		cont.text = "Fortsetzen"
		cont.custom_minimum_size = wbtn.custom_minimum_size
		cont.anchor_left = wbtn.anchor_left
		cont.anchor_top = wbtn.anchor_top
		cont.anchor_right = wbtn.anchor_right
		cont.anchor_bottom = wbtn.anchor_bottom
		cont.offset_left = wbtn.offset_left
		cont.offset_right = wbtn.offset_right
		var h: float = max(wbtn.size.y, wbtn.custom_minimum_size.y)
		cont.offset_top = wbtn.offset_top - h - 24.0
		cont.offset_bottom = wbtn.offset_bottom - h - 24.0
		cont.pressed.connect(_on_continue_pressed)
		wbtn.get_parent().add_child(cont)

func _on_continue_pressed() -> void:
	var save: Dictionary = SaveLib.read_save()
	if save.is_empty():
		return
	var sm := get_node_or_null(^"/root/SaveManager")
	if sm != null:
		sm.pending_load = save
	get_tree().change_scene_to_file("res://scenes/WorldMap.tscn")

func _on_worldmap_pressed() -> void:
	# "Weltkarte" oeffnet jetzt den Neues-Spiel-Dialog (Fraktion + Seed)
	# statt sofort zu starten.
	if _new_game_panel == null:
		_build_new_game_panel()
	_new_game_panel.visible = true

func _on_battle_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/Battle.tscn")


# --- Neues-Spiel-Dialog (M2): Fraktionswahl + Seed ---

func _build_new_game_panel() -> void:
	var panel := Panel.new()
	panel.visible = false
	panel.anchor_left = 0.5
	panel.anchor_top = 0.5
	panel.anchor_right = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -420
	panel.offset_top = -560
	panel.offset_right = 420
	panel.offset_bottom = 560
	add_child(panel)
	_new_game_panel = panel

	var bg := ColorRect.new()
	bg.color = Color(0.08, 0.09, 0.12, 1.0)
	bg.anchor_right = 1.0
	bg.anchor_bottom = 1.0
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(bg)

	var vb := VBoxContainer.new()
	vb.anchor_right = 1.0
	vb.anchor_bottom = 1.0
	vb.offset_left = 40
	vb.offset_top = 40
	vb.offset_right = -40
	vb.offset_bottom = -40
	vb.add_theme_constant_override("separation", 24)
	panel.add_child(vb)

	var title := Label.new()
	title.text = "Neues Spiel"
	title.add_theme_font_size_override("font_size", 44)
	vb.add_child(title)

	var flabel := Label.new()
	flabel.text = "Fraktion waehlen:"
	flabel.add_theme_font_size_override("font_size", 30)
	vb.add_child(flabel)

	for fid in range(FACTIONS.size()):
		var fbtn := Button.new()
		fbtn.text = String(FACTIONS[fid])
		fbtn.custom_minimum_size = Vector2(0, 110)
		fbtn.add_theme_font_size_override("font_size", 34)
		fbtn.add_theme_color_override("font_color", FACTION_COLORS[fid])
		fbtn.pressed.connect(_on_faction_chosen.bind(fid))
		vb.add_child(fbtn)

	var slabel := Label.new()
	slabel.text = "Karten-Seed (leer = Zufall):"
	slabel.add_theme_font_size_override("font_size", 28)
	vb.add_child(slabel)

	_seed_edit = LineEdit.new()
	_seed_edit.placeholder_text = "z.B. 1337"
	_seed_edit.custom_minimum_size = Vector2(0, 90)
	_seed_edit.add_theme_font_size_override("font_size", 32)
	# Nur Ziffern sinnvoll; Godot-virtuelle Tastatur auf Zahlen stellen.
	_seed_edit.virtual_keyboard_type = LineEdit.KEYBOARD_TYPE_NUMBER
	vb.add_child(_seed_edit)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(spacer)

	var close_btn := Button.new()
	close_btn.text = "Zurueck"
	close_btn.custom_minimum_size = Vector2(0, 100)
	close_btn.add_theme_font_size_override("font_size", 30)
	close_btn.pressed.connect(func() -> void: _new_game_panel.visible = false)
	vb.add_child(close_btn)


func _on_faction_chosen(fid: int) -> void:
	var seed_val: int = 0
	var txt: String = _seed_edit.text.strip_edges() if _seed_edit != null else ""
	if txt.is_valid_int():
		seed_val = txt.to_int()
	else:
		# Zufalls-Seed aus der Uhr; positiv halten fuer Anzeige/Eingabe.
		seed_val = int(Time.get_ticks_usec()) % 1000000000
		if seed_val <= 0:
			seed_val = 42
	var sm := get_node_or_null(^"/root/SaveManager")
	if sm != null:
		sm.pending_new_game = {"seed": seed_val, "faction": fid}
	get_tree().change_scene_to_file("res://scenes/WorldMap.tscn")
