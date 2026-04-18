"""Daten-Integritaet: skills.json."""
from __future__ import annotations

import json
import pathlib

DATA = pathlib.Path(__file__).resolve().parent.parent / "data" / "skills.json"


def _load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_primary_skills_have_required_fields() -> None:
    data = _load()
    assert len(data["primary_skills"]) == 4
    for s in data["primary_skills"]:
        for k in ("id", "name", "per_level_bonus", "stat_effect", "description"):
            assert k in s, f"Primary-Skill {s.get('id')} fehlt {k}"


def test_secondary_skills_tier_progression_is_monotone() -> None:
    data = _load()
    assert len(data["secondary_skills"]) >= 8
    for s in data["secondary_skills"]:
        levels = [t["level"] for t in s["tiers"]]
        assert levels == [1, 2, 3], f"{s['id']} hat nicht genau 3 Tiers"


def test_leadership_and_necromancy_conflict() -> None:
    data = _load()
    by_id = {s["id"]: s for s in data["secondary_skills"]}
    assert "necromancy" in by_id["leadership"].get("conflicts_with", [])
    assert "leadership" in by_id["necromancy"].get("conflicts_with", [])


def test_level_up_policy_has_exp_table() -> None:
    data = _load()
    policy = data["level_up_policy"]
    assert len(policy["exp_per_level"]) == 10
    # Monotone Increase
    exp = policy["exp_per_level"]
    for i in range(1, len(exp)):
        assert exp[i] > exp[i - 1], f"Exp-Table nicht monoton bei Index {i}"


def test_all_primary_skill_ids_are_unique() -> None:
    data = _load()
    ids = [s["id"] for s in data["primary_skills"]]
    assert len(set(ids)) == len(ids)


def test_all_secondary_skill_ids_are_unique() -> None:
    data = _load()
    ids = [s["id"] for s in data["secondary_skills"]]
    assert len(set(ids)) == len(ids)
