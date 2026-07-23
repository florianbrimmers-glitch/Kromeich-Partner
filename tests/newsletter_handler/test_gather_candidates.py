from newsletter_handler import matcher
from newsletter_handler.matcher import gather_candidates, significant_tokens
from newsletter_handler.models import Deal, DealTyp, Unit

# Das echte eigene Objekt liegt in Ludwigsfelde – die News nennt aber "Berlin".
LUDWIGSFELDE = Unit(id=9001, name="Verdion PremierPark – DC5", street="Am Güterbahnhof",
                    house_number="1", city="Ludwigsfelde", property_space_value=9158.0,
                    broker_id=387451, broker_name="Marek")
BERLIN_DECOY = Unit(id=9002, name="Lagerhalle Berlin-Spandau", street="Spandauer Damm",
                    house_number="5", city="Berlin", property_space_value=3000.0)


def _deal() -> Deal:
    return Deal(deal_typ=DealTyp.VERMIETUNG, ist_vermietung=True,
                objekt_name="Verdion PremierPark Berlin", vermieter="Verdion",
                mieter="Brabus Automotive", stadt="Berlin", groessen_hinweis="9158",
                confidence=0.9)


def test_significant_tokens_drops_geo_and_legal():
    toks = [t.lower() for t in significant_tokens("Verdion PremierPark Berlin", "Verdion GmbH")]
    assert "verdion" in toks
    assert "premierpark" in toks
    assert "berlin" not in toks   # Stadt als Stopwort raus
    assert "gmbh" not in toks


def test_gather_finds_object_via_developer_token_despite_wrong_city(monkeypatch):
    """Kernfall Verdion: News sagt 'Berlin', Objekt steht unter 'Ludwigsfelde'.
    Über den Entwickler/Projekt-Token wird es trotzdem als Kandidat gefunden."""
    def fake_search(q: str):
        ql = q.lower()
        if "verdion" in ql or "premierpark" in ql:
            return [LUDWIGSFELDE]
        if ql == "berlin":
            return [BERLIN_DECOY]
        return []
    monkeypatch.setattr(matcher, "search_units", fake_search)

    cands = gather_candidates(_deal())
    ids = {u.id for u in cands}
    assert 9001 in ids                      # das richtige Objekt ist dabei (kein harter Stadt-Filter)
    # dedupe nach id: Ludwigsfelde nur einmal, obwohl von mehreren Queries geliefert
    assert sum(1 for u in cands if u.id == 9001) == 1


def test_gather_dedups_and_skips_unspecific(monkeypatch):
    many = [Unit(id=i, city="Berlin") for i in range(100)]  # >= SEARCH_LIMIT -> unspezifisch
    def fake_search(q: str):
        if q.lower() == "berlin":
            return many
        if "verdion" in q.lower():
            return [LUDWIGSFELDE]
        return []
    monkeypatch.setattr(matcher, "search_units", fake_search)

    cands = gather_candidates(_deal())
    ids = {u.id for u in cands}
    assert 9001 in ids
    assert 0 not in ids and 50 not in ids   # die 100-Treffer-Stadt-Query wurde verworfen


def test_gather_no_queryable_fields(monkeypatch):
    monkeypatch.setattr(matcher, "search_units", lambda q: [])
    cands = gather_candidates(Deal(deal_typ=DealTyp.VERMIETUNG, ist_vermietung=True, confidence=0.5))
    assert cands == []


def test_extra_queries_surface_object_via_real_town(monkeypatch):
    """KI-Suchbegriff 'Ludwigsfelde' (echter Ort) findet das Objekt, das über die
    News-Stadt 'Berlin' oder den Entwickler nicht auffindbar wäre."""
    def fake_search(q: str):
        return [LUDWIGSFELDE] if q.lower() == "ludwigsfelde" else []
    monkeypatch.setattr(matcher, "search_units", fake_search)

    # ohne extra_queries: kein Treffer
    assert gather_candidates(_deal()) == []
    # mit KI-Suchbegriff 'Ludwigsfelde': Objekt ist dabei
    cands = gather_candidates(_deal(), extra_queries=["Ludwigsfelde", "Verdion"])
    assert {u.id for u in cands} == {9001}
