class_name Hero
extends RefCounted

# Minimaler Helden-Zustand fuer die Weltkarte.
# Position in Kachel-Koordinaten, Bewegungspunkte pro Tag.
#
# army ist ein Dictionary { unit_id: count }. Rekrutierung, Verluste und
# Anzeige laufen ueber die Helfer add_units/remove_units/total_count.
#
# Stack-Limit: max 6 unterschiedliche Einheiten-Typen pro Held. Ein
# neuer Typ wird abgewiesen, wenn schon 6 Slots belegt sind - bestehende
# Stacks koennen unbegrenzt wachsen. Wert 6 (statt HoMM3-klassischer 7),
# damit auch auf schmalen Handy-Displays die Armee-Zeile lesbar bleibt.
const MAX_ARMY_SLOTS: int = 6

var position: Vector2i
var max_mp: int
var mp: int
var gold: int = 0
var army: Dictionary = {}
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

func total_count() -> int:
	var t: int = 0
	for k in army.keys():
		t += int(army[k])
	return t

func can_add_unit(unit_id: String) -> bool:
	# Stack existiert schon -> Count-Erhoehung ist immer ok.
	# Stack neu -> nur wenn noch ein Slot frei ist.
	if army.has(unit_id):
		return true
	return army.size() < MAX_ARMY_SLOTS

func add_units(unit_id: String, count: int) -> void:
	if count <= 0:
		return
	if not can_add_unit(unit_id):
		return
	army[unit_id] = int(army.get(unit_id, 0)) + count

func remove_units(unit_id: String, count: int) -> void:
	if count <= 0 or not army.has(unit_id):
		return
	var c: int = int(army[unit_id]) - count
	if c <= 0:
		army.erase(unit_id)
	else:
		army[unit_id] = c

func count_of(unit_id: String) -> int:
	return int(army.get(unit_id, 0))

func apply_casualties(cas: Dictionary) -> void:
	for k in cas.keys():
		remove_units(String(k), int(cas[k]))

# Proportionaler Abzug (fuer Auto-Resolve-Kaempfe ohne Overlay, z.B.
# Gegner-KI nimmt Wache ein). Verteilt die Verluste gleichmaessig auf
# alle Stacks. Runden-Rest faellt auf den groessten Stack.
func apply_proportional_losses(total_loss: int) -> void:
	if total_loss <= 0 or army.is_empty():
		return
	var total: int = total_count()
	if total_loss >= total:
		army.clear()
		return
	var removed: int = 0
	var biggest_id: String = ""
	var biggest_count: int = -1
	var new_army: Dictionary = {}
	for k in army.keys():
		var c: int = int(army[k])
		var share: int = int(float(c) / float(total) * float(total_loss))
		removed += share
		var left: int = c - share
		new_army[k] = left
		if left > biggest_count:
			biggest_count = left
			biggest_id = String(k)
	var leftover: int = total_loss - removed
	if leftover > 0 and biggest_id != "":
		new_army[biggest_id] = max(0, int(new_army[biggest_id]) - leftover)
	for k in new_army.keys():
		if int(new_army[k]) <= 0:
			new_army.erase(k)
	army = new_army

# Kurzform fuer Anzeige, z.B. "5 Sw / 3 Bw / 2 Ri". Iteriert in
# Fraktions-Reihenfolge (UnitType.ORDER), damit die Anzeige stabil ist.
func army_summary() -> String:
	if army.is_empty():
		return "0"
	var parts: Array = []
	for uid in UnitType.ORDER:
		if army.has(uid) and int(army[uid]) > 0:
			parts.append("%d %s" % [int(army[uid]), UnitType.short_of(uid)])
	if parts.is_empty():
		for k in army.keys():
			parts.append("%d %s" % [int(army[k]), String(k).substr(0, 2)])
	return " / ".join(parts)
