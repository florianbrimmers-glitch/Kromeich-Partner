import { describe, expect, it } from "vitest";
import { retentionCutoff, serializeParams } from "../src/audit";
import type { Page, PropstackClient, Query } from "../src/propstack-client";
import { PropstackError } from "../src/propstack-client";
import { runTool } from "../src/tools/register";
import { aggregate, listTags, pipelineStatus, searchContacts, searchDeals } from "../src/tools/read-tools";

const page = (rows: Record<string, unknown>[], total: number | null = rows.length): Page => ({ rows, total });

const PIPELINES = [
	{
		deal_stages: [
			{ chance: 0.2, id: 11, name: "Besichtigt", position: 0 },
			{ chance: 0.9, id: 12, name: "Notartermin", position: 2 },
			{ chance: null, id: 13, name: "Offen", position: 1 },
		],
		id: 1,
		name: "Vertrieb",
	},
];

/** Simuliertes Propstack mit Aufzeichnung der Anfragen. */
function fakeClient(overrides: Partial<Record<keyof PropstackClient, unknown>> = {}) {
	const calls: { method: string; query?: Query }[] = [];
	const rec =
		(method: string, fn: (q?: Query) => unknown) =>
		async (q?: Query) => {
			calls.push({ method, query: q });
			return fn(q);
		};
	const client = {
		getContact: rec("getContact", () => ({ id: 1 })),
		getUnit: rec("getUnit", () => ({ id: 1 })),
		listBrokers: rec("listBrokers", () => [
			{ id: 101, name: "Florian" },
			{ id: 102, name: "Lena" },
		]),
		listContactSources: rec("listContactSources", () => page([{ id: 4, name: "Website" }, { id: 5, name: "Messe" }])),
		listCustomFieldGroups: rec("listCustomFieldGroups", () => page([])),
		listDealPipelines: rec("listDealPipelines", () => page(PIPELINES)),
		listGroups: rec("listGroups", () =>
			page([
				{ id: 1, name: "Investor", super_group_id: 50 },
				{ id: 2, name: "Eigentümer", super_group_id: 50 },
				{ id: 3, name: "VIP", super_group_id: null },
			]),
		),
		listProjects: rec("listProjects", () => page([])),
		listPropertyStatuses: rec("listPropertyStatuses", () => page([{ id: 274, name: "Verfügbar" }, { id: 278, name: "Verkauft" }])),
		listSuperGroups: rec("listSuperGroups", () => page([{ id: 50, name: "Rolle" }])),
		searchContacts: rec("searchContacts", (q) => {
			const sources = (q?.sources as number[] | undefined)?.[0];
			const total = sources === 4 ? 30 : sources === 5 ? 0 : 42;
			return page([{ id: 1, name: "Anna", phone: "040" }], total);
		}),
		searchDeals: rec("searchDeals", () =>
			page(
				[
					{ deal_stage_id: 11, id: 1, price: 100_000 },
					{ deal_stage_id: 11, id: 2, sold_price: 50_000 },
					{ deal_stage_id: 12, id: 3, price: 200_000 },
					{ deal_stage_id: 13, id: 4 },
				],
				4,
			),
		),
		searchUnits: rec("searchUnits", (q) => page([], q?.status === "274" ? 7 : q?.status === "278" ? 3 : 10)),
		...overrides,
	} as unknown as PropstackClient;
	return { calls, client };
}

describe("Such-Tools", () => {
	it("searchContacts: Paginierung, Gesamtzahl, gekürzte Treffer", async () => {
		const { client, calls } = fakeClient();
		const out = await searchContacts(client, { page: 2, per_page: 10, query: "Anna" });
		expect(out.count).toBe(42);
		expect(out.result).toEqual({ has_more: true, items: [{ id: 1, name: "Anna", phone: "040" }], page: 2, per_page: 10, total: 42 });
		expect(calls[0].query).toMatchObject({ page: 2, per: 10, q: "Anna" });
	});

	it("searchDeals lädt Pipelines für Phasennamen und Kontakt/Objekt per include", async () => {
		const { client, calls } = fakeClient();
		const out = await searchDeals(client, { pipeline_id: 1 });
		expect(calls.map((c) => c.method)).toEqual(["listDealPipelines", "searchDeals"]);
		expect(calls[1].query).toMatchObject({ deal_pipeline_id: 1, include: "client,property" });
		expect((out.result as { items: { stage: string }[] }).items[0].stage).toBe("Besichtigt");
	});
});

