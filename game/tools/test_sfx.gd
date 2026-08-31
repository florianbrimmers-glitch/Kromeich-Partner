extends SceneTree

# Headless-Tests fuer die Geraeusche (M11):
#
#   godot --headless --path game/ --script tools/test_sfx.gd
#
# Abgedeckt:
#   1. Vollstaendigkeit: jede in SOUND_NAMES erwartete WAV liegt da, laedt
#      als AudioStream und hat eine plausible Laenge
#   2. SfxBus: ohne Autoload ein stilles No-op (genau das ist der Grund,
#      warum die Fassade existiert), mit Autoload spielt es
#   3. Stummschalten wirkt
#   4. Kampf und Weltkarte loesen die richtigen Geraeusche aus
#
# Jede Test-Funktion setzt am Ende eine Marke - ein Laufzeitfehler bricht
# in GDScript nur die Funktion ab (Lehrgeld aus It. 24).

const Sound := preload("res://scripts/core/SfxBus.gd")
const SfxNode := preload("res://scripts/core/Sfx.gd")
const TBS := preload("res://scripts/ui/TacticalBattleScreen.gd")

# Muss zu tools/gen_sfx.py passen. Fehlt hier etwas, faellt es beim
# Verdrahten auf; fehlt dort etwas, faellt es hier auf.
const EXPECTED := [
	"ui_tap", "ui_back", "build", "recruit", "coin", "resource",
	"melee_hit", "arrow_shot", "arrow_hit", "spell_cast", "spell_hit",
	"heal", "death", "wall_break", "catapult", "level_up", "victory",
	"defeat", "day_end", "week_event",
]

var _fails: int = 0
var _done: Array = []


func _init() -> void:
	_test_files()
	await _test_bus()
	await _test_battle()
	await _test_worldmap()

	var expected_marks: Array = ["files", "bus", "battle", "worldmap"]
	var aborted: Array = []
	for name in expected_marks:
		if not _done.has(String(name)):
			aborted.append(String(name))
	_check(aborted.is_empty(),
		"jede Test-Funktion lief bis zum Ende durch (abgebrochen: %s)" % str(aborted))

	print("")
	if _fails == 0:
		print("Geraeusch-Tests: ALLE CHECKS GRUEN")
		quit(0)
	else:
		print("Geraeusch-Tests: %d CHECK(S) ROT" % _fails)
		quit(1)


func _check(cond: bool, msg: String) -> void:
	if not cond:
		_fails += 1
	print(("[OK]   " if cond else "[FAIL] ") + msg)


func _test_files() -> void:
	print("== Dateien ==")
	var missing: Array = []
	var unloadable: Array = []
	var too_short: Array = []
	var total_bytes: int = 0
	for name in EXPECTED:
		var path: String = "res://assets/sfx/%s.wav" % String(name)
		if not ResourceLoader.exists(path):
			missing.append(String(name))
			continue
		var st: AudioStream = load(path) as AudioStream
		if st == null:
			unloadable.append(String(name))
			continue
		# Laenge: unter 30 ms hoert man nur einen Knacks, ueber 2 s haelt es
		# das Spiel auf.
		var len_s: float = st.get_length()
		if len_s < 0.03 or len_s > 2.0:
			too_short.append("%s (%.3f s)" % [String(name), len_s])
		var f := FileAccess.open(path, FileAccess.READ)
		if f != null:
			total_bytes += f.get_length()
	_check(missing.is_empty(), "alle %d Geraeusche vorhanden (fehlen: %s)"
		% [EXPECTED.size(), str(missing)])
	_check(unloadable.is_empty(), "alle laden als AudioStream (%s)" % str(unloadable))
	_check(too_short.is_empty(), "alle in plausibler Laenge (%s)" % str(too_short))
	# Groesse im Blick behalten: die APK ist schon ueber 80 MB.
	_check(total_bytes < 2 * 1024 * 1024,
		"Gesamtgroesse unter 2 MB (ist %d KB)" % (total_bytes / 1024))
	print("        %d KB fuer %d Dateien" % [total_bytes / 1024, EXPECTED.size()])
	_done.append("files")


