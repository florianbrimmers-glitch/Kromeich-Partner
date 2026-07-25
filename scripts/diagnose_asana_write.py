"""Einmal-Diagnose: prüft den echten Asana-Schreibweg des Events-Handlers.

Legt EINE klar markierte Test-Aufgabe im Ziel-Abschnitt an, liest sie zurück und
löscht sie sofort wieder – es bleibt nichts in der Liste stehen. Damit werden der
ASANA_ACCESS_TOKEN, der REST-Client und die Projekt-/Abschnitts-IDs verifiziert.
"""
from __future__ import annotations

from events_handler import config
from events_handler.asana_gateway import _request, build_task, create_event_task
from events_handler.models import Event

TEST_EVENT = Event(
    ist_event=True,
    datum="24.-26.03",
    event_name="[TEST Claude – wird sofort gelöscht] LogiMat",
    branche="Logistik",
    ort="Stuttgart",
    kosten="kostenlos",
    anmeldelink="https://logimat.example/anmeldung",
    confidence=0.9,
)


def main() -> None:
    print("=" * 70)
    print("Projekt :", config.project_id())
    print("Abschnitt:", config.section_id())
    print("=" * 70)

    name, notes = build_task(TEST_EVENT, "https://slack.example/p123")
    print("\nName :", name)
    print("Notes:\n" + notes)

    url = create_event_task(name, notes)
    print("\n--> angelegt:", url)
    if not url:
        print("FEHLER: keine URL – lief der Job versehentlich mit NO_WRITE?")
        return

    task_gid = url.rstrip("/").split("/")[-1]

    # Zurücklesen: liegt die Aufgabe wirklich im Ziel-Abschnitt?
    data = _request(
        "GET", f"/tasks/{task_gid}",
        params={"opt_fields": "name,notes,memberships.section.name,memberships.project.name"},
    ).json()["data"]
    print("\n--- zurückgelesen ---")
    print("name        :", data.get("name"))
    for m in data.get("memberships", []):
        print("Projekt/Abschnitt:", (m.get("project") or {}).get("name"),
              "/", (m.get("section") or {}).get("name"))

    # Aufräumen: Test-Aufgabe wieder löschen
    _request("DELETE", f"/tasks/{task_gid}")
    print("\n--> Test-Aufgabe gelöscht (Liste bleibt sauber)")
    print("=" * 70)


if __name__ == "__main__":
    main()