describe("pipeline_status", () => {
	it("ohne ID: Pipelines mit Phasen in Positionsreihenfolge", async () => {
		const { client } = fakeClient();
		const out = await pipelineStatus(client, {});
		expect((out.result as { pipelines: { stages: { name: string }[] }[] }).pipelines[0].stages.map((s) => s.name)).toEqual([
			"Besichtigt",
			"Offen",
			"Notartermin",
		]);
	});

	it("mit ID: Anzahl, Summe und gewichteter Wert je Phase", async () => {
		const { client } = fakeClient();
		const out = await pipelineStatus(client, { pipeline_id: 1 });
		const result = out.result as { stages: Record<string, unknown>[]; totals: Record<string, number>; complete: boolean };
		expect(result.complete).toBe(true);
		expect(result.stages).toEqual([
			{ chance: 0.2, count: 2, id: 11, name: "Besichtigt", sum_price: 150_000, weighted_value: 30_000 },
			{ count: 1, deals_without_price: 1, id: 13, name: "Offen", sum_price: 0 },
			{ chance: 0.9, count: 1, id: 12, name: "Notartermin", sum_price: 200_000, weighted_value: 180_000 },
		]);
		expect(result.totals).toEqual({ count: 4, sum_price: 350_000, weighted_value: 210_000 });
	});

	it("meldet unvollständige Auswertung, wenn das Seitenbudget nicht reicht", async () => {
		const full = Array.from({ length: 200 }, (_, i) => ({ deal_stage_id: 11, id: i, price: 1 }));
		const { client } = fakeClient({ searchDeals: async () => page(full, 100_000) });
		const out = await pipelineStatus(client, { pipeline_id: 1 });
		expect(out.result).toMatchObject({ complete: false, note: expect.stringMatching(/8000 von 100000/) });
	});

	it("unbekannte Pipeline → 404", async () => {
		const { client } = fakeClient();
		await expect(pipelineStatus(client, { pipeline_id: 999 })).rejects.toThrow(/nicht gefunden/);
	});
});

describe("aggregate", () => {
	it("zählt Kontakte je Quelle über total_count (per=1), Nullgruppen werden zusammengefasst", async () => {
		const { client, calls } = fakeClient();
		const out = await aggregate(client, { contact_filters: { tag_ids: [1] }, entity: "contacts", group_by: "source" });
		expect(out.result).toEqual({
			entity: "contacts",
			group_by: "source",
			groups: [{ count: 30, id: 4, name: "Website" }],
			groups_without_hits: 1,
			note: "12 ohne Zuordnung in dieser Dimension.",
			total: 42,
		});
		const counts = calls.filter((c) => c.method === "searchContacts");
		expect(counts.every((c) => c.query?.per === 1 && (c.query?.group as number[])[0] === 1)).toBe(true);
	});

	it("Objekte je Status nutzen kommagetrennte Status-IDs", async () => {
		const { client } = fakeClient();
		const out = await aggregate(client, { entity: "objects", group_by: "status" });
		expect(out.result).toMatchObject({ groups: [{ count: 7, name: "Verfügbar" }, { count: 3, name: "Verkauft" }], total: 10 });
	});

	it("Tags: Obermerkmal einschränken, Hinweis auf Mehrfachvergabe", async () => {
		const { client } = fakeClient();
		const out = await aggregate(client, { entity: "contacts", group_by: "tag", tag_super_group_id: 50 });
		expect((out.result as { groups: unknown[] }).groups).toHaveLength(2);
		expect(out.result).toMatchObject({ note: expect.stringMatching(/mehrfach/) });
	});

	it("zu viele Gruppen → klare Fehlermeldung statt 50 Anfragen", async () => {
		const many = Array.from({ length: 60 }, (_, i) => ({ id: i + 1, name: `T${i}`, super_group_id: 1 }));
		const { client, calls } = fakeClient({ listGroups: async () => page(many) });
		await expect(aggregate(client, { entity: "contacts", group_by: "tag" })).rejects.toThrow(/tag_super_group_id/);
		expect(calls.filter((c) => c.method === "searchContacts")).toHaveLength(0);
	});

	it("unzulässige Kombination und fehlende Pipeline", async () => {
		const { client } = fakeClient();
		await expect(aggregate(client, { entity: "objects", group_by: "source" })).rejects.toThrow(/nicht möglich/);
		await expect(aggregate(client, { entity: "deals", group_by: "stage" })).rejects.toThrow(/pipeline_id/);
	});

	it("Deals je Phase liefert Summen wie pipeline_status", async () => {
		const { client } = fakeClient();
		const out = await aggregate(client, { deal_filters: { pipeline_id: 1 }, entity: "deals", group_by: "stage" });
		expect(out.result).toMatchObject({ totals: { count: 4, weighted_value: 210_000 } });
	});
});

