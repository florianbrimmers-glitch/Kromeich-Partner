import { describe, expect, it } from "vitest";
import { buildQuery, PropstackClient, PropstackError, retryDelayMs, toPage } from "../src/propstack-client";

function scriptedFetch(responses: Response[]) {
	const requests: { url: string; init?: RequestInit }[] = [];
	const fetchFn = (async (url: string, init?: RequestInit) => {
		requests.push({ init, url });
		const next = responses.shift();
		if (!next) throw new Error("keine weitere Antwort");
		return next;
	}) as unknown as typeof fetch;
	return { fetchFn, requests };
}

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
	new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json", ...headers }, status });

describe("PropstackClient", () => {
	it("ruft GET /v1/brokers mit X-API-KEY auf", async () => {
		const { fetchFn, requests } = scriptedFetch([json([{ id: 1 }])]);
		const client = new PropstackClient({ apiKey: "k", fetchFn });
		expect(await client.listBrokers()).toEqual([{ id: 1 }]);
		expect(requests[0].url).toBe("https://api.propstack.de/v1/brokers");
		expect((requests[0].init?.headers as Record<string, string>)["X-API-KEY"]).toBe("k");
	});

	it("wiederholt bei 429 mit Backoff und Retry-After", async () => {
		const waits: number[] = [];
		const { fetchFn } = scriptedFetch([json({}, 429, { "Retry-After": "2" }), json({}, 429), json([])]);
		const client = new PropstackClient({ apiKey: "k", fetchFn, sleep: async (ms) => void waits.push(ms) });
		expect(await client.listBrokers()).toEqual([]);
		expect(waits).toEqual([2000, 2000]);
	});

	it("gibt nach maxRetries mit sauberem Fehler auf", async () => {
		const { fetchFn } = scriptedFetch([json({}, 429), json({}, 429)]);
		const client = new PropstackClient({ apiKey: "k", fetchFn, maxRetries: 1, sleep: async () => {} });
		await expect(client.listBrokers()).rejects.toMatchObject({ name: "PropstackError", status: 429 });
	});

	it.each([
		[401, /Zugriff verweigert/],
		[500, /Serverfehler/],
		[404, /Nicht gefunden \(404\)/],
		[422, /fehlgeschlagen \(422\)/],
	])("meldet %s ohne Retry", async (status, message) => {
		const { fetchFn, requests } = scriptedFetch([json({ secret: "nicht durchreichen" }, status)]);
		const client = new PropstackClient({ apiKey: "k", fetchFn });
		const error = (await client.listBrokers().catch((e) => e)) as PropstackError;
		expect(error).toBeInstanceOf(PropstackError);
		expect(error.message).toMatch(message);
		expect(error.message).not.toContain("nicht durchreichen");
		expect(requests).toHaveLength(1);
	});

	it("verweigert Start ohne API-Key", () => {
		expect(() => new PropstackClient({ apiKey: "" })).toThrow(/PROPSTACK_API_KEY/);
	});
});

describe("retryDelayMs", () => {
	it("exponentiell ohne Retry-After, gedeckelt bei 30 s", () => {
		expect([0, 1, 2, 10].map((a) => retryDelayMs(a, null))).toEqual([1000, 2000, 4000, 30000]);
	});
	it("ignoriert unbrauchbares Retry-After", () => {
		expect(retryDelayMs(0, "Wed, 21 Oct 2026 07:28:00 GMT")).toBe(1000);
	});
});

describe("buildQuery / toPage", () => {
	it("baut Rails-Arrays, Booleans und lässt Leeres weg", () => {
		expect(buildQuery({ a: [1, 2], b: true, c: false, d: undefined, e: "", f: null, g: "x y" })).toBe(
			"?a%5B%5D=1&a%5B%5D=2&b=1&c=0&g=x+y",
		);
		expect(buildQuery({})).toBe("");
	});

	it("liest nackte Listen und {data, meta}", () => {
		expect(toPage([{ id: 1 }, null, "x"])).toEqual({ rows: [{ id: 1 }], total: null });
		expect(toPage({ data: [{ id: 2 }], meta: { total_count: 7 } })).toEqual({ rows: [{ id: 2 }], total: 7 });
		expect(toPage({ foo: 1 })).toEqual({ rows: [], total: null });
	});
});

describe("Request-Budget", () => {
	it("bricht nach maxRequests mit verständlicher Meldung ab", async () => {
		const { fetchFn } = scriptedFetch([json([]), json([]), json([])]);
		const client = new PropstackClient({ apiKey: "k", fetchFn, maxRequests: 2 });
		await client.listBrokers();
		await client.listBrokers();
		await expect(client.listBrokers()).rejects.toThrow(/Filter enger/);
		expect(client.requestsUsed).toBe(2);
	});

	it("hängt with_meta an Suchen an und nutzt die dokumentierten Pfade", async () => {
		const { fetchFn, requests } = scriptedFetch([json({ data: [], meta: { total_count: 0 } }), json([]), json({ data: [] })]);
		const client = new PropstackClient({ apiKey: "k", fetchFn });
		await client.searchUnits({ status: "1,2" });
		await client.getUnit(5);
		await client.searchDeals({ deal_stage_ids: [3] });
		expect(requests.map((r) => r.url.replace("https://api.propstack.de/v1", ""))).toEqual([
			"/units?status=1%2C2&with_meta=1",
			"/units/5?new=1",
			"/client_properties?deal_stage_ids%5B%5D=3&with_meta=1",
		]);
	});
});
