import { describe, expect, it } from "vitest";
import { berlinOffset, contactQuery, dayEnd, dayStart, dealQuery, objectQuery } from "../src/propstack/filters";
import { customFields, mapContactDetail, mapContactSummary, mapDeal, mapUnitDetail, mapUnitSummary, scalar, stageIndex } from "../src/propstack/mappers";

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
		expect((out.description as string).length).toBe(1501);
		expect(out).not.toHaveProperty("academic_title");
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
