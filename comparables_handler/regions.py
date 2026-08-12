from __future__ import annotations

import re

# Aggregation läuft auf zwei Ebenen:
#   - Leitregion = erste ZWEI PLZ-Stellen (z.B. 59 = Hamm/Unna/Bergkamen)
#   - Postleitzone = erste PLZ-Stelle (z.B. 5 = Köln/Südwestfalen)
# Bei ~20-25 Angeboten trägt die Leitregion oft nur n=1-2; deshalb wird sie
# erst ab MIN_N_LEITREGION eigenständig ausgewiesen, die Zone immer.
#
# Die LABELS sind reine Beschriftung – aggregiert wird über den Zahlen-Key.
# Nicht gelistete Präfixe bekommen "PLZ-Gebiet XX"; die Zahl bleibt korrekt.

ZONE_LABELS = {
    "0": "Sachsen / Sachsen-Anhalt / Ostthüringen",
    "1": "Berlin / Brandenburg / Mecklenburg-Vorpommern",
    "2": "Hamburg / Schleswig-Holstein / Nordwest-Niedersachsen",
    "3": "Hannover / Ostwestfalen / Nordhessen",
    "4": "Ruhrgebiet / Münsterland / Niederrhein",
    "5": "Köln / Südwestfalen / Koblenz",
    "6": "Rhein-Main / Saarland / Nordbaden",
    "7": "Stuttgart / Baden / Württemberg",
    "8": "München / Oberbayern / Schwaben",
    "9": "Nürnberg / Franken / Oberpfalz",
}

# Kuratiert: Leitregionen, in denen K&P nachweislich Angebote hat, plus die
# großen Logistikmärkte. Bewusst konservativ – wo unsicher, kein Eintrag.
LEITREGION_LABELS = {
    "01": "Dresden",
    "04": "Leipzig",
    "06": "Halle / Bitterfeld",
    "07": "Gera / Jena",
    "09": "Chemnitz",
    "10": "Berlin-Mitte",
    "12": "Berlin-Süd",
    "13": "Berlin-Nord",
    "14": "Potsdam",
    "15": "Frankfurt (Oder)",
    "16": "Oranienburg / Brandenburg-Nord",
    "18": "Rostock",
    "19": "Schwerin",
    "20": "Hamburg-Mitte",
    "21": "Hamburg-Süd / Lüneburg",
    "22": "Hamburg-Nord",
    "24": "Kiel / Kaltenkirchen / Rendsburg",
    "26": "Emden / Oldenburg-West",
    "27": "Bremerhaven / Verden",
    "28": "Bremen",
    "29": "Celle / Uelzen",
    "30": "Hannover",
    "31": "Hildesheim / Nienburg",
    "32": "Herford / Minden",
    "33": "Bielefeld / Paderborn",
    "34": "Kassel",
    "37": "Göttingen",
    "38": "Braunschweig / Wolfsburg",
    "39": "Magdeburg",
    "40": "Düsseldorf",
    "41": "Mönchengladbach / Neuss",
    "42": "Wuppertal / Solingen",
    "44": "Dortmund",
    "45": "Essen / Gelsenkirchen",
    "46": "Oberhausen / Wesel / Bocholt",
    "47": "Duisburg / Krefeld",
    "48": "Münster / Steinfurt",
    "49": "Osnabrück / Glandorf / Vechta",
    "50": "Köln-Nord",
    "51": "Köln-Süd / Leverkusen",
    "52": "Aachen / Düren",
    "53": "Bonn",
    "56": "Koblenz",
    "57": "Siegen / Burbach",
    "58": "Hagen / Lüdenscheid",
    "59": "Hamm / Unna / Bergkamen / Soest",
    "60": "Frankfurt am Main",
    "63": "Offenbach / Hanau / Aschaffenburg",
    "64": "Darmstadt",
    "65": "Wiesbaden / Rüsselsheim",
    "66": "Saarbrücken",
    "67": "Ludwigshafen / Kaiserslautern",
    "68": "Mannheim / Heidelberg",
    "70": "Stuttgart",
    "71": "Böblingen / Ludwigsburg",
    "74": "Heilbronn",
    "76": "Karlsruhe",
    "77": "Offenburg",
    "78": "Villingen / Konstanz",
    "79": "Freiburg",
    "80": "München-West",
    "81": "München-Ost",
    "82": "Starnberg / Germering",
    "83": "Rosenheim",
    "84": "Landshut / Erding / Dorfen",
    "85": "Ingolstadt / Freising / München-Nord",
    "86": "Augsburg",
    "88": "Ravensburg / Ulm-Süd",
    "89": "Ulm / Neu-Ulm",
    "90": "Nürnberg",
    "91": "Erlangen / Ansbach",
    "92": "Amberg / Neumarkt",
    "93": "Regensburg",
    "94": "Passau / Deggendorf",
    "95": "Bayreuth / Hof",
    "96": "Bamberg / Coburg",
    "97": "Würzburg / Schweinfurt",
    "98": "Suhl",
    "99": "Erfurt / Weimar",
}

_PLZ_RE = re.compile(r"\b(\d{5})\b")


def normalize_plz(value: str | None) -> str | None:
    """Extrahiert eine 5-stellige deutsche PLZ aus beliebigem Text."""
    if not value:
        return None
    match = _PLZ_RE.search(str(value))
    return match.group(1) if match else None


def leitregion(plz: str | None) -> tuple[str, str] | None:
    """('59', 'Hamm / Unna / Bergkamen / Soest') – None ohne brauchbare PLZ."""
    plz = normalize_plz(plz)
    if not plz:
        return None
    key = plz[:2]
    return key, LEITREGION_LABELS.get(key, f"PLZ-Gebiet {key}")


def zone(plz: str | None) -> tuple[str, str] | None:
    """('5', 'Köln / Südwestfalen / Koblenz') – None ohne brauchbare PLZ."""
    plz = normalize_plz(plz)
    if not plz:
        return None
    key = plz[:1]
    return key, ZONE_LABELS.get(key, f"Postleitzone {key}")
