from __future__ import annotations

import json
import logging

import anthropic

from . import config
from .classifier import _get_client, _parse_extraction_json
from .models import Deal, MatchResult, MatchStatus, Unit

logger = logging.getLogger(__name__)

SELECT_PROMPT = """Du gleichst eine Immobilien-Marktmeldung gegen den Objektbestand eines Gewerbeimmobilien-Maklers (Kromeich & Partner) in Propstack ab.

DEAL (aus einem Logistik-Newsletter):
- Objekt/Projekt: {objekt_name}
- Ort laut Meldung: {ort}
- Vermieter/Entwickler: {vermieter}
- Mieter: {mieter}
- Größe: {groesse}

KANDIDATEN aus Propstack (mögliche Objekte):
{candidates}

So gehst du vor:
1. Nutze dein WELTWISSEN, um den tatsächlichen Standort des Projekts zu bestimmen. Der Ort in der Meldung ist oft die grobe Region (z.B. "Berlin"), das Objekt liegt aber im Umland. Beispiel: "Verdion PremierPark Berlin" liegt in LUDWIGSFELDE.
2. Objekte sind in Propstack häufig nach ihrer ADRESSE benannt (z.B. "Brandenburgische Straße 51 - Ludwigsfelde"), NICHT nach dem Projekt-/Entwicklernamen aus der Meldung. Verlange also NICHT, dass "Verdion" oder "PremierPark" im Kandidatennamen steht.
3. Ein Kandidat, der in der tatsächlichen Gemeinde des Projekts liegt und zur Nutzungsart (Logistik/Gewerbe) passt, ist ein STARKER Treffer – auch ohne Projektname und ohne Flächenübereinstimmung.
4. Wähle den plausibelsten Kandidaten und drücke die Sicherheit über confidence aus (hoch = sehr sicher, mittel = plausibel/prüfen). Gib nur dann null zurück, wenn wirklich KEIN Kandidat zur tatsächlichen Lage des Projekts passt.

Antworte ausschließlich mit JSON:
{{
  "unit_id": <id des passenden Kandidaten> | null,
  "confidence": 0.0-1.0,
  "begruendung": "1 kurzer Satz (nenne den erkannten tatsächlichen Ort)"
}}
"""


QUERY_PROMPT = """Du sollst ein Objekt aus einer Logistik-Marktmeldung im Immobilien-CRM (Propstack) eines Maklers wiederfinden.

DEAL:
- Projekt/Objekt: {objekt_name}
- Ort laut Meldung: {ort}
- Entwickler/Eigentümer: {vermieter}
- Mieter: {mieter}

Nenne 3-6 kurze Suchbegriffe, mit denen man das Objekt in einem CRM findet. Nutze Entwickler- und Projektnamen sowie – WICHTIG – den WAHRSCHEINLICHEN tatsächlichen Standort/die Gemeinde. Marktmeldungen nennen oft nur die grobe Region (z.B. "Berlin" für ein Objekt in Ludwigsfelde). Wenn du das Projekt kennst, gib den echten Ort an. Einzelne Begriffe, keine ganzen Sätze.

Antworte ausschließlich mit JSON:
{{"queries": ["...", "..."]}}
"""


def propose_search_terms(deal: Deal) -> list[str]:
    """Lässt Claude sinnvolle Propstack-Suchbegriffe vorschlagen (inkl. wahrscheinlichem
    echten Ort per Weltwissen, z.B. 'Ludwigsfelde' hinter 'Berlin'). Leere Liste bei Fehler."""
    prompt = config.DOMAIN_CONTEXT + "\n\n" + QUERY_PROMPT.format(
        objekt_name=deal.objekt_name or "-",
        ort=deal.stadt or "-",
        vermieter=deal.vermieter or "-",
        mieter=deal.mieter or "-",
    )
    try:
        response = _get_client().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _parse_extraction_json(response.content[0].text)
    except anthropic.APIError as e:
        logger.error("Claude API error bei Query-Vorschlag: %s", e)
        return []
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Query-Vorschlag nicht parsebar: %s", e)
        return []

    terms: list[str] = []
    for q in raw.get("queries") or []:
        if isinstance(q, str) and q.strip() and q.strip() not in terms:
            terms.append(q.strip())
    logger.info("KI-Suchbegriffe: %s", terms)
    return terms


def _candidate_line(u: Unit) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "title": u.title,
        "street": u.street,
        "house_number": u.house_number,
        "zip_code": u.zip_code,
        "city": u.city,
        "flaeche_qm": u.property_space_value,
        "makler": u.broker_name,
    }


