"""Tests fuer map_gen.py: Determinismus, Objekt-Placement, Template-Integritaet."""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import map_gen as mg  # noqa: E402


def test_deterministic_same_seed() -> None:
    m1 = mg.generate("duell_klein", seed=42)
    m2 = mg.generate("duell_klein", seed=42)
    assert m1.render_ascii() == m2.render_ascii()
    assert len(m1.objects) == len(m2.objects)
    for a, b in zip(m1.objects, m2.objects):
        assert a == b, f"Objekt-Mismatch: {a} vs {b}"


def test_different_seeds_diverge() -> None:
    m1 = mg.generate("duell_klein", seed=1)
    m2 = mg.generate("duell_klein", seed=99)
    assert m1.render_ascii() != m2.render_ascii()


def test_player_starts_have_town_and_hero() -> None:
    m = mg.generate("duell_klein", seed=42)
    towns = [o for o in m.objects if o.kind == "town"]
    heroes = [o for o in m.objects if o.kind == "hero"]
    assert len(towns) == 2, f"Erwarte 2 Staedte, habe {len(towns)}"
    assert len(heroes) == 2, f"Erwarte 2 Helden, habe {len(heroes)}"
    for t in towns:
        assert t.owner in (0, 1)
    for h in heroes:
        assert h.owner in (0, 1)


def test_grosses_template_hat_3_spieler() -> None:
    m = mg.generate("familie_mittel", seed=42)
    towns = [o for o in m.objects if o.kind == "town"]
    assert len(towns) == 3
    assert {t.owner for t in towns} == {0, 1, 2}


def test_map_size_matches_template() -> None:
    m = mg.generate("duell_klein", seed=42)
    assert m.width == 24 and m.height == 24
    m = mg.generate("familie_mittel", seed=42)
    assert m.width == 36 and m.height == 36


def test_all_objects_within_bounds() -> None:
    m = mg.generate("duell_klein", seed=42)
    for o in m.objects:
        assert 0 <= o.x < m.width, f"x={o.x} out of bounds"
        assert 0 <= o.y < m.height, f"y={o.y} out of bounds"


def test_template_json_has_expected_ids() -> None:
    data = json.loads((ROOT / "data" / "map_templates.json").read_text())
    ids = {t["id"] for t in data["templates"]}
    assert {"duell_klein", "familie_mittel"} <= ids
