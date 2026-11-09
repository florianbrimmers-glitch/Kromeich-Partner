import { describe, expect, it } from "vitest";
import type { FieldDef } from "../src/propstack/field-rules";
import {
	checkExposeTexts,
	checkZipPrefix,
	COMMISSION_SCALE,
	commissionFields,
	howtoCustomFields,
	internalNoteLines,
	objectNotProvided,
	ownerNamesOf,
	projectNotProvided,
} from "../src/propstack/howto";

// Regeln aus den Team-How-tos. Wichtig sind hier vor allem die Grenzfälle: Die Prüfungen sollen
// echte Verstöße abweisen, aber normale Hallenbeschreibungen nicht blockieren.

describe("Exposé-Texte", () => {
	const owner = { ownerNames: ["JJW Hillscheid Grundbesitz GmbH"] };

	it("Eigentümername: voller Name (ohne Rechtsform) ist ein Fehler, Namensteil nur ein Hinweis, Ort und Allerweltswörter zählen nicht", () => {
		expect(checkExposeTexts({ description_note: "Ein Objekt der JJW Hillscheid Grundbesitz." }, owner).errors[0]).toMatch(/nennt den Eigentümer/);
		expect(checkExposeTexts({ description_note: "Von JJW entwickelt." }, owner)).toMatchObject({ errors: [], warnings: [expect.stringMatching(/enthält „jjw“/)] });
		// „Hillscheid“ ist der Ort, „Grundbesitz“ ein Allerweltswort – kein Befund
		expect(checkExposeTexts({ description_note: "Logistikhalle in Hillscheid auf eigenem Grundbesitz." }, { ...owner, city: "Hillscheid" })).toEqual({ errors: [], warnings: [] });
		// Firma, deren Name nur aus Ort und Allerweltswörtern besteht
		expect(checkExposeTexts({ description_note: "Der Logistikpark in Herford." }, { city: "Herford", ownerNames: ["Logistikpark Herford GmbH & Co. KG"] }).warnings).toEqual([]);
		// Person: „Hans“ steckt nicht in „Hansestraße“
		expect(checkExposeTexts({ description_note: "Lage an der Hansestraße." }, { ownerNames: ["Hans Müller"] })).toEqual({ errors: [], warnings: [] });
		expect(checkExposeTexts({ description_note: "Ansprechpartner ist Hans Müller." }, { ownerNames: ["Hans Müller"] }).errors).toHaveLength(1);
	});

	it("Preise: Beträge mit €/EUR/Euro sind Fehler, Europaletten und Maße nicht; mit Bestätigung erlaubt", () => {
		for (const text of ["Miete 6,80 €/m²", "ab 5 EUR je m²", "Kaufpreis 2.500.000 Euro", "€ 6,80 je m²"]) {
			expect(checkExposeTexts({ description_note: text }).errors[0]).toMatch(/enthält einen Preis/);
		}
		for (const text of ["Platz für 1.000 Europaletten", "Hallenhöhe 10,5 m UKB, Bodentragkraft 5 t/m²", "Europaweit vernetzt", "30.000 m² Hallenfläche"]) {
			expect(checkExposeTexts({ description_note: text }).errors).toEqual([]);
		}
		expect(checkExposeTexts({ description_note: "Miete 6,80 €/m²" }, { publicPriceConfirmed: true }).errors).toEqual([]);
		// auch in Unterzeile und Ausstattung
		expect(checkExposeTexts({ sub_headline: "Ab 6,50 € je m²" }).errors).toHaveLength(1);
	});

	it("Ausstattung: Komma-Kette abgewiesen, Liste und einzelner Punkt in Ordnung, Dezimalkomma zählt nicht", () => {
		expect(checkExposeTexts({ furnishing_note: "LED, Sprinkler, 10 Rampen" }).errors[0]).toMatch(/Aufzählung/);
		expect(checkExposeTexts({ furnishing_note: "LED; Sprinkler; Rampen" }).errors).toHaveLength(1);
		expect(checkExposeTexts({ furnishing_note: "- LED\n- Sprinkler, ESFR\n- 10 Rampen, 1 ebenerdiges Tor" }).errors).toEqual([]);
		expect(checkExposeTexts({ furnishing_note: "Betreuung durch ein Property-Management-Team" }).errors).toEqual([]);
		expect(checkExposeTexts({ furnishing_note: "Lichte Höhe 10,5 m bei 12,20 m Achsraster" }).errors).toEqual([]);
		// Die Regel gilt nur für die Ausstattung – Fließtext mit Kommas ist normal
		expect(checkExposeTexts({ description_note: "Halle, Büro, Mezzanine und Rampen sind vorhanden." }).errors).toEqual([]);
	});

	it("Lage ohne km und Straße im Text sind Hinweise, keine Fehler", () => {
		const out = checkExposeTexts({ location_note: "Gute Lage an der Röntgenstr. im Gewerbegebiet." }, { street: "Röntgenstraße" });
		expect(out.errors).toEqual([]);
		expect(out.warnings).toEqual([expect.stringMatching(/keine Entfernungen in km/), expect.stringMatching(/nennt die Straße „Röntgenstraße“/)]);
		expect(checkExposeTexts({ location_note: "Autobahnen:\nA2: ca. 0,2 km" }, { street: "Röntgenstraße" }).warnings).toEqual([]);
		// sehr kurze Straßennamen werden nicht geprüft (zu viele Zufallstreffer)
		expect(checkExposeTexts({ description_note: "Lage am See." }, { street: "Am See" }).warnings).toEqual([]);
	});

	it("leere und nicht-textliche Werte (z. B. null beim Rückgängigmachen) werden übergangen", () => {
		expect(checkExposeTexts({ description_note: null, furnishing_note: undefined, location_note: "  " }, owner)).toEqual({ errors: [], warnings: [] });
	});

	it("ownerNamesOf: Name und Firma, ohne Doppelte, auch aus {label, value}", () => {
		expect(ownerNamesOf({ company: { label: "Firma", value: "Goodman Germany GmbH" }, name: "Stefan Prange" })).toEqual(["Stefan Prange", "Goodman Germany GmbH"]);
		expect(ownerNamesOf({ company: "X GmbH", name: "X GmbH" })).toEqual(["X GmbH"]);
		expect(ownerNamesOf(undefined)).toEqual([]);
	});
});

