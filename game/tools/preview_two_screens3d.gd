extends SceneTree

# ZWEI SCHIRME GLEICHZEITIG (It. 68).
#
#   xvfb-run -a -s "-screen 0 720x1280x24" godot --path game/ \
#       --resolution 720x1280 --script tools/preview_two_screens3d.gd
#
# WARUM ES DIESES WERKZEUG GIBT: jede andere Vorschau baut genau EINEN
# Schirm. Im Spiel bleibt die Weltkarte aber bestehen, waehrend Stadt oder
# Kampf darueber aufgehen - und genau dazwischen lag der Fehler, den der
# Nutzer auf seinem Handy gefunden hat und den hier nichts sehen konnte:
# alle drei raeumlichen Ansichten teilten sich eine 3D-Welt, also sah jede
# Kamera die Geometrie der anderen und jedes Licht beschien alles.
#
# Ein Fehler ZWISCHEN zwei Schirmen ist fuer ein Werkzeug, das immer nur
# einen baut, unsichtbar. Dieses hier baut zwei.

const CS := preload("res://scripts/ui/CityScreen.gd")


func _init() -> void:
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 4711, 1)
	await process_frame
	wm.call("_toggle_view3d")
	var h = wm.call("get", "_hero")
	if h != null:
		wm.call("_center_view_on", h.position)
	for i in range(4):
		await process_frame

	# Der Stadtschirm entsteht UND baut seine raeumliche Ansicht auf -
	# genau wie im Spiel, wenn man eine Stadt betreten und wieder
	# geschlossen hat. Danach wird die Karte erneut gezeichnet.
	var cs = CS.new()
	root.add_child(cs)
	await process_frame
	cs.open({
		"city": {"faction": 1, "buildings": ["markt", "kaserne"],
			"garrison": []},
		"buildings": [
			{"id": "markt", "name": "Markt", "cost": {"gold": 1}, "effect": "x"},
			{"id": "kaserne", "name": "Kaserne", "cost": {"gold": 1}, "effect": "x"},
		],
		"faction_names": ["Waldvolk", "Menschen", "Totenreich", "Orks"],
		"faction_colors": [Color.GREEN, Color.YELLOW, Color.PURPLE, Color.RED],
		"wallet": Wallet.new(), "own_city": true,
	})
	await process_frame
	cs.call("_toggle_view3d")
	for i in range(4):
		await process_frame
	var e1: int = root.get_texture().get_image().save_png(
		"user://zwei-stadt.png")

	# Stadt schliessen, Karte wieder sichtbar: JETZT muss die Karte frei
	# von Stadtgeometrie sein.
	cs.visible = false
	wm.call("_request_redraw")
	for i in range(5):
		await process_frame
	var e2: int = root.get_texture().get_image().save_png(
		"user://zwei-karte.png")

	var mv = wm.get("_map3d")
	var cv = cs.get("_city3d")
	print("Welten getrennt: %s | Stadt-Bild err=%d, Karten-Bild err=%d -> %s"
		% [str((mv as Node3D).get_world_3d() != (cv as Node3D).get_world_3d()),
			e1, e2,
			ProjectSettings.globalize_path("user://zwei-karte.png")])
	quit(0)
