extends Control

# Titel-Screen. Einstiegspunkte:
# - Fortsetzen: laedt den Autosave (nur sichtbar, wenn einer existiert)
# - Weltkarte: neues Spiel
# - Kampf-Test: Auto-Battle-Replay zur Verifikation der Battle-Engine

const SaveLib := preload("res://scripts/core/SaveManager.gd")

@export var worldmap_button_path: NodePath = ^"WorldMapBtn"
@export var battle_button_path: NodePath   = ^"BattleBtn"

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
	get_tree().change_scene_to_file("res://scenes/WorldMap.tscn")

func _on_battle_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/Battle.tscn")
