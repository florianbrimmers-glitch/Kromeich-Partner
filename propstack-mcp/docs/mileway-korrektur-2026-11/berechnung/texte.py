"""Erzeugt aus den berechneten Fahrstrecken die Lagetexte nach How-to (Liste, km ab der Adresse, ohne Adresse)."""
import json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))

# Einleitungen: aus dem bisherigen Text des Eigentümers, ohne Adresse und ohne Eigennamen des Gewerbeparks
INTRO = {
    613115: "Die Immobilie befindet sich in Wesseling, einem etablierten Wirtschaftsstandort zwischen den Metropolregionen Köln und Bonn. Die zentrale Lage im Rheinland bietet eine ausgezeichnete Anbindung an die regionalen und überregionalen Verkehrswege.",
    613116: "Die Immobilie liegt im Stadtteil Merklinde an der nordöstlichen Stadtgrenze von Castrop-Rauxel, in direkter Nachbarschaft zu Dortmund. Die Lage im nördlichen Ruhrgebiet sichert eine sehr gute Erreichbarkeit.",
    613117: "Die Immobilie befindet sich in Melle. Über die A 30 ist der Standort an die überregionale Verkehrsachse zwischen den Niederlanden, Osnabrück und Bad Oeynhausen angebunden; von dort besteht Anschluss an die A 1, A 33 und A 2.",
    613118: "Die Immobilie befindet sich in Weiden in der Oberpfalz, einem etablierten Wirtschaftsstandort im Nordosten Bayerns. Die verkehrsgünstige Lage bietet eine hervorragende Anbindung an die wichtigen Verkehrsachsen der Region sowie an die angrenzenden Märkte in Tschechien.",
    613119: "Die Immobilie befindet sich in Kriftel, einem etablierten Gewerbestandort im wirtschaftsstarken Rhein-Main-Gebiet. Die zentrale Lage zwischen Frankfurt am Main, Wiesbaden und dem Flughafen Frankfurt bietet eine ausgezeichnete regionale und überregionale Erreichbarkeit.",
    613120: "Die Immobilie befindet sich in etablierter Gewerbelage in Aachen, südwestlich des Autobahnkreuzes der A 4 und A 44. Eine namhafte Mieterschaft bildet das unmittelbare Umfeld.",
    613121: "Die Immobilie liegt in Bergkamen in einem gewerblich geprägten Umfeld. Die Autobahnen A 1 und A 2 sind schnell erreichbar, wodurch regionale und überregionale Verkehre zügig angebunden sind.",
    613122: "Die Immobilie befindet sich in Dormagen, einem etablierten Gewerbestandort zwischen den Wirtschaftsregionen Köln und Düsseldorf. Im direkten Umfeld befinden sich zahlreiche Unternehmen aus Industrie, Gewerbe und Dienstleistung.",
    613123: "Die Flächen befinden sich in einem Gewerbepark in Reinbek, nur 16 km östlich von Hamburg.",
    613124: "Der Gewerbepark liegt verkehrsgünstig an der Autobahn A 3, ca. 12 Kilometer von Regensburg entfernt. Busverbindungen verbinden den Standort mit den umliegenden Gemeinden und der Stadt Regensburg.",
    613125: "Der Standort liegt in einer wachsenden Wirtschaftsregion an der Grenze zwischen Deutschland und der Schweiz. Die Schweizer Grenze ist nur zwei Kilometer entfernt, bis Konstanz und zum Bodensee sind es etwas mehr als 30 Minuten Fahrt.",
    613126: "Die Flächen befinden sich im Norden von Leipzig in einem etablierten Gewerbeumfeld. Der Standort ist an das Autobahnkreuz Leipzig-Mitte mit der Autobahn A 14 und der Bundesstraße B 2 angebunden.",
    613127: "Die Multitenant-Anlage befindet sich in Pleidelsheim und ist sehr gut angebunden. Die Stadt Ludwigsburg ist nur 20 Fahrminuten entfernt.",
    613128: "Die Immobilie befindet sich in Köln-Porz, einem attraktiven Wirtschaftsstandort mit hoher Nachfrage nach Gewerbeflächen. Die Lage zeichnet sich durch eine hervorragende Verkehrsanbindung an das Autobahnnetz und den öffentlichen Nahverkehr aus.",
    613129: "Der Standort in Neuss ist sowohl mit öffentlichen Verkehrsmitteln als auch mit dem Auto bequem erreichbar. Über die A 46 und das Autobahnkreuz Neuss-Süd besteht eine direkte Verbindung zur A 57.",
}

NO_ACCESS = re.compile(r"^(Rastplatz|Parkplatz|Raststätte|Rasthof|Tank|Autohof|Rastanlage)", re.I)
INTERCHANGE = re.compile(r"(Kreuz|Dreieck)\b", re.I)


def fmt(km):
    if km < 0.05:
        return "weniger als 0,1 km"
    if km < 10:
        return "ca. " + f"{km:.1f}".replace(".", ",") + " km"
    return f"ca. {round(km):d} km"


def clean_name(name):
    name = name.split(";")[0].strip()
    name = re.sub(r"\s*-\s*", "-", name) if re.search(r"\s-\s", name) else name
    name = re.sub(r"\s*/\s*", "/", name)
    return re.sub(r"\s*\(\d+\)$", "", name)


