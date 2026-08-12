"""Testdaten aus der echten Drive-Datenbasis (erhoben am 12.08.2026).

Die beiden Referenzfälle stammen aus der Asana-Aufgabe, an der die Extraktion
am 09.07.2026 manuell verifiziert wurde:
  - Mileway Bergkamen: 4,58 €/m² + NK 2,15
  - Westcore/Sun Park Bitterfeld: Laufzeitstaffel 4,50 / 4,30 / 4,05 €/m²
"""

from comparables_handler.models import AngebotsOption, DriveDoc, Mietangebot


def doc(
    file_id="f1",
    name="Mileway Indikatives Mietangebot_Q-19647.pdf",
    mime_type="application/pdf",
    size=150474,
    md5=None,
    modified_time="2026-04-07T18:55:43.176Z",
    created_time="2026-04-07T18:55:43.948Z",
    **kw,
) -> DriveDoc:
    return DriveDoc(
        file_id=file_id, name=name, mime_type=mime_type, size=size, md5=md5,
        modified_time=modified_time, created_time=created_time,
        web_link=f"https://drive.google.com/file/d/{file_id}/view", **kw,
    )


def mileway_bergkamen() -> Mietangebot:
    """Referenzfall 1: ein Preis, eine Laufzeit."""
    return Mietangebot(
        ist_mietangebot=True,
        objekt="Mileway Bergkamen",
        adresse="Industriestraße 12",
        plz="59192",
        ort="Bergkamen",
        anbieter="Mileway",
        empfaenger="Kromeich & Partner",
        datum="2026-04-07",
        flaeche_qm=5000.0,
        nutzungsart="Logistik",
        sicherheit="3 Monatsmieten Bürgschaft",
        indexierung="VPI 100%, jährlich",
        eigenes_angebot=False,
        optionen=[
            AngebotsOption(
                laufzeit_monate=60, kaltmiete_eur_qm=4.58,
                nebenkosten_eur_qm=2.15, mietfreie_monate=3,
            )
        ],
        confidence=0.92,
        begruendung="Indikatives Mietangebot mit Konditionen",
    )


def westcore_bitterfeld() -> Mietangebot:
    """Referenzfall 2: Laufzeitstaffel -> drei Zeilen."""
    return Mietangebot(
        ist_mietangebot=True,
        objekt="Sun Park Bitterfeld",
        adresse="Zörbiger Straße 8",
        plz="06749",
        ort="Bitterfeld-Wolfen",
        anbieter="Westcore",
        empfaenger="Brüninghoff",
        datum="2026-06-10",
        flaeche_qm=20000.0,
        nutzungsart="Logistik",
        eigenes_angebot=False,
        optionen=[
            AngebotsOption(laufzeit_monate=60, kaltmiete_eur_qm=4.50, nebenkosten_eur_qm=1.90),
            AngebotsOption(laufzeit_monate=84, kaltmiete_eur_qm=4.30, nebenkosten_eur_qm=1.90),
            AngebotsOption(laufzeit_monate=120, kaltmiete_eur_qm=4.05, nebenkosten_eur_qm=1.90),
        ],
        confidence=0.9,
        begruendung="Laufzeitstaffel über drei Laufzeiten",
    )
