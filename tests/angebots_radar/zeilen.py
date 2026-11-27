"""Beispielzeilen so, wie Propstack sie am 26.11.2026 geliefert hat (gekürzt auf die genutzten
Felder). Kundennamen stehen nicht im Repo – die Texte der Suchprofile sind die echten, ohne
Personen- und Firmennamen."""
from __future__ import annotations


def cf(**werte) -> dict:
    return {k: {"value": v, "pretty_value": None if v is None else str(v)} for k, v in werte.items()}


def suchprofil(id=11072931, kontakt=28988960, text="", notiz="", lagerflache=None, aktiv=True, aktiv_feld=(182817,),
               lat=None, lng=None, radius=None, polygon=None, orte=None, laender=None, vermarktung="RENT",
               typen=("INDUSTRY",), angelegt="2026-03-06", bearbeitet=None, betreuer=387451, **felder) -> dict:
    return {
        "id": id, "client_id": kontakt, "broker_id": betreuer, "active": aktiv,
        "created_at": f"{angelegt}T09:51:03.245+01:00", "updated_at": f"{bearbeitet or angelegt}T15:19:03.200+02:00",
        "lat": lat, "lng": lng, "radius": radius, "polygon": polygon, "cities": orte, "regions": laender,
        "marketing_type": vermarktung, "rs_types": list(typen), "note": notiz, "public_note": text,
        "custom_fields": cf(lagerflache=lagerflache, aktiv=list(aktiv_feld) if aktiv_feld else None, wgk=None, batterielager=None),
        **felder,
    }


# Suchprofil 11072931 (06.03.2026): die Vorlage des Teams, vollständig ausgefüllt
WERMELSKIRCHEN = suchprofil(
    text="▪️Wermelskirchen, Umkreis 30 km\n▪️Textilien\n▪️ ~8.000 - 12.000 m² Hallenfläche \n▪️ ~800 - 1.000 m² Bürofläche \n"
         "▪️ mind. 9m Deckenhöhe \n▪️ mind. 4 Rampen\n▪️ 2 Schichtbetrieb, kein 24/7\n▪️ab Sommer 2027\n▪️über 10 Jahre",
    notiz="Herkunft: Tippgeber\n", lagerflache=8000.0, lat=51.14010386809591, lng=7.218892463476565, radius=25326,
)


def einheit(id=5159361, name="Am Weidenbroich 20-22 - Remscheid", titel="Logistikhalle in (42) Remscheid",
            strasse="Am Weidenbroich", hausnummer=None, plz="42897", ort="Remscheid", region="Nordrhein-Westfalen",
            lat=51.1518004, lng=7.2728677, projekt_id=None, projekt_titel=None, status=163674, vermietet=False,
            archiviert=False, typ="INDUSTRY", kategorie="HALL", gesamt=None, frei_ab=None, angelegt="2026-03-20",
            eigentuemer_kontakt=None, makler="Marek Zimmermann", provision="Provisionsfrei", **custom) -> dict:
    """Eine Einheit aus GET /v1/units?expand=1. Viele Felder kommen als {label, value}."""
    custom.setdefault("lagerflache", 8875.0)
    return {
        "id": id, "name": name, "title": {"label": "Überschrift", "value": titel},
        "street": strasse, "house_number": hausnummer, "zip_code": plz, "city": ort, "region": region, "lat": lat, "lng": lng,
        "project_id": projekt_id, "project": {"title": projekt_titel} if projekt_titel else None,
        "rented": {"label": "Vermietet", "value": vermietet}, "archived": archiviert,
        "property_status": {"id": status, "name": "Vermarktung"} if status else None,
        "rs_type": typ, "rs_category": kategorie, "property_space_value": gesamt,
        "industrial_area": {"label": "Gewerbefläche ca.", "value": None},
        "hall_height": {"label": "Hallen-/ Geschosshöhe", "value": None},
        "free_from": {"label": "Verfügbar ab", "value": frei_ab},
        "created_at": f"{angelegt}T10:13:18.669+01:00",
        "courtage": {"label": "Provision", "value": provision},
        "relationships": [{"id": 1, "name": "", "internal_name": "owner", "client_id": eigentuemer_kontakt}] if eigentuemer_kontakt else [],
        "broker": {"id": 387451, "name": makler},
        "custom_fields": cf(**custom),
    }


# Einheit 5159361 (LIP Invest, Remscheid) – 4 km vom Mittelpunkt des Gesuchs Wermelskirchen
REMSCHEID = einheit(hallenhohe=8.58, ramepntore="4", frei_ab="01.01.2027")
