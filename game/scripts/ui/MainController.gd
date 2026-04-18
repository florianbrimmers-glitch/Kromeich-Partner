extends Control

# Titel-Screen, GDScript-Port von MainController.cs.
# "Neues Spiel" wechselt zu Battle.tscn, "Fortsetzen" ist noch disabled.

@export var new_game_button_path: NodePath = ^"NewGameBtn"

func _ready() -> void:
	var btn := get_node_or_null(new_game_button_path) as Button
	if btn != null:
		btn.pressed.connect(_on_new_game_pressed)
	var sub := get_node_or_null(^"Subtitle") as Label
	if sub != null:
		sub.text = "MVP - %s / %s - Touch to play" % [OS.get_name(), OS.get_model_name()]

func _on_new_game_pressed() -> void:
	get_tree().change_scene_to_file("res://scenes/Battle.tscn")
