from comparables_handler import aggregate, normalize
from comparables_handler.models import AngebotsOption

from .fixtures import doc, mileway_bergkamen, westcore_bitterfeld


def _zeilen_mit_mieten(plz: str, mieten: list[float], anbieter="Mileway"):
    angebot = mileway_bergkamen()
    angebot.plz = plz
    angebot.anbieter = anbieter
    angebot.optionen = [
        AngebotsOption(laufzeit_monate=60 + 12 * i, kaltmiete_eur_qm=m)
        for i, m in enumerate(mieten)
    ]
    return normalize.zu_zeilen(doc(name=f"{plz}.pdf"), angebot)


def test_median_und_spanne_pro_region():
    zeilen = _zeilen_mit_mieten("59192", [4.00, 4.58, 5.20])
    stats = aggregate.aggregiere(zeilen)
    leit = aggregate.leitregionen(stats)
    assert len(leit) == 1
    assert leit[0].key == "59"
    assert leit[0].median_kaltmiete == 4.58
    assert leit[0].min_kaltmiete == 4.00
    assert leit[0].max_kaltmiete == 5.20
    assert leit[0].n == 3


def test_median_bei_gerader_anzahl():
    zeilen = _zeilen_mit_mieten("59192", [4.00, 4.50, 4.60, 5.00])
    leit = aggregate.leitregionen(aggregate.aggregiere(zeilen))
    assert leit[0].median_kaltmiete == 4.55


def test_duenne_leitregion_erscheint_nur_in_der_zone():
    """Bei n<3 ist eine 2-stellige PLZ nicht aussagekräftig."""
    zeilen = _zeilen_mit_mieten("59192", [4.50, 4.60])
    stats = aggregate.aggregiere(zeilen)
    assert aggregate.leitregionen(stats) == []
    zonen = aggregate.zonen(stats)
    assert len(zonen) == 1
    assert zonen[0].key == "5"
    assert zonen[0].n == 2


def test_zone_bündelt_mehrere_leitregionen():
    zeilen = _zeilen_mit_mieten("59192", [4.50, 4.60]) + _zeilen_mit_mieten("57299", [5.00, 5.40])
    stats = aggregate.aggregiere(zeilen)
    zonen = aggregate.zonen(stats)
    assert len(zonen) == 1
    assert zonen[0].key == "5"
    assert zonen[0].n == 4
    assert zonen[0].median_kaltmiete == 4.80


def test_ausgeschlossene_zeilen_gehen_nicht_in_die_statistik():
    zeilen = _zeilen_mit_mieten("59192", [4.50, 4.60, 4.70])
    zeilen += _zeilen_mit_mieten("59192", [458.0])  # Komma-Fehler
    stats = aggregate.aggregiere(zeilen)
    leit = aggregate.leitregionen(stats)
    assert leit[0].n == 3
    assert leit[0].max_kaltmiete == 4.70


def test_n_objekte_unterscheidet_sich_von_n_zeilen():
    """Eine Laufzeitstaffel ist EIN Objekt, aber drei Datenpunkte."""
    zeilen = normalize.zu_zeilen(doc(name="sun.pdf"), westcore_bitterfeld())
    stats = aggregate.aggregiere(zeilen)
    leit = aggregate.leitregionen(stats)
    assert leit[0].n == 3
    assert leit[0].n_objekte == 1


def test_eigene_und_erhaltene_werden_getrennt_gezaehlt():
    erhalten = _zeilen_mit_mieten("59192", [4.50, 4.60, 4.70])
    eigen = _zeilen_mit_mieten("59192", [5.00], anbieter="Kromeich & Partner")
    for zeile in eigen:
        zeile.eigenes_angebot = True
    stats = aggregate.aggregiere(erhalten + eigen)
    gesamt = aggregate.gesamt(stats)
    assert gesamt.n_eigene == 1
    assert gesamt.n_erhalten == 3


def test_gesamtzeile_umfasst_alle_regionen():
    zeilen = _zeilen_mit_mieten("59192", [4.00, 4.50]) + _zeilen_mit_mieten("06749", [5.00, 5.50])
    gesamt = aggregate.gesamt(aggregate.aggregiere(zeilen))
    assert gesamt.n == 4
    assert gesamt.median_kaltmiete == 4.75
    assert gesamt.min_kaltmiete == 4.00
    assert gesamt.max_kaltmiete == 5.50


def test_juengstes_datum_wird_ausgewiesen():
    zeilen = _zeilen_mit_mieten("59192", [4.50, 4.60, 4.70])
    zeilen[0].datum = "2026-01-01"
    zeilen[1].datum = "2026-07-15"
    gesamt = aggregate.gesamt(aggregate.aggregiere(zeilen))
    assert gesamt.jüngstes_datum == "2026-07-15"


def test_ohne_verwertbare_zeilen_keine_statistik():
    assert aggregate.aggregiere([]) == []
    unverwertbar = _zeilen_mit_mieten("59192", [458.0])
    assert aggregate.aggregiere(unverwertbar) == []


def test_effektivmiete_median_wird_gebildet():
    angebot = mileway_bergkamen()
    angebot.optionen = [
        AngebotsOption(laufzeit_monate=60, kaltmiete_eur_qm=4.58, mietfreie_monate=3),
        AngebotsOption(laufzeit_monate=120, kaltmiete_eur_qm=4.05, mietfreie_monate=6),
    ]
    stats = aggregate.aggregiere(normalize.zu_zeilen(doc(), angebot))
    gesamt = aggregate.gesamt(stats)
    # 4,35 und 3,85 -> Median 4,10
    assert gesamt.median_effektivmiete == 4.10


def test_standorte_werden_ueber_die_adresse_gezaehlt():
    """Propstack führt Multi-Unit-Standorte mit gleichem Objektnamen.
    Über den Namen gruppiert wären das fälschlich '1 Objekt'."""
    zeilen = _zeilen_mit_mieten("59192", [4.50, 4.60, 4.70])
    for i, zeile in enumerate(zeilen):
        zeile.objekt = "Logistikpark Bergkamen"      # gleicher Name ...
        zeile.adresse = f"Musterweg {i + 1}"         # ... verschiedene Adressen
    stats = aggregate.leitregionen(aggregate.aggregiere(zeilen))
    assert stats[0].n == 3
    assert stats[0].n_objekte == 3
