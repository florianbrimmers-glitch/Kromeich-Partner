class_name MapGen
extends RefCounted

# Deterministischer Zufallskarten-Generator.
# Gleicher Seed + gleiche Parameter -> gleiche Karte.
#
# Die Tiles sind ein flaches Array (y*width+x). Wir nutzen bewusst
# einen plain Array[int] statt PackedInt32Array - Packed-Arrays haben
# sich im exportierten Android-Build als problematisch erwiesen (Hang
# bei .resize/.new()).
#
# Generierung in Phasen: make_empty_tiles, place_water, place_mountains,
# coat_with_sand, place_forests, find_spawn. generate() ist der
# Convenience-Wrapper; WorldMapScreen ruft die Phasen einzeln mit
# Diagnostik auf.

const TILE_GRASS := 0
const TILE_FOREST := 1
const TILE_WATER := 2
const TILE_MOUNTAIN := 3
const TILE_SAND := 4
const TILE_SWAMP := 5

const MAX_CLUSTER_ITERATIONS := 500


static func generate(width: int, height: int, rng: DeterministicRng) -> Dictionary:
	var tiles := make_empty_tiles(width, height)
	place_water(tiles, width, height, rng)
	place_mountains(tiles, width, height, rng)
	coat_with_sand(tiles, width, height)
	place_swamps(tiles, width, height, rng)
	place_forests(tiles, width, height, rng)
	var spawn := find_spawn(tiles, width, height)
	return {
		"width": width,
		"height": height,
		"tiles": tiles,
		"hero_spawn": spawn,
	}


static func make_empty_tiles(width: int, height: int) -> Array:
	var tiles: Array = []
	tiles.resize(width * height)
	for i in range(tiles.size()):
		tiles[i] = TILE_GRASS
	return tiles


static func place_water(tiles: Array, width: int, height: int, rng: DeterministicRng) -> void:
	var clusters: int = max(2, int(float(width * height) / 80.0))
	for i in range(clusters):
		grow_cluster(tiles, width, height, TILE_WATER, rng.next_int(8, 18), rng)


static func place_mountains(tiles: Array, width: int, height: int, rng: DeterministicRng) -> void:
	var clusters: int = max(3, int(float(width * height) / 50.0))
	for i in range(clusters):
		grow_cluster(tiles, width, height, TILE_MOUNTAIN, rng.next_int(4, 10), rng)


static func coat_with_sand(tiles: Array, width: int, height: int) -> void:
	var changes: Array = []
	for y in range(height):
		for x in range(width):
			var ti := y * width + x
			if int(tiles[ti]) != TILE_GRASS:
				continue
			if _has_neighbor(tiles, width, height, x, y, TILE_WATER):
				changes.append(ti)
	for ti in changes:
		tiles[ti] = TILE_SAND


static func place_swamps(tiles: Array, width: int, height: int, rng: DeterministicRng) -> void:
	# Sumpf entsteht auf zwei Wegen: (1) 2-3 eigene Inland-Cluster und
	# (2) an der Kueste, indem ein Teil der Sandfelder zu Sumpf wird.
	# Kuesten-Sumpf fuehlt sich organisch an ("Marschland") und bringt
	# taktische Vielfalt in Kuesten-Kaempfe.
	var clusters: int = max(2, int(float(width * height) / 120.0))
	for i in range(clusters):
		grow_cluster(tiles, width, height, TILE_SWAMP, rng.next_int(3, 8), rng)
	for ti in range(tiles.size()):
		if int(tiles[ti]) == TILE_SAND and rng.next_int(0, 99) < 22:
			tiles[ti] = TILE_SWAMP


static func place_forests(tiles: Array, width: int, height: int, rng: DeterministicRng) -> void:
	for i in range(tiles.size()):
		if int(tiles[i]) == TILE_GRASS and rng.next_int(0, 99) < 20:
			tiles[i] = TILE_FOREST


static func find_spawn(tiles: Array, width: int, height: int) -> Vector2i:
	var cx: int = int(width / 2)
	var cy: int = int(height / 2)
	var max_r: int = max(width, height)
	for r in range(max_r):
		for dy in range(-r, r + 1):
			for dx in range(-r, r + 1):
				var x := cx + dx
				var y := cy + dy
				if x < 0 or x >= width or y < 0 or y >= height:
					continue
				if int(tiles[y * width + x]) == TILE_GRASS:
					return Vector2i(x, y)
	return Vector2i(cx, cy)


static func grow_cluster(tiles: Array, width: int, height: int, terrain: int, target_size: int, rng: DeterministicRng) -> void:
	var cx := rng.next_int(0, width - 1)
	var cy := rng.next_int(0, height - 1)
	var frontier: Array = [Vector2i(cx, cy)]
	var placed := 0
	var iterations := 0
	while placed < target_size and not frontier.is_empty() and iterations < MAX_CLUSTER_ITERATIONS:
		iterations += 1
		var idx := rng.next_int(0, frontier.size() - 1)
		var cell: Vector2i = frontier[idx]
		frontier.remove_at(idx)
		if cell.x < 0 or cell.x >= width or cell.y < 0 or cell.y >= height:
			continue
		var ti: int = cell.y * width + cell.x
		if int(tiles[ti]) != TILE_GRASS:
			continue
		tiles[ti] = terrain
		placed += 1
		frontier.append(Vector2i(cell.x + 1, cell.y))
		frontier.append(Vector2i(cell.x - 1, cell.y))
		frontier.append(Vector2i(cell.x, cell.y + 1))
		frontier.append(Vector2i(cell.x, cell.y - 1))


static func _has_neighbor(tiles: Array, width: int, height: int, x: int, y: int, terrain: int) -> bool:
	for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
		var nx := x + d.x
		var ny := y + d.y
		if nx < 0 or nx >= width or ny < 0 or ny >= height:
			continue
		if int(tiles[ny * width + nx]) == terrain:
			return true
	return false


static func terrain_cost(t: int) -> int:
	# -1 = unpassierbar
	match t:
		TILE_GRASS: return 1
		TILE_SAND: return 1
		TILE_FOREST: return 2
		TILE_SWAMP: return 2
		TILE_WATER: return -1
		TILE_MOUNTAIN: return -1
	return 1


static func is_passable(t: int) -> bool:
	return terrain_cost(t) > 0
