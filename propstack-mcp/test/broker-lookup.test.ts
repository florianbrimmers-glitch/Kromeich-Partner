import { describe, expect, it } from "vitest";
import { authCheckMode, matchBroker, resolveBroker } from "../src/auth/broker-lookup";
import { AuthRejection } from "../src/auth/errors";
import { authorizeLogin, brokerLabel, identityInfo, recheckOnRefresh } from "../src/auth/session";
import { ALLOWED_HOSTED_DOMAIN, BLOCKED_LOGIN_EMAILS, BROKER_ALIASES } from "../src/config";
import { PropstackClient, PropstackError } from "../src/propstack-client";
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
		expect(kv.ttls.get("propstack-broker:v2:florian.brimmers@kromeichpartner.de")).toBe(3600);
	});

	it("lehnt unbekannte Mail ab und cacht die Ablehnung nicht", async () => {
		const kv = new MemoryKV();
		const client = brokerClient();
		await expect(resolveBroker("info@kromeichpartner.de", { client, kv: kv.asKV() })).rejects.toThrow(AuthRejection);
		expect(kv.store.size).toBe(0);
	});

	it("ignoriert kaputte Cache-Einträge", async () => {
		const kv = new MemoryKV();
		kv.store.set("propstack-broker:v2:florian.brimmers@kromeichpartner.de", JSON.stringify({ id: "kaputt" }));
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

	it("Abnahme 3: Funktionspostfach → abgelehnt; unbekannte Adresse → abgelehnt", async () => {
		await expect(login(validClaims({ email: "info@kromeichpartner.de" }))).rejects.toThrow(/Sammelpostfächer/);
		await expect(login(validClaims({ email: "niemand@kromeichpartner.de" }))).rejects.toThrow(/kein aktiver Propstack-Nutzer/);
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
		await expect(resolveBroker("niemand@kromeichpartner.de", deps())).rejects.toThrow(/kein aktiver Propstack-Nutzer/);
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

describe("Strenge Prüfung – nur aktive Propstack-Nutzer, keine Sammelpostfächer (Freigabe Florian, 20.11.2026)", () => {
	// GET /v1/brokers kennt kein Aktiv-Flag. Die zweite Schnittstelle liefert active, blocked, archived und role –
	// live am 20.11.2026: owner, user, consulting und technical (info@, Kontakt Kromeich).
	const V1 = [...BROKERS, { email: "info@kromeichpartner.de", id: 254959, name: "info@" }, { email: "Buchhaltung@kromeichpartner.de", id: 300, name: "Buchhaltung" }];
	const zustand = (id: number, mehr: Record<string, unknown> = {}) => ({ active: true, archived: null, blocked: false, id, role: "user", ...mehr });
	const V2 = [zustand(111), zustand(254958, { role: "owner" }), zustand(254959, { role: "technical" }), zustand(300, { role: "technical" })];
	const ALIASES = { "oguzhan.sahin@kromeichpartner.de": { name: "Oguzhan Sahin", propstackEmail: "lena.klinnert@kromeichpartner.de", propstackId: 254958 } };

	function streng(v2: unknown = V2, v1: unknown = V1) {
		const zaehler = { v1: 0, v2: 0 };
		const client = {
			hasV2Key: true,
			listBrokers: async () => {
				zaehler.v1++;
				return v1;
			},
			listBrokersV2: async () => {
				zaehler.v2++;
				if (v2 instanceof Error) throw v2;
				return v2 as unknown[];
			},
		};
		const kv = new MemoryKV();
		return { aliases: ALIASES, client, kv, zaehler, deps: { aliases: ALIASES, client, kv: kv.asKV() } };
	}
	const mit = (id: number, mehr: Record<string, unknown>) => V2.map((row) => (row.id === id ? { ...row, ...mehr } : row));

	it("aktiver Nutzer kommt durch – mit beiden Abfragen, danach aus dem Cache", async () => {
		const w = streng();
		expect(await resolveBroker("florian.brimmers@kromeichpartner.de", w.deps)).toEqual({ email: "florian.brimmers@kromeichpartner.de", id: 111, name: "Florian Brimmers" });
		await resolveBroker("florian.brimmers@kromeichpartner.de", w.deps);
		expect(w.zaehler).toEqual({ v1: 1, v2: 1 });
	});

	it("deaktiviert, gesperrt, archiviert oder in der zweiten Liste unbekannt → abgelehnt, nichts im Cache", async () => {
		const faelle: unknown[][] = [
			mit(111, { active: false }),
			mit(111, { active: null }),
			mit(111, { blocked: true }),
			mit(111, { archived: true }),
			V2.filter((row) => row.id !== 111),
		];
		for (const v2 of faelle) {
			const w = streng(v2);
			await expect(resolveBroker("florian.brimmers@kromeichpartner.de", w.deps), JSON.stringify(v2[0])).rejects.toThrow(/kein aktiver Propstack-Nutzer/);
			await expect(resolveBroker("florian.brimmers@kromeichpartner.de", w.deps)).rejects.toThrow(AuthRejection);
			expect(w.kv.store.size).toBe(0);
		}
		// archived: false oder null heißt nicht archiviert
		expect((await resolveBroker("florian.brimmers@kromeichpartner.de", streng(mit(111, { archived: false })).deps)).id).toBe(111);
	});

	it("technische Nutzer kommen nicht durch – auch nicht, wenn sie nicht auf der festen Liste stehen", async () => {
		await expect(resolveBroker("buchhaltung@kromeichpartner.de", streng().deps)).rejects.toThrow(/Sammelpostfächer und technische Propstack-Nutzer/);
	});

	it("die beiden Sammelpostfächer sind fest ausgesperrt – ohne zweite Schnittstelle, ohne Cache, ohne Propstack zu fragen", async () => {
		expect(BLOCKED_LOGIN_EMAILS).toEqual(["info@kromeichpartner.de", "kontakt@kromeichpartner.de"]);
		for (const mail of ["info@kromeichpartner.de", " Kontakt@kromeichpartner.de"]) {
			const kv = new MemoryKV();
			// selbst ein vorhandener Cache-Eintrag hilft nicht
			kv.store.set(`propstack-broker:v2:${mail.trim().toLowerCase()}`, JSON.stringify({ email: mail.trim().toLowerCase(), id: 254959, name: "info@" }));
			const client = brokerClient(V1);
			await expect(resolveBroker(mail, { client, kv: kv.asKV() }), mail).rejects.toThrow(/Sammelpostfächer/);
			expect(client.calls).toBe(0);
		}
	});

	it("ohne zweiten Schlüssel, oder wenn er die Nutzerliste nicht lesen darf: einfache Prüfung wie bisher statt alle auszusperren", async () => {
		// kein zweiter Schlüssel
		expect((await resolveBroker("florian.brimmers@kromeichpartner.de", { client: brokerClient(V1), kv: new MemoryKV().asKV() })).id).toBe(111);
		// Schlüssel ohne Berechtigung bzw. ungültig
		for (const status of [401, 403, 404]) {
			const w = streng(new PropstackError(`Propstack lehnt ab (${status})`, status));
			expect((await resolveBroker("florian.brimmers@kromeichpartner.de", w.deps)).id, String(status)).toBe(111);
		}
	});

	it("fällt die zweite Schnittstelle aus oder liefert eine leere Liste, ist das ein vorübergehender Fehler – niemand wird abgemeldet, niemand kommt neu hinein", async () => {
		for (const v2 of [new PropstackError("Propstack-Serverfehler (503)", 503), new Error("Netz"), [], { data: [] }]) {
			const w = streng(v2);
			const fehler = await resolveBroker("florian.brimmers@kromeichpartner.de", w.deps).catch((error) => error);
			expect(fehler).toBeInstanceOf(Error);
			expect(fehler).not.toBeInstanceOf(AuthRejection);
			const props = { brokerId: 111, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers" };
			expect(await recheckOnRefresh(props, streng(v2).deps)).toMatchObject({ kind: "unavailable", ok: false });
		}
	});

	it("Refresh: Wer in Propstack deaktiviert oder gesperrt wurde, verliert den Zugang", async () => {
		const props = { brokerId: 111, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers" };
		expect(await recheckOnRefresh(props, streng().deps)).toEqual({ ok: true, props });
		expect(await recheckOnRefresh(props, streng(mit(111, { active: false })).deps)).toMatchObject({ kind: "rejected", ok: false });
		expect(await recheckOnRefresh(props, streng(mit(111, { blocked: true })).deps)).toMatchObject({ kind: "rejected", ok: false });
	});

	it("Ausnahme: Ist der Propstack-Nutzer der Kollegin deaktiviert oder gesperrt, ist auch die Person draußen", async () => {
		expect(await resolveBroker("oguzhan.sahin@kromeichpartner.de", streng().deps)).toMatchObject({ brokerName: "Lena Klinnert", id: 254958, name: "Oguzhan Sahin" });
		await expect(resolveBroker("oguzhan.sahin@kromeichpartner.de", streng(mit(254958, { active: false })).deps)).rejects.toThrow(/kein aktiver Propstack-Nutzer/);
		await expect(resolveBroker("oguzhan.sahin@kromeichpartner.de", streng(mit(254958, { blocked: true })).deps)).rejects.toThrow(AuthRejection);
	});

	it("whoami sagt, welche Prüfung gilt", async () => {
		expect(await authCheckMode(streng().client)).toMatch(/^streng/);
		expect(await authCheckMode(brokerClient(V1))).toMatch(/^einfach/);
		expect(await authCheckMode(streng(new PropstackError("verboten", 403)).client)).toMatch(/^einfach/);
		expect(await authCheckMode(streng(new PropstackError("Serverfehler", 503)).client)).toMatch(/^derzeit nicht prüfbar/);
	});
});

describe("Strenge Prüfung – mit dem echten Client und Antworten in der Form, wie Propstack sie liefert (20.11.2026)", () => {
	// GET /v1/brokers → Liste; GET /v2/brokers?per=100 → { data: [...] } mit active/blocked als true/false, archived meist null
	function propstack(v2: { status?: number; body?: unknown } = {}) {
		const gesehen: { schluessel: string | null; url: string }[] = [];
		const zustand = [
			{ active: true, archived: null, blocked: false, email: "florian.brimmers@kromeichpartner.de", first_name: "Florian", id: 111, last_name: "Brimmers", role: "user" },
			{ active: true, archived: null, blocked: false, email: "Lena.Klinnert@kromeichpartner.de", first_name: "Lena", id: 254958, last_name: "Klinnert", role: "owner" },
		];
		const fetchFn = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
			const url = String(input);
			gesehen.push({ schluessel: new Headers(init.headers).get("x-api-key"), url });
			if (url.includes("/v2/brokers")) return new Response(JSON.stringify(v2.body ?? { data: zustand }), { status: v2.status ?? 200 });
			return new Response(JSON.stringify(BROKERS), { status: 200 });
		}) as unknown as typeof fetch;
		const client = new PropstackClient({ apiKey: "v1-schluessel", apiKeyV2: "v2-schluessel", fetchFn, sleep: async () => {} });
		return { deps: { client, kv: new MemoryKV().asKV() }, gesehen, zustand };
	}

	it("fragt beide Listen ab – die zweite mit dem zweiten Schlüssel und per=100 – und lässt den aktiven Nutzer durch", async () => {
		const w = propstack();
		expect((await resolveBroker("florian.brimmers@kromeichpartner.de", w.deps)).id).toBe(111);
		expect(w.gesehen.map((g) => `${g.schluessel} ${g.url}`).sort()).toEqual([
			"v1-schluessel https://api.propstack.de/v1/brokers",
			"v2-schluessel https://api.propstack.de/v2/brokers?per=100",
		]);
		expect(await authCheckMode(w.deps.client)).toMatch(/^streng/);
	});

	it("deaktivierter Nutzer wird abgelehnt; die Ausnahme hängt am Zustand von Lenas Nutzer", async () => {
		const aus = propstack();
		aus.zustand[0].active = false;
		await expect(resolveBroker("florian.brimmers@kromeichpartner.de", aus.deps)).rejects.toThrow(/kein aktiver Propstack-Nutzer/);
		expect(await resolveBroker("oguzhan.sahin@kromeichpartner.de", propstack().deps)).toMatchObject({ brokerName: "Lena Klinnert", id: 254958 });
		const gesperrt = propstack();
		gesperrt.zustand[1].blocked = true;
		await expect(resolveBroker("oguzhan.sahin@kromeichpartner.de", gesperrt.deps)).rejects.toThrow(AuthRejection);
	});

	it("darf der zweite Schlüssel die Nutzerliste nicht lesen (403), gilt die einfache Prüfung; bei einem Ausfall (503) kommt niemand neu hinein", async () => {
		const verboten = propstack({ body: { message: "forbidden" }, status: 403 });
		expect((await resolveBroker("florian.brimmers@kromeichpartner.de", verboten.deps)).id).toBe(111);
		expect(await authCheckMode(verboten.deps.client)).toMatch(/^einfach/);
		const ausfall = propstack({ body: { message: "down" }, status: 503 });
		const fehler = await resolveBroker("florian.brimmers@kromeichpartner.de", ausfall.deps).catch((error) => error);
		expect(fehler).toBeInstanceOf(PropstackError);
		expect(fehler).not.toBeInstanceOf(AuthRejection);
		expect(await authCheckMode(ausfall.deps.client)).toMatch(/^derzeit nicht prüfbar/);
	});
});
