class_name Hero
extends RefCounted

# Minimaler Helden-Zustand fuer die Weltkarte.
# Position in Kachel-Koordinaten, Bewegungspunkte pro Zug.

var position: Vector2i
var max_mp: int
var mp: int
var gold: int = 0
var army: int = 0
# Progression: Level startet bei 1; XP sammelt sich monoton. Der
# WorldMapScreen bestimmt per LEVEL_THRESHOLDS, wann ein Level-Up faellt.
var xp: int = 0
var level: int = 1

func _init(start: Vector2i, max_movement: int = 12) -> void:
	position = start
	max_mp = max_movement
	mp = max_movement

func end_turn() -> void:
	mp = max_mp
