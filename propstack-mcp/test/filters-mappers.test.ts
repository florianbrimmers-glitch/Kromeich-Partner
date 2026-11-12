import { describe, expect, it } from "vitest";
import { berlinOffset, contactQuery, dayEnd, dayStart, dealQuery, objectQuery } from "../src/propstack/filters";
import {
	customFields,
	DETAIL_TEXT_MAX,
	fullText,
	mapContactDetail,
	mapContactSummary,
	mapDeal,
	mapProjectDetail,
	mapUnitDetail,
	mapUnitSummary,
	scalar,
	stageIndex,
} from "../src/propstack/mappers";

describe("Datumsgrenzen in deutscher Zeit", () => {
	it("kennt Winter- und Sommerzeit", () => {
		expect(berlinOffset("2026-01-15")).toBe("+01:00");
		expect(berlinOffset("2026-07-15")).toBe("+02:00");
		expect(dayStart("2026-07-15")).toBe("2026-07-15T00:00:00+02:00");
		expect(dayEnd("2026-01-15")).toBe("2026-01-15T23:59:59+01:00");
	});
});

describe("Filter → Propstack-Parameter", () => {
	it("Kontakte: Arrays, DSGVO-Code, Archiv, Datum", () => {
		expect(
			contactQuery({
				archived: "include",
				created_from: "2026-03-01",
				gdpr_status: "widerrufen",
				query: "Müller",
				source_ids: [4],
				tag_ids: [1, 2],
			}),
		).toMatchObject({
			archived: "-1",
			created_at_from: "2026-03-01T00:00:00+01:00",
			gdpr_status: 3,
			group: [1, 2],
			q: "Müller",
			sources: [4],
		});
		expect(contactQuery({ archived: "only" }).archived).toBe("1");
		expect(contactQuery({}).archived).toBeUndefined();
	});

	it("Objekte: kommagetrennte Listen und _from/_to-Bereiche laut Doku", () => {
		expect(
			objectQuery({ area: { from: 500 }, marketing_type: "BUY", price: { from: 1, to: 2 }, status_ids: [274, 276], tag_ids: [9] }),
		).toMatchObject({
			group: "9",
			marketing_type: "BUY",
			price_from: 1,
			price_to: 2,
			property_space_value_from: 500,
			status: "274,276",
		});
	});

	it("Deals: Namen der Propstack-Parameter", () => {
		expect(dealQuery({ contact_id: 1, object_id: 2, pipeline_id: 3, stage_ids: [4] })).toMatchObject({
			client_id: 1,
			deal_pipeline_id: 3,
			deal_stage_ids: [4],
			property_id: 2,
		});
	});
});

