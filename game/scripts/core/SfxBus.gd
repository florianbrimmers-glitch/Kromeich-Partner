extends RefCounted

# Statische Fassade vor dem Sfx-Autoload (M11).
#
# WARUM DIESE SCHICHT: Autoloads werden bei `godot --script tools/x.gd`
# NICHT instanziiert. Ein direktes `Sfx.play(...)` im Screen scheitert dort
# zur Laufzeit - und ein Laufzeitfehler bricht in GDScript nur die
# betroffene Funktion ab. Beim ersten Anlauf hingen dadurch zwei Suiten im
# Timeout, weil die Testfunktion mitten im Ablauf abbrach und `quit()` nie
# erreicht wurde. Das war schwer zu sehen: die Suiten waren nicht rot,
# sondern still.
#
# Alle Screens rufen deshalb `Sound.play("...")` ueber diesen Umweg. Fehlt
# der Autoload, passiert einfach nichts.
#
# Eingebunden per `preload` wie die anderen core-Module (kein class_name,
# Android-Export-Vorsicht).

const AUTOLOAD_NAME := "Sfx"


static func bus() -> Node:
	var loop := Engine.get_main_loop()
	if loop is SceneTree:
		return (loop as SceneTree).root.get_node_or_null(AUTOLOAD_NAME)
	return null


# Spielt ein Geraeusch. Rueckgabe false heisst: kein Autoload da (Tools-
# Skript), Datei fehlt, oder stumm geschaltet.
static func play(name: String) -> bool:
	var b: Node = bus()
	if b == null:
		return false
	return bool(b.call("play", name))


static func available() -> bool:
	return bus() != null


static func set_enabled(on: bool) -> void:
	var b: Node = bus()
	if b != null:
		b.set("enabled", on)


static func toggle() -> bool:
	var b: Node = bus()
	if b == null:
		return false
	return bool(b.call("toggle"))


static func play_count(name: String) -> int:
	var b: Node = bus()
	if b == null:
		return 0
	return int(b.call("play_count", name))
