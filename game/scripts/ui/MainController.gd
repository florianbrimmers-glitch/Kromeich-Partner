extends Control

# Titel-Screen. Zwei Einstiegspunkte:
# - Weltkarte: der eigentliche Spielmodus (MVP Meilenstein 2)
# - Kampf-Test: Auto-Battle-Replay zur Verifikation der Battle-Engine

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

func _on_worldmap_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/WorldMap.tscn")

func _on_battle_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/Battle.tscn")
