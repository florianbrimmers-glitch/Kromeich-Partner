class_name BattleObstacles
extends RefCounted

# Gelaende-Objekte auf dem 10x8-Kampfgrid. Vier Typen, die je eigene
# Kombinationen aus Bewegungs- und Schusslinien-Blockade sowie
# Feldkosten haben. Die Zusammensetzung pro Kampf haengt am Terrain-Id
# des Weltkartenfelds, auf dem der Kampf ausgeloest wurde, damit sich
# Wald-Kaempfe anders anfuehlen als Bergkaempfe.

const KIND_ROCK  := 0  # Stein:     blockt Bewegung + Schusslinie voll.
const KIND_LOG   := 1  # Baumstamm: blockt Bewegung, Schuss durchgebrochen = Schaden /2.
const KIND_BUSH  := 2  # Busch:     durchquerbar, aber doppelte Feldkosten (halbe Speed).
const KIND_SWAMP := 3  # Sumpf:     durchquerbar, doppelte Feldkosten (halbe Speed).


static func blocks_move(kind: int) -> bool:
	return kind == KIND_ROCK or kind == KIND_LOG


static func blocks_los(kind: int) -> bool:
	return kind == KIND_ROCK


static func halves_damage(kind: int) -> bool:
	return kind == KIND_LOG


static func move_cost(kind: int) -> int:
	# Rueckgabe fuer blockierende Felder ist egal - sie tauchen im
	# Dijkstra nie als Knoten auf. Fuer betretbare Obstacles ist das
	# doppelte Feldkosten (2) gegenueber leerem Feld (1).
	if kind == KIND_BUSH or kind == KIND_SWAMP:
		return 2
	return 1


static func display_name(kind: int) -> String:
	match kind:
		KIND_ROCK:  return "Stein"
		KIND_LOG:   return "Baumstamm"
		KIND_BUSH:  return "Busch"
		KIND_SWAMP: return "Sumpf"
	return "?"


static func generate(terrain_id: int, battle_seed: int, cols: int, rows: int) -> Array:
	# 0-3 Obstacles pro Kampf. Verteilung pro Terrain stark verschieden:
	# Wald bringt viel Baumstamm/Busch, Berg bringt Steine, Sumpf bringt
	# Sumpf, Kueste mischt Wasser-Klippen (Stein) und Marsch (Sumpf).
	# Mittelbereich des Grids (Cols 3..cols-4), damit Startreihen
	# beider Seiten frei bleiben.
	var rng := RandomNumberGenerator.new()
	# Seed mit terrain_id mischen, damit gleicher Match-Seed auf
	# unterschiedlichem Terrain unterschiedliche Karten liefert.
	rng.seed = _mix_seed(battle_seed, terrain_id)
	var count: int = rng.randi_range(0, 3)
	var weights: Array = _weights_for_terrain(terrain_id)
	if weights.is_empty():
		return []
	var out: Array = []
	var used: Dictionary = {}
	var min_col: int = 3
	var max_col: int = cols - 4
	if max_col < min_col:
		# Zu kleines Grid: keine Obstacles, um Platzprobleme zu vermeiden.
		return []
	var attempts: int = 0
	while out.size() < count and attempts < 64:
		attempts += 1
		var cx: int = rng.randi_range(min_col, max_col)
		var cy: int = rng.randi_range(0, rows - 1)
		var key: Vector2i = Vector2i(cx, cy)
		if used.has(key):
			continue
		used[key] = true
		var kind: int = _weighted_pick(weights, rng)
		out.append({"pos": key, "kind": kind})
	return out


static func _weights_for_terrain(terrain_id: int) -> Array:
	# Array aus [kind, gewicht]. Gewichte sind relativ, summiert wird
	# beim Pick. Terrain-Ids folgen MapGen.TILE_* (0=Gras, 1=Wald,
	# 2=Wasser, 3=Gebirge, 4=Sand, 5=Sumpf).
	match terrain_id:
		0: return [[KIND_LOG, 40], [KIND_BUSH, 40], [KIND_ROCK, 20]]
		1: return [[KIND_LOG, 45], [KIND_BUSH, 45], [KIND_ROCK, 10]]
		2: return [[KIND_ROCK, 55], [KIND_SWAMP, 45]]
		3: return [[KIND_ROCK, 80], [KIND_LOG, 20]]
		4: return [[KIND_ROCK, 60], [KIND_BUSH, 40]]
		5: return [[KIND_SWAMP, 70], [KIND_BUSH, 30]]
	return [[KIND_LOG, 50], [KIND_BUSH, 50]]


static func _weighted_pick(weights: Array, rng: RandomNumberGenerator) -> int:
	var total: int = 0
	for pair in weights:
		total += int(pair[1])
	if total <= 0:
		return int(weights[0][0])
	var roll: int = rng.randi_range(1, total)
	var acc: int = 0
	for pair in weights:
		acc += int(pair[1])
		if roll <= acc:
			return int(pair[0])
	return int(weights[0][0])


static func _mix_seed(base: int, extra: int) -> int:
	# Einfacher Mix, damit gleiche Match-Seeds auf verschiedenen Terrains
	# unabhaengige Obstacle-Layouts liefern.
	return (base ^ (extra * 2654435761)) & 0x7fffffff


static func line_cells(from: Vector2i, to: Vector2i) -> Array:
	# Bresenham-Linie zwischen zwei Grid-Zellen, inklusive beider
	# Endpunkte. Wird fuer Schusslinien-Checks benutzt.
	var cells: Array = []
	var x0: int = from.x
	var y0: int = from.y
	var x1: int = to.x
	var y1: int = to.y
	var dx: int = abs(x1 - x0)
	var dy: int = abs(y1 - y0)
	var sx: int = 1 if x0 < x1 else -1
	var sy: int = 1 if y0 < y1 else -1
	var err: int = dx - dy
	while true:
		cells.append(Vector2i(x0, y0))
		if x0 == x1 and y0 == y1:
			break
		var e2: int = err * 2
		if e2 > -dy:
			err -= dy
			x0 += sx
		if e2 < dx:
			err += dx
			y0 += sy
	return cells


static func obstacle_at(obstacles: Array, pos: Vector2i) -> Dictionary:
	for o in obstacles:
		if Vector2i(o["pos"]) == pos:
			return o
	return {}


static func line_modifier(obstacles: Array, from: Vector2i, to: Vector2i) -> Dictionary:
	# Durchlaeuft die Bresenham-Zellen zwischen from und to (ohne die
	# Endpunkte) und liefert, ob die Schusslinie vollstaendig blockiert
	# ist und ob ein "halbiert-Schaden"-Modifier aktiv ist.
	var blocked: bool = false
	var halve: bool = false
	var line: Array = line_cells(from, to)
	for i in range(1, line.size() - 1):
		var cell: Vector2i = line[i]
		var ob: Dictionary = obstacle_at(obstacles, cell)
		if ob.is_empty():
			continue
		var kind: int = int(ob["kind"])
		if blocks_los(kind):
			blocked = true
			break
		if halves_damage(kind):
			halve = true
	return {"blocked": blocked, "halve": halve}
