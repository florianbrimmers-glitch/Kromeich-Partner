"""Das Ergebnis des Abgleichs als Daten (JSON) und als Text.

Die Daten sind die Grundlage für alles Weitere – den Textbericht hier, eine Seite, eine
Slack-Nachricht und den späteren Vergleich („was wurde aus den Vorschlägen?“).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from .abgleich import Ergebnis, Vorschlag
from .felder import quartal_text
from .gesuch import Gesuch

ALT_TAGE = 180        # so lange nicht bearbeitet: erst nachfragen, ob das Gesuch noch gilt


def _mz(anzahl, einzahl: str, mehrzahl: str) -> str:
    return f"{anzahl:g} {einzahl if anzahl == 1 else mehrzahl}"


def _wer(kontakt: dict, kontakt_id: int) -> tuple[str, str]:
    """(Name, Firma) – die Firma nur, wenn sie nicht schon im Namen steht."""
    name = kontakt.get("name") or f"Kontakt {kontakt_id}"
    firma = kontakt.get("firma") or ""
    return name, ("" if firma and firma.casefold() in name.casefold() else firma)


def _m2(wert: float | None) -> str:
    return f"{wert:,.0f} m²".replace(",", ".") if wert else "–"


def _wunsch(g: Gesuch) -> str:
    teile = []
    if g.flaeche_von and g.flaeche_bis:
        teile.append(f"{_m2(g.flaeche_von)[:-3]}–{_m2(g.flaeche_bis)}" + ("" if g.flaeche_quelle == "Text" else f" (aus {g.flaeche_quelle})"))
    if g.gebiet == "Umkreis":
        teile.append(f"Umkreis {g.umkreis_km:.0f} km")
    elif g.gebiet == "Orte":
        teile.append(", ".join(g.orte[:4]) + (" …" if len(g.orte) > 4 else ""))
    elif g.gebiet == "Bundesland":
        teile.append(", ".join(g.laender))
    elif g.gebiet == "Gebiet":
        teile.append("gezeichnetes Gebiet")
    else:
        teile.append("ohne Gebiet")
    if g.hoehe_min:
        teile.append(f"Höhe ab {g.hoehe_min:g} m".replace(".", ","))
    if g.rampen_min:
        teile.append("ab " + _mz(g.rampen_min, "Rampe", "Rampen"))
    if g.ab_wann:
        teile.append(f"ab {quartal_text(g.ab_wann)}")
    teile.extend(g.besonderheiten)
    return " · ".join(teile)


def vorschlag_daten(v: Vorschlag) -> dict:
    erste = v.erste
    return {
        "art": v.art,
        "punkte": v.punkte,
        "einheiten": [f.id for f in v.flaechen],
        "projekt_id": erste.projekt_id,
        "bezeichnung": erste.bezeichnung if len(v.flaechen) == 1 else (erste.projekt_titel or erste.bezeichnung.split(" – ")[0]),
        "ort": erste.ort,
        "entfernung_km": round(v.entfernung_km) if v.entfernung_km is not None else None,
        "flaeche": round(v.summe),
        "eigentuemer": erste.eigentuemer,
        "provision": erste.provision,
        "miete_halle": erste.miete_halle,
        "bezug": erste.bezug_text,
        "gruppe": erste.gruppe,
        "gruende": v.gruende,
        "pruefen": v.pruefen,
        "neu": v.neu,
        "weitere_im_projekt": v.weitere_im_projekt,
        "dubletten": v.dubletten,
        "url": erste.url,
    }


def als_daten(ergebnisse: list[Ergebnis], uebrige: list[Gesuch], kontakte: dict[int, dict], makler: dict[int, str],
              heute: date, kopf: dict, je_gesuch: int = 5, nur_neu: bool = False) -> dict:
    """uebrige: aktive Profile, die nicht in den Abgleich gingen (kein Hallengesuch, laut Notiz erledigt)."""
    gesuche = []
    for e in ergebnisse:
        g = e.gesuch
        vorschlaege = [v for v in e.vorschlaege if v.neu] if nur_neu else e.vorschlaege
        name, firma = _wer(kontakte.get(g.kontakt_id, {}), g.kontakt_id)
        gesuche.append({
            "id": g.id,
            "kontakt_id": g.kontakt_id,
            "kontakt": name,
            "firma": firma,
            "betreuer": makler.get(g.betreuer_id or 0) or "ohne Betreuer",
            "angelegt": g.angelegt,
            "bearbeitet": g.bearbeitet,
            "alt": (heute - date.fromisoformat(g.bearbeitet or g.angelegt)).days > ALT_TAGE,
            "wunsch": _wunsch(g),
            "kurztext": g.kurztext,
            "noch_nicht_senden": g.noch_nicht_senden,
            "passend_gesamt": len(vorschlaege),
            "schon_angeboten": e.schon_angeboten,
            "spaeter_frei": e.spaeter_frei,
            "grund_ohne_vorschlag": e.grund_ohne_vorschlag if not e.vorschlaege else "",
            "vorschlaege": [vorschlag_daten(v) for v in vorschlaege[:je_gesuch]],
            "url": f"https://crm.propstack.de/app/contacts/{g.kontakt_id}",
        })
    # Je Betreuer: erst die zuletzt bearbeiteten Gesuche
    gesuche.sort(key=lambda x: x["bearbeitet"], reverse=True)
    gesuche.sort(key=lambda x: (x["alt"], x["betreuer"]))
    aufraeumen = defaultdict(list)
    for g in uebrige:
        name, firma = _wer(kontakte.get(g.kontakt_id, {}), g.kontakt_id)
        eintrag = {"id": g.id, "kontakt_id": g.kontakt_id, "kontakt": name, "firma": firma, "angelegt": g.angelegt,
                   "kurztext": g.kurztext, "betreuer": makler.get(g.betreuer_id or 0) or "ohne Betreuer"}
        if g.erledigt_hinweis:
            aufraeumen["laut_notiz_erledigt"].append({**eintrag, "hinweis": g.erledigt_hinweis})
        elif g.kein_hallengesuch == "Testprofil":
            aufraeumen["testprofil"].append(eintrag)
        elif g.kein_hallengesuch == "hängt an einem Kollegen":
            aufraeumen["am_kollegen"].append(eintrag)
    for e in ergebnisse:
        if e.grund_ohne_vorschlag.startswith(("Fläche", "kein Gebiet")):
            g = e.gesuch
            schluessel = "flaeche_fehlt" if e.grund_ohne_vorschlag.startswith("Fläche") else "gebiet_fehlt"
            name, firma = _wer(kontakte.get(g.kontakt_id, {}), g.kontakt_id)
            aufraeumen[schluessel].append({
                "id": g.id, "kontakt_id": g.kontakt_id, "kontakt": name, "firma": firma, "angelegt": g.angelegt,
                "kurztext": g.kurztext, "betreuer": makler.get(g.betreuer_id or 0) or "ohne Betreuer"})
    return {"stand": heute.isoformat(), "kopf": kopf, "gesuche": gesuche, "aufraeumen": dict(aufraeumen)}


def als_text(daten: dict) -> str:
    kopf = daten["kopf"]
    zeilen = [
        f"Angebots-Radar, Stand {date.fromisoformat(daten['stand']):%d.%m.%Y} – nur gelesen",
        f"{kopf['gesuche_geprueft']} aktive Hallengesuche gegen {kopf['flaechen']} angebotsfähige Flächen "
        f"({kopf['flaechen_geschaetzt']} mit geschätzter Lage, {kopf['flaechen_ohne_lage']} ohne jede Lage).",
        f"{kopf['gesuche_mit_vorschlag']} Gesuche mit Vorschlägen, {kopf['vorschlaege_gezeigt']} Vorschläge gezeigt "
        f"(höchstens {kopf['je_gesuch']} je Gesuch, {kopf['vorschlaege_gesamt']} passende Objekte insgesamt).",
        "",
    ]
    betreuer = None
    alt = False
    for g in daten["gesuche"]:
        if not g["vorschlaege"]:
            continue
        if g["alt"] and not alt:
            alt = True
            betreuer = None
            zeilen += ["", f"████ Seit über {ALT_TAGE} Tagen nicht bearbeitet – erst nachfragen, ob das Gesuch noch gilt ████", ""]
        if g["betreuer"] != betreuer:
            betreuer = g["betreuer"]
            zeilen += [f"══ {betreuer} " + "═" * max(3, 60 - len(betreuer)), ""]
        firma = f" ({g['firma']})" if g["firma"] else ""
        zeilen.append(f"▶ {g['kontakt']}{firma} – Suchprofil {g['id']} vom {date.fromisoformat(g['angelegt']):%d.%m.%Y}"
                      + (f", zuletzt bearbeitet {date.fromisoformat(g['bearbeitet']):%d.%m.%Y}" if g["bearbeitet"] != g["angelegt"] else ""))
        zeilen.append(f"  Gesucht: {g['wunsch']}")
        if g["noch_nicht_senden"]:
            zeilen.append("  ACHTUNG: laut Notiz noch nicht an den Kunden senden – nur Vorauswahl.")
        stand = "  " + _mz(g["passend_gesamt"], "passendes Objekt", "passende Objekte")
        if g["schon_angeboten"]:
            stand += ", " + _mz(g["schon_angeboten"], "Fläche", "Flächen") + " schon angeboten"
        if g["spaeter_frei"]:
            stand += ", " + _mz(g["spaeter_frei"], "wird", "werden") + " erst später frei"
        zeilen.append(stand + ".")
        for nr, v in enumerate(g["vorschlaege"], 1):
            km = f", {v['entfernung_km']} km" if v["entfernung_km"] is not None else ""
            neu = " NEU" if v["neu"] else ""
            zeilen.append(f"  {nr}. {v['bezeichnung']} – {v['ort']}{km} – {_m2(v['flaeche'])} [{v['art']}]{neu}")
            if v["gruende"]:
                zeilen.append(f"     passt: {'; '.join(v['gruende'])}")
            if v["pruefen"]:
                zeilen.append(f"     prüfen: {'; '.join(v['pruefen'])}")
            extras = []
            if v["eigentuemer"]:
                extras.append(v["eigentuemer"])
            if v["provision"]:
                extras.append(v["provision"])
            if v["weitere_im_projekt"]:
                extras.append(_mz(len(v["weitere_im_projekt"]), "weitere passende Einheit", "weitere passende Einheiten") + " im Projekt")
            if v["dubletten"]:
                extras.append("Dublette in Propstack: " + ", ".join(map(str, v["dubletten"])))
            zeilen.append(f"     {' · '.join(extras + [v['url']])}")
        zeilen.append("")

    ohne = [g for g in daten["gesuche"] if not g["vorschlaege"] and g["grund_ohne_vorschlag"]]
    if ohne:
        zeilen += ["── Ohne Vorschlag " + "─" * 44, ""]
        for grund, anzahl in Counter(g["grund_ohne_vorschlag"].split(":")[0].split(" – ")[0] for g in ohne).most_common():
            zeilen.append(f"  {anzahl}× {grund}")
        zeilen.append("")
    auf = daten["aufraeumen"]
    if auf:
        zeilen += ["── Aufräumen in Propstack " + "─" * 36, ""]
        for schluessel, titel in (("laut_notiz_erledigt", "Aktiv, aber laut Notiz erledigt"),
                                  ("flaeche_fehlt", "Aktiv, aber Fläche nicht lesbar – kein Abgleich möglich"),
                                  ("gebiet_fehlt", "Aktiv, aber ohne Gebiet – Vorschläge wären Zufall"),
                                  ("am_kollegen", "Suchprofil hängt an einem Kollegen statt am Kunden"),
                                  ("testprofil", "Testprofil ist aktiv")):
            for eintrag in auf.get(schluessel, []):
                zeilen.append(f"  {titel}: {eintrag['kontakt']} – Suchprofil {eintrag['id']} ({eintrag['betreuer']})"
                              + (f" – „{eintrag['hinweis']}“" if eintrag.get("hinweis") else ""))
        zeilen.append("")
    return "\n".join(zeilen)


def fuer_seite(daten: dict) -> dict:
    """Die Daten für seite/angebots-radar.html (liegt dort als radar.json neben der Seite)."""
    gesuche = []
    for g in daten["gesuche"]:
        vorschlaege = []
        for v in g["vorschlaege"]:
            v = {k: wert for k, wert in v.items() if k not in ("punkte", "projekt_id", "miete_halle", "gruppe", "weitere_im_projekt")} \
                | {"weitere": len(v["weitere_im_projekt"])}
            vorschlaege.append(v)
        gesuche.append({**g, "vorschlaege": vorschlaege})
    return {**daten, "gesuche": gesuche}


def als_nachricht(daten: dict, betreuer: str, grenze: int = 3500) -> str:
    """Eine kurze Wochenmeldung für einen Betreuer (Slack-tauglich: schlichter Text, unter 4.000 Zeichen).
    Nur frische Gesuche; je Gesuch die besten zwei Vorschläge, der Rest als Zahl. Leer, wenn es nichts gibt."""
    eigene = [g for g in daten["gesuche"] if g["betreuer"] == betreuer and g["vorschlaege"] and not g["alt"]]
    if not eigene:
        return ""
    summe = sum(len(g["vorschlaege"]) for g in eigene)
    zeilen = [f"Angebots-Radar, Stand {date.fromisoformat(daten['stand']):%d.%m.%Y}: "
              f"{_mz(summe, 'Vorschlag', 'Vorschläge')} für {_mz(len(eigene), 'Gesuch', 'Gesuche')} – Vorauswahl, noch nicht angeboten."]
    for nr, g in enumerate(eigene):
        block = ["", f"• {g['kontakt']}" + (f" ({g['firma']})" if g["firma"] else "") + f" – {g['wunsch']}"]
        if g["noch_nicht_senden"]:
            block.append("   Laut Notiz noch nicht an den Kunden senden.")
        for v in g["vorschlaege"][:2]:
            km = f", {v['entfernung_km']} km" if v["entfernung_km"] is not None else ""
            pruefen = f" – prüfen: {v['pruefen'][0]}" if v["pruefen"] else ""
            block.append(f"   – {v['bezeichnung']} ({v['ort']}{km}, {_m2(v['flaeche'])}){pruefen}")
            block.append(f"     {v['url']}")
        if len(g["vorschlaege"]) > 2:
            block.append(f"   … und {_mz(len(g['vorschlaege']) - 2, 'weiterer', 'weitere')}")
        if sum(len(z) + 1 for z in zeilen + block) > grenze:
            zeilen += ["", f"… und {_mz(len(eigene) - nr, 'weiteres Gesuch', 'weitere Gesuche')} auf der Seite."]
            break
        zeilen += block
    return "\n".join(zeilen)


def fuer_vergleich(daten: dict) -> dict:
    """Der Lauf ohne Namen und Texte – nur was der spätere Vergleich braucht. So kann er im Repo liegen."""
    return {"stand": daten["stand"], "gesuche": [
        {"id": g["id"], "kontakt_id": g["kontakt_id"], "kontakt": f"Kontakt {g['kontakt_id']}", "vorschlaege": [
            {"einheiten": v["einheiten"], "projekt_id": v["projekt_id"], "bezeichnung": v["bezeichnung"], "ort": v["ort"],
             "art": v["art"], "punkte": v["punkte"]} for v in g["vorschlaege"]]}
        for g in daten["gesuche"] if g["vorschlaege"]]}


def vergleich(alt: dict, deals: list[dict]) -> dict:
    """Was wurde aus früheren Vorschlägen? Zählt, für wie viele es heute einen Deal des Kontakts
    zur Einheit oder zu ihrem Projekt gibt, der NACH dem alten Lauf angelegt wurde."""
    seit = alt["stand"]
    je_kontakt_einheit = {(d.get("client_id"), d.get("property_id")) for d in deals
                          if d.get("property_id") and str(d.get("created_at") or "")[:10] > seit}
    je_kontakt_projekt = {(d.get("client_id"), d.get("project_id")) for d in deals
                          if d.get("project_id") and str(d.get("created_at") or "")[:10] > seit}
    vorschlaege = angeboten = 0
    treffer = []
    for g in alt["gesuche"]:
        for v in g["vorschlaege"]:
            vorschlaege += 1
            if any((g["kontakt_id"], e) in je_kontakt_einheit for e in v["einheiten"]) or \
                    (v["projekt_id"] and (g["kontakt_id"], v["projekt_id"]) in je_kontakt_projekt):
                angeboten += 1
                treffer.append({"gesuch": g["id"], "kontakt": g["kontakt"], "bezeichnung": v["bezeichnung"], "ort": v["ort"]})
    return {"seit": seit, "vorschlaege": vorschlaege, "angeboten": angeboten, "treffer": treffer}
