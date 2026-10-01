"use strict";

const TEXTE = {
  in_pruefung: { titel: "In Prüfung", text: "Wir prüfen Ihren Nachweis. Das dauert in der Regel ein bis zwei Werktage." },
  freigegeben: { titel: "Freigegeben", text: "Ihr Objekt ist für Suchende sichtbar." },
  abgelehnt: { titel: "Abgelehnt", text: "Wir konnten das Objekt nicht freigeben." },
};

const NACHWEIS = {
  grundbuchauszug: "Grundbuchauszug",
  alleinvermarktungsauftrag: "Alleinvermarktungsauftrag",
};

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

(async () => {
  const ziel = document.querySelector("#inhalt");
  const token = new URLSearchParams(window.location.search).get("t");
  ziel.textContent = "";

  if (!token) {
    ziel.innerHTML = '<p class="intro">Dieser Link ist unvollständig. Bitte den vollständigen Link aus der Bestätigung verwenden.</p>';
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
})();
