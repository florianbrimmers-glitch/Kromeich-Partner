"""Gekürzte, aber echte Propstack-Antworten – abgerufen am 20.08.2026.

Wichtig für die Tests: /units liefert `title` als Custom-Field-Objekt, `created_at` nur
mit expand=1, und die Antwort kommt je Endpunkt als {"data": [...]} oder als nackte Liste.
"""

# GET /v1/units?expand=1&with_meta=1&created_at_from=...
UNITS_RESPONSE = {
    "data": [
        {
            "id": 5802066,
            "title": {"label": "Überschrift", "value": "Lagerhalle in (89) Giengen an der Benz"},
            "address": "Frostelstraße , 89537 Giengen an der Brenz, Deutschland",
            "city": {"label": "Stadt", "value": "Giengen an der Brenz"},
            "property_space_value": 10197.0,
            "marketing_type": "BUY",
            "project_id": None,
            "created_at": "2026-08-14T09:12:00.000+02:00",
        },
        {
            "id": 5813977,
            "title": {"label": "Überschrift", "value": "Logistikflächen in (41) Kaarst"},
            "address": "An der Gümpgesbrücke 24, 41564 Kaarst, Deutschland",
            "property_space_value": 4200.0,
            "marketing_type": "RENT",
            "project_id": 570215,
            "created_at": "2026-08-17T15:39:39.244+02:00",
        },
        {
            "id": 5814044,
            "title": "Logistikflächen in (41) Kaarst – Halle B",
            "property_space_value": 8200.5,
            "project_id": 570215,
            "created_at": "2026-08-17T15:48:46.262+02:00",
        },
        {
            # Außerhalb des Fensters – der Serverfilter ist nur tagesgenau, der exakte
            # Schnitt muss clientseitig fallen.
            "id": 5700001,
            "title": "Zu alt",
            "project_id": 554679,
            "created_at": "2026-08-12T23:59:00.000+02:00",
        },
    ],
    "meta": {"total_count": 4},
}

# GET /v1/projects – nackte Liste, ohne jeden Zeitstempel
PROJECTS_RESPONSE = [
    {"id": 570215, "title": "Logistikflächen in (41) Kaarst", "address": "An der Gümpgesbrücke 24"},
    {"id": 554679, "title": "Halle in (44) Bochum", "address": "Wittener Straße 1"},
]

# GET /v1/activities?item_type=reminder&broker_id=254958&sort_by=updated_at&order=desc
ACTIVITIES_RESPONSE = {
    "data": [
        {
            "id": 447177220,
            "title": "Flächenupdate abgleichen: Panattoni",
            "done": True,
            "broker_id": 254958,
            "original_created_at": "2026-07-21T07:22:53.000+02:00",
            "updated_at": "2026-08-17T14:52:15.335+02:00",
            "property_names": ["Panattoni Park Friedewald"],
            "project_names": [],
        },
        {
            "id": 447177233,
            "title": "Newsletter-Vermietung prüfen: Prologis Park Waltershof",
            "done": None,
            "broker_id": 254958,
            "original_created_at": "2026-08-10T10:36:00.000+02:00",
            "updated_at": "2026-08-17T11:38:00.000+02:00",
            "property_names": [],
            "project_names": ["Prologis Park Waltershof"],
        },
        {
            "id": 447177999,
            "title": "Frisch angelegt, nie angefasst",
            "done": None,
            "broker_id": 254958,
            "original_created_at": "2026-08-16T08:00:00.000+02:00",
            "updated_at": "2026-08-16T08:00:00.000+02:00",
        },
        {
            # Vor dem Fenster – ab hier darf die Paginierung abbrechen.
            "id": 440000001,
            "title": "Alte Aufgabe",
            "done": True,
            "broker_id": 254958,
            "original_created_at": "2026-03-29T09:06:11.000+02:00",
            "updated_at": "2026-07-20T17:56:26.000+02:00",
        },
    ],
    "meta": {"total_count": 4},
}
