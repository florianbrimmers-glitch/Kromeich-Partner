class_name GameCalendar
extends RefCounted

# Reine Kalender- und Wachstums-Mathematik, extrahiert aus WorldMapScreen,
# damit sie headless testbar ist (tools/test_core_logic.gd) und der
# Monolith schrumpft.
#
# Konvention: turn_number zaehlt abgeschlossene Tage (Tag 1 laeuft bei
# turn_number == 0). Alle Rueckgaben sind 1-basiert.

const DAYS_PER_WEEK := 7
const WEEKS_PER_MONTH := 4
const MONTHS_PER_YEAR := 12


static func day_num(turn_number: int) -> int:
	return turn_number + 1


static func day_of_week(turn_number: int) -> int:
	return ((day_num(turn_number) - 1) % DAYS_PER_WEEK) + 1


static func week_total(turn_number: int) -> int:
	return ((day_num(turn_number) - 1) / DAYS_PER_WEEK) + 1


static func week_of_month(turn_number: int) -> int:
	return ((week_total(turn_number) - 1) % WEEKS_PER_MONTH) + 1


static func month_total(turn_number: int) -> int:
	return ((week_total(turn_number) - 1) / WEEKS_PER_MONTH) + 1


static func month_of_year(turn_number: int) -> int:
	return ((month_total(turn_number) - 1) % MONTHS_PER_YEAR) + 1


static func year_num(turn_number: int) -> int:
	return ((month_total(turn_number) - 1) / MONTHS_PER_YEAR) + 1


static func calendar_text(turn_number: int) -> String:
	return "T%d W%d M%d J%d" % [
		day_of_week(turn_number), week_of_month(turn_number),
		month_of_year(turn_number), year_num(turn_number)]


# Lange Form fuer die Anzeige. `calendar_text` bleibt die kompakte Form
# ("T4 W1 M1 J1") - sie steckt in Save-/Kontext-Dictionaries und ist
# getestet. Im HUD war sie unlesbar: der Nutzer sah nur einen Code-Streifen.
static func calendar_long(turn_number: int) -> String:
	var parts: Array = [
		"Tag %d" % day_of_week(turn_number),
		"Woche %d" % week_of_month(turn_number),
		"Monat %d" % month_of_year(turn_number),
	]
	# Jahr nur nennen, wenn es eins gibt, das nicht das erste ist - sonst
	# frisst es Platz ohne Information.
	var yr: int = year_num(turn_number)
	if yr > 1:
		parts.append("Jahr %d" % yr)
	return "  ".join(parts)


# Tagesration eines Wochen-Wachstums via Bresenham: die 7 Tageswerte
# summieren sich exakt auf cap, egal wie krumm cap/7 ist.
# dow: 1..DAYS_PER_WEEK.
static func day_delta(cap: int, dow: int) -> int:
	if cap <= 0 or dow <= 0:
		return 0
	return (dow * cap) / DAYS_PER_WEEK - ((dow - 1) * cap) / DAYS_PER_WEEK


# Catch-up fuer ein mitten in der Woche gebautes Gebaeude: Summe der
# Tagesrationen von Tag 1 bis einschliesslich dow.
static func catch_up(cap: int, dow: int) -> int:
	if cap <= 0 or dow <= 0:
		return 0
	return (dow * cap) / DAYS_PER_WEEK
