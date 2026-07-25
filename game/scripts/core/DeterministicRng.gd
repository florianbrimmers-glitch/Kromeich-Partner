class_name DeterministicRng
extends RefCounted

# Deterministischer RNG auf Basis von Godot's RandomNumberGenerator.
# Derselbe Seed erzeugt dieselbe Zahlenfolge. Wir nutzen bewusst die
# Engine-Klasse statt eigenem xorshift64*, weil Hex-Literale > INT64_MAX
# (z.B. 0xFFFFFFFFFFFFFFFF) in GDScript auf Android crashen koennen.

var _rng: RandomNumberGenerator

func _init(initial_seed: int) -> void:
	_rng = RandomNumberGenerator.new()
	_rng.seed = initial_seed if initial_seed != 0 else 1

func next_u64() -> int:
	return _rng.randi()

func next_int(min_inc: int, max_inc: int) -> int:
	if max_inc <= min_inc:
		return min_inc
	return _rng.randi_range(min_inc, max_inc)

# Save/Load: RNG-Zustand als String, weil RandomNumberGenerator.state
# ein int64 ist und JSON-Zahlen oberhalb 2^53 Praezision verlieren.
func get_state_string() -> String:
	return str(_rng.state)

func set_state_string(s: String) -> void:
	if s != "":
		_rng.state = s.to_int()