describe("Mapper kürzen und schützen", () => {
	const rawContact = {
		academic_title: "",
		birth_place: "Berlin",
		custom_fields: { leer: { value: null }, quelle_alt: { pretty_value: "Messe", value: "messe" } },
		description: "x".repeat(2000),
		dob: "1970-01-01",
		email: "a@b.de",
		gdpr_status: 2,
		groups: [{ id: 5, name: "Investor" }],
		home_city: "Hamburg",
		home_street: "Weg",
		home_zip_code: "20095",
		id: 7,
		identity_number: "L01X00T47",
		income: "100000",
		name: "Anna Muster",
		nationality: "DE",
		tax_identification_number: "12345678901",
		token: "geheimer-portal-token",
	};

	it("Kontakt-Detail enthält keine sensiblen Felder", () => {
		const out = mapContactDetail(rawContact);
		const text = JSON.stringify(out);
		for (const secret of ["L01X00T47", "12345678901", "1970-01-01", "geheimer-portal-token", "100000", "Berlin"]) {
			expect(text).not.toContain(secret);
		}
		expect(out).toMatchObject({
			custom_fields: { quelle_alt: "Messe" },
			gdpr_status: "zugestimmt",
			home_address: "Weg, 20095 Hamburg",
			id: 7,
			tags: [{ id: 5, name: "Investor" }],
		});
		// Einzelansicht: die Notiz des Kontakts vollständig (vorher nach 1.500 Zeichen abgeschnitten)
		expect(out.description).toBe("x".repeat(2000));
		expect(out).not.toHaveProperty("academic_title");
	});

	it("Einzelansicht zeigt Texte vollständig – auch das Ende von Notiz und Bemerkung (Ansage Florian, 11.11.2026)", () => {
		// Beide Felder werden nur angehängt: Das Neueste steht am Ende und fiel vorher weg (300 bzw. 1.500 Zeichen)
		const remark = `${"Älterer Eintrag im Protokoll. ".repeat(40)}\nErgänzt am 2026-11-11.\nGebäudefläche gesamt angeglichen: 8.423 m² statt 8.801 m².`;
		const note = `${"Zeile der internen Notiz. ".repeat(100)}\nStellplatzmieten laut Eigentümer: Pkw 25 €, Lkw 50 €.`;
		const location = `Lage:\n${"- A2 (Anschlussstelle): ca. 0,2 km\n".repeat(80)}- Hafen: ca. 12 km`;
		expect(remark.length).toBeGreaterThan(300);
		expect(note.length).toBeGreaterThan(1500);
		expect(location.length).toBeGreaterThan(2000);
		const detail = mapUnitDetail({ custom_fields: { bemerkung: { value: remark } }, id: 9, location_note: location, note });
		expect((detail.custom_fields as Record<string, unknown>).bemerkung).toBe(remark);
		expect(detail.internal_note).toBe(note);
		expect(detail.location).toBe(location);
		const project = mapProjectDetail({ custom_fields: { bemerkung: { value: remark } }, description_note: location, id: 3, note });
		expect(project.description).toBe(location);
		expect(project.internal_note).toBe(note);
		expect((project.custom_fields as Record<string, unknown>).bemerkung).toBe(remark);
	});

	it("über der Obergrenze: Anfang und Ende mit unübersehbarem Hinweis – nie ein stilles Abschneiden", () => {
		const long = `ANFANG ${"x".repeat(DETAIL_TEXT_MAX + 500)} ENDE`;
		const shown = fullText(long)!;
		expect(shown.startsWith("ANFANG ")).toBe(true);
		expect(shown.endsWith(" ENDE")).toBe(true);
		expect(shown).toContain("[… 512 von 10512 Zeichen aus der Mitte ausgelassen – dieser Text ist NICHT vollständig und taugt nicht als Vorlage zum Überschreiben …]");
		expect(shown.length).toBeLessThan(DETAIL_TEXT_MAX + 200);
		// bis zur Grenze unverändert; Leerraum außen fällt weg; leer bleibt leer
		expect(fullText("y".repeat(DETAIL_TEXT_MAX))).toBe("y".repeat(DETAIL_TEXT_MAX));
		expect(fullText("  kurz  ")).toBe("kurz");
		expect(fullText("   ")).toBeUndefined();
		expect(fullText({ label: "Lage", value: "Text" })).toBe("Text");
		// Custom-Felder folgen derselben Regel; Zahlen und kurze Texte bleiben, wie sie sind
		const custom = customFields({ bemerkung: { value: long }, kurz: { value: "ok" }, zahl: { value: 8 } })!;
		expect(custom).toMatchObject({ kurz: "ok", zahl: 8 });
		expect(String(custom.bemerkung)).toContain("NICHT vollständig");
	});

	it("Listen bleiben kurz: die Notiz in der Deal-Liste wird weiter gekürzt", () => {
		const index = stageIndex([{ deal_stages: [{ chance: 0.5, id: 11, name: "Besichtigt" }], id: 1, name: "Vertrieb" }]);
		expect((mapDeal({ deal_stage_id: 11, id: 1, note: "n".repeat(400) }, index).note as string).length).toBe(301);
	});

	it("Kontakt-Liste: Betreuer aus broker_ids, wenn broker_id fehlt", () => {
		expect(mapContactSummary({ broker_ids: [254958], id: 1, name: "X" })).toMatchObject({ broker_id: 254958 });
		expect(mapContactSummary({ broker_ids: [], id: 1, name: "X" })).not.toHaveProperty("broker_id");
	});

	it("Kontakt-Liste nimmt die erste vorhandene Telefonnummer", () => {
		expect(mapContactSummary({ home_cell: "0171", id: 1, name: "X", phone: null })).toEqual({ id: 1, name: "X", phone: "0171" });
	});

	it("Objekte: label/value wird flach, Status-Name, Bilder nur gezählt", () => {
		const raw = {
			address: "Hafenstr. 1, 48291 Telgte",
			broker: { email: "x@y", id: 3, name: "Lena Klinnert" },
			custom_fields: { hallenhoehe: { pretty_value: "8 m", value: 8 } },
			description_note: { label: "Beschreibung", value: "Halle" },
			id: 9,
			images: [{}, {}],
			marketing_type: "RENT",
			property_status: { id: 1, name: "Verfügbar" },
			title: { label: "Überschrift", value: "Logistikhalle" },
		};
		expect(mapUnitSummary(raw)).toMatchObject({ address: "Hafenstr. 1, 48291 Telgte", status: "Verfügbar", title: "Logistikhalle" });
		expect(mapUnitDetail(raw)).toMatchObject({
			broker: { id: 3, name: "Lena Klinnert" },
			custom_fields: { hallenhoehe: "8 m" },
			description: "Halle",
			image_count: 2,
		});
		expect(JSON.stringify(mapUnitDetail(raw))).not.toContain("x@y");
	});

	it("Deals bekommen Phase und Pipeline aus dem Index, Preis aus price oder sold_price", () => {
		const index = stageIndex([{ deal_stages: [{ chance: 0.5, id: 11, name: "Besichtigt" }], id: 1, name: "Vertrieb" }]);
		expect(
			mapDeal({ client: { id: 2, name: "Anna" }, client_id: 2, deal_stage_id: 11, id: 99, property_id: 3, sold_price: 1000 }, index),
		).toMatchObject({ contact: { id: 2, name: "Anna" }, object: { id: 3 }, pipeline: "Vertrieb", price: 1000, stage: "Besichtigt" });
	});

	it("scalar/customFields", () => {
		expect(scalar({ label: "L", value: 3 })).toBe(3);
		expect(scalar({ pretty_value: null, value: "v" })).toBe("v");
		expect(customFields({ a: { value: "" }, b: { value: [] } })).toBeUndefined();
	});
});

