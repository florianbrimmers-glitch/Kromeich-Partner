"use strict";

const ROLLE = { eigentuemer: "Eigentümer", makler: "Vermarktungsmandat" };
const NACHWEIS = {
  grundbuchauszug: "Grundbuchauszug",
  alleinvermarktungsauftrag: "Alleinvermarktungsauftrag",
};
const STATUS = { in_pruefung: "Offen", freigegeben: "Freigegeben", abgelehnt: "Abgelehnt" };

let aktuellerStatus = "in_pruefung";

function datum(wert) {
  if (!wert) return "";
  const d = new Date(wert);
  return Number.isNaN(d.getTime()) ? wert : d.toLocaleDateString("de-DE", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function fehlerZeigen(text) {
  const el = document.querySelector("#fehler");
  el.textContent = text;
  el.hidden = !text;
}

function zahl(wert) {
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 }).format(wert);
}

async function laden() {
  fehlerZeigen("");
  const url = "/api/pruefung" + (aktuellerStatus ? "?status=" + aktuellerStatus : "");
  let daten;
  try {
    const antwort = await fetch(url);
    if (antwort.status === 401) {
      fehlerZeigen("Kein Zugang – bitte Seite neu laden und Benutzername plus Passwort eingeben.");
      return;
    }
    daten = await antwort.json();
    if (!antwort.ok) throw new Error(daten.detail || "Fehler beim Laden");
  } catch (e) {
    fehlerZeigen(e.message);
    return;
  }

  const liste = document.querySelector("#liste");
  liste.textContent = "";
  if (!daten.vorgaenge.length) {
    const p = document.createElement("p");
    p.className = "intro";
    p.textContent = "Keine Vorgänge in dieser Ansicht.";
    liste.appendChild(p);
    return;
  }
  daten.vorgaenge.forEach((v) => liste.appendChild(bauen(v)));
}

function bauen(v) {
  const el = document.createElement("article");
  el.className = "vorgang";

  const kopf = document.createElement("header");
  const titel = document.createElement("h3");
  titel.textContent = v.nummer + " · " + v.adresse;
  const marke = document.createElement("span");
  marke.className = "marke-status " + v.status;
  marke.textContent = STATUS[v.status] || v.status;
  kopf.append(titel, marke);

  const meta = document.createElement("p");
  meta.className = "meta";
  meta.textContent = [
    ROLLE[v.rolle] || v.rolle,
    zahl(v.flaeche_qm) + " m²",
    "eingegangen " + datum(v.eingegangen_am),
    v.bilder.length === 0 ? "keine Fotos"
      : v.bilder.length === 1 ? "1 Foto" : v.bilder.length + " Fotos",
  ].join(" · ");

  el.append(kopf, meta);

  if (v.status === "in_pruefung") {
    const aktionen = document.createElement("div");
    aktionen.className = "aktionen";

    const nachweis = document.createElement("a");
    nachweis.className = "knopf-link";
    nachweis.href = "/api/pruefung/" + v.id + "/nachweis";
    nachweis.target = "_blank";
    nachweis.rel = "noopener";
    nachweis.textContent = NACHWEIS[v.nachweis_art] + " ansehen";

    const pruefer = document.createElement("input");
    pruefer.placeholder = "Ihr Name (Protokoll)";
    pruefer.maxLength = 100;

    const grund = document.createElement("input");
    grund.placeholder = "Grund (nur bei Ablehnung)";
    grund.maxLength = 1000;

    const ja = document.createElement("button");
    ja.className = "knopf-ja";
    ja.textContent = "Freigeben";

    const nein = document.createElement("button");
    nein.className = "knopf-nein";
    nein.textContent = "Ablehnen";

    const entscheiden = async (freigeben) => {
      if (!pruefer.value.trim()) return fehlerZeigen("Bitte Ihren Namen eintragen – er steht im Protokoll.");
      if (!freigeben && !grund.value.trim()) return fehlerZeigen("Eine Ablehnung braucht einen Grund, der Einsender sieht ihn.");
      ja.disabled = nein.disabled = true;
      try {
        const antwort = await fetch("/api/pruefung/" + v.id + "/entscheidung", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ freigeben, pruefer: pruefer.value.trim(), grund: grund.value.trim() }),
        });
        const ergebnis = await antwort.json();
        if (!antwort.ok) throw new Error(ergebnis.detail || "Fehlgeschlagen");
        await laden();
      } catch (e) {
        fehlerZeigen(e.message);
        ja.disabled = nein.disabled = false;
      }
    };

    ja.addEventListener("click", () => entscheiden(true));
    nein.addEventListener("click", () => entscheiden(false));
    aktionen.append(nachweis, pruefer, grund, ja, nein);
    el.appendChild(aktionen);
  } else {
    const protokoll = document.createElement("p");
    protokoll.className = "geloescht";
    const teile = [NACHWEIS[v.nachweis_art] + " geprüft von " + (v.geprueft_von || "?") + " am " + datum(v.geprueft_am)];
    if (!v.nachweis_vorhanden) teile.push("Nachweisdatei gelöscht");
    if (v.ablehnungsgrund) teile.push("Grund: " + v.ablehnungsgrund);
    protokoll.textContent = teile.join(" · ");
    el.appendChild(protokoll);
  }
  return el;
}

document.querySelectorAll(".filter button").forEach((knopf) => {
  knopf.addEventListener("click", () => {
    document.querySelectorAll(".filter button").forEach((k) => k.classList.remove("aktiv"));
    knopf.classList.add("aktiv");
    aktuellerStatus = knopf.dataset.status;
    laden();
  });
});

laden();
