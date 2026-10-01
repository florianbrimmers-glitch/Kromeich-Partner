/* Hallentinder – Frontend ohne Build-Step. Drei Screens: Profil → Deck → Kontakt. */
"use strict";

const ANIMATION_MS = 280;

const state = { token: null, karten: [], index: 0, offset: 0, weitere: false, likes: 0 };

const $ = (sel) => document.querySelector(sel);
const screens = ["profil", "deck", "lead", "danke"];

function zeige(name) {
  screens.forEach((s) => $("#screen-" + s).classList.toggle("aktiv", s === name));
  window.scrollTo({ top: 0 });
}

function fehler(el, text) {
  el.textContent = text;
  el.hidden = !text;
}

async function api(pfad, optionen) {
  const antwort = await fetch(pfad, optionen);
  let daten = null;
  try { daten = await antwort.json(); } catch (e) { daten = null; }
  if (!antwort.ok) {
    throw new Error((daten && daten.detail) || "Es ist ein Fehler aufgetreten.");
  }
  return daten;
}

function zahl(wert) {
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 }).format(wert);
}

function merkmale(karte) {
  const liste = [];
  if (karte.flaeche) liste.push(zahl(karte.flaeche) + " m²");
  if (karte.entfernung_km !== null && karte.entfernung_km !== undefined) {
    liste.push(karte.entfernung_km < 1 ? "direkt vor Ort" : zahl(karte.entfernung_km) + " km entfernt");
  }
  if (karte.hallenhoehe) liste.push(karte.hallenhoehe.toString().replace(".", ",") + " m Höhe");
  if (karte.kranbahn) liste.push("Kranbahn");
  if (karte.baujahr) liste.push("Baujahr " + karte.baujahr);
  return liste;
}

// Rampe wird immer gezeigt – ob vorhanden oder nicht, ist eine Entscheidungsinfo.
// Die gedämpfte Variante sagt: laut Propstack nicht angekreuzt.
function rampenChip(karte) {
  const chip = document.createElement("span");
  chip.className = karte.rampe ? "merkmal" : "merkmal aus";
  chip.textContent = karte.rampe ? "Rampe" : "keine Rampe";
  return chip;
}

function ortszeile(karte) {
  const teile = [karte.plz, karte.stadt].filter(Boolean).join(" ");
  return karte.strasse ? karte.strasse + (teile ? ", " + teile : "") : teile || "Ort auf Anfrage";
}

