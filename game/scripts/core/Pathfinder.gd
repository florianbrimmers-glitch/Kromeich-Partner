class_name Pathfinder
extends RefCounted

# Dijkstra auf einem Tile-Grid mit Terrain-Kosten. Keine Diagonalen.
# Nutzung: compute_costs(map, start) -> Dictionary {Vector2i -> int_cost}.
# Start hat Kosten 0; nicht-erreichbare Felder fehlen im Dictionary.

static func compute_costs(map: Dictionary, start: Vector2i) -> Dictionary:
	var width: int = int(map["width"])
	var height: int = int(map["height"])
	var tiles: Array = map["tiles"]
	var costs: Dictionary = {}
	costs[start] = 0

	# Simple open list als Array<Vector2i>; bei jeder Iteration den
	# billigsten Knoten rauspicken. Fuer 15x22 Grid voellig ausreichend,
	# keine Prioritaetswarteschlange noetig.
	var open: Array = [start]
	while not open.is_empty():
		var best_idx := 0
		var best_cost: int = int(costs[open[0]])
		for i in range(1, open.size()):
			var c: int = int(costs[open[i]])
			if c < best_cost:
				best_cost = c
				best_idx = i
		var cur: Vector2i = open[best_idx]
		open.remove_at(best_idx)
		var cur_cost: int = int(costs[cur])

		for d: Vector2i in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			var nx: int = cur.x + d.x
			var ny: int = cur.y + d.y
			if nx < 0 or nx >= width or ny < 0 or ny >= height:
				continue
			var t: int = int(tiles[ny * width + nx])
			# Integer-Literale statt MapGen.TILE_*: Cross-File-
			# class_name-Konstanten verhalten sich im Android-Export
			# wie die static MapGen.xxx()-Calls (Wert kommt nicht an).
			# 0=GRASS, 1=FOREST, 2=WATER, 3=MOUNTAIN, 4=SAND.
			var step := -1
			if t == 0 or t == 4:
				step = 1
			elif t == 1:
				step = 2
			if step < 0:
				continue
			var next_cost := cur_cost + step
			var key := Vector2i(nx, ny)
			if not costs.has(key) or next_cost < int(costs[key]):
				costs[key] = next_cost
				open.append(key)
	return costs
