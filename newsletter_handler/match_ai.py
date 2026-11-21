from __future__ import annotations

import json
import logging

import anthropic

import re

from . import config, eigentuemer
from .classifier import _get_client, _parse_extraction_json
from .matcher import normalize_street
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
3. EIGENTÜMER: Steht bei einem Kandidaten ein "eigentuemer", vergleiche ihn mit dem Vermieter/Entwickler der Meldung. Stimmen sie überein, ist das das stärkste Indiz – stärker als eine besser passende Fläche bei einem Kandidaten eines anderen Eigentümers. Gehört ein Kandidat erkennbar jemand anderem als dem genannten Vermieter, ist er in aller Regel NICHT gemeint, auch wenn der Ort stimmt. Umgekehrt ersetzt der Eigentümer nie den Ort: Ein Kandidat desselben Eigentümers in einer anderen Gemeinde als der des Projekts ist NICHT gemeint.
4. EINHEITEN: Eine Vermietung betrifft oft mehrere Einheiten desselben Objekts. Passt die Fläche der Meldung zu einer Einheit, nenne nur diese. Passt sie zur Summe mehrerer Einheiten an derselben Adresse, oder ist das Objekt laut Meldung vollständig vermietet, nenne genau diese Einheiten. Ist das Objekt eindeutig, aber NICHT zu erkennen, welche seiner Einheiten gemeint ist (keine Fläche genannt, mehrere gleich große Einheiten), dann nenne alle in Frage kommenden Einheiten dieses Objekts und bleibe bei confidence höchstens 0.7. Gib in diesem Fall KEINE leere Liste zurück – das Objekt ist gefunden, nur die Einheit ist offen.
5. Ein Kandidat, der nur in der Gemeinde des Projekts liegt – ohne passenden Eigentümer, ohne passende Fläche, ohne Projekt- oder Straßennamen – ist eine schwache Spur: confidence höchstens 0.5.
6. Wähle den plausibelsten Kandidaten und drücke die Sicherheit über confidence aus (hoch = sehr sicher, mittel = plausibel/prüfen). Gib eine leere Liste nur zurück, wenn KEIN Kandidat zur tatsächlichen Lage des Projekts passt.