func _test_bus() -> void:
	print("")
	print("== SfxBus ==")
	# Genau das ist der Grund fuer die Fassade: bei "--script" gibt es
	# keinen Autoload, und ein direkter Aufruf wuerde die Testfunktion
	# abbrechen.
	_check(not Sound.available(),
		"ohne Autoload nicht verfuegbar (Tools-Skript-Fall)")
	_check(Sound.play("melee_hit") == false, "und play() ist ein stilles No-op")
	_check(Sound.play_count("melee_hit") == 0, "ohne Autoload wird nichts gezaehlt")
	_check(Sound.toggle() == false, "toggle() faellt ebenfalls weich aus")

	# Jetzt den Autoload von Hand einhaengen - so laeuft es im Spiel.
	var bus := SfxNode.new()
	bus.name = "Sfx"
	root.add_child(bus)
	await process_frame
	_check(Sound.available(), "mit eingehaengtem Knoten verfuegbar")
	_check(bus.get_child_count() == SfxNode.POOL_SIZE,
		"Player-Pool angelegt (%d von %d)" % [bus.get_child_count(), SfxNode.POOL_SIZE])

	bus.reset_counts()
	_check(Sound.play("melee_hit"), "play() liefert true")
	_check(Sound.play_count("melee_hit") == 1, "und zaehlt mit")

	# Fehlende Datei darf nicht abstuerzen.
	_check(Sound.play("gibt_es_nicht") == false, "unbekanntes Geraeusch ist harmlos")

	# Stumm: weiterhin gezaehlt (der Test will die AUFRUFE pruefen), aber
	# nicht gespielt.
	Sound.set_enabled(false)
	var before: int = Sound.play_count("coin")
	_check(Sound.play("coin") == false, "stumm spielt nicht")
	_check(Sound.play_count("coin") == before + 1, "zaehlt aber weiter")
	Sound.set_enabled(true)
	_check(Sound.play("coin"), "wieder an")

	bus.queue_free()
	await process_frame
	_check(not Sound.available(), "nach dem Entfernen wieder still")
	_done.append("bus")


# Haengt einen frischen Bus ein und gibt ihn zurueck.
func _make_bus():
	var bus := SfxNode.new()
	bus.name = "Sfx"
	root.add_child(bus)
	return bus


func _test_battle() -> void:
	print("")
	print("== Kampf loest Geraeusche aus ==")
	var bus = _make_bus()
	await process_frame
	var bs = TBS.new()
	bs.fx_speed = 0.0
	root.add_child(bs)
	await process_frame
	bs.set_battle({
		"player_stacks": [{"type": "men_archer", "count": 20}],
		"enemy_stacks": [{"type": "ork_goblin", "count": 1}],
		"seed": 7, "allow_flee": true,
		"player_mana": 40, "player_spell_power": 2,
		"player_spells": ["magic_arrow", "heal"],
	})
	bs._obstacles = []
	bs._ob_map = {}
	await process_frame

	var player: Dictionary = bs._p_stacks[0]
	var enemy: Dictionary = bs._e_stacks[0]
	player["pos"] = Vector2i(1, 4)
	enemy["pos"] = Vector2i(6, 4)

	bus.reset_counts()
	bs._rebuild_order()
	for i in range(bs._turn_order.size()):
		if int(bs._turn_order[i]["side"]) == 0:
			bs._active_slot = i
			break
	bs._try_attack_enemy(0)
	_check(Sound.play_count("arrow_shot") >= 1, "Schuss macht ein Geraeusch")
	_check(Sound.play_count("death") >= 1, "gefallener Stack ebenfalls")

	# Nahkampf
	bus.reset_counts()
	var e2: Dictionary = {"type": "ork_goblin", "count": 40,
		"top_hp": UnitType.hp_of("ork_goblin"), "count_start": 40,
		"pos": Vector2i(2, 4), "side": 1, "retaliations": 0}
	bs._e_stacks = [e2]
	bs._melee_exchange(player, e2)
	_check(Sound.play_count("melee_hit") >= 1, "Nahkampf macht ein Geraeusch")

	# Zauber
	bus.reset_counts()
	bs._casts_left = 1
	bs._p_mana = 40
	bs._cast("magic_arrow", e2)
	_check(Sound.play_count("spell_cast") >= 1, "Zaubern macht ein Geraeusch")
	_check(Sound.play_count("spell_hit") >= 1, "und der Einschlag auch")

	bs.queue_free()
	bus.queue_free()
	await process_frame
	_done.append("battle")


func _test_worldmap() -> void:
	print("")
	print("== Weltkarte loest Geraeusche aus ==")
	var bus = _make_bus()
	await process_frame
	var scene := load("res://scenes/WorldMap.tscn") as PackedScene
	var wm = scene.instantiate()
	root.add_child(wm)
	await process_frame
	wm.call("_start", 555, 1)
	await process_frame

	# Tagesende bzw. Wochenwechsel.
	bus.reset_counts()
	wm.set("_turn_number", 2)
	wm.call("_finalize_turn")
	await process_frame
	_check(Sound.play_count("day_end") >= 1, "Tagesende macht ein Geraeusch")

	bus.reset_counts()
	wm.set("_turn_number", 6)   # Zug 7 = neue Woche
	wm.call("_finalize_turn")
	await process_frame
	_check(Sound.play_count("week_event") >= 1, "Wochenwechsel hat ein eigenes")
	_check(Sound.play_count("day_end") == 0,
		"und dann NICHT zusaetzlich die Tagesglocke")

	# Kein Check fuer die Bonus-Objekte: das Geraeusch haengt am
	# Bewegungs-Pfad in _try_move, nicht an _visit_bonus_object. Ein
	# _check(true, ...) waere eine Attrappe - lieber keine Zeile als eine,
	# die immer gruen ist.

	# Stufenaufstieg
	bus.reset_counts()
	var hero = wm.get("_hero")
	hero.xp = 400
	wm.call("_check_level_up")
	_check(Sound.play_count("level_up") >= 1, "Stufenaufstieg macht ein Geraeusch")

	wm.queue_free()
	bus.queue_free()
	await process_frame
	_done.append("worldmap")
