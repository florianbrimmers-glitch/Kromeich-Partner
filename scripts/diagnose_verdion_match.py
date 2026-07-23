"""Einmal-Diagnose: prüft, ob das neue KI-Matching den Verdion-Fall findet.

Baut den Deal aus dem #newsletter-Digest vom 13.07. ("Brabus mietet im Verdion
PremierPark Berlin") und läuft gather_candidates -> select_match gegen das echte
Propstack + Claude. Reiner Lese-Lauf (nur search_units + Claude), keine Writes.
"""
from __future__ import annotations

from newsletter_handler.matcher import gather_candidates
from newsletter_handler.match_ai import propose_search_terms, select_match
from newsletter_handler.models import Deal, DealTyp

DEAL = Deal(
    deal_typ=DealTyp.VERMIETUNG,
    ist_vermietung=True,
    objekt_name="Verdion PremierPark Berlin",
    vermieter="Verdion",
    mieter="Brabus Automotive",
    stadt="Berlin",
    groessen_hinweis="9158",
    confidence=0.9,
)


def main() -> None:
    print("=" * 70)
    print("Deal:", DEAL.objekt_name, "| Ort(News):", DEAL.stadt, "| Vermieter:", DEAL.vermieter)
    print("=" * 70)

    terms = propose_search_terms(DEAL)
    print("\nKI-Suchbegriffe:", terms)

    candidates = gather_candidates(DEAL, extra_queries=terms)
    print(f"\n{len(candidates)} Kandidat(en):")
    for u in candidates:
        print(f"  - id={u.id} | name={u.name!r} | {u.street} {u.house_number}, {u.city} "
              f"| {u.property_space_value} m² | Makler={u.broker_name}")

    match = select_match(DEAL, candidates)
    print("\n--- KI-Auswahl ---")
    print("status:", match.status.value)
    print("grund :", match.grund)
    print("units :", [(u.id, u.name, u.city) for u in match.units])
    print("=" * 70)


if __name__ == "__main__":
    main()