Antworte ausschließlich mit JSON:
{{
  "unit_ids": [<id>, ...],
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
        "einheit": u.einheit,
        "flaeche_qm": u.property_space_value,
        "eigentuemer": u.eigentuemer,
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

    confidence = raw.get("confidence") or 0.0
    begruendung = raw.get("begruendung") or ""

    genannt = _genannte_ids(raw)
    if not genannt:
        return MatchResult(status=MatchStatus.NONE,
                           kandidaten=candidates[:10],
                           grund=f"KI: kein passendes Objekt ({begruendung})")

    gewaehlt = _selbes_objekt([by_id[i] for i in genannt if i in by_id])
    if not gewaehlt:
        return MatchResult(status=MatchStatus.AMBIGUOUS, kandidaten=candidates[:10],
                           grund=f"KI wählte unbekannte id {genannt[0]!r} – manuelle Prüfung")

    ids = {u.id for u in gewaehlt}
    andere = [u for u in candidates if u.id not in ids][:max(0, 10 - len(gewaehlt))]
    wo = gewaehlt[0].adresse() + (f" ({len(gewaehlt)} Einheiten)" if len(gewaehlt) > 1 else "")
    if len(gewaehlt) > 1 and not _gesamt_passt(groesse(deal), gewaehlt):
        # „Eine oder mehrere von diesen“ – das Objekt steht, die Einheit nicht. Nie Stufe A.
        return MatchResult(
            status=MatchStatus.AMBIGUOUS,
            units=gewaehlt,
            kandidaten=gewaehlt + andere,
            grund=f"Objekt erkannt, Einheit offen (conf {confidence:.2f}): {wo} – {begruendung}",
        )
    if confidence < config.CONFIDENCE_THRESHOLD:
        return MatchResult(
            status=MatchStatus.AMBIGUOUS,
            units=gewaehlt,
            kandidaten=gewaehlt + andere,
            grund=f"KI-Treffer unsicher (conf {confidence:.2f}): {wo} – {begruendung}",
        )
    return MatchResult(
        status=MatchStatus.UNIQUE,
        units=gewaehlt,
        kandidaten=gewaehlt + andere,
        grund=f"KI-Zuordnung (conf {confidence:.2f}): {wo} – {begruendung}",
    )


def _genannte_ids(raw: dict) -> list:
    """Die gewählten Einheiten: "unit_ids" (Liste) oder, wie bis 20.11.2026, "unit_id"."""
    werte = raw.get("unit_ids")
    if werte is None:
        werte = [raw.get("unit_id")]
    elif not isinstance(werte, list):
        werte = [werte]
    ids: list = []
    for wert in werte:
        try:
            zahl = int(wert)
        except (TypeError, ValueError):
            if wert is not None:
                ids.append(wert)   # nicht lesbar – führt unten zu „unbekannte id“
            continue
        if zahl not in ids:
            ids.append(zahl)
    return ids


def _selbes_objekt(units: list[Unit]) -> list[Unit]:
    """Mehrere Einheiten gelten nur zusammen, wenn sie am selben Ort und – soweit bekannt –
    in derselben Straße liegen wie die erste. Sonst hat die KI zwei Objekte vermischt;
    dann zählt nur die erste Einheit."""
    if len(units) < 2:
        return units
    erste = units[0]
    strasse = normalize_street(erste.street) if erste.street else ""
    return [
        u for u in units
        if _ort(u) == _ort(erste)
        and (not strasse or not u.street or normalize_street(u.street) == strasse)
    ]


def groesse(deal: Deal) -> float | None:
    """Quadratmeter aus dem Größen-Hinweis („6000“, „rund 6.700 m²“); None, wenn keine Zahl."""
    treffer = re.search(r"\d[\d.,]*", deal.groessen_hinweis or "")
    if not treffer:
        return None
    try:
        wert = float(treffer.group().replace(".", "").replace(",", "."))
    except ValueError:
        return None
    return wert if wert >= 100 else None


FLAECHEN_TOLERANZ = 0.10


def _summe_passt(soll: float | None, units: list[Unit]) -> bool:
    """Passt die gemeldete Fläche (±10 %) auf eine der Einheiten oder auf ihre Summe?"""
    if not soll:
        return False
    werte = [u.property_space_value for u in units if u.property_space_value]
    if len(werte) > 1:
        werte = werte + [sum(werte)]
    return any(abs(ist - soll) <= FLAECHEN_TOLERANZ * soll for ist in werte)


def _teilmenge_passt(soll: float | None, units: list[Unit]) -> bool:
    """Lässt sich die gemeldete Fläche (±10 %) aus einigen der Einheiten zusammensetzen?

    Schwacher Beleg dafür, starker dagegen: Bei vielen kleinen Einheiten geht fast jede
    Fläche auf – aber 19.000 m² lassen sich nicht aus einer freien Halle mit 3.318 m² bilden."""
    werte = [u.property_space_value for u in units if u.property_space_value]
    if not soll or not werte:
        return False
    unten, oben = soll * (1 - FLAECHEN_TOLERANZ), soll * (1 + FLAECHEN_TOLERANZ)
    if len(werte) > 16:   # zu viele Kombinationen – dann zählt, ob die Fläche überhaupt reicht
        return sum(werte) >= unten and min(werte) <= oben
    erreichbar = {0.0}
    for wert in werte:
        erreichbar |= {summe + wert for summe in erreichbar if summe + wert <= oben}
    return any(summe >= unten for summe in erreichbar)


def _gesamt_passt(soll: float | None, units: list[Unit]) -> bool:
    """Passt die gemeldete Fläche (±10 %) auf die Summe ALLER genannten Einheiten?"""
    werte = [u.property_space_value for u in units if u.property_space_value]
    return bool(soll) and len(werte) == len(units) and abs(sum(werte) - soll) <= FLAECHEN_TOLERANZ * soll


def select_match_geprueft(deal: Deal, candidates: list[Unit]) -> MatchResult:
    """select_match mit Eigentümer-Probe.

    Gehört die gewählte Einheit erkennbar einem anderen als dem Vermieter der Meldung:
    - Gibt es unter den Kandidaten Einheiten dieses Vermieters AM SELBEN ORT (Ort der
      ersten Wahl oder Ort der Meldung), wählt die KI noch einmal nur unter ihnen (Moers
      12.11.2026: Ixocon-Meldung an einer BEOS-Halle, die Ixocon-Halle lag unter den
      Kandidaten). Nur am selben Ort: Die Suche nach dem Vermieternamen bringt dessen
      Einheiten aus dem ganzen Bestand unter die Kandidaten – Aurelis lag am 20.11.2026
      in zwölf Städten. Eine Meldung aus München darf nicht in Kerpen landen.
    - Sonst ist es kein eigener Bestand: NONE.

    Keine Ausnahme für „Fläche oder Name passt trotzdem“. Die gab es im ersten Entwurf;
    an den 129 geprüften Aufgaben hätte sie sieben stehen lassen, alle sieben Rauschen
    (Wedel: 3.000 m² gemeldet, 3.097 m² bei uns, anderer Eigentümer, andere Halle). Der
    Preis: Steht am Objekt ein veralteter Eigentümer (Langenselbold: bei uns Hillwood,
    verkauft an Propel), fällt eine echte Meldung durch – sie steht dann in der
    Slack-Antwort („gehört einem anderen Eigentümer“), nicht in einer Aufgabe.
    """
    match = select_match(deal, candidates)
    if not match.units:
        return match
    erste = match.units[0]
    if eigentuemer.passt(deal.vermieter, erste.eigentuemer) is not False:
        return match

    hinweis = f"{erste.adresse()} (Unit {erste.id}) gehört {erste.eigentuemer}, die Meldung nennt {deal.vermieter}"
    orte = {_ort(erste), " ".join((deal.stadt or "").casefold().split())} - {""}
    eigene = [
        u for u in candidates
        if _ort(u) in orte and eigentuemer.passt(deal.vermieter, u.eigentuemer) is True
    ]
    if eigene:
        zweite = select_match(deal, eigene)
        if zweite.units:
            zweite.grund = f"Erste Wahl verworfen ({hinweis}). {zweite.grund}"
            return zweite
    return MatchResult(
        status=MatchStatus.NONE,
        kandidaten=match.kandidaten,
        grund=f"Kein eigener Bestand: {hinweis}",
        anderer_eigentuemer=True,
    )


def _ort(unit: Unit) -> str:
    return " ".join((unit.city or "").casefold().split())


def select_open_match(deal: Deal, candidates: list[Unit]) -> tuple[MatchResult, bool]:
    """Wie select_match_geprueft, aber eine bereits vermietete/abgeschlossene Einheit zählt
    nicht als Treffer. Rückgabe: (Ergebnis, bereits_abgeschlossen).

    Anlass (Stand 19.11.2026): 40 von 156 offenen Review-Aufgaben zeigten auf Einheiten,
    die in Propstack vermietet, abgeschlossen oder archiviert waren – Westring 8 in Dissen
    bekam sieben Aufgaben, nachdem das Objekt schon abgeschlossen war.

    Die KI wählt aus ALLEN Kandidaten: So erkennt sie das gemeinte Objekt auch dann, wenn
    es schon abgeschlossen ist, statt auf ein anderes auszuweichen. Ist unter den gewählten
    Einheiten eine abgeschlossene, entscheidet die gemeldete Fläche, ob noch etwas zu tun ist:

    1. Sie passt (±10 %) auf eine der abgeschlossenen Einheiten oder auf deren Summe -> erledigt.
    2. Gewählt waren auch offene Einheiten: Aufgabe an ihnen nur, wenn sich die Fläche aus
       offenen Einheiten zusammensetzen lässt oder erst mit ihnen zusammen aufgeht. Ohne
       Flächenangabe -> erledigt.
    3. Alle gewählten sind abgeschlossen und die Fläche passt nicht auf sie: zweite Auswahl
       unter den offenen Einheiten (sichere erste Wahl: nur am selben Ort) – sie zählt nur,
       wenn die Fläche auf sie passt. Ohne Flächenangabe -> erledigt.

    Warum so streng (Lese-Lauf über 72 Digests, 20.11.2026): Vorher folgte auf jede
    abgeschlossene Wahl eine zweite unter den freien Einheiten am Ort. Das ergab 8 Aufgaben,
    alle an einer freien Nachbar-Einheit (Krefeld: 19.000 m² gemeldet, Aufgabe an 3.318 m²).
    Weitere 8 entstanden, weil die KI einen ganzen Park nannte, in dem ein Teil schon
    vermietet war (Frankfurt (Oder): 16 Einheiten, 10 davon abgeschlossen).
    Die Grenze: Zwei gleich große Hallen, eine vermietet, eine frei – eine neue Meldung mit
    dieser Fläche gilt als die schon erfasste. Und ohne Flächenangabe wird ein teils
    vermieteter Park nicht mehr zur Aufgabe.
    """
    match = select_match_geprueft(deal, candidates)
    zu = [u for u in match.units if u.ist_abgeschlossen(config.STATUS_ABGESCHLOSSEN)]
    if not zu:
        return match, False

    offen = [u for u in match.units if not u.ist_abgeschlossen(config.STATUS_ABGESCHLOSSEN)]
    soll = groesse(deal)
    erste = zu[0]
    weitere = f" und {len(zu) - 1} weitere" if len(zu) > 1 else ""
    hinweis = f"{erste.adresse()} (Unit {erste.id}{weitere}) ist in Propstack bereits vermietet/abgeschlossen"

    def erledigt(zusatz: str = "") -> tuple[MatchResult, bool]:
        return MatchResult(status=MatchStatus.NONE, kandidaten=match.kandidaten, grund=hinweis + zusatz), True

    if _summe_passt(soll, zu):
        return erledigt()

    if offen:
        if _teilmenge_passt(soll, offen) or _gesamt_passt(soll, match.units):
            return MatchResult(
                status=MatchStatus.AMBIGUOUS,
                units=offen,
                kandidaten=match.kandidaten,
                grund=f"{len(zu)} der genannten Einheiten sind schon vermietet; die gemeldete Fläche "
                      f"spricht für die {len(offen)} offene(n). {match.grund}",
            ), False
        return erledigt(f"; für die {len(offen)} offene(n) Einheit(en) daneben spricht keine Fläche")

    if not soll:
        return erledigt()
    offene = [u for u in candidates if not u.ist_abgeschlossen(config.STATUS_ABGESCHLOSSEN)]
    if match.status == MatchStatus.UNIQUE:
        offene = [u for u in offene if _ort(erste) and _ort(u) == _ort(erste)]
        wo = "am selben Ort"
    else:
        wo = "unter den Kandidaten"
    if not offene:
        return erledigt()

    zweite = select_match_geprueft(deal, offene)
    if not zweite.units or not _summe_passt(soll, zweite.units):
        return erledigt(f"; keine der {len(offene)} offenen Einheiten {wo} passt zur gemeldeten Fläche")
    zweite.grund = f"Erste Wahl bereits abgeschlossen ({hinweis}). {zweite.grund}"
    return zweite, False
