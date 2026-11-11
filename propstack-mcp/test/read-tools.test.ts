import { describe, expect, it } from "vitest";
import { retentionCutoff, serializeParams } from "../src/audit";
import type { Page, PropstackClient, Query } from "../src/propstack-client";
import { PropstackError } from "../src/propstack-client";
import { runTool } from "../src/tools/register";
import {
	aggregate,
	getContact,
	getObject,
	getProject,
	linkSummary,
	listFields,
	listTags,
	OWNER_PROJECT_LIMIT,
	ownerLinks,
	pipelineStatus,
	searchContacts,
	searchDeals,
	searchObjects,
} from "../src/tools/read-tools";

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
		expect(calls.filter((c) => c.method === "searchContacts")).toHaveLength(1);
		expect(calls[0].query).toMatchObject({ page: 2, per: 10, q: "Anna" });
	});

	it("searchDeals lädt Pipelines für Phasennamen und Kontakt/Objekt per include", async () => {
		const { client, calls } = fakeClient();
		const out = await searchDeals(client, { pipeline_id: 1 });
		expect(calls.map((c) => c.method)).toEqual(["listDealPipelines", "searchDeals", "listBrokers"]);
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

describe("Objekte lesen nach Feld-Mapping", () => {
	it("get_object ergänzt den lückenhaften Einzel-GET um den expand-Kanal", async () => {
		const { client, calls } = fakeClient({
			getUnit: async () => ({ broker: { id: 3, name: "Lena" }, id: 9, lat: 51.1, status: { id: 163674, name: "Vermarktung" }, title: "Halle" }),
			searchUnits: async () =>
				page([{ hall_height: { label: "Hallenhöhe", value: 10 }, id: { value: 9 }, industrial_area: { label: "Hallenfläche", value: 5863 }, lat: 51, rs_category: { value: "HALL" } }]),
		});
		const out = (await getObject(client, { id: 9 })).result as Record<string, unknown>;
		expect(out).toMatchObject({ hall_height: 10, industrial_area: 5863, lat: 51.1, rs_category: "HALL", status: "Vermarktung" });
	});

	it("list_fields zeigt Einheit, Option-IDs und gesperrte Felder", async () => {
		const { client } = fakeClient({
			listCustomFieldGroups: async () =>
				page([
					{
						custom_fields: [
							{ field_type: "Number", name: "mezzanineflache", unit: "euro" },
							{ custom_options: [{ id: 1, name: "Ja" }], field_type: "Dropdown", name: "spekulative_entwicklung" },
						],
						name: "Webseite",
					},
				]),
		});
		const out = (await listFields(client, { entity: "objects" })).result as { groups: { fields: Record<string, unknown>[] }[] };
		expect(out.groups[0].fields).toEqual([
			{ blocked: expect.stringMatching(/Euro/), key: "mezzanineflache", type: "Number", unit: "euro" },
			{ key: "spekulative_entwicklung", options: [{ id: 1, name: "Ja" }], type: "Dropdown" },
		]);
	});
});

describe("Diagnose: Verknüpfungen", () => {
	const relationships = [
		{ client_id: 17366591, id: 1, internal_name: "owner", name: null, project_id: 566962, related_type: "Project" },
		{ client_id: 17366591, id: 2, internal_name: "partner", name: "Ansprechpartner", property: { id: 5, title: "Geheimer Titel" }, related_type: "Property" },
	];

	it("linkSummary: Feldnamen über alle Einträge, Art-Felder mit Ausprägungen – keine Inhalte", () => {
		const summary = linkSummary(relationships)!;
		expect(summary.count).toBe(2);
		expect(summary.fields).toMatchObject({ client_id: "number", internal_name: "string", name: "leer | string", project_id: "number", property: "Objekt{id, title}" });
		expect(summary.kinds).toEqual({ internal_name: ["owner", "partner"], related_type: ["Project", "Property"] });
		expect(JSON.stringify(summary)).not.toContain("Geheimer Titel");
		expect(JSON.stringify(summary)).not.toContain("17366591");
		expect(linkSummary(undefined)).toBeUndefined();
		expect(linkSummary([7, null])).toEqual({ count: 2, fields: { "(Eintrag)": "number | leer" } });
	});

	it("get_contact diagnose liest den Kontakt mit Verknüpfungen und gibt nur Namen und Typen aus", async () => {
		const { client, calls } = fakeClient({
			getContactLinks: async (id: number) => {
				calls.push({ method: `getContactLinks:${id}` });
				return { id, name: "Hillwood Germany GmbH", owned_properties: [{ id: 3063644, title: "Geheimer Titel" }], relationships };
			},
		});
		const { result } = await getContact(client, { diagnose: "field_names", id: 17366591 });
		expect(calls.map((c) => c.method)).toEqual(["getContactLinks:17366591"]);
		expect(result).toMatchObject({
			entity: "contact",
			field_names: { name: "string", owned_properties: "Liste[1] von {id, title}" },
			links: { owned_properties: { count: 1, fields: { id: "number", title: "string" } }, relationships: { count: 2 } },
		});
		expect(JSON.stringify(result)).not.toContain("Hillwood");
		expect(JSON.stringify(result)).not.toContain("Geheimer Titel");
	});

	it("get_project diagnose=list_channel: Projektliste einfach und mit expand, Fehler wird gemeldet statt geworfen", async () => {
		const { client } = fakeClient({
			listProjects: async () => page([{ id: 1, title: "A" }, { id: 2, title: "B" }]),
			listProjectsExpanded: async () =>
				page([
					{ description_note: "Text", id: 1, relationships: [], title: "A" },
					{ description_note: "Text", id: 2, relationships: [relationships[0]], title: "B" },
				]),
		});
		const { result } = await getProject(client, { diagnose: "list_channel", id: 2 });
		expect(result).toMatchObject({
			entity: "project",
			list_channel: {
				expand: { fields: ["description_note", "id", "relationships", "title"], relationships: { count: 1, kinds: { internal_name: ["owner"] } }, rows: 2, rows_with_linked_contact: 1, rows_with_relationships: 2 },
				fields: ["id", "title"],
				rows: 2,
			},
		});

		const failing = fakeClient({
			listProjects: async () => page([{ id: 1 }]),
			listProjectsExpanded: async () => {
				throw new PropstackError("Propstack nicht erreichbar: timeout", 0);
			},
		});
		const failed = (await getProject(failing.client, { diagnose: "list_channel", id: 1 })).result as { list_channel: { expand: { error: string } } };
		expect(failed.list_channel.expand.error).toContain("timeout");
	});
});

describe("Suche nach Eigentümer (owner_contact_id)", () => {
	// Form wie live am 11.11.2026 (Hillwood): Eigentümer meist nur am Projekt, an Einzelobjekten direkt
	const HILLWOOD = {
		id: 17366591,
		name: "Hillwood Germany GmbH",
		relationships: [
			{ client: null, id: 1, internal_name: "owner", name: null, project: { id: 566962, name: "Logistikpark in (14) Falkensee" }, property: null, related_client: { id: 17366591, name: "Hillwood Germany GmbH" } },
			{ client: null, id: 2, internal_name: "owner", name: null, project: { id: 503126, name: "Logistikflächen in (40) Düsseldorf" }, property: null, related_client: { id: 17366591, name: "Hillwood Germany GmbH" } },
			// an der Einheit direkt verknüpft (zugleich Einheit eines Projekts) und ein Einzelobjekt ohne Projekt
			{ client: null, id: 3, internal_name: "owner", name: null, project: null, property: { id: 5121159, name: "Unit 1" }, related_client: { id: 17366591, name: "Hillwood Germany GmbH" } },
			{ client: null, id: 4, internal_name: "owner", name: null, project: null, property: { id: 3063644, name: "Falkensee alt" }, related_client: { id: 17366591, name: "Hillwood Germany GmbH" } },
			// andere Rolle und Kontakt-zu-Kontakt zählen nicht
			{ client: null, id: 5, internal_name: "partner", name: "Ansprechpartner", project: { id: 999, name: "Fremdes Projekt" }, property: null, related_client: { id: 17366591, name: "Hillwood Germany GmbH" } },
			{ client: { id: 17366591, name: "Hillwood Germany GmbH" }, id: 6, internal_name: "associate", name: "Mitarbeiter", project: null, property: null, related_client: { id: 17366586, name: "Arndt Rellecke" } },
			// nennt der Eintrag einen anderen Kontakt, gehört er nicht zu diesem
			{ client: null, id: 7, internal_name: "owner", name: null, project: { id: 888, name: "Projekt eines anderen" }, property: null, related_client: { id: 4711, name: "Anderer" } },
		],
	};
	const unit = (id: number, project_id: number | null, extra: Record<string, unknown> = {}) => ({
		city: project_id === 503126 ? "Düsseldorf" : "Falkensee",
		id,
		project_id,
		status: { id: 163674, name: "Vermarktung" },
		title: `Objekt ${id}`,
		unit_id: `Halle ${id % 10}`,
		zip_code: project_id === 503126 ? "40597" : "14612",
		...extra,
	});
	const UNITS = [
		unit(5766192, 566962),
		unit(5766193, 566962, { archived: true }),
		unit(5121159, 503126),
		unit(5121205, 503126, { status: { id: 163676, name: "Abgeschlossen" } }),
		unit(3063644, null),
		unit(1, 999),
		unit(2, null),
	];
	/** Propstack-Verhalten: project_id, property_ids, archived (Standard: ohne Archivierte), q als Volltext. */
	const unitSearch = (rows = UNITS) => (q?: Query) => {
		let hit = rows;
		if (q?.project_id !== undefined) hit = hit.filter((r) => r.project_id === q.project_id);
		if (q?.property_ids !== undefined) hit = hit.filter((r) => String(q.property_ids).split(",").includes(String(r.id)));
		if (q?.archived !== "-1") hit = hit.filter((r) => !(r as { archived?: boolean }).archived);
		if (typeof q?.q === "string") hit = hit.filter((r) => `${r.city} ${r.zip_code}`.toLowerCase().includes(q.q!.toString().toLowerCase()));
		return page(hit);
	};
	const hillwood = (overrides: Partial<Record<keyof PropstackClient, unknown>> = {}) => {
		const world = fakeClient({ getContactRelationships: async () => structuredClone(HILLWOOD), ...overrides });
		const calls = world.calls;
		const client = { ...world.client, searchUnits: async (q?: Query) => (calls.push({ method: "searchUnits", query: q }), unitSearch()(q)), ...overrides } as unknown as PropstackClient;
		return { calls, client };
	};
	type OwnerResult = { total: number; items: { id: number }[]; owner: { objects_total: number; objects_via_projects: number; objects_linked_directly: number; projects: { id: number; name: string; objects: number }[]; note: string } };

	it("ownerLinks: nur Eigentümer-Verknüpfungen dieses Kontakts; fehlt die Liste, wird abgebrochen", async () => {
		const links = await ownerLinks({ getContactRelationships: async () => HILLWOOD } as never, 17366591);
		expect([...links.projects]).toEqual([[566962, "Logistikpark in (14) Falkensee"], [503126, "Logistikflächen in (40) Düsseldorf"]]);
		expect([...links.direct]).toEqual([5121159, 3063644]);
		expect(links.otherRoles).toBe(2);
		expect(links.contact).toEqual({ id: 17366591, name: "Hillwood Germany GmbH" });
		await expect(ownerLinks({ getContactRelationships: async () => ({ id: 1, name: "X" }) } as never, 1)).rejects.toThrow(/liefert die Verknüpfungen dieses Kontakts nicht/);
	});

	it("findet den ganzen Bestand: Einheiten der Projekte des Eigentümers UND direkt verknüpfte Objekte", async () => {
		const { client, calls } = hillwood();
		const { result, count } = await searchObjects(client, { owner_contact_id: 17366591 });
		const r = result as OwnerResult;
		// 5 Objekte gehören dem Eigentümer (eines davon archiviert); fremde (1, 2) bleiben draußen
		expect(r.owner).toMatchObject({ contact: { id: 17366591, name: "Hillwood Germany GmbH" }, objects_linked_directly: 2, objects_total: 5, objects_via_projects: 4 });
		expect(r.owner.projects).toEqual([
			{ id: 503126, name: "Logistikflächen in (40) Düsseldorf", objects: 2 },
			{ id: 566962, name: "Logistikpark in (14) Falkensee", objects: 2 },
		]);
		// sortiert nach Projekt und Einheit, Einzelobjekt zuletzt; das archivierte fehlt und wird genannt
		expect(r.items.map((i) => i.id)).toEqual([5121205, 5121159, 5766192, 3063644]);
		expect(count).toBe(4);
		expect(r.owner.note).toMatch(/1 der 5 Objekte sind hier nicht enthalten \(archiviert/);
		expect(r.owner.note).toMatch(/Datensätze ohne diese Verknüpfung .* findet die Suche nicht/);
		// je Projekt eine Abfrage (mit Archivierten), dann die Treffer in einem Rutsch
		const unitCalls = calls.filter((c) => c.method === "searchUnits").map((c) => c.query);
		expect(unitCalls.slice(0, 2)).toEqual([expect.objectContaining({ archived: "-1", project_id: 566962 }), expect.objectContaining({ archived: "-1", project_id: 503126 })]);
		expect(String(unitCalls[2]?.property_ids).split(",").sort()).toEqual(["3063644", "5121159", "5121205", "5766192", "5766193"]);
	});

	it("lässt sich mit den übrigen Filtern kombinieren (Status, Ort, Archivierte, object_ids)", async () => {
		const { client } = hillwood();
		const ids = async (input: Parameters<typeof searchObjects>[1]) => ((await searchObjects(client, input)).result as OwnerResult).items?.map((i) => i.id) ?? [];
		expect(await ids({ owner_contact_id: 17366591, status_ids: [163674] })).toEqual([5121159, 5766192, 3063644]);
		expect(await ids({ city: "Düsseldorf", owner_contact_id: 17366591 })).toEqual([5121205, 5121159]);
		expect(await ids({ archived: "include", owner_contact_id: 17366591 })).toEqual([5121205, 5121159, 5766192, 5766193, 3063644]);
		// object_ids schränkt ein, erweitert aber nie über den Bestand des Eigentümers hinaus
		expect(await ids({ object_ids: [5766192, 1], owner_contact_id: 17366591 })).toEqual([5766192]);
		await expect(searchObjects(client, { owner_contact_id: 17366591, tag_ids: [1, 2], tag_match: "all" })).rejects.toThrow(/nicht mit tag_match=all kombinieren/);
		// sort_by wirkt hier nicht – das wird gesagt statt verschwiegen
		expect(((await searchObjects(client, { owner_contact_id: 17366591, sort_by: "created_at" })).result as OwnerResult).owner.note).toMatch(/sort_by wirkt zusammen mit owner_contact_id nicht/);
	});

	it("Kontakt ohne Eigentümer-Verknüpfung: leeres Ergebnis mit Hinweis statt stiller Null", async () => {
		const { client, calls } = hillwood({
			getContactRelationships: async () => ({ id: 17366586, name: "Arndt Rellecke", relationships: [HILLWOOD.relationships[4], HILLWOOD.relationships[5]] }),
		});
		const { result, count } = await searchObjects(client, { owner_contact_id: 17366586 });
		expect(count).toBe(0);
		expect((result as OwnerResult).owner.note).toMatch(/nirgends als Eigentümer verknüpft – aber 1-mal in anderer Rolle .* Eigentümer ist meist der Firmenkontakt/);
		expect(calls.filter((c) => c.method === "searchUnits")).toHaveLength(0);
	});

	it("viele Projekte: statt je Projekt wird der Bestand einmal geladen und nach Projekt gefiltert", async () => {
		const many = Array.from({ length: OWNER_PROJECT_LIMIT + 1 }, (_, i) => ({
			client: null,
			id: i,
			internal_name: "owner",
			name: null,
			project: { id: 1000 + i, name: `Projekt ${String(i).padStart(2, "0")}` },
			property: null,
			related_client: { id: 5, name: "Großer Eigentümer" },
		}));
		const rows = [...many.map((m, i) => unit(9000 + i, m.project.id)), unit(1, 999)];
		const calls: (Query | undefined)[] = [];
		const { client } = hillwood({
			getContactRelationships: async () => ({ id: 5, name: "Großer Eigentümer", relationships: many }),
			searchUnits: async (q?: Query) => (calls.push(q), unitSearch(rows)(q)),
		});
		const { result } = await searchObjects(client, { owner_contact_id: 5, per_page: 50 });
		const r = result as OwnerResult;
		expect(r.owner.objects_total).toBe(OWNER_PROJECT_LIMIT + 1);
		expect(r.total).toBe(OWNER_PROJECT_LIMIT + 1);
		expect(r.owner.projects.every((p) => p.objects === 1)).toBe(true);
		// keine Abfrage je Projekt
		expect(calls.some((q) => q?.project_id !== undefined)).toBe(false);
		expect(calls[0]).toMatchObject({ archived: "-1" });
	});
});
