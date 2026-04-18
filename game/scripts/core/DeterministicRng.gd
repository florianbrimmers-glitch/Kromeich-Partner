class_name DeterministicRng
extends RefCounted

# xorshift64*-RNG, identisch zu DeterministicRng.cs. Derselbe Seed
# erzeugt dieselbe Zahlenfolge auf allen Plattformen.

var _state: int

func _init(seed: int) -> void:
	_state = seed if seed != 0 else 1

func next_u64() -> int:
	var s := _state
	s ^= (s << 13) & 0xFFFFFFFFFFFFFFFF
	s ^= (s >> 7)
	s ^= (s << 17) & 0xFFFFFFFFFFFFFFFF
	_state = s
	return s

func next_int(min_inc: int, max_inc: int) -> int:
	if max_inc <= min_inc:
		return min_inc
	var range_size := max_inc - min_inc + 1
	return min_inc + int(next_u64() % range_size)
