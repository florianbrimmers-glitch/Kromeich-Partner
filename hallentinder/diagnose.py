"""Read-only-Diagnose gegen die Live-Propstack-API.

Prüft die Annahmen, die sich lokal nicht klären lassen: liefert `GET /units`
ohne `q` den ganzen Bestand, wie viele Objekte überstehen den Hallen-Filter,
wie gut sind die Felder gepflegt, die die Karten und das Ranking brauchen.

Schreibt nichts. Aufruf: `NO_WRITE=true python -m hallentinder.diagnose`

Ausgabe bewusst aggregiert – in einem Actions-Log haben Adressdaten nichts
verloren; einzelne Objekte erscheinen nur als ID + Stadt + Fläche.
"""
from __future__ import annotations

import logging
import os
from collections import Counter

from . import catalog, config, leads, propstack, ranking
from .models import HallCard, LeadPayload, SearchProfile, SwipeRichtung
from .session import SessionStore

logger = logging.getLogger("hallentinder.diagnose")

# Profile, mit denen das Ranking gegen den echten Bestand gefahren wird
TESTPROFILE = [
    SearchProfile(ort="49076", flaeche_min=2000, flaeche_max=8000, radius_km=50),
    SearchProfile(ort="Hamburg", flaeche_min=5000, flaeche_max=15000, radius_km=50),
    SearchProfile(ort="10115", flaeche_min=0, flaeche_max=0, radius_km=100),
]

# Felder, ohne die Karte bzw. Ranking schlechter werden
PFLEGE_FELDER = {
    "Koordinaten (Umkreissuche)": lambda k: k.lat is not None and k.lng is not None,
    "Fläche (Filter + Karte)": lambda k: k.flaeche is not None,
    "Stadt": lambda k: bool(k.stadt),
    "PLZ": lambda k: bool(k.plz),
    "Hallenhöhe": lambda k: k.hallenhoehe is not None,
    "Rampe vorhanden": lambda k: k.rampe,
    "Kranbahn vorhanden": lambda k: k.kranbahn,
    "Baujahr": lambda k: k.baujahr is not None,
    "Bild": lambda k: bool(k.bilder),
    "mehr als ein Bild": lambda k: len(k.bilder) > 1,
    "Einheitennummer im Namen": lambda k: bool(k.einheit),
    "Exposé-Link": lambda k: bool(k.expose_url),
}


def _titel(text: str) -> None:
    print(f"\n{'=' * 68}\n{text}\n{'=' * 68}")


def _quote(anzahl: int, gesamt: int) -> str:
    if not gesamt:
        return "–"
    return f"{anzahl:>5} / {gesamt} ({anzahl / gesamt * 100:4.1f} %)"


def _wertform(value) -> str:
    """Wert typgerecht darstellen – Strings gekürzt, damit das Log lesbar bleibt."""
    roh = catalog._scalar(value)
    typ = type(roh).__name__
    if roh is None:
        return "None"
    if isinstance(roh, str):
        gekuerzt = roh[:40] + ("…" if len(roh) > 40 else "")
        return f"{typ}: {gekuerzt!r}"
    return f"{typ}: {roh!r}"


def _ablehnungsgrund(raw: dict) -> str:
    """Spiegelt die Reihenfolge in catalog.ist_verfuegbare_halle wider."""
    if catalog._scalar(raw.get("rented")):
        return "vermietet"
    vermarktung = str(catalog._text(raw.get("marketing_type")) or "").lower()
    if vermarktung and any(k in vermarktung for k in catalog.KAUF_KEYWORDS):
        if not any(k in vermarktung for k in ("rent", "miet", "lease")):
            return f"nur Kauf ({vermarktung})"
    if catalog._enum(raw, "object_type") in catalog.AUSSCHLUSS_OBJECT_TYPE:
        return "Wohnimmobilie (object_type LIVING)"
    if catalog._enum(raw, "rs_type") in catalog.AUSSCHLUSS_RS_TYPE:
        return "Wohnimmobilie (rs_type APARTMENT)"
    rs_category = catalog._enum(raw, "rs_category")
    if rs_category in catalog.AUSSCHLUSS_RS_CATEGORY:
        return f"keine Halle (rs_category {rs_category})"
    if any(k in catalog._kategorie_text(raw) for k in catalog.AUSSCHLUSS_KEYWORDS):
        return "keine Halle (Textkeyword)"
    return "kein Hallen-Signal (strict)"