function baueKarte(karte) {
  const el = document.createElement("article");
  el.className = "karte";
  el.dataset.id = String(karte.id);

  const bild = document.createElement("div");
  bild.className = "bild";
  // Als <img>, nicht als CSS-background: die URL wird als Property gesetzt statt in
  // einen CSS-String gebaut. Kein Escaping nötig (encodeURI würde bereits kodierte
  // URLs zerstören: %20 -> %2520) und kein Weg, aus der URL heraus CSS einzuschmuggeln.
  const urls = (karte.bilder || []).filter((u) => /^https?:\/\/|^data:image\//i.test(u));
  if (urls.length) {
    const platzhalter = document.createElement("span");
    platzhalter.className = "kein-bild";
    platzhalter.textContent = "K&P";
    platzhalter.hidden = true;
    bild.appendChild(platzhalter);

    urls.forEach((url, i) => {
      const foto = document.createElement("img");
      foto.alt = "";
      foto.loading = i === 0 ? "eager" : "lazy";
      foto.hidden = i !== 0;
      foto.addEventListener("error", () => {
        foto.dataset.kaputt = "1";
        if (bild.querySelectorAll("img:not([data-kaputt])").length === 0) {
          platzhalter.hidden = false;
        }
      });
      foto.src = url;
      bild.appendChild(foto);
    });

    if (urls.length > 1) {
      const punkte = document.createElement("div");
      punkte.className = "punkte";
      urls.forEach((_, i) => {
        const punkt = document.createElement("span");
        if (i === 0) punkt.className = "aktiv";
        punkte.appendChild(punkt);
      });
      bild.appendChild(punkte);
    }
    el._bildAnzahl = urls.length;
    el._bildIndex = 0;
  } else {
    bild.textContent = "K&P";
    el._bildAnzahl = 0;
  }

  const text = document.createElement("div");
  text.className = "text";

  const kopf = document.createElement("div");
  kopf.className = "kopfzeile";
  if (karte.einheit) {
    const marke = document.createElement("span");
    marke.className = "einheit";
    marke.textContent = karte.einheit;
    kopf.appendChild(marke);
  }
  const titel = document.createElement("h3");
  titel.textContent = karte.titel;
  kopf.appendChild(titel);

  const ort = document.createElement("p");
  ort.className = "ort";
  ort.textContent = ortszeile(karte);
  const chips = document.createElement("div");
  chips.className = "merkmale";
  merkmale(karte).forEach((m) => {
    const chip = document.createElement("span");
    chip.className = "merkmal";
    chip.textContent = m;
    chips.appendChild(chip);
  });
  chips.appendChild(rampenChip(karte));
  text.append(kopf, ort, chips);

  const ja = document.createElement("span");
  ja.className = "stempel ja";
  ja.textContent = "INTERESSANT";
  const nein = document.createElement("span");
  nein.className = "stempel nein";
  nein.textContent = "PASST NICHT";

  el.append(bild, text, ja, nein);
  zieheGeste(el);
  return el;
}

function aktuelleKarte() {
  return state.karten[state.index] || null;
}

function zeichneDeck() {
  const deck = $("#deck");
  deck.textContent = "";
  const rest = state.karten.slice(state.index, state.index + 2).reverse();
  rest.forEach((karte) => deck.appendChild(baueKarte(karte)));

  const fertig = state.index >= state.karten.length;
  if (fertig) {
    const leer = document.createElement("div");
    leer.className = "leer";
    leer.textContent = state.likes
      ? "Das war's – jetzt deine Auswahl absenden."
      : "Keine weiteren Hallen. Starte gern eine neue Suche mit größerem Umkreis.";
    deck.appendChild(leer);
  }
  $("#btn-fertig").hidden = state.likes === 0;
  $("#zaehler-likes").textContent = String(state.likes);
  $("#zaehler-rest").textContent = String(Math.max(state.karten.length - state.index, 0));
  ["#btn-ja", "#btn-nein", "#btn-detail"].forEach((sel) => { $(sel).disabled = fertig; });
}

async function nachladen() {
  if (!state.weitere || state.index < state.karten.length - 3) return;
  try {
    const daten = await api("/api/cards?token=" + encodeURIComponent(state.token) + "&offset=" + state.offset);
    state.karten = state.karten.concat(daten.karten);
    state.offset = daten.offset;
    state.weitere = daten.weitere;
  } catch (e) {
    state.weitere = false;
  }
}

async function swipe(richtung) {
  const karte = aktuelleKarte();
  if (!karte) return;
  state.index += 1;
  if (richtung === "like") state.likes += 1;
  $("#zaehler-likes").textContent = String(state.likes);
  $("#zaehler-rest").textContent = String(Math.max(state.karten.length - state.index, 0));
  // erst nach der Weg-Animation neu zeichnen, sonst verschwindet die Karte abrupt
  setTimeout(zeichneDeck, ANIMATION_MS);
  nachladen();
  try {
    const daten = await api("/api/swipe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: state.token, unit_id: karte.id, richtung }),
    });
    state.likes = daten.likes;
    $("#zaehler-likes").textContent = String(state.likes);
  } catch (e) {
    /* Sitzung abgelaufen o. Ä. – beim Absenden wird es sauber gemeldet */
  }
}

function wegAnimieren(el, richtung) {
  const ziel = richtung === "like" ? 1 : -1;
  el.classList.add("wandert");
  el.style.transform = "translateX(" + ziel * 140 + "%) rotate(" + ziel * 18 + "deg)";
  el.style.opacity = "0";
}

