extends Control

# Minimaler GDScript-Startbildschirm ohne C#, um zu testen ob der
# Android-Crash am .NET-Runtime-Laden liegt. Wenn diese Szene startet,
# wissen wir: Godot selbst laeuft - nur der C#-Teil crashed.

func _ready() -> void:
	var lbl := $Label as Label
	var info := "Kromeich Heroes - Safe Mode\n"
	info += "Godot startet OK\n"
	info += "OS: %s / %s\n" % [OS.get_name(), OS.get_model_name()]
	info += "Renderer: %s\n" % RenderingServer.get_rendering_device().get_device_name() if RenderingServer.get_rendering_device() else "Renderer: (kein RenderingDevice)"
	info += "API Level: %d\n" % OS.get_version()
	info += "Touch: %s" % str(DisplayServer.is_touchscreen_available())
	lbl.text = info
	print("[SafeMode] _ready OK")
