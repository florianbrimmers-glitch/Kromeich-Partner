from events_handler import config
from events_handler.models import Event
from events_handler.sheets import build_row


def test_build_row_column_order_and_empty_judgment_columns():
    event = Event(
        ist_event=True, datum="04.10.2026", event_name="Alpenländisch meets Real Estate",
        branche="Immobilien", ort="Tegernsee", kosten="kostenlos", confidence=0.9,
    )
    row = build_row(event, "https://slack.example/permalink")

    # exakt 8 Spalten in der Reihenfolge der Tabelle
    assert len(row) == len(config.SHEET_COLUMNS) == 8
    assert row[0] == "04.10.2026"          # Datum
    assert row[1] == "Alpenländisch meets Real Estate"  # Event
    assert row[2] == "Immobilien"          # Branche
    assert row[3] == "Tegernsee"           # Ort
    assert row[4] == "kostenlos"           # Kosten
    assert row[5] == ""                     # Funktion KP – leer für Mensch
    assert row[6] == ""                     # Spannend für – leer für Mensch
    assert row[7] == "https://slack.example/permalink"  # Notiz / Link


def test_build_row_handles_missing_fields():
    event = Event(ist_event=True, event_name="Webinar", confidence=0.7)
    row = build_row(event, "")
    assert row[0] == ""   # kein Datum
    assert row[1] == "Webinar"
    assert all(isinstance(c, str) for c in row)   # nie None (Sheets-API-safe)