function blaettern(el, richtung) {
  const bilder = [...el.querySelectorAll(".bild img")];
  if (bilder.length < 2) return;
  const punkte = [...el.querySelectorAll(".punkte span")];
  const neu = Math.min(Math.max(el._bildIndex + richtung, 0), bilder.length - 1);
  if (neu === el._bildIndex) return;
  bilder.forEach((b, i) => { b.hidden = i !== neu; });
  punkte.forEach((p, i) => { p.className = i === neu ? "aktiv" : ""; });
  el._bildIndex = neu;
}

function zieheGeste(el) {
  let startX = 0, startY = 0, dx = 0, dy = 0, aktiv = false;

  el.addEventListener("pointerdown", (e) => {
    if (el !== el.parentElement.lastElementChild) return;
    aktiv = true;
    startX = e.clientX;
    startY = e.clientY;
    el.setPointerCapture(e.pointerId);
  });

  el.addEventListener("pointermove", (e) => {
    if (!aktiv) return;
    dx = e.clientX - startX;
    dy = e.clientY - startY;
    el.style.transform = "translate(" + dx + "px, " + dy * 0.25 + "px) rotate(" + dx / 22 + "deg)";
    el.querySelector(".stempel.ja").style.opacity = dx > 40 ? String(Math.min(dx / 120, 1)) : "0";
    el.querySelector(".stempel.nein").style.opacity = dx < -40 ? String(Math.min(-dx / 120, 1)) : "0";
  });

  const ende = (e) => {
    if (!aktiv) return;
    aktiv = false;

    // Kurzer Tipp statt Wischen: in den Bildern blättern (rechts weiter, links zurück)
    if (Math.abs(dx) < 10 && Math.abs(dy) < 10) {
      el.style.transform = "";
      el.querySelectorAll(".stempel").forEach((s) => { s.style.opacity = "0"; });
      if (e && typeof e.clientX === "number") {
        const box = el.getBoundingClientRect();
        blaettern(el, (e.clientX - box.left) / box.width > 0.45 ? 1 : -1);
      }
      dx = 0; dy = 0;
      return;
    }

    if (Math.abs(dx) > 110) {
      const richtung = dx > 0 ? "like" : "dislike";
      wegAnimieren(el, richtung);
      swipe(richtung);
    } else {
      el.classList.add("wandert");
      el.style.transform = "";
      el.querySelectorAll(".stempel").forEach((s) => { s.style.opacity = "0"; });
    }
    dx = 0; dy = 0;
  };

  el.addEventListener("pointerup", ende);
  el.addEventListener("pointercancel", ende);
}

function detailZeigen() {
  const karte = aktuelleKarte();
  if (!karte) return;
  const inhalt = $("#detail-inhalt");
  inhalt.textContent = "";

  const titel = document.createElement("h3");
  titel.textContent = karte.einheit ? karte.einheit + " · " + karte.titel : karte.titel;
  const dl = document.createElement("dl");
  const zeilen = [
    ["Adresse", ortszeile(karte)],
    ["Fläche", karte.flaeche ? zahl(karte.flaeche) + " m²" : null],
    ["Entfernung", karte.entfernung_km == null
      ? null
      : (karte.entfernung_km < 1 ? "direkt vor Ort" : zahl(karte.entfernung_km) + " km")],
    ["Hallenhöhe", karte.hallenhoehe ? String(karte.hallenhoehe).replace(".", ",") + " m" : null],
    ["Rampe", karte.rampe ? "vorhanden" : "nicht angegeben"],
    ["Kranbahn", karte.kranbahn ? "vorhanden" : null],
    ["Baujahr", karte.baujahr],
  ];
  zeilen.forEach(([label, wert]) => {
    if (!wert) return;
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = String(wert);
    dl.append(dt, dd);
  });
  inhalt.append(titel, dl);

  if (karte.expose_url) {
    const link = document.createElement("a");
    link.href = karte.expose_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Exposé öffnen";
    inhalt.appendChild(link);
  }
  $("#detail").showModal();
}