describe("list_tags", () => {
	it("gruppiert nach Obermerkmal, ohne Obermerkmal separat", async () => {
		const { client } = fakeClient();
		const out = await listTags(client, { entity: "contacts" });
		expect(out.result).toEqual({
			categories: [
				{ name: "Rolle", super_group_id: 50, tags: [{ id: 1, name: "Investor" }, { id: 2, name: "Eigentümer" }] },
				{ name: "Ohne Obermerkmal", tags: [{ id: 3, name: "VIP" }] },
			],
			entity: "contacts",
		});
	});
});

describe("runTool + Audit-Log", () => {
	function fakeDb(fail = false) {
		const inserts: unknown[][] = [];
		const db = {
			prepare: () => ({
				bind: (...args: unknown[]) => ({
					run: async () => {
						if (fail) throw new Error("D1 down");
						inserts.push(args);
						return { meta: { changes: 1 } };
					},
				}),
			}),
		} as unknown as D1Database;
		return { db, inserts };
	}

	const props = () => ({ brokerId: 347158, email: "florian.brimmers@kromeichpartner.de", name: "Florian" });
	let tick = 1_800_000_000_000;
	const now = () => (tick += 25);

	it("protokolliert Erfolg mit Nutzer, Tool, Parametern, Trefferzahl und Dauer", async () => {
		const { db, inserts } = fakeDb();
		const result = await runTool(
			{ createClient: () => ({}) as PropstackClient, env: { AUDIT_DB: db } as Env, now, props },
			"search_contacts",
			{ query: "Müller" },
			async () => ({ count: 3, result: { items: [] } }),
		);
		expect(result).toEqual({ content: [{ text: '{"items":[]}', type: "text" }] });
		const [ts, email, broker, tool, params, count, ok, error, duration] = inserts[0];
		expect([email, broker, tool, params, count, ok, error, duration]).toEqual([
			"florian.brimmers@kromeichpartner.de",
			347158,
			"search_contacts",
			'{"query":"Müller"}',
			3,
			1,
			null,
			25,
		]);
		expect(ts).toMatch(/^\d{4}-\d{2}-\d{2}T/);
	});

	it("Propstack-Fehler → isError mit Meldung, Audit mit ok=0", async () => {
		const { db, inserts } = fakeDb();
		const result = await runTool(
			{ createClient: () => ({}) as PropstackClient, env: { AUDIT_DB: db } as Env, now, props },
			"get_contact",
			{ id: 1 },
			async () => {
				throw new PropstackError("Nicht gefunden (404)", 404);
			},
		);
		expect(result).toEqual({ content: [{ text: "Nicht gefunden (404)", type: "text" }], isError: true });
		expect(inserts[0][6]).toBe(0);
		expect(inserts[0][7]).toBe("Nicht gefunden (404)");
	});

	it("unerwartete Fehler geben keine Interna preis", async () => {
		const { db } = fakeDb();
		const result = await runTool(
			{ createClient: () => ({}) as PropstackClient, env: { AUDIT_DB: db } as Env, now, props },
			"x",
			{},
			async () => {
				throw new Error("TypeError at secret/internal/path.ts:42");
			},
		);
		expect(result.content[0].text).toBe("Interner Fehler im Propstack-Connector.");
	});

	it("ein kaputtes Audit-Log bricht Lese-Tools nicht ab", async () => {
		const { db } = fakeDb(true);
		const result = await runTool(
			{ createClient: () => ({}) as PropstackClient, env: { AUDIT_DB: db } as Env, now, props },
			"whoami",
			{},
			async () => ({ count: 1, result: { ok: true } }),
		);
		expect(result.isError).toBeUndefined();
	});

	it("Parameter werden begrenzt, Aufbewahrung 12 Monate", () => {
		expect(serializeParams({ q: "x".repeat(5000) }).length).toBe(2001);
		expect(retentionCutoff(new Date("2026-10-09T00:00:00Z"))).toBe("2025-10-09T00:00:00.000Z");
	});
});
