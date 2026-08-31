extends SceneTree

# Headless-Tests fuer Titelschirm und Anleitung (It. 46):
#
#   godot --headless --path game/ --script tools/test_menu.gd
#
# Abgedeckt:
#   1. Main.tscn hat die Knoepfe, die ein Spieler braucht - und NICHT den
#      alten Entwickler-Knopf "Kampf-Test"
#   2. Der Untertitel stellt das Spiel nicht mehr als "MVP" vor
#   3. Die Anleitung enthaelt die ECHTEN Zahlen aus den Konstanten. Das ist
#      der eigentliche Grund fuer diese Suite: eine Anleitung, die ihre
#      Zahlen selbst schreibt, ist nach der ersten Balance-Aenderung eine
#      Luege - und der SPIELER liest sie.
#   4. Das Anleitungs-Panel passt in Geraetegroesse auf den Schirm

const Manual := preload("res://scripts/core/Manual.gd")
const WMS := preload("res://scripts/ui/WorldMapScreen.gd")
const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")
const Spl := preload("res://scripts/core/HeroSpells.gd")
const SaveLib := preload("res://scripts/core/SaveManager.gd")

const DEVICE_W := 1080
const DEVICE_H := 1920

var _fails: int = 0
var _done: Array = []


func _init() -> void:
	await _test_menu()
	_test_manual_numbers()
	await _test_help_panel()
	await _test_worldmap_help()

	var missing: Array = []
	for m in get_method_list():
		var mn: String = String(m["name"])
		if mn.begins_with("_test") and not _done.has(mn):
			missing.append(mn)
	_check(missing.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)" % str(missing))

	print("")
	if _fails == 0:
		print("Menue-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Menue-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_menu() -> void:
	print("== Titelschirm ==")
	var scene := load("res://scenes/Main.tscn") as PackedScene
	_check(scene != null, "Main.tscn laedt")
	var mc = scene.instantiate()
	root.add_child(mc)
	# _ready laeuft erst im naechsten Frame (Falle aus It. 42/43).
	await process_frame

	var labels: Array = []
	for ch in mc.get_children():
		if ch is Button:
			labels.append(String((ch as Button).text))
	_check(labels.has("Neues Spiel"), "Knopf 'Neues Spiel' da (%s)" % str(labels))
	_check(labels.has("Anleitung"), "Knopf 'Anleitung' da")
	_check(not labels.has("Kampf-Test"),
		"der Entwickler-Knopf 'Kampf-Test' ist weg")
	# Und die Szene, in die er fuehrte, auch - sonst bleibt toter Code
	# liegen, den niemand mehr prueft.
	_check(not ResourceLoader.exists("res://scenes/Battle.tscn"),
		"scenes/Battle.tscn ist geloescht")
	_check(not FileAccess.file_exists("res://scripts/ui/BattleScreen.gd"),
		"scripts/ui/BattleScreen.gd ist geloescht")

	var sub := mc.get_node_or_null(^"Subtitle") as Label
	_check(sub != null, "Untertitel vorhanden")
	if sub != null:
		_check(not sub.text.contains("MVP"),
			"der Untertitel nennt das Spiel nicht mehr 'MVP' ('%s')" % sub.text)
		_check(sub.text.length() > 8, "und sagt etwas ueber das Spiel")

	mc.queue_free()
	await process_frame
	_done.append("_test_menu")


func _test_manual_numbers() -> void:
	print("")
	print("== Anleitung: die Zahlen stimmen ==")
	# Die Zahlen kommen aus MainController.manual_numbers() - genau der
	# Weg, den das Spiel geht.
	var n: Dictionary = _numbers_from_main()
	var secs: Array = Manual.sections(n)
	_check(secs.size() >= 6, "%d Abschnitte" % secs.size())
	var empty: Array = []
	for sec in secs:
		if String(sec[0]).is_empty() or String(sec[1]).length() < 20:
			empty.append(String(sec[0]))
	_check(empty.is_empty(), "jeder Abschnitt hat Titel und Inhalt (%s)" % str(empty))

	var txt: String = Manual.text(n)
	# KEIN Fragezeichen: Manual._v setzt eines, wenn ein Schluessel fehlt.
	# Lieber sichtbar unvollstaendig als still falsch - und hier faellt es
	# auf.
	_check(not txt.contains("?"),
		"keine fehlende Zahl in der Anleitung (Platzhalter '?')")

	# Jede Zahl muss die aus der Konstante sein.
	var pairs: Array = [
		["max_heroes", WMS.MAX_HEROES],
		["hire_gold", int((WMS.HERO_HIRE_COST as Dictionary).get("gold", 0))],
		["grace_days", WMS.LOSS_GRACE_DAYS],
		["army_slots", Hero.MAX_ARMY_SLOTS],
		["grid_cols", TBS.GRID_COLS],
		["grid_rows", TBS.GRID_ROWS],
		["casts", Spl.CASTS_PER_ROUND],
	]
	var wrong: Array = []
	for pr in pairs:
		var key: String = String(pr[0])
		var val: int = int(pr[1])
		if int(n.get(key, -1)) != val:
			wrong.append("%s: %s statt %d" % [key, str(n.get(key, "fehlt")), val])
		elif not txt.contains(str(val)):
			wrong.append("%s (%d) steht nicht im Text" % [key, val])
	_check(wrong.is_empty(), "jede Zahl kommt aus ihrer Konstante (%s)" % str(wrong))

	# Gegenprobe: eine FEHLENDE Zahl muss auffallen, sonst prueft der
	# Platzhalter-Check nichts.
	var broken: Dictionary = n.duplicate()
	broken.erase("max_heroes")
	_check(Manual.text(broken).contains("?"),
		"eine fehlende Zahl wird als '?' sichtbar (Gegenprobe)")
	_done.append("_test_manual_numbers")


func _numbers_from_main() -> Dictionary:
	var scene := load("res://scenes/Main.tscn") as PackedScene
	var mc = scene.instantiate()
	var n: Dictionary = mc.manual_numbers()
	mc.free()
	return n


func _test_help_panel() -> void:
	print("")
	print("== Anleitungs-Panel in Geraetegroesse ==")
	var scene := load("res://scenes/Main.tscn") as PackedScene
	var mc = scene.instantiate()
	root.add_child(mc)
	await process_frame
	mc.set_anchors_preset(Control.PRESET_TOP_LEFT)
	mc.size = Vector2(DEVICE_W, DEVICE_H)
	await process_frame
	mc.call("_on_help_pressed")
	await process_frame
	await process_frame

	var panel: Panel = mc.get("_help_panel")
	_check(panel != null and panel.visible, "Panel steht")
	if panel != null:
		var screen := Rect2(Vector2.ZERO, Vector2(DEVICE_W, DEVICE_H))
		_check(screen.encloses(panel.get_rect()),
			"Panel liegt ganz auf dem Schirm %s" % str(panel.get_rect()))
		var closer: Button = null
		var heads: int = 0
		for c in panel.get_children():
			if not (c is VBoxContainer):
				continue
			for c2 in (c as VBoxContainer).get_children():
				if c2 is Button:
					closer = c2 as Button
				if c2 is ScrollContainer:
					for c3 in (c2 as ScrollContainer).get_children():
						if c3 is VBoxContainer:
							heads = (c3 as VBoxContainer).get_child_count()
		_check(closer != null and screen.encloses(closer.get_global_rect()),
			"der Zurueck-Knopf ist erreichbar")
		# Zwei Knoten je Abschnitt (Ueberschrift + Text).
		_check(heads == Manual.sections(mc.manual_numbers()).size() * 2,
			"jeder Abschnitt ist gezeichnet (%d Knoten)" % heads)

	mc.queue_free()
	await process_frame
	_done.append("_test_help_panel")
# Die Anleitung muss AUCH mitten im Spiel erreichbar sein - und der Platz,
# auf dem sie sitzt, trug bis It. 46 einen Knopf, der das laufende Spiel
# ohne Rueckfrage weggeworfen hat.
func _test_worldmap_help() -> void:
	print("")
	print("== Anleitung auf der Weltkarte ==")
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 321, 1)
	await process_frame

	var labels: Array = []
	for ch in (wm.get_node(^"BottomBar") as Control).get_children():
		if ch is Button:
			labels.append(String((ch as Button).text))
	_check(labels.has("Anleitung"), "Knopf 'Anleitung' in der Fussleiste (%s)" % str(labels))
	_check(not labels.has("Neue Karte"),
		"der Knopf 'Neue Karte' ist weg - er hat ohne Rueckfrage neu gestartet")
	_check(not wm.has_method("_on_reroll"), "und die Funktion dahinter auch")

	wm.call("_on_help")
	await process_frame
	var panel: Panel = wm.get("_help_panel")
	_check(panel != null and panel.visible, "Panel oeffnet sich")

	# ZURUECK MUSS SICHERN. Vorher war alles seit dem letzten Tagesende
	# weg, wenn man kurz ins Menue ging.
	SaveLib.delete_autosave()
	_check(not SaveLib.has_autosave(), "kein Spielstand als Ausgangslage")
	wm.call("_save_now")
	_check(SaveLib.has_autosave(), "_save_now schreibt einen Spielstand")

	# Nach einer Niederlage darf NICHT mehr gespeichert werden - dort ist
	# der Stand absichtlich geloescht.
	SaveLib.delete_autosave()
	wm.set("_game_lost", true)
	wm.call("_save_now")
	_check(not SaveLib.has_autosave(),
		"nach der Niederlage wird nicht mehr gespeichert")

	wm.queue_free()
	await process_frame
	_done.append("_test_worldmap_help")
