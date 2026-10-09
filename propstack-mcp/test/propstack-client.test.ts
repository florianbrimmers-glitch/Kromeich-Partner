import { describe, expect, it } from "vitest";
import { PropstackClient, PropstackError, retryDelayMs } from "../src/propstack-client";

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
		[401, /API-Key abgelehnt/],
		[500, /Serverfehler/],
		[404, /fehlgeschlagen \(404\)/],
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
