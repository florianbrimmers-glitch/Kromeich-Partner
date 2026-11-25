import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { describe, expect, it, vi } from "vitest";
import { type Props, identityInfo } from "../src/auth/session";
import { type ServiceClaims, serviceSecret, signServiceToken, verifyServiceToken } from "../src/auth/service-token";
import { PropstackError } from "../src/propstack-client";
import { serviceAccess } from "../src/service-access";
import { registerReadTools, registerWriteTools, runTool } from "../src/tools/register";
import { SERVICE_TOOLS, serviceServer } from "../src/tools/service-rules";
import { MemoryKV } from "./helpers";

// Service-Zugang für den GitHub-Workflow „Objekte Handler“ (Auftrag Florian, 25.11.2026): Der Workflow ruft den
// Connector über die Claude-API auf (MCP-Connector, authorization_token) – Anthropic schickt das Token als
// „Authorization: Bearer svc.<payload>.<signatur>“ an /mcp.

const SECRET = "test-geheimnis-nur-fuer-tests-0123456789abcdef";
const NOW = 1_764_100_000;
const TS = "1764099999.123456";
const claims = (over: Record<string, unknown> = {}) => ({ broker_id: 111, exp: NOW + 600, iat: NOW - 5, sub: "objekte-handler", ts: TS, ...over });

/** base64url ohne Padding – so, wie der Workflow es baut (Python: urlsafe_b64encode(...).rstrip(b"=")). */
const b64url = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const utf8 = (text: string) => new TextEncoder().encode(text);

async function hmac(text: string, secret = SECRET): Promise<string> {
	const key = await crypto.subtle.importKey("raw", utf8(secret), { hash: "SHA-256", name: "HMAC" }, false, ["sign"]);
	return b64url(new Uint8Array(await crypto.subtle.sign("HMAC", key, utf8(`svc.${text}`))));
}

/** So baut der Workflow das Token – unabhängig vom Connector-Code, genau nach der Vorgabe. */
async function workflowToken(payload: unknown, secret = SECRET): Promise<string> {
	const body = b64url(utf8(JSON.stringify(payload)));
	return `svc.${body}.${await hmac(body, secret)}`;
}