async function auswahlZeigen() {
  const liste = $("#lead-liste");
  liste.textContent = "";
  try {
    const daten = await api("/api/likes?token=" + encodeURIComponent(state.token));
    daten.karten.forEach((karte) => {
      const li = document.createElement("li");
      li.textContent = karte.titel;
      const span = document.createElement("span");
      span.textContent = ortszeile(karte) + (karte.flaeche ? " · " + zahl(karte.flaeche) + " m²" : "");
      li.appendChild(span);
      liste.appendChild(li);
    });
  } catch (e) {
    fehler($("#lead-fehler"), e.message);
  }
  zeige("lead");
}

$("#profil-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const knopf = e.target.querySelector("button");
  fehler($("#profil-fehler"), "");
  if (!String(form.get("ort") || "").trim()) {
    fehler($("#profil-fehler"), "Bitte gib eine PLZ oder einen Ort an.");
    return;
  }
  knopf.disabled = true;
  try {
    const daten = await api("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ort: String(form.get("ort")).trim(),
        flaeche_min: Number(form.get("flaeche_min") || 0),
        flaeche_max: Number(form.get("flaeche_max") || 0),
        nutzung: form.get("nutzung"),
        zeithorizont: form.get("zeithorizont"),
        radius_km: Number(form.get("radius_km")),
      }),
    });
    Object.assign(state, {
      token: daten.token,
      karten: daten.karten,
      index: 0,
      offset: daten.offset,
      weitere: daten.weitere,
      likes: 0,
    });
    const hinweis = daten.region_erkannt
      ? daten.treffer + " Hallen im Umkreis von " + daten.radius_km + " km."
      : daten.treffer + " Hallen gefunden – die Region konnten wir nicht zuordnen, daher ohne Umkreisfilter.";
    $("#deck-info").textContent = daten.treffer
      ? hinweis
      : "Aktuell haben wir dazu nichts im Bestand. Probier einen größeren Umkreis.";
    zeichneDeck();
    zeige("deck");
  } catch (err) {
    fehler($("#profil-fehler"), err.message);
  } finally {
    knopf.disabled = false;
  }
});

$("#btn-ja").addEventListener("click", () => {
  const el = $("#deck").lastElementChild;
  if (el && el.classList.contains("karte")) wegAnimieren(el, "like");
  swipe("like");
});
$("#btn-nein").addEventListener("click", () => {
  const el = $("#deck").lastElementChild;
  if (el && el.classList.contains("karte")) wegAnimieren(el, "dislike");
  swipe("dislike");
});
$("#btn-detail").addEventListener("click", detailZeigen);
$("#detail-zu").addEventListener("click", () => $("#detail").close());
$("#btn-fertig").addEventListener("click", auswahlZeigen);

$("#lead-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const knopf = e.target.querySelector("button");
  fehler($("#lead-fehler"), "");
  knopf.disabled = true;
  try {
    const daten = await api("/api/lead", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token: state.token,
        vorname: form.get("vorname") || "",
        nachname: form.get("nachname") || "",
        email: form.get("email") || "",
        telefon: form.get("telefon") || "",
        firma: form.get("firma") || "",
        nachricht: form.get("nachricht") || "",
        website: form.get("website") || "",
        einwilligung: form.get("einwilligung") === "on",
      }),
    });
    const anzahl = daten.deals_angelegt || daten.deals_geplant || 0;
    $("#danke-text").textContent =
      "Wir haben deine Anfrage zu " + anzahl + (anzahl === 1 ? " Halle" : " Hallen") +
      " aufgenommen. Ein Berater von Kromeich & Partner meldet sich bei dir.";
    zeige("danke");
  } catch (err) {
    fehler($("#lead-fehler"), err.message);
  } finally {
    knopf.disabled = false;
  }
});

$("#btn-neu").addEventListener("click", () => {
  state.token = null;
  state.karten = [];
  state.index = 0;
  state.likes = 0;
  $("#lead-form").reset();
  zeige("profil");
});