describe("(XX) in Überschrift und Name", () => {
	it("falsche Ziffern sind ein Fehler, fehlende ein Hinweis", () => {
		expect(checkZipPrefix("Überschrift", "Logistikhalle in (56) Hillscheid", "56204")).toEqual({});
		expect(checkZipPrefix("Überschrift", "Logistikhalle in (50) Hillscheid", "56204").error).toMatch(/richtig wäre \(56\)/);
		expect(checkZipPrefix("Überschrift", "Build-to-Suit Logistikstandort", "56204").warning).toMatch(/ohne „\(56\)“/);
		expect(checkZipPrefix("Projektname", "Logistikhalle Hillscheid", "56204", false)).toEqual({});
		expect(checkZipPrefix("Überschrift", undefined, "56204")).toEqual({});
	});
});

describe("Provision", () => {
	it("Vorgaben setzen die Standardtexte, eigene Texte haben Vorrang, nur für Miete", () => {
		expect(commissionFields("provisionsfrei", "RENT", {})).toEqual({ courtage: "Provisionsfrei", courtage_note: "Die Anmietung erfolgt provisionsfrei für den Mieter." });
		expect(commissionFields("provisionsfrei", "RENT", { courtage_note: "eigener Hinweis" })).toEqual({ courtage: "Provisionsfrei" });
		expect(commissionFields("staffel", "RENT", {})).toEqual({ courtage_note: COMMISSION_SCALE });
		expect(commissionFields(undefined, "BUY", {})).toEqual({});
		expect(() => commissionFields("staffel", "BUY", {})).toThrow(/nur für Miete/);
		expect(COMMISSION_SCALE.split("\n").map((l) => /(\S+ \(\d[\d,]*\)) Nettokaltmieten/.exec(l)?.[1])).toEqual(["zwei (2)", "drei (3)", "dreieinhalb (3,5)", "vier (4)"]);
	});
});