def bestand_pruefen() -> tuple[list[dict], list[HallCard]]:
    _titel("1. Bestandsabruf – GET /units ohne q, paginiert")
    rohdaten = propstack.list_units()
    print(f"Objekte gesamt:              {len(rohdaten)}")
    print(f"Seiten à 100 (max. {propstack.MAX_PAGES}):     {len(rohdaten) // 100 + 1}")
    if len(rohdaten) >= propstack.MAX_PAGES * 100:
        print("WARNUNG: Seitenlimit erreicht – MAX_PAGES erhöhen, der Bestand ist unvollständig.")

    if propstack.letzte_duplikate:
        print(f"\nACHTUNG: {propstack.letzte_duplikate} doppelt gelieferte Objekte verworfen.")
        print("Die Seitenabfrage driftet während des Durchlaufs – es fehlen entsprechend")
        print("viele andere Objekte im Bestand.")
    else:
        print("Doppelt gelieferte Objekte:  keine (Seitenabfrage war über den ganzen Lauf stabil)")

    karten = catalog.build_cards(rohdaten)
    print(f"Davon vermietbare Hallen:    {_quote(len(karten), len(rohdaten))}")

    gruende = Counter(_ablehnungsgrund(r) for r in rohdaten if not catalog.ist_verfuegbare_halle(r))
    if gruende:
        print("\nAussortiert:")
        for grund, anzahl in gruende.most_common():
            print(f"  {anzahl:>5}  {grund}")
    return rohdaten, karten


def paginierung_pruefen() -> None:
    """Liefert dieselbe Seite zweimal dasselbe? Ohne stabile Sortierung
    wandern Objekte zwischen den Seiten – dann fehlen bei jedem Laden andere."""
    _titel("1b. Ist die Seitenabfrage stabil?")

    def seite(params: dict) -> list[int]:
        antwort = propstack._request(
            "GET", "/units", key=config.propstack_key_objekte(), params=params
        )
        return [u.get("id") for u in propstack._items(antwort.json())]

    varianten = {
        "ohne Sortierung": {"expand": 1, "page": 2, "per": 100},
        "sort_by=id": {"expand": 1, "page": 2, "per": 100, "sort_by": "id", "order": "asc"},
    }
    ergebnisse: dict[str, list[int]] = {}
    for label, params in varianten.items():
        try:
            erste, zweite = seite(params), seite(params)
        except Exception as e:
            print(f"  {label:<18} Fehler: {e}")
            continue
        ergebnisse[label] = erste
        gleich = erste == zweite
        ueberlappung = len(set(erste) & set(zweite))
        print(f"  {label:<18} zweimal identisch: {gleich}, gemeinsame IDs: {ueberlappung}/{len(erste)}")

    if len(ergebnisse) == 2:
        ohne, mit = ergebnisse["ohne Sortierung"], ergebnisse["sort_by=id"]
        if ohne == mit:
            print("\n  sort_by=id ändert nichts – entweder ignoriert die API den Parameter,")
            print("  oder die Standardsortierung ist bereits die id.")
        else:
            aufsteigend = mit == sorted(mit)
            print(f"\n  sort_by=id wirkt (andere Reihenfolge), aufsteigend sortiert: {aufsteigend}")


def felder_pruefen(rohdaten: list[dict], karten: list[HallCard]) -> None:
    _titel("2. Feldpflege im Bestand")
    print(f"Grundlage: {len(karten)} vermietbare Hallen\n")
    for label, test in PFLEGE_FELDER.items():
        print(f"  {label:<28} {_quote(sum(1 for k in karten if test(k)), len(karten))}")

    _titel("3. Welche Felder liefert die API überhaupt? (nur Feldnamen)")
    vorhanden = Counter()
    for raw in rohdaten:
        vorhanden.update(k for k, v in raw.items() if v not in (None, "", [], {}))
    interessant = [
        "images", "pictures", "title_picture", "picture", "image",
        "lat", "lng", "hall_height", "ramp", "crane_runway", "industrial_area",
        "marketing_type", "rs_category", "rs_type", "object_type", "rented",
        "public_expose_url", "property_space_value",
    ]
    for feld in interessant:
        status = _quote(vorhanden.get(feld, 0), len(rohdaten))
        print(f"  {feld:<24} {status}")

    unbekannt = sorted(set(vorhanden) - set(interessant))
    print(f"\nWeitere befüllte Felder ({len(unbekannt)}): {', '.join(unbekannt[:40])}")

    _titel("3b. Welche WERTE stehen in den Kategorie- und Ausstattungsfeldern?")
    print("Technische Enums/Flags – entscheidet, wie sauber gefiltert und angezeigt werden kann.\n")
    for feld in ("marketing_type", "rs_category", "rs_type", "object_type",
                 "ramp", "crane_runway", "hall_height", "rented"):
        werte = Counter(_wertform(raw.get(feld)) for raw in rohdaten)
        # Enums vollständig zeigen – sonst bleiben seltene Kategorien unentdeckt
        grenze = 12 if feld == "hall_height" else 40
        print(f"  {feld}:")
        for wert, anzahl in werte.most_common(grenze):
            print(f"      {anzahl:>5}  {wert}")
        if len(werte) > grenze:
            print(f"      … {len(werte) - grenze} weitere Ausprägungen")
        print()


