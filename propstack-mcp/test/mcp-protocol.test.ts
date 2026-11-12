import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Kein Netz in Tests: Geokodierung (OpenStreetMap) findet nichts
beforeEach(() => {
	vi.stubGlobal("fetch", async () => new Response("[]", { status: 200 }));
});
import type { PropstackClient } from "../src/propstack-client";
import { registerReadTools, registerWriteTools } from "../src/tools/register";

// Ende-zu-Ende über das echte MCP-Protokoll (In-Memory): Tool-Liste, JSON-Schemas,
// Eingabevalidierung und Ergebnisformat – so wie Claude die Tools sieht.

async function connect(fakeClient: Partial<PropstackClient> = {}) {
	const server = new McpServer({ name: "test", version: "0" });
	const audits: unknown[][] = [];
	const db = {
		prepare: () => ({ bind: (...a: unknown[]) => ({ run: async () => audits.push(a) }) }),
	} as unknown as D1Database;
	registerReadTools(server, {
		createClient: () => fakeClient as PropstackClient,
		env: { AUDIT_DB: db } as Env,
		props: () => ({ brokerId: 1, email: "t@kromeichpartner.de", name: "T" }),
	});
	const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
	await server.connect(serverTransport);
	const client = new Client({ name: "claude-test", version: "0" });
	await client.connect(clientTransport);
	return { audits, client };
}