describe("Objekt-Detail: interne Notiz, verknüpfte Kontakte, Energie", async () => {
	const { mapUnitDetail, relationshipList } = await import("../src/propstack/mappers");

	it("zeigt Notiz, Eigentümer/Ansprechpartner und Energieträger; Unbekanntes mit Feldnamen statt still zu verschwinden", () => {
		const detail = mapUnitDetail({
			firing_types: { label: "Wesentlicher Energieträger", value: "GAS" },
			id: 1,
			note: { label: "Notiz", value: "Exposé: https://example.org" },
			relationships: [
				{ internal_name: "owner", related_client: { id: 111, name: "Eigentümer GmbH" }, related_client_id: 111 },
				{ internal_name: "partner", name: "Ansprechpartner", related_client_id: 222 },
			],
		});
		expect(detail).toMatchObject({
			contacts: [
				{ contact_id: 111, name: "Eigentümer GmbH", role: "Eigentümer" },
				{ contact_id: 222, role: "Ansprechpartner" },
			],
			energy_source: "GAS",
			internal_note: "Exposé: https://example.org",
		});
		expect(relationshipList([{ foo: 1, bar: 2 }])).toEqual([{ unknown_shape: ["foo", "bar"] }]);
		expect(relationshipList([])).toBeUndefined();
	});
});

describe("Kontakt-Einzelansicht: Quelle mit Namen (Live-Abnahme Kontakte, 12.11.2026)", () => {
	it("zeigt den Namen der Quelle, nicht nur die Nummer; ohne Quelle fehlt das Feld", () => {
		const mit = mapContactDetail({ client_source: { created_at: "2025-01-01", id: 211511, name: "Homepage" }, client_source_id: 211511, id: 1, name: "Anna Muster" });
		expect(mit).toMatchObject({ client_source_id: 211511, source: { id: 211511, name: "Homepage" } });
		expect(mapContactDetail({ client_source: null, id: 1, name: "Anna Muster" })).not.toHaveProperty("source");
	});

	it("zeigt die Website – sonst lässt sich am Firmen-Datensatz nicht nachlesen, was create_company gesetzt hat (Live-Abnahme 12.11.2026)", () => {
		const firma = mapContactDetail({ company: "MCP-TEST Musterfirma GmbH", home_url: null, id: 38366588, is_company: true, name: "MCP-TEST Musterfirma GmbH", office_url: "https://example.com" });
		expect(firma).toMatchObject({ is_company: true, office_url: "https://example.com" });
		expect(firma).not.toHaveProperty("home_url");
	});
});

