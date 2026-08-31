class_name Pathfinder
extends RefCounted

# Dijkstra auf einem Tile-Grid mit Terrain-Kosten. Keine Diagonalen.
# Nutzung: compute_costs(map, start) -> Dictionary {Vector2i -> int_cost}.
# Start hat Kosten 0; nicht-erreichbare Felder fehlen im Dictionary.
#
# Kosten kommen aus core/Movement.gd (M7 Teil 2). Vorher standen hier
# eigene Integer-Literale - und die kannten den Sumpf nicht, ein Feld das
# es seit der Sumpf-Kachel gibt: er galt als unpassierbar.

const Move := preload("res://scripts/core/Movement.gd")


static func compute_costs(map: Dictionary, start: Vector2i,
		pathfinding_tier: int = 0) -> Dictionary:
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
			# preload-Modul statt class_name: static-Calls ueber
			# class_name sind im Android-Export historisch unzuverlaessig
			# (Wert kommt nicht an), preload-Konstanten nicht.
			var step: int = Move.step_cost(t, pathfinding_tier)
			if step < 0:
				continue
			var next_cost := cur_cost + step
			var key := Vector2i(nx, ny)
			if not costs.has(key) or next_cost < int(costs[key]):
				costs[key] = next_cost
				open.append(key)
	return costs
