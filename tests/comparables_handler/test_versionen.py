"""Versions-Dedup: 'Duplikate/Versionen deduplizieren (jüngste zählt)'.

Realer Fall aus dem Drive: das VIR21-Angebot für IMC Pro Logistics liegt in
drei Fassungen (16.03., 20.03., 30.04.2026) mit unterschiedlichem Inhalt.
"""

from comparables_handler import normalize

from .fixtures import doc, mileway_bergkamen, westcore_bitterfeld


def _vir21(datum: str, name: str, modified: str):
    angebot = mileway_bergkamen()
    angebot.objekt = "IMC Pro Logistics"
    angebot.adresse = "Am Logistikpark 3"
    angebot.plz = "44145"
    angebot.anbieter = "VIR21"
    angebot.datum = datum
    return doc(file_id=name, name=name, modified_time=modified), angebot


VERSIONEN = [
    _vir21("2026-03-16", "26-03-16 VIR21 Indikatives Mietangebot IMC Pro Logistics.pdf",
           "2026-03-19T21:05:08.941Z"),
    _vir21("2026-03-20", "26-03-20 VIR21 Indikatives Mietangebot IMC Pro Logistics.pdf",
           "2026-03-23T12:56:12.663Z"),
    _vir21("2026-04-30", "26-04-30 VIR21 Indikatives Mietangebot IMC Pro Logistics.pdf",
           "2026-05-07T15:41:24.380Z"),
]


def test_nur_die_juengste_version_zaehlt():
    behalten, verworfen = normalize.dedupliziere_versionen(list(VERSIONEN))
    assert len(behalten) == 1
    assert behalten[0][1].datum == "2026-04-30"
    assert len(verworfen) == 2
    assert all("jüngste Fassung" in grund for _, grund in verworfen)


def test_reihenfolge_der_eingabe_ist_irrelevant():
    behalten, _ = normalize.dedupliziere_versionen(list(reversed(VERSIONEN)))
    assert behalten[0][1].datum == "2026-04-30"


def test_verschiedene_objekte_bleiben_erhalten():
    paare = [VERSIONEN[0], (doc(file_id="sun"), westcore_bitterfeld())]
    behalten, verworfen = normalize.dedupliziere_versionen(paare)
    assert len(behalten) == 2
    assert verworfen == []


def test_ohne_datum_entscheidet_die_drive_aenderungszeit():
    alt = _vir21(None, "alt.pdf", "2026-01-01T00:00:00Z")
    neu = _vir21(None, "neu.pdf", "2026-06-01T00:00:00Z")
    behalten, verworfen = normalize.dedupliziere_versionen([alt, neu])
    assert len(behalten) == 1
    assert behalten[0][0].name == "neu.pdf"


def test_gleiches_objekt_verschiedene_anbieter_wird_nicht_zusammengelegt():
    """Zwei Anbieter für dieselbe Adresse sind zwei echte Datenpunkte."""
    a_doc, a = _vir21("2026-03-16", "a.pdf", "2026-03-16T00:00:00Z")
    b_doc, b = _vir21("2026-04-30", "b.pdf", "2026-04-30T00:00:00Z")
    b.anbieter = "Mileway"
    behalten, _ = normalize.dedupliziere_versionen([(a_doc, a), (b_doc, b)])
    assert len(behalten) == 2


def test_ohne_objektkennung_wird_nicht_gruppiert():
    """Lieber eine Dublette als ein verlorenes Angebot."""
    paare = []
    for i in range(3):
        angebot = mileway_bergkamen()
        angebot.objekt = None
        angebot.adresse = None
        angebot.plz = None
        paare.append((doc(file_id=f"f{i}", name=f"f{i}.pdf"), angebot))
    behalten, verworfen = normalize.dedupliziere_versionen(paare)
    assert len(behalten) == 3
    assert verworfen == []
