extends RefCounted

# Wochenereignisse (M12).
#
# Statische Regelschicht wie Abilities/Morale/HeroSkills, per `preload`
# eingebunden (kein `class_name`, Android-Export-Vorsicht).
#
# WARUM: der Kalender zaehlte nur. Tag, Woche, Monat und Jahr standen in
# der Kopfzeile, aber keine dieser Einheiten hatte eine Wirkung - eine
# Woche war sieben gleiche Tage. In HoMM3 ist der Wochenwechsel ein
# Ereignis, auf das man plant.
#
# NICHTS WIRD GESPEICHERT: das Ereignis leitet sich deterministisch aus
# Karten-Seed und Wochennummer ab. Derselbe Spielstand hat immer dieselben
# Wochen, und Speichern/Laden kann daran nichts verschieben.

const KIND_NONE := "none"
const KIND_UNIT := "unit"        # Woche des <Einheit>: Wachstum verdoppelt
const KIND_PLAGUE := "plague"    # Seuche: Wachstum halbiert
const KIND_HARVEST := "harvest"  # Ernte: Einmal-Gold je eigener Stadt

# Gewichte. Ereignislose Wochen muessen die Mehrheit sein, sonst wird das
# Besondere gewoehnlich.
const WEIGHTS := {
	KIND_NONE: 8,
	KIND_UNIT: 6,
	KIND_HARVEST: 3,
	KIND_PLAGUE: 2,
}

# Wachstums-Faktoren als Bruch (Zaehler, Nenner) statt Fliesskomma: die
# Pool-Rechnung laeuft ueber Bresenham auf ganzen Zahlen, und ein
# 0.5-Faktor haette dort Rundungsdrift erzeugt.
const UNIT_WEEK_NUM := 2
const UNIT_WEEK_DEN := 1
const PLAGUE_NUM := 1
const PLAGUE_DEN := 2

const HARVEST_GOLD_PER_CITY := 250

# Die erste Woche ist immer ereignislos. Ein Seuchenzug im Startzug waere
# eine Strafe fuer nichts.
#
# WICHTIG: GameCalendar.week_total ist EINS-BASIERT - Zug 0 ist Woche 1.
# Mit dem urspruenglichen Wert 0 hat diese Sperre im Spiel NIE gegriffen,
# weil Woche 0 nicht vorkommt; Woche 1 bekam ein gewuerfeltes Ereignis. Der
# eigene Test hat das zunaechst nicht gezeigt, weil er for_week(seed, 0)
# geprueft hat - also einen Fall, den es nicht gibt.
const FIRST_QUIET_WEEK := 1


# Deterministischer Hash mit Bit-Mischung. Ohne die zweite Runde koppelt
# die Paritaet an die Wochennummer, und die Ereignisse wechseln sich
# regelmaessig ab statt zu streuen (dieselbe Falle wie bei den
# Weltkarten-Kacheln in It. 19).
static func _hash(map_seed: int, week: int, salt: int) -> int:
	var h: int = (map_seed * 83492791) ^ (week * 19349663) ^ (salt * 73856093)
	h = (h ^ (h >> 13)) * 1274126177
	h = h ^ (h >> 16)
	return absi(h)


# Ereignis einer Woche. `week` ist GameCalendar.week_total(turn_number).
# Rueckgabe:
#   kind    -> eine der KIND_*-Konstanten
#   unit    -> Einheiten-ID (nur bei KIND_UNIT)
#   title   -> Zeile fuer die Kopfzeile, z.B. "Woche des Greifs"
#   detail  -> ausgeschriebene Wirkung fuer die Statuszeile
static func for_week(map_seed: int, week: int, unit_ids: Array) -> Dictionary:
	if week <= FIRST_QUIET_WEEK:
		return {"kind": KIND_NONE, "unit": "",
			"title": "Ruhige Woche", "detail": "Kein besonderes Ereignis."}
	var total: int = 0
	for k in WEIGHTS.keys():
		total += int(WEIGHTS[k])
	var roll: int = _hash(map_seed, week, 1) % total
	var acc: int = 0
	var kind: String = KIND_NONE
	for k2 in WEIGHTS.keys():
		acc += int(WEIGHTS[k2])
		if roll < acc:
			kind = String(k2)
			break

	if kind == KIND_UNIT:
		if unit_ids.is_empty():
			return {"kind": KIND_NONE, "unit": "",
				"title": "Ruhige Woche", "detail": "Kein besonderes Ereignis."}
		var idx: int = _hash(map_seed, week, 2) % unit_ids.size()
		var uid: String = String(unit_ids[idx])
		var name: String = UnitType.name_of(uid)
		return {
			"kind": KIND_UNIT, "unit": uid,
			"title": "Woche des %s" % name,
			"detail": "%s wachsen diese Woche doppelt - in ALLEN Staedten." % name,
		}
	if kind == KIND_PLAGUE:
		return {"kind": KIND_PLAGUE, "unit": "",
			"title": "Woche der Seuche",
			"detail": "Alle Einheiten wachsen diese Woche nur halb."}
	if kind == KIND_HARVEST:
		return {"kind": KIND_HARVEST, "unit": "",
			"title": "Woche der Ernte",
			"detail": "+%d Gold je eigener Stadt, einmalig." % HARVEST_GOLD_PER_CITY}
	return {"kind": KIND_NONE, "unit": "",
		"title": "Ruhige Woche", "detail": "Kein besonderes Ereignis."}


# Wachstums-Faktor auf die Wochenrate EINER Einheit, als Bruch.
# Rueckgabe [Zaehler, Nenner].
static func growth_factor(event: Dictionary, uid: String) -> Array:
	var kind: String = String(event.get("kind", KIND_NONE))
	if kind == KIND_UNIT and String(event.get("unit", "")) == uid:
		return [UNIT_WEEK_NUM, UNIT_WEEK_DEN]
	if kind == KIND_PLAGUE:
		return [PLAGUE_NUM, PLAGUE_DEN]
	return [1, 1]


# Wochenrate mit Ereignis. Mindestens 1, solange die Grundrate positiv war -
# eine Seuche soll bremsen, nicht die Produktion ganz abschalten.
static func apply_growth(event: Dictionary, uid: String, base: int) -> int:
	if base <= 0:
		return base
	var f: Array = growth_factor(event, uid)
	var out: int = int(base) * int(f[0]) / int(f[1])
	return max(1, out)


static func is_quiet(event: Dictionary) -> bool:
	return String(event.get("kind", KIND_NONE)) == KIND_NONE