describe("MCP-Protokoll", () => {
	it("listet genau die erwarteten Lese-Tools mit Schemas und readOnlyHint", async () => {
		const { client } = await connect();
		const { tools } = await client.listTools();
		expect(tools.map((t) => t.name).sort()).toEqual([
			"aggregate",
			"dashboard_daten",
			"get_contact",
			"get_object",
			"get_project",
			"list_fields",
			"list_reference",
			"list_tags",
			"pipeline_status",
			"search_contacts",
			"search_deals",
			"search_objects",
		]);
		for (const tool of tools) {
			expect(tool.annotations?.readOnlyHint).toBe(true);
			expect(tool.inputSchema.type).toBe("object");
			// Harte Regel: keine Delete- und keine Passthrough-Tools
			expect(tool.name).not.toMatch(/delete|remove|raw|request|passthrough|call_api/i);
		}
		const search = tools.find((t) => t.name === "search_objects")!;
		expect(Object.keys(search.inputSchema.properties ?? {})).toEqual(
			expect.arrayContaining(["query", "status_ids", "marketing_type", "price", "page", "per_page"]),
		);
	});

	it("validiert Eingaben, bevor Propstack gefragt wird", async () => {
		let called = false;
		const { client } = await connect({
			searchUnits: async () => {
				called = true;
				return { rows: [], total: 0 };
			},
		});
		const result = await client.callTool({ arguments: { per_page: 500 }, name: "search_objects" });
		expect(result.isError).toBe(true);
		expect(called).toBe(false);
	});

	it("unbekannte Parameter werden abgewiesen statt still verworfen (veraltete Tool-Liste im Client)", async () => {
		let called = false;
		const { client } = await connect({
			searchUnits: async () => {
				called = true;
				return { rows: [], total: 0 };
			},
		});
		const { tools } = await client.listTools();
		expect(tools.find((t) => t.name === "search_objects")!.inputSchema.additionalProperties).toBe(false);
		const result = await client.callTool({ arguments: { living_space: { from: 1 }, wohnflaeche: 5 }, name: "search_objects" });
		expect(result.isError).toBe(true);
		expect(JSON.stringify(result.content)).toMatch(/wohnflaeche/);
		expect(called).toBe(false);
	});

	it("führt ein Tool aus, liefert JSON-Text und schreibt das Audit-Log", async () => {
		const { client, audits } = await connect({
			getContact: async () => ({ id: 5, identity_number: "GEHEIM", name: "Anna" }),
			listBrokers: async () => [],
		});
		const result = await client.callTool({ arguments: { id: 5 }, name: "get_contact" });
		expect(result.isError).toBeFalsy();
		const text = (result.content as { text: string }[])[0].text;
		expect(JSON.parse(text)).toEqual({ id: 5, name: "Anna" });
		expect(audits[0][3]).toBe("get_contact");
	});

	it("IDs als Ziffern-Text werden angenommen (Clients mit veralteter Tool-Liste), das Schema bleibt integer", async () => {
		const seen: unknown[] = [];
		const { client } = await connect({
			getContact: async (id: number) => {
				seen.push(id);
				return { id, name: "Anna" };
			},
			listBrokers: async () => [],
		});
		const { tools } = await client.listTools();
		expect((tools.find((t) => t.name === "get_contact")!.inputSchema.properties as Record<string, { type: string }>).id.type).toBe("integer");
		expect((await client.callTool({ arguments: { id: "5" }, name: "get_contact" })).isError).toBeFalsy();
		expect(seen).toEqual([5]);
		// alles andere bleibt streng
		for (const bad of ["5.000", "abc", true, -1]) {
			expect((await client.callTool({ arguments: { id: bad }, name: "get_contact" })).isError).toBe(true);
		}
		expect(seen).toEqual([5]);
	});

	it("get_project: gekürzte Projektdaten mit Einheiten und Bildtiteln; Diagnose liefert nur Feldnamen, keine Werte", async () => {
		const project = {
			city: "Hillscheid",
			courtage: "Provisionsfrei",
			description_note: "Beschreibung",
			id: 604473,
			images: [{ id: 1, is_floorplan: false, title: "Außenansicht", url: "https://geheim.example/bild.jpg" }, { id: 2, is_floorplan: true, title: null }],
			lat: 50.4109821,
			lng: 7.6811256,
			name: "BTS-Logistikhalle in (56) Hillscheid",
			relationships: [{ client_id: 111, id: 1, internal_name: "owner", name: null }, { client_id: 222, id: 2, internal_name: "partner", name: null }],
			show_units_on_landing_page: true,
			status: { color: "#123", label: "Vertrieb" },
			sub_headline: "Direkt an der A48",
			title: { label: "Überschrift", value: "Logistikhalle in (56) Hillscheid" },
		};
		const { client } = await connect({
			getContact: async (id: number) => ({ id, name: id === 111 ? "Eigentümer GmbH" : "Anna Ansprech" }),
			getProject: async () => project,
			listBrokers: async () => [],
			searchUnits: async () => ({ rows: [{ id: 6282819, status: { id: 1, name: "Vermarktung" }, title: "Halle", unit_id: "Unit 1" }], total: 1 }),
		});
		const detail = JSON.parse(((await client.callTool({ arguments: { id: 604473 }, name: "get_project" })).content as { text: string }[])[0].text);
		expect(detail).toMatchObject({
			contacts: [
				{ contact_id: 111, name: "Eigentümer GmbH", role: "Eigentümer" },
				{ contact_id: 222, name: "Anna Ansprech", role: "Ansprechpartner" },
			],
			images: [{ id: 1, title: "Außenansicht" }, { floorplan: true, id: 2 }],
			show_units_on_landing_page: true,
			status: "Vertrieb",
			sub_headline: "Direkt an der A48",
			title: "Logistikhalle in (56) Hillscheid",
			unit_count: 1,
			units: [{ id: 6282819, status: "Vermarktung", unit_id: "Unit 1" }],
		});
		expect(JSON.stringify(detail)).not.toContain("geheim.example");
		const diagnose = ((await client.callTool({ arguments: { diagnose: "field_names", id: 604473 }, name: "get_project" })).content as { text: string }[])[0].text;
		expect(JSON.parse(diagnose).field_names).toMatchObject({ lat: "number", status: "Objekt{color, label}", sub_headline: "string", title: "„Überschrift“ (string)" });
		expect(JSON.parse(diagnose).field_names.images).toMatch(/^Liste\[2\] von \{id, is_floorplan, title, url\}$/);
		// keine Werte
		expect(diagnose).not.toContain("Hillscheid");
		expect(diagnose).not.toContain("Provisionsfrei");
		// mit Filter: nur passende Felder (Name oder Bezeichnung), dafür tiefer aufgeschlüsselt
		const filtered = JSON.parse(((await client.callTool({ arguments: { diagnose: "field_names", diagnose_key: "image", id: 604473 }, name: "get_project" })).content as { text: string }[])[0].text);
		expect(filtered.field_names).toEqual({ images: "Liste[2] von {id: number, is_floorplan: boolean, title: string, url: string}" });
		const byLabel = JSON.parse(((await client.callTool({ arguments: { diagnose: "field_names", diagnose_key: "überschrift", id: 604473 }, name: "get_project" })).content as { text: string }[])[0].text);
		expect(Object.keys(byLabel.field_names)).toEqual(["title"]);
	});

	it("Schreib-Tools: genau dreizehn, nicht readOnly, Updates als überschreibend markiert, kein Löschen", async () => {
		const server = new McpServer({ name: "test", version: "0" });
		const ctx = { env: {} as Env, props: () => ({ brokerId: 1, email: "t@kromeichpartner.de", name: "T" }) };
		registerReadTools(server, ctx);
		registerWriteTools(server, ctx);
		const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
		await server.connect(serverTransport);
		const client = new Client({ name: "claude-test", version: "0" });
		await client.connect(clientTransport);
		const { tools } = await client.listTools();
		const writes = tools.filter((t) => t.annotations?.readOnlyHint === false);
		expect(writes.map((t) => [t.name, t.annotations?.destructiveHint])).toEqual([
			["create_contact", false],
			["update_contact", true],
			["create_object", false],
			["update_object", true],
			["create_project", false],
			["update_project", true],
			["set_project_owner", false],
			["add_images", false],
			["image_upload_url", false],
			["create_task", false],
			["plan", false],
			["apply_plan", true],
			["undo_plan", true],
		]);
		expect(tools.some((t) => /delete|remove_contact|remove_object|destroy|purge/i.test(t.name))).toBe(false);
		const create = tools.find((t) => t.name === "create_contact")!;
		expect(create.inputSchema.required).toEqual(["last_name"]);
		expect(create.description).toMatch(/MCP-TEST/);
		// Live-Befund 15.10.: property_space_value ist berechnet und darf nicht als Eingabe angeboten werden
		const createObject = tools.find((t) => t.name === "create_object")!;
		const objectFields = Object.keys(createObject.inputSchema.properties ?? {});
		// Feld-Mapping: berechnete/abgeleitete Felder und öffentliche Mietfelder nicht anbieten
		for (const field of ["property_space_value", "object_type", "total_rent"]) expect(objectFields).not.toContain(field);
		expect(objectFields).toEqual(expect.arrayContaining(["industrial_area", "total_floor_space", "hall_height", "rented", "price_on_inquiry", "bemerkung_append", "public_price_confirmed"]));
		// Team-How-to: wichtige Felder als eigene Parameter; Einheiten im Projekt brauchen weder Adresse noch Überschrift
		expect(objectFields).toEqual(
			expect.arrayContaining(["dock_doors", "ground_level_doors", "hall_divisible_from", "mezzanine_area", "car_parking", "truck_parking", "wgk", "lighting", "sprinkler", "heating", "certification", "internal_rent_hall", "active", "commission", "source_link", "mandate", "owner_contact_id", "contact_person_id"]),
		);
		expect(createObject.inputSchema.required).toEqual(["marketing_type", "rs_type"]);
		const props = createObject.inputSchema.properties as Record<string, { type?: string }>;
		expect(props.dock_doors.type).toBe("integer");
		expect(props.active.type).toBe("boolean");
		// Verknüpfen nur über create_* und set_project_owner – nicht über update_object
		expect(Object.keys(tools.find((t) => t.name === "update_object")!.inputSchema.properties ?? {})).not.toContain("contact_person_id");
		expect(Object.keys(tools.find((t) => t.name === "set_project_owner")!.inputSchema.properties ?? {})).toContain("role");
		expect(tools.find((t) => t.name === "create_project")!.description).toMatch(/mindestens zwei getrennt vermietbare Einheiten/);
		// Aufgaben: nur Anlegen, mit festem Parametersatz – kein Ändern, kein Löschen, kein freier API-Aufruf
		const task = tools.find((t) => t.name === "create_task")!;
		expect(task.inputSchema.required).toEqual(["title", "body"]);
		expect(Object.keys(task.inputSchema.properties ?? {}).sort()).toEqual(["assignee_id", "body", "contact_ids", "due_date", "object_ids", "project_ids", "test", "title"]);
		expect(tools.some((t) => /update_task|complete_task|task_delete/i.test(t.name))).toBe(false);
	});
});
