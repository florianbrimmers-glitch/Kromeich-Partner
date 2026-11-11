extends RefCounted

# Bewegungskosten auf der Weltkarte (M7 Teil 2).
#
# Reine statische Regelschicht wie Abilities/Morale/HeroSkills, eingebunden
# per `preload` (NICHT `class_name` - das ist im Android-Export
# unzuverlaessig).
#
# WARUM DIESES MODUL: die Kostenzahlen standen DREIMAL im Baum - in
# MapGen.terrain_cost, in Pathfinder.compute_costs und als Integer-Literale
# in WorldMapScreen._dijkstra (dort absichtlich inline, aus Angst vor
# class_name-Aufrufen im Export). Der Skill Wegfindung muss aber genau
# diese Zahl aendern; drei Kopien haetten garantiert auseinandergelaufen.
#
# FEINERE EINHEIT: vorher kostete ein flaches Feld 1 Punkt und ein raues 2.
# Ein prozentualer Abschlag auf einen Aufschlag von 1 ist in ganzen Zahlen
# nicht darstellbar - "-25 %" waere entweder nichts oder alles. Deshalb
# zaehlt ein flaches Feld jetzt UNIT (4) Punkte; der Aufschlag fuer raues
# Gelaende ist damit 4 und laesst sich vierteln. Die Bewegungspunkte des
# Helden sind mitskaliert (BASE_MAX_MP 10 -> 40), also aendert sich die
# Reichweite ohne Skill nicht: 40 / 4 = 10 flache Felder wie vorher.
# Alte Spielstaende bekommen ihre Punkte in SaveManager._migrate_3_to_4
# hochskaliert.

const UNIT := 4
const IMPASSABLE := -1

# Gelaende-IDs wie MapGen: 0=Gras, 1=Wald, 2=Wasser, 3=Berg, 4=Sand,
# 5=Sumpf. Wald und Sumpf sind "rau" - sie kosten doppelt, und genau
# diesen Aufschlag greift die Wegfindung ab.
static func base_cost(t: int) -> int:
	match t:
		0: return UNIT          # Gras
		4: return UNIT          # Sand
		1: return UNIT * 2      # Wald
		5: return UNIT * 2      # Sumpf
		2: return IMPASSABLE    # Wasser
		3: return IMPASSABLE    # Berg
	return UNIT


# Abschlag auf den Gelaende-AUFSCHLAG je Wegfindungs-Stufe (skills.json:
# rough_terrain_cost_-25pct / -50pct / ignored). Stufe 3 macht raues
# Gelaende so billig wie flaches - nicht schneller.
const ROUGH_REDUCTION_PCT := [0, 25, 50, 100]


static func step_cost(t: int, pathfinding_tier: int = 0) -> int:
	var base: int = base_cost(t)
	if base <= 0:
		return IMPASSABLE
	var extra: int = base - UNIT
	if extra <= 0 or pathfinding_tier <= 0:
		return base
	var pct: int = int(ROUGH_REDUCTION_PCT[clampi(pathfinding_tier, 0, 3)])
	# Ganzzahlig abgerundet: der Spieler bekommt nie mehr als versprochen.
	return UNIT + (extra - int(extra * pct / 100))


static func is_passable(t: int) -> bool:
	return base_cost(t) > 0


# Fuer die Anzeige: wie viele flache Felder stecken in den Punkten.
static func tiles_of(points: int) -> int:
	return int(points) / UNIT
