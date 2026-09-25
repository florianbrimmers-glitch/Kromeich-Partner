extends Node

# Geraeusch-Wiedergabe (M11). Autoload, damit jeder Screen ohne
# Verkabelung ein Geraeusch anstossen kann - Geraeusche gehoeren
# zu keinem Bildschirm allein.
#
# Die WAVs kommen aus tools/gen_sfx.py (selbst erzeugt, keine Lizenzfrage).
#
# WARUM EIN POOL: ein einzelner AudioStreamPlayer schneidet sich selbst ab.
# Im Kampf fallen Schuss, Treffer und Zerfall dicht aufeinander; mit einem
# Player waere immer nur das letzte zu hoeren. Der Pool nimmt den ersten
# freien Player und laesst laufende Geraeusche in Ruhe.
#
# WICHTIG: Screens rufen NICHT direkt hier an, sondern ueber
# core/SfxBus.gd. Autoloads werden bei "godot --script tools/x.gd" nicht
# instanziiert; ein direkter Aufruf scheitert dort zur Laufzeit und bricht
# die Testfunktion ab (das hat beim ersten Anlauf zwei Suiten still im
# Timeout haengen lassen).
#
# HEADLESS: Godot laeuft in der CI mit dem Dummy-Audio-Treiber. play() ist
# dort wirkungslos, aber gueltig. `enabled` schaltet trotzdem alles ab.

const SFX_PATH := "res://assets/sfx/%s.wav"
const POOL_SIZE := 6

# Global stummschalten. Der Weltkarten-Screen haengt einen Knopf daran.
var enabled: bool = true
# Lautstaerke in Dezibel. Geraeusche sollen nicht ueber die Sprachausgabe
# des Geraets bruellen.
var volume_db: float = -6.0

var _pool: Array = []
var _cache: Dictionary = {}
# Zaehler fuer die Tests: wie oft wurde was gespielt. Ohne das laesst sich
# headless nicht pruefen, ob ein Ereignis ueberhaupt ein Geraeusch ausloest.
var _played: Dictionary = {}


func _ready() -> void:
	for i in range(POOL_SIZE):
		var p := AudioStreamPlayer.new()
		p.name = "Sfx%d" % i
		p.volume_db = volume_db
		add_child(p)
		_pool.append(p)


# Liefert den Stream oder null. Fehlende Dateien werden als null gemerkt,
# damit der Pfad nicht bei jedem Aufruf neu gesucht wird.
func stream_for(name: String) -> AudioStream:
	if _cache.has(name):
		return _cache[name] as AudioStream
	var path: String = SFX_PATH % name
	var st: AudioStream = null
	if ResourceLoader.exists(path):
		st = load(path) as AudioStream
	else:
		push_warning("Geraeusch fehlt: " + path)
	_cache[name] = st
	return st


func play(name: String) -> bool:
	# Mitzaehlen auch bei aus - der Test will wissen, ob die AUFRUFE
	# stimmen, nicht ob der Treiber Ton macht.
	_played[name] = int(_played.get(name, 0)) + 1
	if not enabled:
		return false
	var st: AudioStream = stream_for(name)
	if st == null:
		return false
	for p in _pool:
		var pl := p as AudioStreamPlayer
		if not pl.playing:
			pl.stream = st
			pl.volume_db = volume_db
			pl.play()
			return true
	# Alle belegt: das aelteste ueberschreiben, statt das Geraeusch zu
	# verschlucken. Bei sechs Playern passiert das praktisch nur, wenn
	# mehrere Flaechenschaeden gleichzeitig einschlagen.
	var first := _pool[0] as AudioStreamPlayer
	first.stream = st
	first.play()
	return true


func play_count(name: String) -> int:
	return int(_played.get(name, 0))


func reset_counts() -> void:
	_played.clear()


func toggle() -> bool:
	enabled = not enabled
	if not enabled:
		for p in _pool:
			(p as AudioStreamPlayer).stop()
	return enabled
