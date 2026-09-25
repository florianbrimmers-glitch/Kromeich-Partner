extends RefCounted

# Das Anleitungs-Panel (It. 46) - EIN Bauplan fuer beide Aufrufer:
# Titelschirm (vor dem Spiel) und Weltkarte (mitten im Spiel).
#
# Der Text kommt aus core/Manual.gd, die Zahlen aus den Konstanten des
# Aufrufers. Dieses Modul preloadet KEINEN Screen - sonst gaebe es einen
# Preload-Kreis mit dem WorldMapScreen.

const Manual := preload("res://scripts/core/Manual.gd")

const W := 1000
const H := 1280
const FONT_TITLE := 40
const FONT_HEAD := 30
const FONT_BODY := 24


static func build(parent: Control, n: Dictionary) -> Panel:
	var panel := Panel.new()
	panel.visible = false
	panel.anchor_left = 0.5
	panel.anchor_top = 0.5
	panel.anchor_right = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -W / 2
	panel.offset_top = -H / 2
	panel.offset_right = W / 2
	panel.offset_bottom = H / 2
	parent.add_child(panel)

	var bg := ColorRect.new()
	bg.color = Color(0.07, 0.08, 0.11, 1.0)
	bg.anchor_right = 1.0
	bg.anchor_bottom = 1.0
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(bg)

	var vb := VBoxContainer.new()
	vb.anchor_right = 1.0
	vb.anchor_bottom = 1.0
	vb.offset_left = 28
	vb.offset_top = 28
	vb.offset_right = -28
	vb.offset_bottom = -28
	vb.add_theme_constant_override("separation", 14)
	panel.add_child(vb)

	var title := Label.new()
	title.text = "Anleitung"
	title.add_theme_font_size_override("font_size", FONT_TITLE)
	title.add_theme_color_override("font_color", Color(0.95, 0.85, 0.40))
	vb.add_child(title)

	# Scrollbar: die Anleitung ist laenger als jedes Handy hoch ist.
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	vb.add_child(scroll)

	var list := VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list.add_theme_constant_override("separation", 18)
	scroll.add_child(list)

	for sec in Manual.sections(n):
		var head := Label.new()
		head.text = String(sec[0])
		head.add_theme_font_size_override("font_size", FONT_HEAD)
		head.add_theme_color_override("font_color", Color(0.70, 0.85, 1.0))
		list.add_child(head)
		var body := Label.new()
		body.text = String(sec[1])
		body.add_theme_font_size_override("font_size", FONT_BODY)
		body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		list.add_child(body)

	var close_btn := Button.new()
	close_btn.text = "Zurueck"
	close_btn.custom_minimum_size = Vector2(0, 96)
	close_btn.add_theme_font_size_override("font_size", FONT_HEAD)
	close_btn.pressed.connect(func() -> void: panel.visible = false)
	vb.add_child(close_btn)
	return panel
