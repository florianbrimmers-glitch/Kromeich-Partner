import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { describe, expect, it } from "vitest";
import type { PropstackClient } from "../src/propstack-client";
import { registerReadTools } from "../src/tools/register";

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

	it("führt ein Tool aus, liefert JSON-Text und schreibt das Audit-Log", async () => {
		const { client, audits } = await connect({
			getContact: async () => ({ id: 5, identity_number: "GEHEIM", name: "Anna" }),
		});
		const result = await client.callTool({ arguments: { id: 5 }, name: "get_contact" });
		expect(result.isError).toBeFalsy();
		const text = (result.content as { text: string }[])[0].text;
		expect(JSON.parse(text)).toEqual({ id: 5, name: "Anna" });
		expect(audits[0][3]).toBe("get_contact");
	});
});
