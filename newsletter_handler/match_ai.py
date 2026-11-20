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
4. MEHRERE EINHEITEN: Eine Vermietung betrifft oft mehrere Einheiten desselben Objekts. Passt die Fläche der Meldung zur Summe mehrerer Einheiten an derselben Adresse, oder ist das Objekt laut Meldung vollständig vermietet, nenne ALLE diese Einheiten. Sonst genau eine.
5. Ein Kandidat, der nur in der Gemeinde des Projekts liegt – ohne passenden Eigentümer, ohne passende Fläche, ohne Projekt- oder Straßennamen – ist eine schwache Spur: confidence höchstens 0.5.
6. Wähle den plausibelsten Kandidaten und drücke die Sicherheit über confidence aus (hoch = sehr sicher, mittel = plausibel/prüfen). Gib eine leere Liste zurück, wenn KEIN Kandidat zur tatsächlichen Lage des Projekts passt.

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


def _flaeche_passt(deal: Deal, units: list[Unit], candidates: list[Unit]) -> bool:
    """Passt die gemeldete Fläche auf eine der gewählten Einheiten, auf ihre Summe oder
    auf die Summe aller Einheiten an derselben Adresse (±10 %)?"""
    soll = groesse(deal)
    if not soll or not units:
        return False
    erste = units[0]
    selbe_adresse = [
        u for u in candidates
        if erste.street and u.street and _ort(u) == _ort(erste)
        and normalize_street(u.street) == normalize_street(erste.street)
        and (u.house_number or "") == (erste.house_number or "")
    ]
    werte = [u.property_space_value for u in units if u.property_space_value]
    summen = [sum(werte)] if len(werte) > 1 else []
    adresse = [u.property_space_value for u in selbe_adresse if u.property_space_value]
    if len(adresse) > 1:
        summen.append(sum(adresse))
    return any(abs(ist - soll) <= FLAECHEN_TOLERANZ * soll for ist in werte + summen)


def _name_passt(deal: Deal, unit: Unit) -> bool:
    """Nennt die Meldung die Straße der Einheit, oder steht ein Wort des Projektnamens in
    ihrem Namen? Ortsname und Eigentümername zählen nicht – die sagen nichts über das Objekt."""
    if deal.strasse and unit.street and normalize_street(deal.strasse) == normalize_street(unit.street):
        return True
    ohne = eigentuemer.namen(deal.vermieter) | eigentuemer.namen(unit.eigentuemer)
    ohne |= set(re.findall(r"[a-zäöüß0-9]+", f"{unit.city or ''} {deal.stadt or ''}".lower()))
    woerter = {w for w in eigentuemer.namen(deal.objekt_name) if len(w) >= 4} - ohne
    heuhaufen = f"{unit.name or ''} {unit.title or ''} {unit.street or ''}".lower()
    return any(w in heuhaufen for w in woerter)


def select_match_geprueft(deal: Deal, candidates: list[Unit]) -> MatchResult:
    """select_match mit Eigentümer-Probe.

    Gehört die gewählte Einheit erkennbar einem anderen als dem Vermieter der Meldung:
    - Gibt es unter den Kandidaten Einheiten dieses Vermieters AM SELBEN ORT (Ort der
      ersten Wahl oder Ort der Meldung), wählt die KI noch einmal nur unter ihnen (Moers
      12.11.2026: Ixocon-Meldung an einer BEOS-Halle, die Ixocon-Halle lag unter den
      Kandidaten). Nur am selben Ort: Die Suche nach dem Vermieternamen bringt dessen
      Einheiten aus dem ganzen Bestand unter die Kandidaten – Aurelis lag am 20.11.2026
      in zwölf Städten. Eine Meldung aus München darf nicht in Kerpen landen.
    - Sonst: Spricht die Fläche oder der Name trotzdem für die Einheit, bleibt sie als
      unsicherer Treffer stehen – der Eigentümer am Objekt kann veraltet sein (Entwickler
      verkauft an Investor). Spricht nichts für sie, ist es kein eigener Bestand: NONE.
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

    if _flaeche_passt(deal, match.units, candidates) or _name_passt(deal, erste):
        return MatchResult(
            status=MatchStatus.AMBIGUOUS,
            units=match.units,
            kandidaten=match.kandidaten,
            grund=f"Eigentümer passt nicht ({hinweis}), Fläche oder Name aber schon. {match.grund}",
        )
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

    Die KI wählt weiterhin aus ALLEN Kandidaten: So erkennt sie das gemeinte Objekt
    auch dann, wenn es schon abgeschlossen ist, statt auf ein anderes auszuweichen.
    Ist die Wahl abgeschlossen, folgt eine zweite Auswahl nur unter Einheiten in Vermarktung:
    - sichere Wahl (UNIQUE): nur am selben Ort – gemeint sein kann dann noch eine andere
      Einheit desselben Parks oder der richtige Datensatz neben einer stillgelegten Dublette;
    - unsichere Wahl (AMBIGUOUS): unter allen offenen Kandidaten – die erste Wahl kann
      schlicht falsch gewesen sein.
    Bleibt die zweite Auswahl ohne Treffer: NONE, bereits_abgeschlossen=True (nichts zu tun).
    """
    match = select_match_geprueft(deal, candidates)
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

    zweite = select_match_geprueft(deal, offene)
    if zweite.status == MatchStatus.NONE:
        return MatchResult(
            status=MatchStatus.NONE,
            kandidaten=match.kandidaten,
            grund=f"{hinweis}; keine der {len(offene)} offenen Einheiten {wo} passt",
        ), True
    zweite.grund = f"Erste Wahl bereits abgeschlossen ({hinweis}). {zweite.grund}"
    return zweite, False
