import { describe, expect, it } from "vitest";
import type { Page, PropstackClient, Query } from "../src/propstack-client";
import { aggregate, matchesLocation, pipelineStatus, searchContacts, searchObjects, searchDeals, getContact } from "../src/tools/read-tools";

// Regressionstests zu den Befunden aus dem Live-Test vom 09.10.2026.

const page = (rows: Record<string, unknown>[], total: number | null = rows.length): Page => ({ rows, total });
const ids = (from: number, n: number) => Array.from({ length: n }, (_, i) => ({ id: from + i, name: `K${from + i}` }));

function recorder<T extends object>(impl: T) {
	const calls: { method: string; query?: Query }[] = [];
	const client = new Proxy(impl as Record<string, unknown>, {
		get(target, prop: string) {
			const fn = target[prop];
			if (typeof fn !== "function") return fn;
			return async (q?: Query) => {
				calls.push({ method: prop, query: q });
				return (fn as (q?: Query) => unknown)(q);
			};
		},
	}) as unknown as PropstackClient;
	return { calls, client };
}

describe("Bug 1: Merkmale UND vs. ODER", () => {
	// Logistiker 78, E-Com 85, Überschneidung 28 – wie live gemessen.
	const logistik = ids(1, 78);
	const ecom = [...ids(51, 28), ...ids(1000, 57)];
	const contacts = {
		listBrokers: () => [{ id: 254958, name: "Lena Klinnert" }],
		searchContacts: (q: Query) => {
			const group = q.group as number[] | undefined;
			if (group?.length === 1 && group[0] === 636740) return page(logistik, 78);
			if (group?.length === 1 && group[0] === 718303) return page(ecom, 85);
			return page(ids(1, 20), 135); // Propstack: ODER
		},
	};

	it("tag_match=all bildet die Schnittmenge: 28 statt 135", async () => {
		const { client } = recorder(contacts);
		const out = await searchContacts(client, { per_page: 50, tag_ids: [636740, 718303], tag_match: "all" });
		expect(out.count).toBe(28);
		expect((out.result as { items: { id: number }[] }).items.map((i) => i.id)).toEqual(ids(51, 28).map((r) => r.id));
	});

	it("Standard bleibt ODER (eine Anfrage, Propstack-Gesamtzahl)", async () => {
		const { client, calls } = recorder(contacts);
		const out = await searchContacts(client, { tag_ids: [636740, 718303] });
		expect(out.count).toBe(135);
		expect(calls.filter((c) => c.method === "searchContacts")).toHaveLength(1);
	});

	it("aggregate lehnt tag_match=all ab statt falsch zu zählen", async () => {
		const { client } = recorder(contacts);
		await expect(
			aggregate(client, { contact_filters: { tag_ids: [1, 2], tag_match: "all" }, entity: "contacts", group_by: "source" }),
		).rejects.toThrow(/nur mit ODER/);
	});
});

