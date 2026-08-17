import types

from events_handler import asana_gateway, config


def _fake_response(payload: dict):
    return types.SimpleNamespace(json=lambda: payload)


def test_bestand_wird_ueber_projekt_gelesen_und_nach_abschnitt_gefiltert(monkeypatch):
    """Der Abschnitts-Endpunkt lieferte in der Praxis unvollständige Listen. Gelesen
    wird deshalb das Projekt; gefiltert wird über memberships.section.gid."""
    ziel = config.section_id()
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method, path, *, json=None, params=None):
        calls.append((method, path, params or {}))
        return _fake_response({"data": [
            {"gid": "1", "name": "Im Ziel-Abschnitt",
             "memberships": [{"section": {"gid": ziel}}]},
            {"gid": "2", "name": "Anderer Abschnitt",
             "memberships": [{"section": {"gid": "999"}}]},
            {"gid": "3", "name": "Mehrfach-Mitgliedschaft",
             "memberships": [{"section": {"gid": "999"}}, {"section": {"gid": ziel}}]},
            {"gid": "4", "name": "Ohne Abschnitt", "memberships": []},
        ]})

    monkeypatch.setattr(asana_gateway, "_request", fake_request)
    tasks = asana_gateway.list_section_tasks()

    assert [t["gid"] for t in tasks] == ["1", "3"]
    # gelesen wird /tasks mit project-Filter, NICHT /sections/:id/tasks
    method, path, params = calls[0]
    assert (method, path) == ("GET", "/tasks")
    assert params["project"] == config.project_id()
    assert "memberships.section.gid" in params["opt_fields"]


def test_bestand_paginiert(monkeypatch):
    ziel = config.section_id()
    seiten = [
        {"data": [{"gid": "1", "name": "Seite 1", "memberships": [{"section": {"gid": ziel}}]}],
         "next_page": {"offset": "abc"}},
        {"data": [{"gid": "2", "name": "Seite 2", "memberships": [{"section": {"gid": ziel}}]}],
         "next_page": None},
    ]
    gesehen: list[str | None] = []

    def fake_request(method, path, *, json=None, params=None):
        gesehen.append((params or {}).get("offset"))
        return _fake_response(seiten[len(gesehen) - 1])

    monkeypatch.setattr(asana_gateway, "_request", fake_request)
    tasks = asana_gateway.list_section_tasks()

    assert [t["gid"] for t in tasks] == ["1", "2"]
    assert gesehen == [None, "abc"]   # zweite Seite wird mit offset geholt


def test_due_on_wird_nur_gesetzt_wenn_vorhanden(monkeypatch):
    gesendet: list[dict] = []

    def fake_request(method, path, *, json=None, params=None):
        gesendet.append({"path": path, "json": json})
        return _fake_response({"data": {"gid": "42", "permalink_url": "https://asana.example/42"}})

    monkeypatch.setattr(asana_gateway, "_request", fake_request)
    monkeypatch.setattr(config, "no_write", lambda: False)

    asana_gateway.create_event_task("08./09.09.2026 Kongress", "notes", due_on="2026-09-08")
    assert gesendet[0]["json"]["data"]["due_on"] == "2026-09-08"

    gesendet.clear()
    asana_gateway.create_event_task("Event ohne Datum", "notes", due_on=None)
    assert "due_on" not in gesendet[0]["json"]["data"]