def norm(s):
    s = (s or "").lower().replace("straße", "str").replace("strasse", "str").replace("str.", "str")
    return re.sub(r"[^a-z0-9äöüß]+", " ", s).strip()


def build(pid, s):
    street = norm(s["street"])
    lines, notes = [], []

    # Autobahnen: je Autobahn die nächste Anschlussstelle (keine Rastplätze; Kreuze/Dreiecke nur, wenn es keine Anschlussstelle gibt)
    per_ref = {}
    for a in s["autobahn"]:
        if NO_ACCESS.search(a["name"]):
            continue
        ref = re.sub(r"^A\s*", "A ", a["ref"])
        cur = per_ref.get(ref)
        regular = not INTERCHANGE.search(a["name"])
        if cur is None or (regular and not cur["regular"]) or (regular == cur["regular"] and a["km"] < cur["km"]):
            per_ref[ref] = {**a, "ref": ref, "regular": regular}
    ranked = sorted(per_ref.values(), key=lambda a: a["km"])
    # die nächste immer; weitere Autobahnen nur bis 10 km (darüber ist die Auswahl der Kandidaten nicht mehr sicher vollständig)
    auto = ranked[:1] + [a for a in ranked[1:] if a["km"] <= 10][:2]
    if auto:
        lines.append("Autobahnen:")
        for a in auto:
            label = f"Anschlussstelle {clean_name(a['name'])}" if a["regular"] else clean_name(a["name"])
            lines.append(f"- {a['ref']} ({label}): {fmt(a['km'])}")
        lines.append("")
    else:
        notes.append("keine Anschlussstelle innerhalb von 15 km gefunden")

    # Bundesstraßen: bis 10 km, höchstens zwei, ohne Abzweige wie „B 1a“ neben „B 1“
    bund, seen = [], set()
    for b in s["bundesstrasse"]:
        base = re.sub(r"[a-z]+$", "", b["ref"])
        if b["km"] <= 10 and base not in seen:
            seen.add(base)
            bund.append(b)
    if bund[:2]:
        lines.append("Bundesstraßen:")
        for b in bund[:2]:
            lines.append(f"- {b['ref']}: {fmt(b['km'])}")
        lines.append("")

    # ÖPNV: nächste Haltestelle und nächster Bahnhof
    oepnv = []
    if s["bus"] and s["bus"][0]["km"] <= 1.5:
        b = s["bus"][0]
        kind = "Straßenbahnhaltestelle" if b["art"] == "tram" else "Bushaltestelle"
        if street and street in norm(b["name"]):
            oepnv.append(f"- Nächste {kind}: {fmt(b['km'])}")
            notes.append(f"Name der Haltestelle („{b['name']}“) weggelassen – er nennt die Straße des Objekts")
        else:
            oepnv.append(f"- {kind} {clean_name(b['name'])}: {fmt(b['km'])}")
    if s["bahn"]:
        b = s["bahn"][0]
        oepnv.append(f"- {'Bahnhof' if b['art'] == 'station' else 'Haltepunkt'} {b['name']}: {fmt(b['km'])}")
    if oepnv:
        lines += ["ÖPNV:"] + oepnv + [""]

    # Häfen: nächster; ein zweiter nur, wenn er höchstens 15 % weiter ist
    if s["hafen"]:
        lines.append("Häfen:")
        first = s["hafen"][0]
        lines.append(f"- {first['name']}: {fmt(first['km'])}")
        if len(s["hafen"]) > 1 and first["km"] <= 100 and s["hafen"][1]["km"] <= first["km"] * 1.15:
            lines.append(f"- {s['hafen'][1]['name']}: {fmt(s['hafen'][1]['km'])}")
        lines.append("")

    # Flughäfen: nächster; ist das kein großer, zusätzlich der nächste große
    if s["flughafen"]:
        lines.append("Flughäfen:")
        first = s["flughafen"][0]
        lines.append(f"- {first['name']}: {fmt(first['km'])}")
        if not first.get("gross"):
            hub = next((f for f in s["flughafen"][1:] if f.get("gross")), None)
            if hub:
                lines.append(f"- {hub['name']}: {fmt(hub['km'])}")
        lines.append("")

    text = INTRO[pid] + "\n\n" + "\n".join(lines).rstrip()
    # Selbstprüfung nach den Regeln des Connectors: Straße darf nicht vorkommen, km als Liste
    problems = []
    if street and street in norm(text):
        problems.append("Text nennt die Straße des Objekts")
    if "luftlinie" in text.lower():
        problems.append("Luftlinie")
    return text, notes, problems


if __name__ == "__main__":
    res = json.load(open(os.path.join(BASE, "lage_ergebnis.json"), encoding="utf-8"))
    out = {}
    for pid, s in sorted(res.items()):
        text, notes, problems = build(int(pid), s)
        out[pid] = {"city": s["city"], "text": text, "notes": notes, "problems": problems}
        print(f"##### {pid} {s['city']}" + (f"  !! {problems}" if problems else ""))
        print(text)
        for n in notes:
            print("  Hinweis:", n)
        print()
    json.dump(out, open(os.path.join(BASE, "lage_texte.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
