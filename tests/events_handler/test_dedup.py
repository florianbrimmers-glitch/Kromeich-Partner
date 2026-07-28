import types

from events_handler import dedup
from events_handler.models import Event

# Der reale Fall: dasselbe Event kam als Einzel-Einladung UND im Sammel-Newsletter,
# in abweichender Schreibweise ("8. und 9. September 2026 … – …" vs. "08. und 09. September … / …").
EXISTING = [
    {"gid": "111", "name": "8. und 9. September 2026 Zukunftskongress Logistik – 44. Dortmunder Gespräche"},
    {"gid": "222", "name": "24.-26.03 LogiMat"},
]


def _event(name="Zukunftskongress Logistik / 44. Dortmunder Gespräche",
           datum="08. und 09. September") -> Event:
    return Event(ist_event=True, datum=datum, event_name=name, ort="Dortmund", confidence=0.9)


def _patch(monkeypatch, text: str):
    msg = types.SimpleNamespace(content=[types.SimpleNamespace(text=text)])
    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=lambda **kw: msg))
    monkeypatch.setattr(dedup, "_get_client", lambda: client)


def test_no_existing_tasks_no_api_call():
    gid, _ = dedup.find_duplicate(_event(), [])
    assert gid is None


def test_recognises_duplicate_despite_different_spelling(monkeypatch):
    _patch(monkeypatch, '{"duplikat_gid": "111", "begruendung": "gleicher Termin, andere Schreibweise"}')
    gid, grund = dedup.find_duplicate(_event(), EXISTING)
    assert gid == "111"
    assert grund


def test_new_event_is_not_a_duplicate(monkeypatch):
    _patch(monkeypatch, '{"duplikat_gid": null, "begruendung": "steht noch nicht in der Liste"}')
    gid, _ = dedup.find_duplicate(_event("Expo Real", "06.-08.10"), EXISTING)
    assert gid is None


def test_hallucinated_gid_is_not_treated_as_duplicate(monkeypatch):
    """Nennt die KI eine unbekannte gid, darf das Event NICHT verworfen werden."""
    _patch(monkeypatch, '{"duplikat_gid": "999", "begruendung": "halluziniert"}')
    gid, grund = dedup.find_duplicate(_event(), EXISTING)
    assert gid is None
    assert "999" in grund


def test_unparsable_answer_creates_task(monkeypatch):
    """Bei Parsefehler lieber anlegen als ein Event verlieren."""
    _patch(monkeypatch, "kein json")
    gid, _ = dedup.find_duplicate(_event(), EXISTING)
    assert gid is None


def test_fenced_json_is_parsed(monkeypatch):
    _patch(monkeypatch, '```json\n{"duplikat_gid": "111", "begruendung": "ok"}\n```')
    gid, _ = dedup.find_duplicate(_event(), EXISTING)
    assert gid == "111"
