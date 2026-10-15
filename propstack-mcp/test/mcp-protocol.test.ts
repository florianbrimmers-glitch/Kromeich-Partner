import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { describe, expect, it } from "vitest";
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
			"get_contact",
			"get_object",
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

	it("Schreib-Tools: genau vier, nicht readOnly, Updates als überschreibend markiert, kein Löschen", async () => {
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
		]);
		expect(tools.some((t) => /delete|remove_contact|remove_object|destroy|purge/i.test(t.name))).toBe(false);
		const create = tools.find((t) => t.name === "create_contact")!;
		expect(create.inputSchema.required).toEqual(["last_name"]);
		expect(create.description).toMatch(/MCP-TEST/);
		// Live-Befund 15.10.: property_space_value ist berechnet und darf nicht als Eingabe angeboten werden
		const createObject = tools.find((t) => t.name === "create_object")!;
		const objectFields = Object.keys(createObject.inputSchema.properties ?? {});
		// Feld-Mapping: berechnete/abgeleitete Felder und öffentliche Mietfelder nicht anbieten
		for (const field of ["property_space_value", "object_type", "base_rent", "total_rent"]) expect(objectFields).not.toContain(field);
		expect(objectFields).toEqual(expect.arrayContaining(["industrial_area", "total_floor_space", "hall_height", "rented", "price_on_inquiry", "bemerkung_append"]));
	});
});
