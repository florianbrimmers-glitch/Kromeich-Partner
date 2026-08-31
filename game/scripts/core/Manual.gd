extends RefCounted

# Spielanleitung (It. 46).
#
# WARUM ES DIESE DATEI GIBT: bis It. 46 erklaerte das Spiel sich nirgends.
# Der Titelschirm hiess "MVP", der Knopf zum Spielen "Weltkarte" und der
# dritte Knopf fuehrte in ein Entwickler-Werkzeug. Wer HoMM3 nicht kennt,
# hatte keine Chance - und wer es kennt, kennt UNSERE Abweichungen nicht
# (Schonfrist bei Stadtverlust, drei Helden, Flucht kostet die Armee).
#
# DIE WICHTIGSTE REGEL AN DIESER DATEI: sie enthaelt KEINE eigenen Zahlen.
# Jede Zahl kommt als Wert herein, aus der Konstante, die sie im Spiel
# auch bestimmt. Eine Anleitung, die ihre Zahlen selbst schreibt, ist
# nach der ersten Balance-Aenderung eine Luege - dieselbe Lehre wie bei
# den Vorschau-Werkzeugen (It. 36/37), nur schlimmer, weil der SPIELER
# sie liest.
#
# Rein statisch, Einbindung per preload (Android-class_name-Falle, siehe
# Kopf von TacticalBattleScreen.gd).


# Benannter Bauplan fuer das Zahlen-Buendel. Die SCHLUESSEL leben damit an
# EINER Stelle - die Werte reicht jeder Aufrufer aus seinen eigenen
# Konstanten herein.
#
# Warum nicht hier selbst nachschlagen: dazu muesste dieses Modul den
# WorldMapScreen preloaden, und der preloadet die Anleitung - ein
# Preload-Kreis, den GDScript nicht sauber aufloest.
static func numbers(max_heroes: int, hire_gold: int, grace_days: int,
		army_slots: int, grid_cols: int, grid_rows: int, casts: int) -> Dictionary:
	return {
		"max_heroes": max_heroes,
		"hire_gold": hire_gold,
		"grace_days": grace_days,
		"army_slots": army_slots,
		"grid_cols": grid_cols,
		"grid_rows": grid_rows,
		"casts": casts,
	}


# `n` liefert die Zahlen. Fehlt eine, steht ein "?" im Text - lieber
# sichtbar unvollstaendig als still falsch.
static func _v(n: Dictionary, key: String) -> String:
	return str(n[key]) if n.has(key) else "?"


static func sections(n: Dictionary) -> Array:
	return [
		["Ziel des Spiels", "\n".join([
			"Du gewinnst, wenn keine Gegner-Fraktion mehr eine Stadt",
			"besitzt UND kein Gegner-Held mehr lebt.",
			"Neutrale Staedte und Minen musst du dafuer nicht einnehmen.",
		])],
		["Bewegung", "\n".join([
			"Ein Feld antippen: der Held laeuft hin, wenn seine",
			"Bewegungspunkte reichen. Der helle Rand zeigt, wie weit er",
			"heute kommt.",
			"Wald, Sand und Sumpf kosten mehr als Wiese; Wasser und Berge",
			"sind unpassierbar. Der Skill Wegfindung senkt den Aufschlag.",
			"Zwei Finger ziehen: Karte verschieben.",
		])],
		["Kampf", "\n".join([
			"Gitter %s x %s. Du bist links, der Gegner rechts." % [
				_v(n, "grid_cols"), _v(n, "grid_rows")],
			"Deinen Stack antippen ist nicht noetig - wer am Zug ist,",
			"leuchtet. Gegner antippen = angreifen, freies Feld = laufen.",
			"WARTEN schiebt den Stack ans Ende der Runde.",
			"ZAUBER: %s pro Runde, Mana wird nicht im Kampf nachgefuellt." % _v(n, "casts"),
			"FLIEHEN: der Held ueberlebt, verliert aber seine GANZE Armee.",
			"KAPITULIEREN: kostet Gold in Hoehe deiner Armee, dafuer",
			"bleiben die Ueberlebenden bei dir.",
			"Beides braucht eine eigene Stadt als Rueckzugsziel, beendet",
			"den Tag des Helden - und geht NICHT, wenn du deine eigene",
			"Stadt verteidigst.",
		])],
		["Stadt", "\n".join([
			"Auf die eigene Stadt tippen oeffnet sie. Gebaeude antippen",
			"zum Bauen; ein gebautes Militaergebaeude bietet Einheiten an.",
			"Der Vorrat waechst jede Woche nach.",
			"GARNISON: Einheiten, die die Stadt verteidigen. Steht dein",
			"Held in der Stadt, kaempft er mit.",
			"MARKT: Ressourcen gegen Gold tauschen.",
		])],
		["Helden", "\n".join([
			"Bis zu %s Helden. Anwerben in einer eigenen Stadt fuer" % _v(n, "max_heroes"),
			"%s Gold - die Einheiten kommen aus der Fraktion DIESER Stadt." % _v(n, "hire_gold"),
			"Einen ANDEREN eigenen Helden antippen: er wird der aktive.",
			"Steht er direkt daneben, oeffnet sich statt dessen der",
			"Armee-Tausch.",
			"Ein Held traegt hoechstens %s verschiedene Einheiten-Typen;" % _v(n, "army_slots"),
			"ein Stapel selbst darf beliebig gross werden.",
			"Gold gehoert DIR, nicht dem Helden - alle geben aus demselben",
			"Beutel aus.",
		])],
		["Stufenaufstieg und Zauber", "\n".join([
			"Jede Stufe gibt einen Primaerwert und die Wahl aus zwei",
			"Skills. Wissen hebt das Mana-Maximum, Zauberkraft die",
			"Wirkung.",
			"Weisheit gibt hoehere Zauberstufen frei. Der Abenteuer-Zauber",
			"Stadttor steht im Heldenblatt und bringt Held samt Armee in",
			"die naechste eigene Stadt.",
		])],
		["Niederlage", "\n".join([
			"Verloren ist erst, wenn dein LETZTER Held gefallen ist.",
			"Verlierst du alle Staedte, laeuft eine Frist von %s Tagen -" % _v(n, "grace_days"),
			"erobere in der Zeit eine Stadt, geht es weiter.",
		])],
		["Speichern", "\n".join([
			"Am Ende jedes Tages wird automatisch gespeichert.",
			"Im Titelmenue fuehrt FORTSETZEN zurueck ins laufende Spiel.",
			"Nach Sieg oder Niederlage wird der Spielstand geloescht.",
		])],
	]


# Ein Fliesstext aus allen Abschnitten - fuer Tests und fuer eine
# einfache Anzeige ohne eigene Ueberschriften-Logik.
static func text(n: Dictionary) -> String:
	var parts: Array = []
	for sec in sections(n):
		parts.append("%s\n%s" % [String(sec[0]), String(sec[1])])
	return "\n\n".join(parts)
