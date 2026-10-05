"use strict";

const TEXTE = {
  in_pruefung: { titel: "In Prüfung", text: "Wir prüfen Ihren Nachweis. Das dauert in der Regel ein bis zwei Werktage." },
  freigegeben: { titel: "Freigegeben", text: "Ihr Objekt ist für Suchende sichtbar." },
  abgelehnt: { titel: "Abgelehnt", text: "Wir konnten das Objekt nicht freigeben. Sie können die Angaben ändern und erneut einreichen." },
  zurueckgezogen: { titel: "Zurückgezogen", text: "Ihr Objekt ist derzeit nicht sichtbar. Sie können es jederzeit wieder online stellen." },
};

const NACHWEIS = {
  grundbuchauszug: "Grundbuchauszug",
  alleinvermarktungsauftrag: "Alleinvermarktungsauftrag",
};

const token = new URLSearchParams(window.location.search).get("t");
const $ = (sel) => document.querySelector(sel);
let adresseVorher = "";

function datum(wert) {
  if (!wert) return null;
  const d = new Date(wert);
  return Number.isNaN(d.getTime()) ? wert : d.toLocaleDateString("de-DE", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function zeile(dl, bezeichnung, wert) {
  if (!wert) return;
  const dt = document.createElement("dt");
  dt.textContent = bezeichnung;
  const dd = document.createElement("dd");
  dd.textContent = wert;
  dl.append(dt, dd);
}

function adressSchluessel(o) {
  return [o.strasse, o.hausnummer, o.plz, o.stadt]
    .map((t) => String(t || "").trim().replace(/\s+/g, " ").toLowerCase()).join("|");
}

function fehlerZeigen(text) {
  const el = $("#formfehler");
  el.textContent = text;
  el.hidden = !text;
}

function formularFuellen(objekt) {
  const form = $("#bearbeiten");
  for (const [feld, wert] of Object.entries(objekt)) {
    const el = form.elements[feld];
    if (!el) continue;
    if (el.type === "checkbox") el.checked = Boolean(wert);
    else el.value = wert === null || wert === undefined ? "" : wert;
  }
  adresseVorher = adressSchluessel(objekt);
}

function objektAusFormular() {
  const form = $("#bearbeiten");
  const zahl = (name) => {
    const text = String(form.elements[name].value || "").trim();
    if (!text) return null;
    const z = Number(text.replace(",", "."));
    return Number.isFinite(z) ? z : null;
  };
  return {
    strasse: form.elements.strasse.value.trim(),
    hausnummer: form.elements.hausnummer.value.trim(),
    plz: form.elements.plz.value.trim(),
    stadt: form.elements.stadt.value.trim(),
    flaeche_qm: zahl("flaeche_qm"),
    hallenhoehe_m: zahl("hallenhoehe_m"),
    rampe: form.elements.rampe.checked,
    nutzung: form.elements.nutzung.value,
    verfuegbar_ab: form.elements.verfuegbar_ab.value.trim(),
    miete_eur_qm: zahl("miete_eur_qm"),
    beschreibung: form.elements.beschreibung.value,
  };
}

function fotosZeichnen(bilder) {
  const ziel = $("#fotos");
  ziel.textContent = "";
  bilder.forEach((name) => {
    const kachel = document.createElement("div");
    kachel.className = "foto";
    const img = document.createElement("img");
    img.alt = "";
    img.src = `/api/vorgang/${encodeURIComponent(token)}/bild/${encodeURIComponent(name)}`;
    const weg = document.createElement("button");
    weg.type = "button";
    weg.title = "Foto entfernen";
    weg.textContent = "×";
    weg.addEventListener("click", async () => {
      weg.disabled = true;
      const antwort = await fetch(`/api/vorgang/${encodeURIComponent(token)}/bilder/${encodeURIComponent(name)}`,
                                  { method: "DELETE" });
      if (antwort.ok) fotosZeichnen((await antwort.json()).bilder);
      else { weg.disabled = false; fehlerZeigen("Foto konnte nicht entfernt werden."); }
    });
    kachel.append(img, weg);
    ziel.appendChild(kachel);
  });
  if (!bilder.length) {
    const p = document.createElement("p");
    p.className = "hinweis";
    p.textContent = "Noch keine Fotos.";
    ziel.appendChild(p);
  }
}

async function laden() {
  const ziel = $("#inhalt");
  ziel.textContent = "";

  if (!token) {
    ziel.innerHTML = '<p class="intro">Dieser Link ist unvollständig. Bitte den vollständigen Link aus der Bestätigungsmail verwenden.</p>';
    return;
  }

  let daten;
  try {
    const antwort = await fetch("/api/status/" + encodeURIComponent(token));
    daten = await antwort.json();
    if (!antwort.ok) throw new Error(daten.detail || "Nicht gefunden");
  } catch (e) {
    const p = document.createElement("p");
    p.className = "intro";
    p.textContent = e.message;
    ziel.appendChild(p);
    return;
  }

  const zustand = TEXTE[daten.status] || TEXTE.in_pruefung;
  const marke = document.createElement("span");
  marke.className = "marke-status " + daten.status;
  marke.textContent = zustand.titel;
  const text = document.createElement("p");
  text.className = "intro";
  text.textContent = zustand.text;
  ziel.append(marke, text);

  const dl = document.createElement("dl");
  dl.className = "werte";
  zeile(dl, "Vorgang", daten.nummer);
  zeile(dl, "Objekt", daten.adresse);
  zeile(dl, "Eingegangen", datum(daten.eingegangen_am));
  zeile(dl, "Geprüft", datum(daten.geprueft_am));
  zeile(dl, "Nachweis", NACHWEIS[daten.nachweis_art] || daten.nachweis_art);
  if (daten.nachweis_geloescht) zeile(dl, "Nachweisdatei", "nach der Prüfung gelöscht");
  if (daten.ablehnungsgrund) zeile(dl, "Grund", daten.ablehnungsgrund);
  ziel.appendChild(dl);

  if (daten.verlauf && daten.verlauf.length) {
    const liste = document.createElement("ul");
    liste.className = "verlauf";
    daten.verlauf.slice().reverse().forEach((e) => {
      const li = document.createElement("li");
      li.textContent = e.text;
      const wann = document.createElement("span");
      wann.textContent = datum(e.zeitpunkt);
      li.appendChild(wann);
      liste.appendChild(li);
    });
    ziel.appendChild(liste);
  }

  $("#verwaltung").hidden = false;
  $("#btn-zurueckziehen").hidden = daten.status !== "freigegeben";
  $("#btn-online").hidden = daten.status !== "zurueckgezogen";
  formularFuellen(daten.objekt);
  fotosZeichnen(daten.bilder || []);
}

$("#btn-bearbeiten").addEventListener("click", () => {
  const form = $("#bearbeiten");
  form.hidden = !form.hidden;
  if (!form.hidden) form.scrollIntoView({ behavior: "smooth", block: "start" });
});

async function sichtbarkeit(sichtbar) {
  const daten = new FormData();
  daten.append("sichtbar", sichtbar ? "true" : "false");
  const antwort = await fetch(`/api/vorgang/${encodeURIComponent(token)}/sichtbarkeit`,
                              { method: "POST", body: daten });
  if (antwort.ok) laden();
  else fehlerZeigen((await antwort.json()).detail || "Hat nicht geklappt.");
}

$("#btn-zurueckziehen").addEventListener("click", () => {
  if (confirm("Objekt für Suchende ausblenden? Sie können es jederzeit wieder online stellen.")) sichtbarkeit(false);
});
$("#btn-online").addEventListener("click", () => sichtbarkeit(true));

$("#bearbeiten").addEventListener("input", () => {
  const neueAdresse = adressSchluessel(objektAusFormular()) !== adresseVorher;
  $("#nachweis-feld").hidden = !neueAdresse;
});

$("#bearbeiten").addEventListener("submit", async (e) => {
  e.preventDefault();
  fehlerZeigen("");
  const knopf = e.target.querySelector("button[type=submit]");
  const objekt = objektAusFormular();
  if (!objekt.flaeche_qm) return fehlerZeigen("Bitte die Fläche angeben.");

  const paket = new FormData();
  paket.append("objekt", JSON.stringify(objekt));
  const nachweisDatei = e.target.elements.nachweis.files[0];
  if (nachweisDatei) paket.append("nachweis", nachweisDatei);

  knopf.disabled = true;
  knopf.textContent = "Wird gespeichert …";
  try {
    const antwort = await fetch(`/api/vorgang/${encodeURIComponent(token)}`, { method: "PUT", body: paket });
    const ergebnis = await antwort.json();
    if (!antwort.ok) throw new Error(ergebnis.detail || "Speichern fehlgeschlagen.");

    const neueFotos = $("#neue-fotos").files;
    if (neueFotos.length) {
      const bildpaket = new FormData();
      for (const f of neueFotos) bildpaket.append("bilder", f);
      const bildAntwort = await fetch(`/api/vorgang/${encodeURIComponent(token)}/bilder`,
                                      { method: "POST", body: bildpaket });
      if (!bildAntwort.ok) throw new Error((await bildAntwort.json()).detail || "Fotos konnten nicht ergänzt werden.");
      $("#neue-fotos").value = "";
    }

    $("#bearbeiten").hidden = true;
    await laden();
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (err) {
    fehlerZeigen(err.message);
  } finally {
    knopf.disabled = false;
    knopf.textContent = "Änderungen speichern";
  }
});

laden();
