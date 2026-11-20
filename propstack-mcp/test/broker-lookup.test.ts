import { describe, expect, it } from "vitest";
import { matchBroker, resolveBroker } from "../src/auth/broker-lookup";
import { AuthRejection } from "../src/auth/errors";
import { authorizeLogin, brokerLabel, identityInfo, recheckOnRefresh } from "../src/auth/session";
import { ALLOWED_HOSTED_DOMAIN, BROKER_ALIASES } from "../src/config";
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

describe("Ausnahme – Person ohne eigenen Propstack-Nutzer schreibt unter dem einer Kollegin (Entscheidung Florian, 20.11.2026)", () => {
	const ALIASES = { "oguzhan.sahin@kromeichpartner.de": { name: "Oguzhan Sahin", propstackEmail: "lena.klinnert@kromeichpartner.de", propstackId: 254958 } };
	const OGUZHAN = { brokerId: 254958, brokerName: "Lena Klinnert", email: "oguzhan.sahin@kromeichpartner.de", name: "Oguzhan Sahin" };
	const deps = (brokers: unknown = BROKERS, aliases: typeof ALIASES | Record<string, never> = ALIASES) => ({ aliases, client: brokerClient(brokers), kv: new MemoryKV().asKV() });

	it("hinterlegt ist genau eine Ausnahme: Oguzhan → Lena (254958) – in der erlaubten Domain, klein geschrieben, ohne Kette", () => {
		expect(BROKER_ALIASES).toEqual(ALIASES);
		for (const [mail, ziel] of Object.entries(BROKER_ALIASES)) {
			expect(mail).toBe(mail.trim().toLowerCase());
			expect(mail.endsWith(`@${ALLOWED_HOSTED_DOMAIN}`)).toBe(true);
			expect(ziel.propstackEmail).toBe(ziel.propstackEmail.trim().toLowerCase());
			expect(ziel.propstackEmail).not.toBe(mail);
			expect(Object.keys(BROKER_ALIASES)).not.toContain(ziel.propstackEmail);
		}
	});

	it("eigene Google-Adresse, Propstack-Nutzer der Kollegin – der Name der Person bleibt, und nichts landet im Cache", async () => {
		const kv = new MemoryKV();
		const identity = await resolveBroker(" Oguzhan.Sahin@kromeichpartner.de", { aliases: ALIASES, client: brokerClient(), kv: kv.asKV() });
		expect(identity).toEqual({ brokerName: "Lena Klinnert", email: "oguzhan.sahin@kromeichpartner.de", id: 254958, name: "Oguzhan Sahin" });
		// nie im Cache: Wird die Ausnahme entfernt, endet der Zugang beim nächsten Refresh
		expect(kv.store.size).toBe(0);
	});

	it("ohne Ausnahme bleibt die Person draußen – und die Ausnahme gilt nur für genau diese Adresse", async () => {
		await expect(resolveBroker("oguzhan.sahin@kromeichpartner.de", deps(BROKERS, {}))).rejects.toThrow(/kein aktiver Propstack-Nutzer/);
		await expect(resolveBroker("oguzhan.sahin2@kromeichpartner.de", deps())).rejects.toThrow(/kein aktiver Propstack-Nutzer/);
		await expect(resolveBroker("info@kromeichpartner.de", deps())).rejects.toThrow(/kein aktiver Propstack-Nutzer/);
	});

	it("zeigt die Ausnahme ins Leere, wird abgelehnt statt auf jemand anderen umgeleitet", async () => {
		// Nutzer der Kollegin entfernt
		await expect(resolveBroker("oguzhan.sahin@kromeichpartner.de", deps([BROKERS[0]]))).rejects.toThrow(/Ausnahme hinterlegt/);
		// dieselbe E-Mail, aber eine andere Propstack-ID
		await expect(resolveBroker("oguzhan.sahin@kromeichpartner.de", deps([BROKERS[0], { ...BROKERS[1], id: 5 }]))).rejects.toThrow(/Ausnahme hinterlegt/);
		// dieselbe ID, aber der Nutzer gehört inzwischen jemand anderem (andere E-Mail)
		await expect(resolveBroker("oguzhan.sahin@kromeichpartner.de", deps([BROKERS[0], { ...BROKERS[1], email: "neu@kromeichpartner.de" }]))).rejects.toThrow(/Ausnahme hinterlegt/);
		for (const brokers of [[BROKERS[0]], [BROKERS[0], { ...BROKERS[1], id: 5 }]]) {
			await expect(resolveBroker("oguzhan.sahin@kromeichpartner.de", deps(brokers))).rejects.toThrow(AuthRejection);
		}
	});

	it("bekommt die Person einen eigenen Propstack-Nutzer, gilt der – die Ausnahme greift nicht mehr", async () => {
		const mitEigenem = [...BROKERS, { email: "oguzhan.sahin@kromeichpartner.de", id: 4711, name: "Oguzhan Sahin" }];
		expect(await resolveBroker("oguzhan.sahin@kromeichpartner.de", deps(mitEigenem))).toEqual({ email: "oguzhan.sahin@kromeichpartner.de", id: 4711, name: "Oguzhan Sahin" });
	});

	it("die Kollegin selbst ist nicht betroffen", async () => {
		expect(await resolveBroker("lena.klinnert@kromeichpartner.de", deps())).toEqual({ email: "lena.klinnert@kromeichpartner.de", id: 254958, name: "Lena Klinnert" });
	});

	it("Login mit der echten Einstellung: Oguzhans Google-Konto → Lenas Propstack-ID, beide Namen in der Sitzung", async () => {
		const { jwksFetch, sign } = await createSigner();
		const props = await authorizeLogin(await sign(validClaims({ email: "oguzhan.sahin@kromeichpartner.de" })), {
			client: brokerClient(),
			clientId: CLIENT_ID,
			fetchFn: jwksFetch,
			kv: new MemoryKV().asKV(),
			nowSeconds: NOW,
		});
		expect(props).toEqual(OGUZHAN);
	});

	it("Refresh: bestätigt die Ausnahme – und beendet den Zugang, sobald sie entfernt ist oder Lenas Nutzer fehlt", async () => {
		expect(await recheckOnRefresh(OGUZHAN, { client: brokerClient(), kv: new MemoryKV().asKV() })).toEqual({ ok: true, props: OGUZHAN });
		expect(await recheckOnRefresh(OGUZHAN, deps(BROKERS, {}))).toMatchObject({ kind: "rejected", ok: false });
		expect(await recheckOnRefresh(OGUZHAN, deps([BROKERS[0]]))).toMatchObject({ kind: "rejected", ok: false });
		// eigener Propstack-Nutzer inzwischen angelegt: Die Sitzung wechselt auf die eigene ID, der zweite Name entfällt
		const mitEigenem = [...BROKERS, { email: "oguzhan.sahin@kromeichpartner.de", id: 4711, name: "Oguzhan Sahin" }];
		const eigen = await recheckOnRefresh(OGUZHAN, deps(mitEigenem));
		expect(eigen).toEqual({ ok: true, props: { brokerId: 4711, email: "oguzhan.sahin@kromeichpartner.de", name: "Oguzhan Sahin" } });
		expect(eigen.ok && "brokerName" in eigen.props).toBe(false);
	});

	it("whoami und Ergebnisse sagen, unter wessen Propstack-Nutzer geschrieben wird", () => {
		expect(brokerLabel(OGUZHAN)).toBe("Lena Klinnert");
		expect(brokerLabel({ name: "Florian Brimmers" })).toBe("Florian Brimmers");
		expect(identityInfo(OGUZHAN)).toEqual({
			email: "oguzhan.sahin@kromeichpartner.de",
			hinweis:
				"Du hast keinen eigenen Propstack-Nutzer. Was du über Claude schreibst, läuft in Propstack unter Lena Klinnert (Betreuer, Aufgaben). In den Notizen und im Protokoll des Connectors steht dein Name.",
			name: "Oguzhan Sahin",
			propstack_user_id: 254958,
			propstack_user_name: "Lena Klinnert",
		});
		// alle anderen: wie bisher, ohne Zusatz
		expect(identityInfo({ brokerId: 347158, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers" })).toEqual({
			email: "florian.brimmers@kromeichpartner.de",
			name: "Florian Brimmers",
			propstack_user_id: 347158,
		});
	});
});