describe("Bug 2: Ortsfilter und Objekte ohne Status", () => {
	const units = [
		{ city: "Leverkusen", id: 1, status: { id: 163674, name: "Vermarktung" }, zip_code: "51373" },
		{ city: "Leverkusen", id: 2, status: { id: 163674, name: "Vermarktung" }, zip_code: "51373" },
		{ city: "Mannheim", id: 5231701, status: { id: 163674, name: "Vermarktung" }, zip_code: "68169" },
		{ city: "Leverkusen", id: 3, status: null, zip_code: "51377" },
		{ city: "Leverkusen-Opladen", id: 4, status: { id: 99, name: "Vermietet" }, zip_code: "51379" },
	];

	it("city filtert exakt (Mannheim raus, Ortsteile drin) und meldet Objekte ohne Status", async () => {
		const { client, calls } = recorder({ listBrokers: () => [], searchUnits: () => page(units, units.length) });
		const out = await searchObjects(client, { city: "Leverkusen", marketing_type: "RENT", status_ids: [163674] });
		const result = out.result as { items: { id: number }[]; excluded_without_status: number; total: number; note: string };
		expect(result.items.map((i) => i.id)).toEqual([1, 2]);
		expect(result.total).toBe(2);
		expect(result.excluded_without_status).toBe(1);
		expect(result.note).toMatch(/keinen Status/);
		// Status wird clientseitig gefiltert, damit Objekte ohne Status zählbar sind
		expect(calls.find((c) => c.method === "searchUnits")?.query).toMatchObject({ marketing_type: "RENT", q: "Leverkusen" });
		expect(calls.find((c) => c.method === "searchUnits")?.query?.status).toBeUndefined();
	});

	it("matchesLocation: Ortsteile ja, Teilwörter nein, PLZ-Präfix", () => {
		expect(matchesLocation({ city: "Leverkusen-Opladen" }, "leverkusen")).toBe(true);
		expect(matchesLocation({ city: "Leverkusener Str." }, "Leverkusen")).toBe(false);
		expect(matchesLocation({ zip_code: "51373" }, undefined, "51")).toBe(true);
		expect(matchesLocation({ zip_code: "68169" }, undefined, "51")).toBe(false);
	});

	it("ohne Ortsfilter: Objekte ohne Status über zwei Zählabfragen", async () => {
		const { client } = recorder({
			listBrokers: () => [],
			listPropertyStatuses: () => page([{ id: 163674 }, { id: 99 }]),
			searchUnits: (q: Query) => (q.per === 1 ? page([], q.status ? 18 : 19) : page([units[0], units[1]], 2)),
		});
		const out = await searchObjects(client, { query: "Leverkusen", status_ids: [163674] });
		expect(out.result).toMatchObject({ excluded_without_status: 1, total: 2 });
	});

	it("aggregate lehnt city ab", async () => {
		const { client } = recorder({});
		await expect(aggregate(client, { entity: "objects", group_by: "status", object_filters: { city: "Leverkusen" } })).rejects.toThrow(
			/city/,
		);
	});
});

describe("Betreuername statt nur ID", () => {
	it("get_contact, search_deals liefern broker_name", async () => {
		const { client } = recorder({
			getContact: () => ({ broker_id: 254958, id: 24433456, name: "Konstantin Brockmann" }),
			listBrokers: () => [{ id: 254958, name: "Lena Klinnert" }],
			listDealPipelines: () => page([]),
			searchDeals: () => page([{ broker_id: 254958, id: 1 }]),
		});
		expect((await getContact(client, { id: 24433456 })).result).toMatchObject({ broker_id: 254958, broker_name: "Lena Klinnert" });
		expect(((await searchDeals(client, {})).result as { items: unknown[] }).items[0]).toMatchObject({ broker_name: "Lena Klinnert" });
	});
});

describe("pipeline_status: Lücken offenlegen", () => {
	const pipelines = page([
		{
			deal_stages: [
				{ chance: 0.05, id: 1, name: "Absage", position: 9 },
				{ chance: 0.3, id: 2, name: "Expose versendet", position: 1 },
			],
			id: 266668,
			name: "300 Sontra",
		},
	]);

	it("Sontra: 268 in Phasen + 2 ohne Phase = 270, ohne Preise keine 0-€-Summen", async () => {
		const deals = [...Array.from({ length: 268 }, (_, i) => ({ deal_stage_id: 2, id: i })), { deal_stage_id: null, id: 900 }, { deal_stage_id: null, id: 901 }];
		const { client } = recorder({ listDealPipelines: () => pipelines, searchDeals: () => page(deals, 270) });
		const out = await pipelineStatus(client, { pipeline_id: 266668 });
		const result = out.result as Record<string, unknown> & { totals: Record<string, unknown>; stages: Record<string, unknown>[] };
		expect(out.count).toBe(270);
		expect(result.deals_total).toBe(270);
		expect(result.outside_stages).toBe(2);
		expect(result.totals).toEqual({ count: 268 });
		expect(result.values_available).toBe(false);
		expect(result.stages.every((s) => s.sum_price === undefined && s.weighted_value === undefined)).toBe(true);
		expect(result.note).toMatch(/2 Deals sind keiner Phase/);
		expect(result.note).toMatch(/Kein Deal hat einen Preis/);
	});
});
