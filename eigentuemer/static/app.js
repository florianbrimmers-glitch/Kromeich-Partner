"use strict";

const $ = (sel) => document.querySelector(sel);

const NACHWEIS_TEXT = {
  eigentuemer: "Bitte laden Sie einen aktuellen Grundbuchauszug hoch, aus dem hervorgeht, dass Sie Eigentümer der Fläche sind.",
  makler: "Bitte laden Sie den Alleinvermarktungsauftrag hoch, aus dem hervorgeht, dass Sie die Fläche vermarkten dürfen.",
};

function gewaehlteRolle() {
  return (document.querySelector('input[name=rolle]:checked') || {}).value || "eigentuemer";
}

function hinweisSetzen() {
  $("#nachweis-hinweis").textContent = NACHWEIS_TEXT[gewaehlteRolle()];
}

document.querySelectorAll('input[name=rolle]').forEach((r) => r.addEventListener("change", hinweisSetzen));
hinweisSetzen();

function zahlOderNull(wert) {
  const text = String(wert || "").trim();
  if (!text) return null;
  const zahl = Number(text.replace(",", "."));
  return Number.isFinite(zahl) ? zahl : null;
}

function fehlerZeigen(text) {
  const el = $("#fehler");
  el.textContent = text;
  el.hidden = !text;
  if (text) el.scrollIntoView({ behavior: "smooth", block: "center" });
}

$("#formular").addEventListener("submit", async (e) => {
  e.preventDefault();
  fehlerZeigen("");
  const form = e.target;
  const daten = new FormData(form);
  const knopf = form.querySelector("button[type=submit]");

  const kontakt = {
    vorname: daten.get("vorname") || "",
    nachname: (daten.get("nachname") || "").trim(),
    firma: daten.get("firma") || "",
    email: (daten.get("email") || "").trim(),
    telefon: daten.get("telefon") || "",
  };
  const objekt = {
    strasse: (daten.get("strasse") || "").trim(),
    hausnummer: daten.get("hausnummer") || "",
    plz: (daten.get("plz") || "").trim(),
    stadt: (daten.get("stadt") || "").trim(),
    flaeche_qm: zahlOderNull(daten.get("flaeche_qm")),
    hallenhoehe_m: zahlOderNull(daten.get("hallenhoehe_m")),
    rampe: daten.get("rampe") === "on",
    nutzung: daten.get("nutzung"),
    verfuegbar_ab: daten.get("verfuegbar_ab") || "",
    miete_eur_qm: zahlOderNull(daten.get("miete_eur_qm")),
    beschreibung: daten.get("beschreibung") || "",
  };

  if (!kontakt.nachname || !kontakt.email) return fehlerZeigen("Name und E-Mail werden gebraucht.");
  if (!objekt.strasse || !objekt.plz || !objekt.stadt) return fehlerZeigen("Bitte die vollständige Adresse angeben.");
  if (!objekt.flaeche_qm) return fehlerZeigen("Bitte die Fläche in m² angeben.");
  if (!daten.get("einwilligung")) return fehlerZeigen("Ohne Einwilligung können wir den Vorgang nicht bearbeiten.");

  const nachweisDatei = form.querySelector('input[name=nachweis]').files[0];
  if (!nachweisDatei) return fehlerZeigen("Bitte den Nachweis hochladen.");

  const paket = new FormData();
  paket.append("rolle", gewaehlteRolle());
  paket.append("kontakt", JSON.stringify(kontakt));
  paket.append("objekt", JSON.stringify(objekt));
  paket.append("einwilligung", "true");
  paket.append("nachweis", nachweisDatei);
  for (const bild of form.querySelector('input[name=bilder]').files) paket.append("bilder", bild);

  knopf.disabled = true;
  knopf.textContent = "Wird übertragen …";
  try {
    const antwort = await fetch("/api/einreichung", { method: "POST", body: paket });
    const ergebnis = await antwort.json().catch(() => null);
    if (!antwort.ok) throw new Error((ergebnis && ergebnis.detail) || "Übertragung fehlgeschlagen.");

    $("#nummer").textContent = ergebnis.nummer;
    const link = new URL(ergebnis.status_url, window.location.origin).href;
    const a = $("#statuslink");
    a.href = link;
    a.textContent = link;
    form.hidden = true;
    $("#danke").hidden = false;
    window.scrollTo({ top: 0 });
  } catch (err) {
    fehlerZeigen(err.message);
  } finally {
    knopf.disabled = false;
    knopf.textContent = "Zur Prüfung einreichen";
  }
});
