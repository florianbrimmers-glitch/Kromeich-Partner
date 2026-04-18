extends Control

# Minimaler GDScript-Startbildschirm + C#-Probe-Kind-Node testet ob .NET
# auf dem Geraet ueberhaupt laedt. Siehe CSharpProbe.cs.

func _ready() -> void:
	var lbl := $Label as Label
	var info := "Kromeich Heroes - Safe Mode\n"
	info += "Godot startet OK\n"
	info += "OS: %s / %s\n" % [OS.get_name(), OS.get_model_name()]
	info += "Touch: %s" % str(DisplayServer.is_touchscreen_available())
	lbl.text = info
	print("[SafeMode] _ready OK")
