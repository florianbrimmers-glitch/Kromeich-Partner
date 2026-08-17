from events_handler.asana_gateway import build_task
from events_handler.models import Event

PERMALINK = "https://slack.example/permalink"


def test_name_follows_section_convention():
    """Aufgaben heißen '<Datum> <Event>' – Datum im einheitlichen deutschen Kurzformat."""
    event = Event(ist_event=True, datum="04.10.2026", datum_kompakt="04.10.2026",
                  event_name="Alpenländisch meets Real Estate",
                  branche="Immobilien", ort="Tegernsee", kosten="kostenlos", confidence=0.9)
    name, notes = build_task(event, PERMALINK)

    assert name == "04.10.2026 Alpenländisch meets Real Estate"
    assert "Branche: Immobilien" in notes
    assert "Ort: Tegernsee" in notes
    assert "Kosten (nur Ticket): kostenlos" in notes
    assert PERMALINK in notes


def test_judgment_columns_stay_out_of_notes():
    """'Funktion KP'/'Spannend für' füllt ein Mensch – die KI trägt dort nichts ein."""
    event = Event(ist_event=True, datum="01.02.2026", event_name="Logistik-Gipfel", confidence=0.8)
    _, notes = build_task(event, PERMALINK)

    assert "Funktion KP:" not in notes
    assert "Spannend für:" not in notes
    # Hinweis für den Menschen ist aber enthalten
    assert "manuell" in notes.lower()


def test_missing_fields_are_omitted_not_none():
    event = Event(ist_event=True, event_name="Webinar", confidence=0.7)
    name, notes = build_task(event, "")

    assert name == "Webinar"          # kein Datum -> nur der Name, kein "None"
    assert "None" not in notes
    assert "Ort:" not in notes        # leere Felder werden weggelassen
    assert "Quelle" not in notes      # kein Permalink -> keine leere Quellzeile


def test_name_never_empty():
    """Ohne Datum und Namen darf kein leerer Aufgaben-Name entstehen (Asana lehnt das ab)."""
    name, _ = build_task(Event(ist_event=True, confidence=0.5), "")
    assert name.strip()


def test_anmeldelink_in_notes():
    event = Event(ist_event=True, datum="10.03.2026", event_name="LogiMat",
                  anmeldelink="https://logimat.example/anmeldung", confidence=0.9)
    _, notes = build_task(event, PERMALINK)
    assert "https://logimat.example/anmeldung" in notes


def test_kompaktes_datum_gewinnt_gegen_originalschreibweise():
    """Die Liste soll einheitlich sein: '3. und 4. September 2026' bzw.
    '14 and 15 October 2026' dürfen nicht im Namen landen."""
    event = Event(ist_event=True, datum="3. und 4. September 2026",
                  datum_kompakt="03./04.09.2026", datum_iso="2026-09-03",
                  event_name="Summer Camp 2026 – Reinventing Germany", confidence=0.9)
    name, _ = build_task(event, PERMALINK)
    assert name == "03./04.09.2026 Summer Camp 2026 – Reinventing Germany"

    englisch = Event(ist_event=True, datum="14 and 15 October 2026",
                     datum_kompakt="14./15.10.2026", datum_iso="2026-10-14",
                     event_name="Handelsblatt Conference „Corporate Climate Adaptation“",
                     confidence=0.9)
    name, _ = build_task(englisch, PERMALINK)
    assert name.startswith("14./15.10.2026 ")
    assert "October" not in name


def test_fallback_auf_originaldatum_wenn_kompakt_fehlt():
    """Liefert die KI kein Kurzformat, ist die Originalschreibweise besser als kein Datum."""
    event = Event(ist_event=True, datum="16./17.06", event_name="Real Estate Arena", confidence=0.8)
    name, _ = build_task(event, PERMALINK)
    assert name == "16./17.06 Real Estate Arena"
