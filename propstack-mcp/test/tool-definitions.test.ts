import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { describe, expect, it } from "vitest";
import { registerReadTools, registerWriteTools } from "../src/tools/register";
import { TOOL_DEFINITIONS } from "./tool-definitions.snapshot";

// Wächter: Der Wortlaut vorhandener Tools bleibt stabil (Befund 11.11.2026, README 5c).
//
// Claude bindet ein gespeichertes „Immer erlauben“ an die Definition eines Tools. Ändert ein Deployment die
// Beschreibung oder die Parameter, gilt das Tool als neu und steht bei jeder Person im Team wieder auf
// „Genehmigung erforderlich“. Am 11.11.2026 fragte update_object bei jedem Aufruf nach – es war in drei Tagen
// dreimal geändert worden; das nie geänderte apply_plan lief ohne Nachfrage.
//
// Dieser Test schlägt fehl, sobald sich die Definition eines Tools ändert, ein Tool dazukommt oder wegfällt.
// Ist die Änderung gewollt: den Stand aus der Fehlermeldung nach test/tool-definitions.snapshot.ts übernehmen
// und im Bericht an Florian die betroffenen Tools nennen („bitte neu erlauben: …“).
// Nicht erfasst: whoami (wird in src/index.ts registriert).

async function fingerprint(value: unknown): Promise<string> {
	const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify(value)));
	return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0"))
		.join("")
		.slice(0, 16);
}

async function currentDefinitions(): Promise<Record<string, string>> {
	const server = new McpServer({ name: "test", version: "0" });
	const ctx = { createClient: () => ({}), env: {}, props: () => ({ brokerId: 1, email: "t@example.org", name: "T" }) };
	registerReadTools(server, ctx as never);
	registerWriteTools(server, ctx as never);
	const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
	await server.connect(serverTransport);
	const client = new Client({ name: "claude-test", version: "0" });
	await client.connect(clientTransport);
	const { tools } = await client.listTools();
	const out: Record<string, string> = {};
	for (const tool of [...tools].sort((a, b) => a.name.localeCompare(b.name))) {
		out[tool.name] = await fingerprint([tool.description, tool.inputSchema]);
	}
	return out;
}

describe("Tool-Definitionen bleiben stabil", () => {
	it("keine Definition ändert sich unbemerkt – sonst verlieren alle Nutzer ihr „Immer erlauben“ für dieses Tool", async () => {
		const actual = await currentDefinitions();
		const changed = Object.keys(actual).filter((name) => name in TOOL_DEFINITIONS && TOOL_DEFINITIONS[name] !== actual[name]);
		const added = Object.keys(actual).filter((name) => !(name in TOOL_DEFINITIONS));
		const removed = Object.keys(TOOL_DEFINITIONS).filter((name) => !(name in actual));
		const report = [
			changed.length ? `geändert: ${changed.join(", ")} – setzt die gespeicherte Erlaubnis dieser Tools bei allen Nutzern zurück` : "",
			added.length ? `neu: ${added.join(", ")}` : "",
			removed.length ? `entfernt: ${removed.join(", ")}` : "",
		].filter(Boolean);
		const entries = Object.entries(actual)
			.map(([name, value]) => `\t${name}: "${value}",`)
			.join("\n");
		expect(
			report,
			`Tool-Definitionen weichen vom gespeicherten Stand ab. Wenn gewollt: die betroffenen Tools im Bericht nennen und diesen Stand nach test/tool-definitions.snapshot.ts übernehmen:\n${entries}`,
		).toEqual([]);
	});
});