describe("Service-Token: Format und Prüfung", () => {
	it("gültiges Token – auch so gebaut, wie es der Workflow mit eigenen Mitteln tut", async () => {
		expect(await verifyServiceToken(await workflowToken(claims()), SECRET, NOW)).toEqual(claims());
		const eigenes = await signServiceToken(claims() as ServiceClaims, SECRET);
		expect(eigenes).toBe(await workflowToken(claims()));
		expect(eigenes).toMatch(/^svc\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
	});

	it("falsche Signatur, anderes Secret, verändertes payload → abgelehnt", async () => {
		const token = await workflowToken(claims());
		const [, body, signature] = token.split(".");
		expect(await verifyServiceToken(await workflowToken(claims(), `${SECRET}x`), SECRET, NOW)).toBeNull();
		expect(await verifyServiceToken(`svc.${body}.${signature.slice(0, -2)}AA`, SECRET, NOW)).toBeNull();
		// broker_id austauschen, Signatur behalten
		const fremd = b64url(utf8(JSON.stringify(claims({ broker_id: 222 }))));
		expect(await verifyServiceToken(`svc.${fremd}.${signature}`, SECRET, NOW)).toBeNull();
	});

	it("abgelaufen → abgelehnt", async () => {
		expect(await verifyServiceToken(await workflowToken(claims({ exp: NOW })), SECRET, NOW)).toBeNull();
		expect(await verifyServiceToken(await workflowToken(claims({ exp: NOW - 1 })), SECRET, NOW)).toBeNull();
		expect(await verifyServiceToken(await workflowToken(claims({ exp: NOW + 1 })), SECRET, NOW)).not.toBeNull();
	});

	it("exp − iat > 1800 → abgelehnt; genau 1800 geht; exp vor iat geht nicht", async () => {
		expect(await verifyServiceToken(await workflowToken(claims({ exp: NOW + 1796, iat: NOW - 5 })), SECRET, NOW)).toBeNull();
		expect(await verifyServiceToken(await workflowToken(claims({ exp: NOW + 1795, iat: NOW - 5 })), SECRET, NOW)).not.toBeNull();
		expect(await verifyServiceToken(await workflowToken(claims({ exp: NOW + 10, iat: NOW + 20 })), SECRET, NOW)).toBeNull();
	});

	it("iat mehr als 60 s in der Zukunft → abgelehnt; 60 s gehen", async () => {
		expect(await verifyServiceToken(await workflowToken(claims({ exp: NOW + 600, iat: NOW + 61 })), SECRET, NOW)).toBeNull();
		expect(await verifyServiceToken(await workflowToken(claims({ exp: NOW + 600, iat: NOW + 60 })), SECRET, NOW)).not.toBeNull();
	});

	it("falsches sub, fehlende oder zusätzliche Felder, falsche Typen, ts nicht im Slack-Format → abgelehnt", async () => {
		const falsch: Record<string, unknown>[] = [
			claims({ sub: "personalkarussell" }),
			claims({ sub: undefined }),
			claims({ broker_id: "111" }),
			claims({ broker_id: 0 }),
			claims({ broker_id: 1.5 }),
			claims({ ts: "heute" }),
			claims({ ts: "1764099999.123456; rm -rf" }),
			claims({ iat: "1764100000" }),
			claims({ admin: true }),
		];
		for (const payload of falsch) expect(await verifyServiceToken(await workflowToken(payload), SECRET, NOW), JSON.stringify(payload)).toBeNull();
	});

	it("Padding, falsches Präfix, zu lang, kaputtes JSON → abgelehnt", async () => {
		const [, body, signature] = (await workflowToken(claims())).split(".");
		const kaputt = b64url(utf8("{kein json"));
		for (const token of [
			`svc.${body}=.${signature}`,
			`svc.${body}.${signature}=`,
			`SVC.${body}.${signature}`,
			`svc.${body}.${signature}.x`,
			`svc.${body}`,
			`svc.${kaputt}.${await hmac(kaputt)}`,
			`svc.${"A".repeat(3000)}.${await hmac("A".repeat(3000))}`,
		]) {
			expect(await verifyServiceToken(token, SECRET, NOW), token.slice(0, 40)).toBeNull();
		}
	});

	it("überlange Tokens werden abgewiesen, bevor überhaupt gerechnet wird (Schutz vor Last)", async () => {
		const verify = vi.spyOn(crypto.subtle, "verify");
		try {
			expect(await verifyServiceToken(`svc.${"A".repeat(3000)}.${"B".repeat(43)}`, SECRET, NOW)).toBeNull();
			expect(verify).not.toHaveBeenCalled();
			await verifyServiceToken(await workflowToken(claims()), SECRET, NOW);
			expect(verify).toHaveBeenCalledTimes(1);
		} finally {
			verify.mockRestore();
		}
	});

	it("Secret fehlt, ist leer oder kürzer als 32 Zeichen → der Weg ist aus", () => {
		expect(serviceSecret({})).toBeNull();
		expect(serviceSecret({ SERVICE_TOKEN_SECRET: "   " })).toBeNull();
		expect(serviceSecret({ SERVICE_TOKEN_SECRET: "x".repeat(31) })).toBeNull();
		expect(serviceSecret({ SERVICE_TOKEN_SECRET: ` ${SECRET}\n` })).toBe(SECRET);
	});
});

describe("Service-Zugang an /mcp", () => {
	// Nutzerlisten in der Form, wie Propstack sie liefert (live 20.11.2026)
	const V1 = [
		{ email: "florian.brimmers@kromeichpartner.de", first_name: "Florian", id: 111, last_name: "Brimmers", name: "Florian Brimmers" },
		{ email: "info@kromeichpartner.de", id: 254959, name: "info@" },
		{ email: "buchhaltung@kromeichpartner.de", id: 300, name: "Buchhaltung" },
		{ email: "ehemalig@kromeichpartner.de", id: 500, name: "Ehe Malig" },
		// Sammelpostfach, in Propstack aber nicht als technisch markiert – die feste Sperrliste greift trotzdem
		{ email: "Kontakt@kromeichpartner.de", id: 419593, name: "Kontakt Kromeich" },
	];
	const zustand = (id: number, mehr: Record<string, unknown> = {}) => ({ active: true, archived: null, blocked: false, id, role: "user", ...mehr });
	const V2 = { data: [zustand(111), zustand(254959, { role: "technical" }), zustand(300, { role: "technical" }), zustand(500, { active: false }), zustand(419593)] };

	function welt(options: { v2?: unknown; secret?: string | null; v2Key?: boolean } = {}) {
		const zaehler = { v1: 0, v2: 0 };
		const client = {
			hasV2Key: options.v2Key ?? true,
			listBrokers: async () => {
				zaehler.v1++;
				return V1;
			},
			listBrokersV2: async () => {
				zaehler.v2++;
				if (options.v2 instanceof Error) throw options.v2;
				return options.v2 ?? V2;
			},
		};
		const env = options.secret === null ? {} : { SERVICE_TOKEN_SECRET: options.secret ?? SECRET };
		const kv = new MemoryKV();
		const call = (token: string | undefined, path = "/mcp") =>
			serviceAccess(new Request(`https://propstack-mcp.example${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {}, method: "POST" }), env, {
				client,
				kv: kv.asKV(),
				nowSeconds: NOW,
			});
		return { call, kv, zaehler };
	}

	it("gültiges Token → Sitzung wie die eines angemeldeten Nutzers, mit service und auftrag", async () => {
		const w = welt();
		expect(await w.call(await workflowToken(claims()))).toEqual({
			kind: "props",
			props: { auftrag: TS, brokerId: 111, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers", service: "objekte-handler" },
		});
		// auch Unterpfade von /mcp
		expect(await w.call(await workflowToken(claims()), "/mcp/")).toMatchObject({ kind: "props" });
	});

	it("ungültig, abgelaufen oder ohne Secret → kein Service-Weg; der normale Anmeldeweg antwortet wie heute mit 401", async () => {
		const w = welt();
		expect(await w.call(await workflowToken(claims(), `${SECRET}x`))).toBeNull();
		expect(await w.call(await workflowToken(claims({ exp: NOW - 1 })))).toBeNull();
		expect(await welt({ secret: null }).call(await workflowToken(claims()))).toBeNull();
		expect(await welt({ secret: "zu-kurz" }).call(await workflowToken(claims(), "zu-kurz"))).toBeNull();
		// Propstack wurde dafür nicht gefragt
		expect(w.zaehler).toEqual({ v1: 0, v2: 0 });
	});

	it("OAuth-Weg unverändert: andere Tokens, kein Token und andere Pfade gehen gar nicht durch den Service-Weg", async () => {
		const w = welt();
		for (const token of [undefined, "nutzer:grant:geheim", "svc", "Bearer"]) expect(await w.call(token)).toBeNull();
		for (const path of ["/authorize", "/token", "/register", "/callback", "/mcpx", "/upload/images/abc"]) expect(await w.call(await workflowToken(claims()), path)).toBeNull();
		expect(w.zaehler).toEqual({ v1: 0, v2: 0 });
	});

	it("broker_id unbekannt, technisch, inaktiv oder Sammelpostfach → 403", async () => {
		for (const brokerId of [999999, 254959, 300, 500, 419593]) {
			const antwort = await welt().call(await workflowToken(claims({ broker_id: brokerId })));
			expect(antwort?.kind, String(brokerId)).toBe("response");
			const response = (antwort as { response: Response }).response;
			expect(response.status, String(brokerId)).toBe(403);
			expect((await response.json()) as object).toMatchObject({ error: "forbidden" });
		}
	});

	it("ohne strenge Nutzerprüfung (zweiter Schlüssel fehlt oder darf die Liste nicht lesen) → 403 statt einfacher Prüfung", async () => {
		for (const w of [welt({ v2Key: false }), welt({ v2: new PropstackError("verboten", 403) })]) {
			const antwort = (await w.call(await workflowToken(claims()))) as { response: Response };
			expect(antwort.response.status).toBe(403);
			expect(((await antwort.response.json()) as { error_description: string }).error_description).toMatch(/strenge/);
		}
	});

	it("Propstack nicht erreichbar → 503 (vorübergehend), nicht 403", async () => {
		const antwort = (await welt({ v2: new PropstackError("Propstack-Serverfehler (503)", 503) }).call(await workflowToken(claims()))) as { response: Response };
		expect(antwort.response.status).toBe(503);
		expect(antwort.response.headers.get("Retry-After")).toBe("60");
	});

	it("die Nutzerprüfung wird 5 Minuten zwischengespeichert – nicht bei jedem Aufruf zweimal Propstack", async () => {
		const w = welt();
		await w.call(await workflowToken(claims()));
		await w.call(await workflowToken(claims()));
		expect(w.zaehler).toEqual({ v1: 1, v2: 1 });
		expect(w.kv.ttls.get("propstack-service-broker:v1:111")).toBe(300);
	});
});

describe("Service-Sitzung: nur freigegebene Werkzeuge, keine Freigaben ohne Menschen", () => {
	const SERVICE: Props = { auftrag: TS, brokerId: 111, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers", service: "objekte-handler" };
	const MENSCH: Props = { brokerId: 111, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers" };
	const audits: unknown[][] = [];
	const db = { prepare: () => ({ bind: (...args: unknown[]) => ({ run: async () => (audits.push(args), { meta: { last_row_id: 1 } }) }) }) } as unknown as D1Database;
	const ctx = (props: Props) => ({ createClient: () => ({}) as never, env: { AUDIT_DB: db } as Env, props: () => props });

	it("die Liste ist genau die vereinbarte", () => {
		expect([...SERVICE_TOOLS].sort()).toEqual(
			["add_images", "create_object", "create_project", "create_task", "get_contact", "get_object", "get_project", "list_fields", "list_reference", "search_contacts", "search_objects", "set_project_owner", "whoami"].sort(),
		);
	});

	it("bietet nur diese Werkzeuge an – für Menschen bleibt alles wie bisher", async () => {
		const liste = async (props: Props) => {
			const server = new McpServer({ name: "test", version: "0" });
			const target = serviceServer(server, props);
			target.registerTool("whoami", { description: "x" }, async () => ({ content: [] }));
			registerReadTools(target, ctx(props));
			registerWriteTools(target, ctx(props));
			const [a, b] = InMemoryTransport.createLinkedPair();
			await server.connect(b);
			const client = new Client({ name: "t", version: "0" });
			await client.connect(a);
			return (await client.listTools()).tools.map((t) => t.name).sort();
		};
		expect(await liste(SERVICE)).toEqual([...SERVICE_TOOLS].sort());
		const alle = await liste(MENSCH);
		expect(alle.length).toBeGreaterThan(SERVICE_TOOLS.size);
		expect(alle).toEqual(expect.arrayContaining(["update_object", "plan", "apply_plan", "create_contact", "dashboard_daten"]));
	});

	it("ein Werkzeug außerhalb der Liste wird auch beim Aufruf abgewiesen", async () => {
		let gerufen = false;
		const out = await runTool(ctx(SERVICE), "update_object", { id: 1 }, async () => {
			gerufen = true;
			return { count: 1, result: {} };
		});
		expect(out.isError).toBe(true);
		expect(out.content[0].text).toMatch(/Service-Zugang/);
		expect(gerufen).toBe(false);
		// für Menschen unverändert
		expect((await runTool(ctx(MENSCH), "update_object", { id: 1 }, async () => ({ count: 1, result: {} }))).isError).toBeUndefined();
	});

	it("allow_duplicate_reason und public_price_confirmed werden abgewiesen – dafür braucht es einen Menschen", async () => {
		for (const params of [{ allow_duplicate_reason: "andere Halle" }, { public_price_confirmed: true }]) {
			let gerufen = false;
			const out = await runTool(ctx(SERVICE), "create_object", { marketing_type: "RENT", ...params }, async () => {
				gerufen = true;
				return { count: 1, result: {} };
			});
			expect(out.isError, JSON.stringify(params)).toBe(true);
			expect(out.content[0].text).toMatch(/Service-Zugang/);
			expect(gerufen).toBe(false);
		}
		const mensch = await runTool(ctx(MENSCH), "create_object", { allow_duplicate_reason: "andere Halle" }, async () => ({ count: 1, result: {} }));
		expect(mensch.isError).toBeUndefined();
	});

	it("das Audit-Log hält Ablauf und Auftrag fest – auch bei abgewiesenen Aufrufen", async () => {
		audits.length = 0;
		await runTool(ctx(SERVICE), "get_object", { id: 1 }, async () => ({ count: 1, result: {} }));
		await runTool(ctx(SERVICE), "plan", {}, async () => ({ count: 1, result: {} }));
		await runTool(ctx(MENSCH), "get_object", { id: 1 }, async () => ({ count: 1, result: {} }));
		expect(audits.map((row) => row.slice(-2))).toEqual([
			["objekte-handler", TS],
			["objekte-handler", TS],
			[null, null],
		]);
		// der abgewiesene Aufruf steht als Fehler drin
		expect(audits[1][6]).toBe(0);
	});

	it("whoami zeigt den Service-Zugang", () => {
		expect(identityInfo(SERVICE)).toMatchObject({ auftrag: TS, name: "Florian Brimmers", propstack_user_id: 111, service: "objekte-handler" });
		expect(identityInfo(MENSCH)).not.toHaveProperty("service");
	});
});
