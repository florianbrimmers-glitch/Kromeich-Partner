import { describe, expect, it } from "vitest";
import { matchBroker, resolveBroker } from "../src/auth/broker-lookup";
import { AuthRejection } from "../src/auth/errors";
import { authorizeLogin, recheckOnRefresh } from "../src/auth/session";
import { PropstackError } from "../src/propstack-client";
import { BROKERS, CLIENT_ID, MemoryKV, NOW, brokerClient, createSigner, validClaims } from "./helpers";

describe("3b – matchBroker", () => {
	it("findet Nutzer per Mail, ignoriert Groß-/Kleinschreibung und Leerzeichen", () => {
		expect(matchBroker(BROKERS, "  lena.klinnert@kromeichpartner.de ")).toEqual({
			email: "lena.klinnert@kromeichpartner.de",
			id: 254958,
			name: "Lena Klinnert",
		});
	});

	it("liefert null für Funktionspostfach ohne Propstack-Nutzer", () => {
		expect(matchBroker(BROKERS, "info@kromeichpartner.de")).toBeNull();
	});

	it("lehnt mehrdeutige Treffer ab", () => {
		const doubled = [...BROKERS, { email: "florian.brimmers@kromeichpartner.de", id: 222, name: "Dublette" }];
		expect(() => matchBroker(doubled, "florian.brimmers@kromeichpartner.de")).toThrow(/mehrere/);
	});

	it("baut Namen aus Vor-/Nachname, wenn name fehlt", () => {
		expect(matchBroker([{ email: "a@kromeichpartner.de", first_name: "Anna", id: 5, last_name: "B" }], "a@kromeichpartner.de")?.name).toBe(
			"Anna B",
		);
	});

	it("überspringt kaputte Einträge statt abzustürzen", () => {
		expect(matchBroker([{ id: "x" }, "müll", null, ...BROKERS], "florian.brimmers@kromeichpartner.de")?.id).toBe(111);
	});

	it("wirft bei unerwartetem Antwortformat (kein Array)", () => {
		expect(() => matchBroker({ data: [] }, "x@kromeichpartner.de")).toThrow(/Unerwartetes Format/);
	});
});

describe("3b – resolveBroker mit KV-Cache", () => {
	it("cacht Treffer mit TTL 1 h und fragt Propstack danach nicht mehr", async () => {
		const kv = new MemoryKV();
		const client = brokerClient();
		const deps = { client, kv: kv.asKV() };

		await resolveBroker("florian.brimmers@kromeichpartner.de", deps);
		const again = await resolveBroker("Florian.Brimmers@kromeichpartner.de", deps);

		expect(again.id).toBe(111);
		expect(client.calls).toBe(1);
		expect(kv.ttls.get("propstack-broker:florian.brimmers@kromeichpartner.de")).toBe(3600);
	});

	it("lehnt unbekannte Mail ab und cacht die Ablehnung nicht", async () => {
		const kv = new MemoryKV();
		const client = brokerClient();
		await expect(resolveBroker("info@kromeichpartner.de", { client, kv: kv.asKV() })).rejects.toThrow(AuthRejection);
		expect(kv.store.size).toBe(0);
	});

	it("ignoriert kaputte Cache-Einträge", async () => {
		const kv = new MemoryKV();
		kv.store.set("propstack-broker:florian.brimmers@kromeichpartner.de", JSON.stringify({ id: "kaputt" }));
		const client = brokerClient();
		expect((await resolveBroker("florian.brimmers@kromeichpartner.de", { client, kv: kv.asKV() })).id).toBe(111);
		expect(client.calls).toBe(1);
	});
});

describe("Login-Ablauf 3a → 3b", () => {
	async function login(claims: Record<string, unknown>, brokers: unknown = BROKERS) {
		const { jwksFetch, sign } = await createSigner();
		return authorizeLogin(await sign(claims), {
			client: brokerClient(brokers),
			clientId: CLIENT_ID,
			fetchFn: jwksFetch,
			kv: new MemoryKV().asKV(),
			nowSeconds: NOW,
		});
	}

	it("Abnahme 1: Domain-Konto mit Propstack-Nutzer → korrekte Propstack-ID", async () => {
		expect(await login(validClaims())).toEqual({
			brokerId: 111,
			email: "florian.brimmers@kromeichpartner.de",
			name: "Florian Brimmers",
		});
	});

	it("Abnahme 2: privates Gmail-Konto → abgelehnt, Propstack wird gar nicht gefragt", async () => {
		const claims = validClaims({ email: "florian@gmail.com" });
		delete claims.hd;
		const client = brokerClient();
		const { jwksFetch, sign } = await createSigner();
		await expect(
			authorizeLogin(await sign(claims), {
				client,
				clientId: CLIENT_ID,
				fetchFn: jwksFetch,
				kv: new MemoryKV().asKV(),
				nowSeconds: NOW,
			}),
		).rejects.toThrow(AuthRejection);
		expect(client.calls).toBe(0);
	});

	it("Abnahme 3: Funktionspostfach ohne Propstack-Nutzer → abgelehnt", async () => {
		await expect(login(validClaims({ email: "info@kromeichpartner.de" }))).rejects.toThrow(/kein aktiver Propstack-Nutzer/);
	});
});

describe("Refresh – Re-Check 3b", () => {
	const props = { brokerId: 111, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers" };

	it("bestätigt aktiven Nutzer", async () => {
		const result = await recheckOnRefresh(props, { client: brokerClient(), kv: new MemoryKV().asKV() });
		expect(result).toEqual({ ok: true, props });
	});

	it("lehnt offboardeten Nutzer ab", async () => {
		const result = await recheckOnRefresh(props, { client: brokerClient([BROKERS[1]]), kv: new MemoryKV().asKV() });
		expect(result).toMatchObject({ kind: "rejected", ok: false });
	});

	it("übernimmt geänderte Propstack-ID", async () => {
		const moved = [{ ...BROKERS[0], id: 777 }];
		const result = await recheckOnRefresh(props, { client: brokerClient(moved), kv: new MemoryKV().asKV() });
		expect(result).toEqual({ ok: true, props: { ...props, brokerId: 777 } });
	});

	it("schlägt bei Propstack-Ausfall geschlossen fehl (vorübergehend)", async () => {
		const failing = {
			listBrokers: async () => {
				throw new PropstackError("Propstack-Serverfehler (503)", 503);
			},
		};
		const result = await recheckOnRefresh(props, { client: failing, kv: new MemoryKV().asKV() });
		expect(result).toMatchObject({ kind: "unavailable", ok: false });
	});
});