def select_match(deal: Deal, candidates: list[Unit]) -> MatchResult:
    """Lässt Claude aus den Kandidaten das passende Objekt wählen.

    - kein Kandidat -> NONE (kein API-Call)
    - Claude wählt null -> NONE
    - Treffer, confidence >= Schwelle -> UNIQUE
    - Treffer, confidence < Schwelle -> AMBIGUOUS (wird zu Stufe-B-Review)
    - API-/Parsefehler -> AMBIGUOUS mit Kandidaten (kein stiller Verlust)
    """
    if not candidates:
        return MatchResult(status=MatchStatus.NONE, grund="Keine Kandidaten gefunden")

    by_id = {u.id: u for u in candidates}
    prompt = config.DOMAIN_CONTEXT + "\n\n" + SELECT_PROMPT.format(
        objekt_name=deal.objekt_name or "-",
        ort=deal.stadt or "-",
        vermieter=deal.vermieter or "-",
        mieter=deal.mieter or "-",
        groesse=deal.groessen_hinweis or "-",
        candidates=json.dumps([_candidate_line(u) for u in candidates], ensure_ascii=False, indent=1),
    )

    try:
        response = _get_client().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _parse_extraction_json(response.content[0].text)
    except anthropic.APIError as e:
        logger.error("Claude API error bei Match-Auswahl: %s", e)
        return MatchResult(status=MatchStatus.AMBIGUOUS, kandidaten=candidates[:10],
                           grund="KI-Auswahl fehlgeschlagen (API) – manuelle Prüfung")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Match-Auswahl-Antwort nicht parsebar: %s", e)
        return MatchResult(status=MatchStatus.AMBIGUOUS, kandidaten=candidates[:10],
                           grund="KI-Auswahl nicht parsebar – manuelle Prüfung")

    unit_id = raw.get("unit_id")
    confidence = raw.get("confidence") or 0.0
    begruendung = raw.get("begruendung") or ""

    if unit_id is None:
        return MatchResult(status=MatchStatus.NONE,
                           kandidaten=candidates[:10],
                           grund=f"KI: kein passendes Objekt ({begruendung})")

    try:
        chosen = by_id.get(int(unit_id))
    except (TypeError, ValueError):
        chosen = None
    if chosen is None:
        return MatchResult(status=MatchStatus.AMBIGUOUS, kandidaten=candidates[:10],
                           grund=f"KI wählte unbekannte id {unit_id!r} – manuelle Prüfung")

    andere = [u for u in candidates if u.id != chosen.id][:9]
    if confidence < config.CONFIDENCE_THRESHOLD:
        return MatchResult(
            status=MatchStatus.AMBIGUOUS,
            units=[chosen],
            kandidaten=[chosen] + andere,
            grund=f"KI-Treffer unsicher (conf {confidence:.2f}): {chosen.adresse()} – {begruendung}",
        )
    return MatchResult(
        status=MatchStatus.UNIQUE,
        units=[chosen],
        kandidaten=[chosen] + andere,
        grund=f"KI-Zuordnung (conf {confidence:.2f}): {chosen.adresse()} – {begruendung}",
    )


def _ort(unit: Unit) -> str:
    return " ".join((unit.city or "").casefold().split())


def select_open_match(deal: Deal, candidates: list[Unit]) -> tuple[MatchResult, bool]:
    """Wie select_match, aber eine bereits vermietete/abgeschlossene Einheit zählt nicht
    als Treffer. Rückgabe: (Ergebnis, bereits_abgeschlossen).

    Anlass (Stand 19.11.2026): 40 von 156 offenen Review-Aufgaben zeigten auf Einheiten,
    die in Propstack vermietet, abgeschlossen oder archiviert waren – Westring 8 in Dissen
    bekam sieben Aufgaben, nachdem das Objekt schon abgeschlossen war.

    Die KI wählt weiterhin aus ALLEN Kandidaten: So erkennt sie das gemeinte Objekt
    auch dann, wenn es schon abgeschlossen ist, statt auf ein anderes auszuweichen.
    Ist die Wahl abgeschlossen, folgt eine zweite Auswahl nur unter Einheiten in Vermarktung:
    - sichere Wahl (UNIQUE): nur am selben Ort – gemeint sein kann dann noch eine andere
      Einheit desselben Parks oder der richtige Datensatz neben einer stillgelegten Dublette;
    - unsichere Wahl (AMBIGUOUS): unter allen offenen Kandidaten – die erste Wahl kann
      schlicht falsch gewesen sein.
    Bleibt die zweite Auswahl ohne Treffer: NONE, bereits_abgeschlossen=True (nichts zu tun).
    """
    match = select_match(deal, candidates)
    if not match.units or not all(u.ist_abgeschlossen(config.STATUS_ABGESCHLOSSEN) for u in match.units):
        return match, False

    gewaehlt = match.units[0]
    hinweis = f"{gewaehlt.adresse()} (Unit {gewaehlt.id}) ist in Propstack bereits vermietet/abgeschlossen"
    offene = [u for u in candidates if not u.ist_abgeschlossen(config.STATUS_ABGESCHLOSSEN)]
    if match.status == MatchStatus.UNIQUE:
        ort = _ort(gewaehlt)
        offene = [u for u in offene if ort and _ort(u) == ort]
        wo = "am selben Ort"
    else:
        wo = "unter den Kandidaten"
    if not offene:
        return MatchResult(status=MatchStatus.NONE, kandidaten=match.kandidaten, grund=hinweis), True

    zweite = select_match(deal, offene)
    if zweite.status == MatchStatus.NONE:
        return MatchResult(
            status=MatchStatus.NONE,
            kandidaten=match.kandidaten,
            grund=f"{hinweis}; keine der {len(offene)} offenen Einheiten {wo} passt",
        ), True
    zweite.grund = f"Erste Wahl bereits abgeschlossen ({hinweis}). {zweite.grund}"
    return zweite, False
