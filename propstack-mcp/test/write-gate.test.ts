import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { describe, expect, it } from "vitest";
import type { PropstackClient } from "../src/propstack-client";
import { registerWriteTools } from "../src/tools/register";

// Live 26.11.2026, Projekt 623542: Unit 1 lief allein und vollständig durch; die vier gleichzeitig angelegten
// Units 2–5 scheiterten an „Too many subrequests“. Gleichzeitige Aufrufe einer Sitzung teilen sich bei Cloudflare
// die Grenze für Unteraufrufe (Workers Free: 50). Deshalb: je Sitzung nur ein Schreibvorgang auf einmal.

function sitzung() {
	let freigeben: () => void = () => {};
	const warten = new Promise<void>((resolve) => {
		freigeben = resolve;
	});
	let angelegt = 0;
	const fake = {
		createTask: async () => {
			angelegt++;
			if (angelegt === 1) await warten; // der erste Aufruf hängt, bis der Test ihn freigibt
			return { id: angelegt };
		},
		getTask: async () => ({}),
		listBrokers: async () => [{ connected: true, id: 1, name: "T" }],
	} as unknown as PropstackClient;
	const db = { prepare: () => ({ bind: () => ({ run: async () => ({ meta: { last_row_id: 1 } }) }) }) } as unknown as D1Database;
	const server = new McpServer({ name: "test", version: "0" });
	registerWriteTools(server, { createClient: () => fake, env: { AUDIT_DB: db } as Env, props: () => ({ brokerId: 1, email: "t@kromeichpartner.de", name: "T" }) });
	return { freigeben, server, zaehler: () => angelegt };
}

async function verbinden(server: McpServer): Promise<Client> {
	const [a, b] = InMemoryTransport.createLinkedPair();
	await server.connect(b);
	const client = new Client({ name: "t", version: "0" });
	await client.connect(a);
	return client;
}

const aufgabe = (titel: string) => ({ arguments: { body: "Bitte prüfen.", title: `Aufgabe ${titel}` }, name: "create_task" });

describe("Schreib-Werkzeuge: je Sitzung nur einer auf einmal", () => {
	it("ein gleichzeitiger zweiter Schreibvorgang wird sofort abgewiesen – ohne zu schreiben; danach geht es wieder", async () => {
		const s = sitzung();
		const client = await verbinden(s.server);
		const erster = client.callTool(aufgabe("Eins"));
		// warten, bis der erste wirklich läuft (begrenzt – sonst hinge der Test bei einem frühen Fehler)
		for (let i = 0; s.zaehler() === 0 && i < 500; i++) await new Promise((r) => setTimeout(r, 1));
		expect(s.zaehler()).toBe(1);

		const zweiter = (await client.callTool(aufgabe("Zwei"))) as { content: { text: string }[]; isError?: boolean };
		expect(zweiter.isError).toBe(true);
		expect(zweiter.content[0].text).toMatch(/Ein anderer Schreibvorgang dieser Sitzung läuft noch/);
		expect(zweiter.content[0].text).toMatch(/nichts geschrieben/);
		expect(s.zaehler()).toBe(1);

		s.freigeben();
		expect(((await erster) as { isError?: boolean }).isError).toBeUndefined();
		// nach dem Ende des ersten läuft der nächste normal
		const dritter = (await client.callTool(aufgabe("Drei"))) as { isError?: boolean };
		expect(dritter.isError).toBeUndefined();
		expect(s.zaehler()).toBe(2);
	});

	it("auch nach einem Fehler ist die Sperre wieder frei", async () => {
		const s = sitzung();
		const client = await verbinden(s.server);
		// HTML im Text → Fehler vor dem Schreiben
		const kaputt = (await client.callTool({ arguments: { body: "<b>fett</b>", title: "Aufgabe kaputt" }, name: "create_task" })) as { isError?: boolean };
		expect(kaputt.isError).toBe(true);
		s.freigeben();
		const danach = (await client.callTool(aufgabe("Danach"))) as { isError?: boolean };
		expect(danach.isError).toBeUndefined();
	});
});