describe("Wichtige Felder → Custom-Felder", () => {
	const defs = new Map<string, FieldDef>(
		(
			[
				["ramepntore", "String"],
				["anzahl_rampentore_2", "Number"],
				["mezzanineflache_gesamt", "Number"],
				["mezzanineflache_verfugbar", "Number"],
				["beleuchtung", "String"],
			] as const
		).map(([key, type]) => [key, { key, options: [], type }]),
	);

	it("Form richtet sich nach dem Feldtyp; verfügbare Fläche nur, solange nicht vermietet; fehlendes Zweitfeld ist kein Fehler", () => {
		expect(howtoCustomFields({ dock_doors: 10, ground_level_doors: 1, lighting: "LED", mezzanine_area: 800 }, defs, undefined, "available")).toEqual({
			anzahl_rampentore_2: 1,
			beleuchtung: "LED", // beleuchtung_halle fehlt in dieser Registry → stillschweigend ausgelassen
			mezzanineflache_gesamt: 800,
			mezzanineflache_verfugbar: 800,
			ramepntore: "10",
		});
		expect(howtoCustomFields({ mezzanine_area: 800 }, defs, undefined, "rented")).toEqual({ mezzanineflache_gesamt: 800 });
		expect(howtoCustomFields({ mezzanine_area: 800 }, defs, undefined, "unknown")).toEqual({ mezzanineflache_gesamt: 800 });
		expect(howtoCustomFields({ dock_doors: null }, defs, undefined, "available")).toEqual({ ramepntore: null });
	});

	it("fehlt das Hauptfeld in Propstack, wird laut abgebrochen statt den Wert still zu verlieren", () => {
		expect(() => howtoCustomFields({ wgk: "WGK 1" }, defs, undefined, "available")).toThrow(/„wgk“ \(WGK\) gibt es nicht/);
		expect(() => howtoCustomFields({ dock_doors: 10 }, defs, { ramepntore: "9" }, "available")).toThrow(/gleichzeitig/);
	});
});

describe("Was laut How-to fehlt", () => {
	it("Halle als Einzelobjekt: alle wichtigen Angaben; Büroeinheit im Projekt: nur was dort Sinn ergibt", () => {
		const hall = objectNotProvided({}, { marketing_type: "RENT", rs_type: "INDUSTRY" }, { inProject: false });
		expect(hall).toEqual(
			expect.arrayContaining(["Hallenfläche", "Hallenhöhe (m UKB)", "Rampentore", "Ebenerdige Tore", "WGK", "Bodentragkraft", "Sprinkleranlage", "Grundstücksfläche", "Interne Notiz: Mandat", "Mietpreise (intern)", "Eigentümer", "Provision", "Lage"]),
		);
		const office = objectNotProvided(
			{ owner_contact_id: 1 },
			{ courtage: "Provisionsfrei", description_note: "x", furnishing_note: "x", location_note: "x", marketing_type: "RENT", rs_category: "OFFICE", rs_type: "OFFICE", usable_floor_space: 400 },
			{ inProject: true },
		);
		for (const label of ["Hallenfläche", "Rampentore", "WGK", "Grundstücksfläche", "Interne Notiz: Mandat", "Eigentümer", "Provision", "Lage"]) expect(office).not.toContain(label);
		expect(office).toEqual(expect.arrayContaining(["Bürofläche teilbar ab", "Mietpreise (intern)", "Verfügbar ab"]));
		// direkt gesetztes Custom-Feld zählt als angegeben
		expect(objectNotProvided({}, { rs_type: "INDUSTRY" }, { explicit: { ramepntore: "9" }, inProject: true })).not.toContain("Rampentore");
	});

	it("Projekt und interne Notiz", () => {
		expect(projectNotProvided({ marketing_type: "RENT" }, {})).toEqual(expect.arrayContaining(["Eigentümer", "Interne Notiz: Mietpreise", "Unterzeile (z. B. „Direkt an der A40“)", "Lage"]));
		expect(projectNotProvided({ marketing_type: "BUY" }, {})).not.toContain("Interne Notiz: Mietpreise");
		expect(internalNoteLines({ developer_project_name: "Panattoni Park", mandate: "Alleinmandat von XY" })).toEqual(["Mandat: Alleinmandat von XY", "Projektname Entwickler: Panattoni Park"]);
	});
});