def unbekannte_kategorien(rohdaten: list[dict]) -> None:
    _titel("3c. Kategorien, die weder ausgeschlossen noch als Halle bekannt sind")
    bekannt = catalog.AUSSCHLUSS_RS_CATEGORY | catalog.HALLE_RS_CATEGORY
    offen = Counter(
        catalog._enum(raw, "rs_category") for raw in rohdaten
        if catalog._enum(raw, "rs_category") and catalog._enum(raw, "rs_category") not in bekannt
    )
    if not offen:
        print("Keine – alle vorkommenden Kategorien sind eingeordnet.")
        return
    print("Diese landen aktuell im Deck (bzw. fallen bei STRICT_HALLE raus):")
    for kategorie, anzahl in offen.most_common():
        print(f"  {anzahl:>5}  {kategorie}")


def ranking_pruefen(karten: list[HallCard]) -> None:
    _titel("4. Ranking gegen den echten Bestand")
    for profil in TESTPROFILE:
        treffer, zentrum, radius = ranking.rangliste(karten, profil)
        minimum, maximum = profil.spanne()
        spanne = f"{minimum}-{maximum} m²" if (minimum or maximum) else "Fläche offen"
        print(f"\n'{profil.ort}' / {spanne} / Start-Radius {profil.radius_km} km")
        print(f"  Zentrum: {zentrum.quelle}, verwendeter Radius: {radius} km, Treffer: {len(treffer)}")
        for karte in treffer[:3]:
            flaeche = f"{karte.flaeche:,.0f} m²".replace(",", ".") if karte.flaeche else "Fläche offen"
            entfernung = f"{karte.entfernung_km} km" if karte.entfernung_km is not None else "Entfernung unbekannt"
            print(f"    #{karte.id}  {karte.stadt or '?':<20} {flaeche:>12}  {entfernung}")


def kontakt_lesen_pruefen() -> None:
    _titel("5. Kontakt-Endpunkt (nur lesend)")
    test_email = "diagnose-lauf-existiert-nicht@kromeichpartner.de"
    treffer = propstack.find_contact_by_email(test_email)
    print(f"GET /contacts?q=… erreichbar, Dublettencheck liefert: {treffer!r} (erwartet: None)")


def lead_simulieren(karten: list[HallCard]) -> None:
    _titel("6. Lead-Simulation (NO_WRITE – nichts wird geschrieben)")
    if not config.no_write():
        print("ÜBERSPRUNGEN: nur mit NO_WRITE=true, sonst würde hier wirklich geschrieben.")
        return
    if not karten:
        print("ÜBERSPRUNGEN: kein Bestand.")
        return

    profil = SearchProfile(ort="49076", flaeche_min=0, flaeche_max=0, radius_km=400)
    treffer, _, _ = ranking.rangliste(karten, profil)
    if not treffer:
        print("ÜBERSPRUNGEN: keine Treffer für das Testprofil.")
        return

    store = SessionStore()
    session = store.anlegen(profil, treffer, 400)
    for karte in treffer[:2]:
        store.swipe(session.token, karte.id, SwipeRichtung.LIKE)

    ergebnis = leads.verarbeite(session, LeadPayload(
        token=session.token,
        vorname="Diagnose",
        nachname="Testlauf",
        email="diagnose-lauf-existiert-nicht@kromeichpartner.de",
        firma="Kromeich & Partner (Testlauf)",
        nachricht="Automatischer Diagnoselauf – keine echte Anfrage.",
        einwilligung=True,
    ))
    print(f"\nGeplante Writes: 1 Kontakt + {ergebnis.deals_geplant} Deals (tatsächlich geschrieben: 0)")
    print("Die geplanten Payloads stehen oben in den [NO_WRITE]-Logzeilen.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not os.environ.get("PROPSTACK_API_KEY"):
        raise SystemExit("FEHLER: PROPSTACK_API_KEY nicht gesetzt.")

    print(f"NO_WRITE = {config.no_write()}  |  STRICT_HALLE = {config.strict_halle()}")
    rohdaten, karten = bestand_pruefen()
    paginierung_pruefen()
    felder_pruefen(rohdaten, karten)
    unbekannte_kategorien(rohdaten)
    ranking_pruefen(karten)
    kontakt_lesen_pruefen()
    lead_simulieren(karten)

    _titel("Kurzfassung")
    print(f"  Objekte geladen:           {len(rohdaten)}")
    print(f"  Duplikate verworfen:       {propstack.letzte_duplikate}  (>0 = Bestand unvollständig)")
    print(f"  vermietbare Hallen:        {len(karten)}")
    print(f"  mit Koordinaten:           {sum(1 for k in karten if k.lat is not None)}")
    print(f"  mit Flächenangabe:         {sum(1 for k in karten if k.flaeche is not None)}")
    print(f"  mit Bild:                  {sum(1 for k in karten if k.bilder)}")
    bilder_gesamt = sum(len(k.bilder) for k in karten)
    print(f"  Bilder im Schnitt:         {bilder_gesamt / len(karten):.1f}" if karten else "")

    _titel("Offen bleibt")
    print("POST /client_properties (Deal-Anlage) – nur mit einem echten Schreibtest zu")
    print("verifizieren, deshalb hier bewusst nicht enthalten.")


if __name__ == "__main__":
    main()
