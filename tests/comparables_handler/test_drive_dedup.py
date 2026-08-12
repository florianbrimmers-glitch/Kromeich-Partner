"""Datei-Dedup: dasselbe Angebot liegt im Drive mehrfach.

Gemessen am 12.08.2026: die Titelsuche 'Mietangebot' liefert ~70 Treffer, aber
nur ~22 physisch verschiedene Dokumente. Ohne diesen Schritt würde jede Kopie
einzeln an Claude geschickt.
"""

from comparables_handler import drive_gateway

from .fixtures import doc


def test_md5_ist_der_dedup_schluessel():
    a = doc(file_id="a", md5="abc123")
    b = doc(file_id="b", md5="abc123")
    assert a.dedup_key() == b.dedup_key()


def test_ohne_md5_zaehlt_groesse_und_mime():
    a = doc(file_id="a", size=150474)
    b = doc(file_id="b", size=150474)
    c = doc(file_id="c", size=150475)
    assert a.dedup_key() == b.dedup_key()
    assert a.dedup_key() != c.dedup_key()


def test_ohne_groesse_bleibt_die_datei_eigenstaendig():
    """Kein Zusammenlegen auf Verdacht – lieber ein Call zu viel."""
    a = doc(file_id="a", size=None)
    b = doc(file_id="b", size=None)
    assert a.dedup_key() != b.dedup_key()


def test_original_wird_der_kopie_vorgezogen():
    """'(1)' im Namen markiert die Kopie – der klare Name gewinnt."""
    original = doc(file_id="a", name="2026-01-13 Mietangebot_Flex City_L.I.T..pdf",
                   created_time="2026-01-13T17:19:39Z")
    kopie = doc(file_id="b", name="2026-01-13 Mietangebot_Flex City_L.I.T. (1).pdf",
                created_time="2026-02-04T18:04:34Z")
    assert min(original, kopie, key=drive_gateway._copy_score) is original
    assert min(kopie, original, key=drive_gateway._copy_score) is original


def test_bei_gleichem_namen_gewinnt_der_aeltere_eintrag():
    frueh = doc(file_id="a", name="Mietangebot_EAE_Final.pdf", created_time="2025-07-28T08:21:09Z")
    spaet = doc(file_id="b", name="Mietangebot_EAE_Final.pdf", created_time="2026-08-01T06:31:55Z")
    assert min(spaet, frueh, key=drive_gateway._copy_score) is frueh


def test_discovery_fasst_mehrfachablagen_zusammen(monkeypatch):
    """Der reale Mileway-Fall: dieselbe Datei liegt in drei Ordnern."""
    treffer = [
        {"id": "1", "name": "Mileway Indikatives Mietangebot_Q-19647.pdf",
         "mimeType": "application/pdf", "size": "150474", "md5Checksum": "m1",
         "createdTime": "2026-03-31T15:21:15Z", "modifiedTime": "2026-04-07T19:31:20Z"},
        {"id": "2", "name": "Mileway Indikatives Mietangebot_Q-19647.pdf",
         "mimeType": "application/pdf", "size": "150474", "md5Checksum": "m1",
         "createdTime": "2026-04-07T18:55:43Z", "modifiedTime": "2026-04-07T18:55:43Z"},
        {"id": "3", "name": "Mileway Indikatives Mietangebot_Q-19647.pdf",
         "mimeType": "application/pdf", "size": "150474", "md5Checksum": "m1",
         "createdTime": "2026-08-01T06:30:58Z", "modifiedTime": "2026-08-01T06:30:58Z"},
        {"id": "4", "name": "Mietangebot_EAE_Final.pdf",
         "mimeType": "application/pdf", "size": "218195", "md5Checksum": "m2",
         "createdTime": "2025-07-28T08:21:09Z", "modifiedTime": "2025-07-28T11:03:46Z"},
    ]
    monkeypatch.setattr(drive_gateway, "_list", lambda query: treffer if "name contains" in query else [])
    monkeypatch.setattr(drive_gateway.config, "SEED_FOLDER_IDS", ())

    docs, rohtreffer, kopien = drive_gateway.discover_documents()
    assert rohtreffer == 4
    assert kopien == 2
    assert len(docs) == 2
    mileway = next(d for d in docs if "Mileway" in d.name)
    assert mileway.fundstellen == 3
    assert mileway.file_id == "1"   # ältester Eintrag = Original


def test_ordner_und_titelsuche_zaehlen_dieselbe_datei_nur_einmal(monkeypatch):
    datei = {
        "id": "1", "name": "Mietangebot HIH", "mimeType": "application/pdf",
        "size": "1172899", "md5Checksum": "m1",
        "createdTime": "2026-06-24T17:38:44Z", "modifiedTime": "2026-06-24T18:19:50Z",
    }

    def fake_list(query: str):
        if "name contains" in query:
            return [datei]
        if "in parents" in query:
            return [datei]
        return []

    monkeypatch.setattr(drive_gateway, "_list", fake_list)
    monkeypatch.setattr(drive_gateway.config, "SEED_FOLDER_IDS", ("ordner1",))

    docs, rohtreffer, kopien = drive_gateway.discover_documents()
    assert rohtreffer == 2      # zwei Rohtreffer (Titel + Ordner) ...
    assert kopien == 0          # ... aber keine Mehrfachablage im Drive
    assert len(docs) == 1       # dieselbe file_id zählt nur einmal
