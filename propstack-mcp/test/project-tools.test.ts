import { describe, expect, it } from "vitest";
import type { Page, PropstackClient } from "../src/propstack-client";
import { createReviewTask, nextWorkdayNine } from "../src/review-task";
import { addImages, checkImageUrl, createProject, setProjectOwner, updateProject } from "../src/tools/project-tools";

const page = (rows: Record<string, unknown>[]): Page => ({ rows, total: rows.length });
const USER = { brokerId: 347158, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers" };
const NOW = () => new Date("2026-10-16T10:00:00Z"); // Freitag

function fakeDb() {
	const rows: unknown[][] = [];
	const updates: unknown[][] = [];
	const db = {
		prepare: (sql: string) => ({
			bind: (...args: unknown[]) => ({
				run: async () => {
					if (sql.startsWith("INSERT")) rows.push(args);
					else updates.push(args);
					return { meta: { changes: 1, last_row_id: rows.length } };
				},
			}),
		}),
	} as unknown as D1Database;
	return { db, rows, updates };
}

function fakeClient(impl: Record<string, (...args: unknown[]) => unknown>) {
	const calls: { method: string; args: unknown[] }[] = [];
	const defaults: Record<string, (...args: unknown[]) => unknown> = {
		createTask: () => ({ id: 77 }),
		getContact: () => ({ id: 17366550, name: "Goodman Germany GmbH" }),
		searchProjects: () => page([]),
	};
	const all = { ...defaults, ...impl };
	const client = new Proxy(
		{},
		{
			get: (_t, prop: string) => async (...args: unknown[]) => {
				calls.push({ args, method: prop });
				const fn = all[prop];
				if (!fn) throw new Error(`unerwarteter Aufruf ${prop}`);
				return fn(...args);
			},
		},
	) as unknown as PropstackClient;
	return { calls, client };
}

describe("Prüfaufgabe", () => {
	it("nächster Werktag 9:00", () => {
		expect(nextWorkdayNine(new Date("2026-10-16T10:00:00Z"))).toBe("2026-10-19T09:00:00"); // Fr → Mo
		expect(nextWorkdayNine(new Date("2026-10-14T21:30:00Z"))).toBe("2026-10-15T09:00:00"); // Mi 23:30 Berlin → Do
	});

	it("geht an Lena als Erinnerung, Testdaten an den Nutzer", async () => {
		let sent: Record<string, unknown> = {};
		const { client } = fakeClient({
			createTask: (t) => {
				sent = t as Record<string, unknown>;
				return { id: 1 };
			},
		});
		const out = await createReviewTask(client, fakeDb().db, { lines: ["Objekt <b>1</b>: Hallé"], now: NOW(), propertyIds: [1], test: false, title: "Halle", user: USER });
		expect(out).toMatchObject({ assigned_to: "Lena Klinnert", id: 1 });
		expect(sent).toMatchObject({ broker_id: 254958, is_reminder: true, property_ids: [1], title: "Prüfung: Halle" });
		expect(sent.body).toBe("<p>Objekt &lt;b&gt;1&lt;/b&gt;: Hallé</p>"); // Umlaute/Sonderzeichen bleiben
		await createReviewTask(client, fakeDb().db, { lines: [], now: NOW(), test: true, title: "Halle", user: USER });
		expect(sent).toMatchObject({ broker_id: 347158, title: "[MCP-TEST] Prüfung: Halle" });
	});

	it("Fehler beim Anlegen der Aufgabe wird gemeldet, nicht geworfen", async () => {
		const { client } = fakeClient({
			createTask: () => {
				throw new Error("Propstack hat den Zugriff verweigert (403)");
			},
		});
		const out = await createReviewTask(client, fakeDb().db, { lines: [], now: NOW(), test: false, title: "X", user: USER });
		expect(out.error).toMatch(/403/);
	});
});

describe("create_project", () => {
	const input = { city: "Düsseldorf", house_number: "12", marketing_type: "RENT" as const, name: "Logistikhalle in (40) Düsseldorf – Kappeler Straße", street: "Kappeler Straße", zip_code: "40597" };

	it("legt an, setzt verlorene Felder einzeln nach, verknüpft Eigentümer, Prüfaufgabe", async () => {
		const stored: Record<string, unknown> = {};
		const puts: Record<string, unknown>[] = [];
		const { client } = fakeClient({
			createProject: (p) => {
				const { broker_id: _dropped, ...rest } = p as Record<string, unknown>; // broker_id geht im POST verloren
				Object.assign(stored, rest);
				return { id: 600 };
			},
			// Propstack hat selbst geokodiert → keine Koordinaten-Writes
			getProject: () => ({ ...stored, broker: stored.broker_id ? { id: stored.broker_id } : null, id: 600, lat: 51.2, lng: 6.8 }),
			updateProject: (_id, p) => {
				puts.push(p as Record<string, unknown>);
				if (!("relationships_attributes" in (p as object))) Object.assign(stored, p);
				else if (puts.filter((x) => "relationships_attributes" in x).length > 1) {
					throw new Error('Propstack-Anfrage fehlgeschlagen (400): ["Relationships project ist bereits mit dem Kontakt verbunden"]');
				}
				return {};
			},
		});
		const out = await createProject(
			{ client, db: fakeDb().db, now: NOW, user: USER },
			{ ...input, courtage: "Provisionsfrei", owner_contact_id: 17366550, review_notes: ["Energieausweis fehlt"], test: true },
		);
		expect(stored).toMatchObject({ country: "DEU", for_rent: true, name: "MCP-TEST Logistikhalle in (40) Düsseldorf – Kappeler Straße" });
		// Interne Notiz am Projekt (API-Doku: note) mit Herkunft
		expect(String(stored.note)).toMatch(/^Angelegt über Claude \(Propstack MCP\) von Florian Brimmers/);
		const link = { relationships_attributes: [{ internal_name: "owner", related_client_id: 17366550 }] };
		expect(puts).toEqual([{ broker_id: 347158 }, link, link]); // zweiter Aufruf = Gegenprobe
		expect(out.result).toMatchObject({
			created: true,
			id: 600,
			owner: { id: 17366550, linked: true, name: "Goodman Germany GmbH" },
			review_task: { assigned_to: "Florian Brimmers", due: "2026-10-19T09:00:00", id: 77 },
		});
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
	});

	it("Dublette per Adresse blockiert", async () => {
		const { client, calls } = fakeClient({
			searchProjects: () => page([{ house_number: "12", id: 5, name: "Alt", street: "Kappeler Str.", zip_code: "40597" }]),
		});
		const out = await createProject({ client, db: fakeDb().db, now: NOW, user: USER }, input);
		expect(out.result).toMatchObject({ blocked: "Dublette", duplicates: [{ id: 5 }] });
		expect(calls.some((c) => c.method === "createProject")).toBe(false);
	});
});

describe("set_project_owner", () => {
	it("fremder Shop wird verständlich gemeldet", async () => {
		const { client } = fakeClient({
			getProject: () => ({ id: 1, name: "P" }),
			updateProject: () => {
				throw new Error("Propstack-Anfrage fehlgeschlagen (400): Relationships project muss demselben Shop angehören");
			},
		});
		await expect(setProjectOwner({ client, db: fakeDb().db, user: USER }, { contact_id: 120978, project_id: 1 })).rejects.toThrow(/eigenen Shop/);
	});

	it("bestätigt eine neue Verknüpfung über die Gegenprobe (Propstack lehnt Doppelte ab)", async () => {
		let calls = 0;
		const { client } = fakeClient({
			getProject: () => ({ id: 1, name: "P" }),
			updateProject: () => {
				calls++;
				if (calls === 1) return {};
				throw new Error('Propstack-Anfrage fehlgeschlagen (400): ["Relationships project ist bereits mit dem Kontakt verbunden"]');
			},
		});
		const out = await setProjectOwner({ client, db: fakeDb().db, user: USER }, { contact_id: 2, project_id: 1 });
		expect(out.result).toMatchObject({ linked: true });
		expect(calls).toBe(2);
	});

	it("nimmt Propstack die Probe ebenfalls an, gilt das als nicht prüfbar", async () => {
		const { client } = fakeClient({ getProject: () => ({ id: 1, name: "P" }), updateProject: () => ({}) });
		const out = await setProjectOwner({ client, db: fakeDb().db, user: USER }, { contact_id: 2, project_id: 1 });
		expect(out.result).toMatchObject({ linked: "nicht prüfbar", note: expect.stringMatching(/zweimal/) });
	});

	it("Live-Meldung „bereits mit dem Kontakt verbunden“ zählt als verknüpft (Projekt 603380, 15.10.)", async () => {
		const { client } = fakeClient({
			getProject: () => ({ id: 603380, name: "P" }),
			updateProject: () => {
				throw new Error('Propstack-Anfrage fehlgeschlagen (400): ["Relationships project ist bereits mit dem Kontakt verbunden"]');
			},
		});
		const out = await setProjectOwner({ client, db: fakeDb().db, user: USER }, { contact_id: 37523924, project_id: 603380 });
		expect(out.result).toMatchObject({ already_linked: true, linked: true });
	});

	it("bereits verknüpft zählt als erfolgreich", async () => {
		const { client } = fakeClient({
			getProject: () => ({ id: 1, name: "P" }),
			updateProject: () => {
				throw new Error("Propstack-Anfrage fehlgeschlagen (400): Diese Verknüpfung existiert bereits.");
			},
		});
		const out = await setProjectOwner({ client, db: fakeDb().db, user: USER }, { contact_id: 2, project_id: 1 });
		expect(out.result).toMatchObject({ already_linked: true, linked: true });
	});
});

describe("add_images", () => {
	const fetchFn = (async (url: string) =>
		url.includes("ok")
			? new Response(null, { headers: { "content-type": "image/jpeg" }, status: 200 })
			: url.includes("html")
				? new Response(null, { headers: { "content-type": "text/html" }, status: 200 })
				: new Response(null, { status: 404 })) as unknown as typeof fetch;

	it("prüft URLs vorab, lädt nur echte Bilder hoch", async () => {
		const sent: unknown[] = [];
		const { client } = fakeClient({
			createImage: (i) => {
				sent.push(i);
				return { id: 900 + sent.length };
			},
			getUnit: () => ({ id: 5 }),
		});
		const out = await addImages(
			{ client, db: fakeDb().db, fetchFn, user: USER },
			{ object_id: 5, titles: ["Außenansicht", "Seite", "Weg", "Halle innen"], urls: ["https://x.de/ok1.jpg", "https://x.de/page.html", "https://x.de/weg.jpg", "https://x.de/ok2.jpg"] },
		);
		expect(sent).toEqual([
			{ imageable_id: 5, imageable_type: "Property", remote_photo_url: "https://x.de/ok1.jpg", title: "Außenansicht" },
			{ imageable_id: 5, imageable_type: "Property", remote_photo_url: "https://x.de/ok2.jpg", title: "Halle innen" },
		]);
		expect(out.result).toMatchObject({ image_ids: [901, 902], rejected: [{ reason: expect.stringMatching(/kein Bild/) }, { reason: expect.stringMatching(/404/) }], uploaded: 2 });
	});

	it("genau ein Ziel", async () => {
		const { client } = fakeClient({});
		await expect(addImages({ client, db: fakeDb().db, fetchFn, user: USER }, { titles: ["Außenansicht"], urls: ["https://x.de/ok.jpg"] })).rejects.toThrow(/Genau eins/);
	});

	it("checkImageUrl schickt User-Agent und fällt bei 405 auf GET zurück", async () => {
		const methods: string[] = [];
		const f = (async (_u: string, init: RequestInit) => {
			methods.push(String(init.method));
			// neutraler Client-Name – keine Firmen- oder Personendaten an fremde Server
			expect((init.headers as Record<string, string>)["User-Agent"]).toMatch(/^propstack-mcp\//);
			expect((init.headers as Record<string, string>)["User-Agent"]).not.toMatch(/kromeich/i);
			return init.method === "HEAD" ? new Response(null, { status: 405 }) : new Response(null, { headers: { "content-type": "image/png" }, status: 206 });
		}) as unknown as typeof fetch;
		expect(await checkImageUrl("https://x.de/a.png", f)).toBeNull();
		expect(methods).toEqual(["HEAD", "GET"]);
	});
});

describe("Koordinaten (Notion-Korrektur 34)", async () => {
	const { coordinatesLine, ensureCoordinates, writeCoordinates } = await import("../src/propstack/geo");

	it("lat einmal, lng in Stufen 1–4 Nachkommastellen, dann exakt; Kontrolle per Einzel-GET", async () => {
		const puts: Record<string, unknown>[] = [];
		let stored: Record<string, number> = {};
		const out = await writeCoordinates(
			async () => stored,
			async (b) => {
				puts.push(b);
				stored = { ...stored, ...(b as Record<string, number>) };
			},
			{ lat: 50.4367, lng: 7.704712 },
		);
		expect(puts).toEqual([{ lat: 50.4367 }, { lng: 7.7 }, { lng: 7.7 }, { lng: 7.705 }, { lng: 7.7047 }, { lng: 7.704712 }]);
		expect(out).toMatchObject({ verified: true });
	});

	it("Propstack hat selbst Koordinaten → nichts schreiben; sonst OpenStreetMap mit ehrlicher Genauigkeit", async () => {
		const noWrite = await ensureCoordinates({ current: { lat: 50.1, lng: 7.1 }, put: async () => { throw new Error("darf nicht schreiben"); }, read: async () => ({}) });
		expect(noWrite).toMatchObject({ source: "Propstack", verified: true });

		const store = () => {
			let stored: Record<string, number> = {};
			return { put: async (b: unknown) => void (stored = { ...stored, ...(b as Record<string, number>) }), read: async () => stored };
		};
		const osm = (houseNumberKnown: boolean) =>
			(async (url: string, init: RequestInit) => {
				expect(url).toContain("postalcode=56204");
				expect(url).toContain("addressdetails=1");
				expect((init.headers as Record<string, string>)["User-Agent"]).not.toMatch(/kromeich/i);
				return new Response(JSON.stringify([{ address: houseNumberKnown ? { house_number: "3" } : { road: "Am Scheid" }, lat: "50.4109123", lon: "7.6809456" }]), { status: 200 });
			}) as unknown as typeof fetch;

		// Ohne Hausnummer: straßengenau – wird gesetzt und als solches gemeldet.
		// (Korrektur 09.11.: Die UI zieht für dieselbe Adresse 50.4109821/7.6811256, OSM liegt ≈ 15 m daneben.)
		const street = await ensureCoordinates({ address: { city: "Hillscheid", street: "Am Scheid", zip_code: "56204" }, current: {}, fetchFn: osm(false), ...store() });
		expect(street).toMatchObject({ lat: 50.410912, lng: 7.680946, precision: "Straße (keine Hausnummer)", source: "OpenStreetMap", verified: true });
		expect(street.note).toMatch(/straßengenau/);
		expect(coordinatesLine(street)).toMatch(/Genauigkeit Straße \(keine Hausnummer\)\) – Nur straßengenau/);

		// Mit Hausnummer gefragt, OpenStreetMap kennt sie nicht → nicht als „Hausnummer“ ausgeben
		const unknownNumber = await ensureCoordinates({ address: { city: "Hillscheid", house_number: "3", street: "Am Scheid", zip_code: "56204" }, current: {}, fetchFn: osm(false), ...store() });
		expect(unknownNumber).toMatchObject({ precision: "Straße (Hausnummer in OpenStreetMap nicht gefunden)", verified: true });

		const exact = await ensureCoordinates({ address: { city: "Hillscheid", house_number: "3", street: "Am Scheid", zip_code: "56204" }, current: {}, fetchFn: osm(true), ...store() });
		expect(exact).toMatchObject({ precision: "Hausnummer", source: "OpenStreetMap", verified: true });
		expect(exact.note).toBeUndefined();

		// Vom Projekt übernommene Koordinaten werden als solche ausgewiesen
		const fromProject = await ensureCoordinates({ current: {}, provided: { lat: 50.4109821, lng: 7.6811256 }, providedSource: "Projekt", ...store() });
		expect(fromProject).toMatchObject({ lat: 50.4109821, lng: 7.6811256, source: "Projekt", verified: true });
	});

	it("lng haftet nicht → nach einem zweiten Durchgang als nicht verifiziert gemeldet", async () => {
		let puts = 0;
		const pauses: number[] = [];
		const out = await writeCoordinates(async () => ({ lat: 50, lng: 7 }), async () => void puts++, { lat: 50.5, lng: 7.5 }, async (ms) => void pauses.push(ms));
		expect(out.verified).toBe(false);
		expect(puts).toBe(12); // zwei Durchgänge: je lat + fünf lng-Stufen
		expect(pauses).toEqual([1000]);
	});

	it("lng bleibt im ersten Durchgang auf einem Zwischenwert stehen → zweiter Durchgang sitzt (live 09.11., Projekt 603710)", async () => {
		let stored: Record<string, number> = { lat: 50.4367, lng: 7.7047 };
		let lngPuts = 0;
		const out = await writeCoordinates(
			async () => stored,
			async (b) => {
				const body = b as Record<string, number>;
				if ("lng" in body) {
					lngPuts++;
					// Propstack übernimmt im ersten Durchgang nur die ersten beiden Stufen
					if (lngPuts > 2 && lngPuts <= 5) return;
				}
				stored = { ...stored, ...body };
			},
			{ lat: 50.4109821, lng: 7.6811256 },
			async () => {},
		);
		expect(out).toMatchObject({ lat: 50.4109821, lng: 7.6811256, verified: true });
		expect(lngPuts).toBe(10);
	});

	it("Propstack speichert lng nur auf vier Nachkommastellen: gilt als gesetzt (≈ 3,5 m), kein Fehlalarm, kein zweiter Durchgang (live 10.11., Projekt 613378)", async () => {
		let stored: Record<string, number> = {};
		let puts = 0;
		const put = async (b: unknown) => {
			puts++;
			const body = b as Record<string, number>;
			// der exakte Wert (sechs Stellen) wird verworfen, die vierstellige Stufe bleibt
			if ("lng" in body && String(body.lng).split(".")[1]?.length > 4) return;
			stored = { ...stored, ...body };
		};
		const out = await writeCoordinates(async () => stored, put, { lat: 50.411816, lng: 7.688649 }, async () => {});
		expect(out).toMatchObject({ lat: 50.411816, lng: 7.6886, rounded: true, verified: true });
		expect(puts).toBe(6);
		const result = await ensureCoordinates({ current: {}, provided: { lat: 50.411816, lng: 7.688649 }, put, read: async () => stored, sleep: async () => {} });
		expect(result).toMatchObject({ lng: 7.6886, source: "angegeben", verified: true });
		expect(result.note).toMatch(/vier Nachkommastellen/);
		// 85 m daneben (zwei Stellen) bleibt ein Befund
		expect((await writeCoordinates(async () => ({ lat: 50.411816, lng: 7.69 }), async () => {}, { lat: 50.411816, lng: 7.688649 }, async () => {})).verified).toBe(false);
	});

	it("veralteter Lesewert nach dem Schreiben: nach der Pause neu lesen, nicht noch einmal schreiben", async () => {
		const target = { lat: 50.4109821, lng: 7.6811256 };
		let reads = 0;
		let puts = 0;
		const out = await writeCoordinates(
			async () => (++reads <= 2 ? { lat: 50.4, lng: 7.68 } : target), // 1. Lesen vorher, 2. Lesen veraltet, 3. Lesen aktuell
			async () => void puts++,
			target,
			async () => {},
		);
		expect(out.verified).toBe(true);
		expect(puts).toBe(6);
	});
});

describe("update_project", () => {
	it("schreibt nur Änderungen, sichert vorher, setzt Verlorenes einzeln nach, Koordinaten per Stufen-Trick", async () => {
		const stored: Record<string, unknown> = { city: "Hillscheid", courtage: null, courtage_note: null, id: 603710, name: "P", street: "Am Scheid", zip_code: "56204" };
		const puts: Record<string, unknown>[] = [];
		const { client } = fakeClient({
			getProject: () => ({ ...stored }),
			updateProject: (_id, p) => {
				const payload = p as Record<string, unknown>;
				puts.push(payload);
				// Sammel-PUT verliert courtage_note still
				const keys = Object.keys(payload);
				for (const [k, v] of Object.entries(payload)) if (!(k === "courtage_note" && keys.length > 1)) stored[k] = v;
				return {};
			},
		});
		const { db, rows } = fakeDb();
		const out = await updateProject(
			{ client, db, now: NOW, user: USER },
			{ city: "Hillscheid", courtage: "Provisionsfrei", courtage_note: "Die Anmietung erfolgt provisionsfrei für den Mieter.", id: 603710, lat: 50.4367, lng: 7.7047 },
		);
		expect(puts[0]).toEqual({ courtage: "Provisionsfrei", courtage_note: "Die Anmietung erfolgt provisionsfrei für den Mieter." });
		expect(puts[1]).toEqual({ courtage_note: "Die Anmietung erfolgt provisionsfrei für den Mieter." });
		expect(puts[2]).toEqual({ lat: 50.4367 });
		expect(out.result).toMatchObject({ changed: ["courtage", "courtage_note", "lat/lng"], coordinates: { verified: true }, updated: true });
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
		// Snapshot vorher: auch die bisherigen Koordinaten (hier: keine)
		expect(JSON.parse(rows[0][7] as string)).toEqual({ courtage: null, courtage_note: null, lat: null, lng: null });
	});

	it("keine Änderung → kein Write; Adresse kollidiert → blockiert", async () => {
		const { client, calls } = fakeClient({
			getProject: () => ({ city: "Hillscheid", courtage: "Provisionsfrei", id: 1, name: "P", street: "Am Scheid", zip_code: "56204" }),
			searchProjects: () => page([{ id: 2, name: "Anderes", street: "Hauptstraße", house_number: "1", zip_code: "56204" }]),
		});
		const deps = { client, db: fakeDb().db, now: NOW, user: USER };
		expect((await updateProject(deps, { courtage: "Provisionsfrei", id: 1 })).result).toMatchObject({ updated: false });
		expect((await updateProject(deps, { house_number: "1", id: 1, street: "Hauptstraße" })).result).toMatchObject({ blocked: "Dublette", duplicates: [{ id: 2 }] });
		expect(calls.some((c) => c.method === "updateProject")).toBe(false);
	});
});

describe("update_project – interne Notiz, Unterzeile", () => {
	it("hängt die Notiz an (alter Text bleibt), schreibt sub_headline, meldet nicht Gespeichertes", async () => {
		const stored: Record<string, unknown> = { city: "Hillscheid", id: 1, name: "P", note: "Alt", street: "Am Scheid", sub_headline: null, zip_code: "56204" };
		const { client } = fakeClient({
			getProject: () => ({ ...stored }),
			listCustomFieldGroups: () => page([]),
			updateProject: (_id, p) => {
				const payload = p as Record<string, unknown>;
				// Simulation: Propstack verwirft note still (wie laut Notion früher beobachtet)
				for (const [k, v] of Object.entries(payload)) if (k !== "note") stored[k] = v;
				return {};
			},
		});
		const out = await updateProject(
			{ client, db: fakeDb().db, now: NOW, user: USER },
			{ id: 1, note_append: "Exposé: https://example.org/expose.pdf · Alleinmandat", sub_headline: "Direkt an der A48" },
		);
		expect(stored.sub_headline).toBe("Direkt an der A48");
		expect(out.result).toMatchObject({ changed: ["sub_headline", "note"], not_applied: ["note"] });
	});
});

describe("create_project – Team-How-to", () => {
	const input = { city: "Düsseldorf", house_number: "12", marketing_type: "RENT" as const, name: "Logistikhalle in (40) Düsseldorf", street: "Kappeler Straße", zip_code: "40597" };

	function world() {
		const stored: Record<string, unknown> = {};
		const links: unknown[] = [];
		let task: Record<string, unknown> = {};
		const { client, calls } = fakeClient({
			createProject: (p) => {
				Object.assign(stored, p);
				return { id: 700 };
			},
			createTask: (t) => {
				task = t as Record<string, unknown>;
				return { id: 78 };
			},
			getContact: (id) => (id === 111 ? { company: "Goodman Germany GmbH", id: 111, name: "Goodman Germany GmbH" } : { company: "Goodman Germany GmbH", id: 222, name: "Stefan Prange" }),
			// GET liefert note nicht zurück (live 09.11.) und kennt die Adresse – Propstack hat selbst geokodiert
			getProject: () => {
				const { note: _note, ...rest } = stored;
				return { ...rest, broker: { id: 347158 }, id: 700, lat: 51.2, lng: 6.8 };
			},
			updateProject: (_id, p) => {
				const body = p as { relationships_attributes?: { internal_name: string; related_client_id: number }[] };
				if (!body.relationships_attributes) return Object.assign(stored, p);
				const key = JSON.stringify(body.relationships_attributes[0]);
				if (links.includes(key)) throw new Error('Propstack-Anfrage fehlgeschlagen (400): ["Relationships project ist bereits mit dem Kontakt verbunden"]');
				links.push(key);
				return {};
			},
		});
		return { calls, client, links, stored, task: () => task };
	}

	it("Ansprechpartner als verknüpfter Kontakt, Provision per Vorgabe, interne Notiz strukturiert und in der Prüfaufgabe", async () => {
		const w = world();
		const out = await createProject(
			{ client: w.client, db: fakeDb().db, now: NOW, user: USER },
			{
				...input,
				commission: "provisionsfrei",
				contact_person_id: 222,
				description_note: "Logistikpark mit drei Hallen und insgesamt 30.000 m² Hallenfläche.",
				furnishing_note: "- 30 Rampentore\n- LED-Beleuchtung",
				internal_commission: "Tischregel 50/50",
				internal_rents: "Halle 6,80 €/m², Büro 12,80 €/m²",
				location_note: "Autobahnen:\nA46: ca. 2 km",
				mandate: "kein Alleinmandat",
				owner_contact_id: 111,
				source_link: "https://example.org/expose.pdf",
				sub_headline: "Direkt an der A46",
			},
		);
		expect(w.stored).toMatchObject({ courtage: "Provisionsfrei", courtage_note: "Die Anmietung erfolgt provisionsfrei für den Mieter.", title: "Logistikhalle in (40) Düsseldorf" });
		// How-to „Webseite & Landing-Page“: Mietprojekt und Einheiten auf der Landing-Page
		expect(w.stored).toMatchObject({ for_rent: true, show_units_on_landing_page: true });
		expect(String(w.stored.note).split("\n")).toEqual([
			"Angelegt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-16.",
			"Exposé/Website: https://example.org/expose.pdf",
			"Mandat: kein Alleinmandat",
			"Mietpreise: Halle 6,80 €/m², Büro 12,80 €/m²",
			"Provision intern: Tischregel 50/50",
		]);
		expect(w.links).toEqual([
			JSON.stringify({ internal_name: "owner", related_client_id: 111 }),
			JSON.stringify({ internal_name: "partner", related_client_id: 222 }),
		]);
		expect(out.result).toMatchObject({
			contact_person: { id: 222, linked: true, name: "Stefan Prange" },
			owner: { id: 111, linked: true },
		});
		// Die Notiz speichert Propstack, liefert sie aber nie zurück – bekannt, kein Befund je Anlage
		expect((out.result as { not_verifiable?: string[] }).not_verifiable).toBeUndefined();
		expect((out.result as { howto_not_provided?: string[] }).howto_not_provided).toBeUndefined();
		expect((out.result as { ui_steps: string[] }).ui_steps.join(" ")).toMatch(/Einheitenliste im Exposé anzeigen/);
		// Prüfaufgabe: UI-Schritte und beide Verknüpfungen
		const body = String(w.task().body);
		expect(body).toMatch(/Ansprechpartner: Stefan Prange \(222\)/);
		expect(body).toMatch(/Einheitenliste im Exposé anzeigen/);
	});

	it("meldet, was laut How-to fehlt, und Hinweise zu Texten", async () => {
		const w = world();
		const out = await createProject(
			{ client: w.client, db: fakeDb().db, now: NOW, user: USER },
			{ ...input, location_note: "Autobahnen:\nA46: ca. 2 km", title: "Logistikpark in (40) Düsseldorf – Kappeler Straße" },
		);
		const result = out.result as { howto_not_provided: string[]; text_warnings: string[] };
		expect(result.howto_not_provided).toEqual(
			expect.arrayContaining(["Eigentümer", "Interne Notiz: Exposé-/Website-Link", "Interne Notiz: Mandat", "Interne Notiz: Mietpreise", "Unterzeile (z. B. „Direkt an der A40“)", "Provision", "Projektbeschreibung", "Ausstattung"]),
		);
		expect(result.howto_not_provided).not.toContain("Lage");
		// Straße in der Überschrift: Hinweis; Überschrift ≠ Name: Hinweis
		expect(result.text_warnings.join(" ")).toMatch(/Überschrift: nennt die Straße „Kappeler Straße“/);
		expect(result.text_warnings.join(" ")).toMatch(/Überschrift weicht vom Projektnamen ab/);
		expect(String(w.task().body)).toMatch(/Nicht angegeben \(laut How-to wichtig\): Eigentümer/);
	});

	it("weist Texte gegen die Team-Regeln vor dem Anlegen ab", async () => {
		const w = world();
		const deps = { client: w.client, db: fakeDb().db, now: NOW, user: USER };
		await expect(createProject(deps, { ...input, description_note: "Ein Projekt der Goodman Germany GmbH.", owner_contact_id: 111 })).rejects.toThrow(/nennt den Eigentümer „Goodman Germany GmbH“/);
		await expect(createProject(deps, { ...input, description_note: "Miete 6,80 €/m² zzgl. Nebenkosten." })).rejects.toThrow(/enthält einen Preis \(„6,80 €“\)/);
		await expect(createProject(deps, { ...input, furnishing_note: "LED-Beleuchtung, Sprinkler, 30 Rampen, Hallenhöhe 10,5 m" })).rejects.toThrow(/Ausstattung: bitte als Aufzählung/);
		await expect(createProject(deps, { ...input, name: "Logistikhalle in (50) Düsseldorf" })).rejects.toThrow(/\(50\) passt nicht zur PLZ 40597 – richtig wäre \(40\)/);
		// streng nach How-to: Name ohne „(XX)“, Lage ohne km, Adresse im Text
		await expect(createProject(deps, { ...input, name: "Logistikhalle Düsseldorf" })).rejects.toThrow(/Projektname „Logistikhalle Düsseldorf“ ohne „\(40\)“/);
		await expect(createProject(deps, { ...input, location_note: "Verkehrsgünstig gelegen." })).rejects.toThrow(/es fehlen die Entfernungen in km/);
		await expect(createProject(deps, { ...input, description_note: "Logistikpark an der Kappeler Straße 12." })).rejects.toThrow(/nennt die Straße „Kappeler Straße“ – die Adresse darf/);
		await expect(createProject(deps, { ...input, commission: "staffel", marketing_type: "BUY" })).rejects.toThrow(/commission gilt nur für Miete/);
		expect(w.calls.some((c) => c.method === "createProject")).toBe(false);
		// Preis im Text nur auf ausdrückliche Ansage
		const ok = await createProject(deps, { ...input, description_note: "Miete 6,80 €/m² zzgl. Nebenkosten.", public_price_confirmed: true });
		expect(ok.result).toMatchObject({ created: true });
	});

	it("Staffel-Vorgabe: Provisionshinweis mit den vier Standardsätzen, Außenprovision bleibt frei", async () => {
		const w = world();
		await createProject({ client: w.client, db: fakeDb().db, now: NOW, user: USER }, { ...input, commission: "staffel" });
		expect(w.stored.courtage).toBeUndefined();
		const lines = String(w.stored.courtage_note).split("\n");
		expect(lines).toHaveLength(4);
		expect(lines[0]).toBe("Bei Mietverträgen mit einer Laufzeit von weniger als fünf (5) Jahren beträgt der Provisionsanspruch zwei (2) Nettokaltmieten zzgl. MwSt.");
		expect(lines[3]).toMatch(/ab zehn \(10\) Jahren .* vier \(4\) Nettokaltmieten zzgl\. MwSt\.$/);
	});
});

describe("update_project – Schutz der internen Notiz, Hinweis auf die Einheiten", () => {
	it("hängt nicht an, wenn Propstack die vorhandene Notiz nicht zurückliefert (würde sie überschreiben)", async () => {
		const { client, calls } = fakeClient({ getProject: () => ({ city: "Hillscheid", id: 1, name: "P", street: "Am Scheid", zip_code: "56204" }) });
		await expect(updateProject({ client, db: fakeDb().db, now: NOW, user: USER }, { id: 1, note_append: "Exposé: https://example.org" })).rejects.toThrow(/nicht zurück – anhängen würde sie überschreiben/);
		expect(calls.some((c) => c.method === "updateProject")).toBe(false);
	});

	it("geänderte Texte: Regeln greifen, Ergebnis nennt den Weg zu den Einheiten", async () => {
		const stored: Record<string, unknown> = { city: "Hillscheid", for_rent: true, id: 5, name: "P", street: "Am Scheid", zip_code: "56204" };
		const { client } = fakeClient({
			getProject: () => ({ ...stored }),
			updateProject: (_id, p) => Object.assign(stored, p),
		});
		const deps = { client, db: fakeDb().db, now: NOW, user: USER };
		await expect(updateProject(deps, { furnishing_note: "LED, Sprinkler, Rampen", id: 5 })).rejects.toThrow(/Aufzählung/);
		const out = await updateProject(deps, { commission: "provisionsfrei", furnishing_note: "- LED\n- Sprinkler", id: 5 });
		expect(stored).toMatchObject({ courtage: "Provisionsfrei", furnishing_note: "- LED\n- Sprinkler" });
		expect(String((out.result as { units_hint: string }).units_hint)).toMatch(/object_filter \{project_id: 5\}/);
	});
});

describe("set_project_owner – Ansprechpartner", () => {
	it("role=contact_person verknüpft als Kontakt ohne Bezeichnung (wie von Hand); Gegenprobe bestätigt", async () => {
		const sent: unknown[] = [];
		const { client } = fakeClient({
			getUnit: () => ({ id: 9, title: "Halle" }),
			updateUnit: (_id, p) => {
				sent.push(p);
				if (sent.length > 1) throw new Error('Propstack-Anfrage fehlgeschlagen (400): ["Relationships property ist bereits mit dem Kontakt verbunden"]');
				return {};
			},
		});
		const out = await setProjectOwner({ client, db: fakeDb().db, user: USER }, { contact_id: 222, object_id: 9, role: "contact_person" });
		expect(sent[0]).toEqual({ relationships_attributes: [{ internal_name: "partner", related_client_id: 222 }] });
		expect(out.result).toMatchObject({ contact: { id: 222 }, linked: true, role: "Ansprechpartner" });
	});

	it("Einheit: schon verknüpft → nichts schreiben; neu verknüpft → am Einzel-GET bestätigt", async () => {
		let links = [{ client_id: 111, internal_name: "owner", name: null }];
		const sent: unknown[] = [];
		const { client } = fakeClient({
			getUnit: () => ({ id: 9, relationships: links, title: "Halle" }),
			updateUnit: (_id, p) => {
				sent.push(p);
				links = [...links, { client_id: 222, internal_name: "partner", name: null }];
				return {};
			},
		});
		const deps = { client, db: fakeDb().db, user: USER };
		expect((await setProjectOwner(deps, { contact_id: 111, object_id: 9 })).result).toMatchObject({ already_linked: true, linked: true });
		expect(sent).toEqual([]);
		// derselbe Kontakt in anderer Rolle zählt nicht als verknüpft
		expect((await setProjectOwner(deps, { contact_id: 222, object_id: 9, role: "contact_person" })).result).toMatchObject({ linked: true });
		expect(sent).toHaveLength(1);
	});

	it("Projekt: Verknüpfung wird am Projekt-GET gegengelesen (relationships) – ohne zweiten Schreibversuch; schon verknüpft → nichts schreiben", async () => {
		let links = [{ client_id: 111, internal_name: "owner", name: null }];
		const sent: unknown[] = [];
		const { client } = fakeClient({
			getProject: () => ({ id: 603710, name: "P", relationships: links }),
			updateProject: (_id, p) => {
				sent.push(p);
				links = [...links, { client_id: 222, internal_name: "partner", name: null }];
				return {};
			},
		});
		const deps = { client, db: fakeDb().db, user: USER };
		expect((await setProjectOwner(deps, { contact_id: 222, project_id: 603710, role: "contact_person" })).result).toMatchObject({ linked: true, role: "Ansprechpartner" });
		expect(sent).toEqual([{ relationships_attributes: [{ internal_name: "partner", related_client_id: 222 }] }]);
		expect((await setProjectOwner(deps, { contact_id: 111, project_id: 603710 })).result).toMatchObject({ already_linked: true, linked: true });
		expect(sent).toHaveLength(1);
	});

	it("verlangt Propstack eine Bezeichnung, wird einmal mit „Ansprechpartner“ wiederholt", async () => {
		const sent: { relationships_attributes: Record<string, unknown>[] }[] = [];
		const { client } = fakeClient({
			getProject: () => ({ id: 1, name: "P" }),
			updateProject: (_id, p) => {
				const body = p as { relationships_attributes: Record<string, unknown>[] };
				sent.push(body);
				if (!body.relationships_attributes[0].name) throw new Error('Propstack-Anfrage fehlgeschlagen (422): {"relationships.name":["muss ausgefüllt werden"]}');
				if (sent.length > 2) throw new Error('Propstack-Anfrage fehlgeschlagen (400): ["Relationships project ist bereits mit dem Kontakt verbunden"]');
				return {};
			},
		});
		const out = await setProjectOwner({ client, db: fakeDb().db, user: USER }, { contact_id: 222, project_id: 1, role: "contact_person" });
		expect(sent[1].relationships_attributes[0]).toEqual({ internal_name: "partner", name: "Ansprechpartner", related_client_id: 222 });
		expect(out.result).toMatchObject({ linked: "nicht prüfbar" }); // Gegenprobe ohne Bezeichnung scheitert an der Pflichtangabe
	});
});

describe("add_images – Titel", () => {
	const fetchFn = (async () => new Response(null, { headers: { "content-type": "image/jpeg" }, status: 200 })) as unknown as typeof fetch;

	it("gibt Titel an Propstack weiter; Anzahl muss passen", async () => {
		const sent: unknown[] = [];
		const { client } = fakeClient({
			createImage: (i) => {
				sent.push(i);
				return { id: 1 };
			},
			getProject: () => ({ id: 7 }),
		});
		const deps = { client, db: fakeDb().db, fetchFn, user: USER };
		await addImages(deps, { project_id: 7, titles: ["Außenansicht", "Halle innen"], urls: ["https://x.de/a.jpg", "https://x.de/b.jpg"] });
		expect(sent).toEqual([
			{ imageable_id: 7, imageable_type: "Project", remote_photo_url: "https://x.de/a.jpg", title: "Außenansicht" },
			{ imageable_id: 7, imageable_type: "Project", remote_photo_url: "https://x.de/b.jpg", title: "Halle innen" },
		]);
		await expect(addImages(deps, { project_id: 7, titles: ["nur einer"], urls: ["https://x.de/a.jpg", "https://x.de/b.jpg"] })).rejects.toThrow(/genau so viele/);
		// Dateiname statt Titel wird abgewiesen (How-to: Bilder müssen benannt sein)
		await expect(addImages(deps, { project_id: 7, titles: ["IMG_0001"], urls: ["https://x.de/a.jpg"] })).rejects.toThrow(/Dateiname, kein Titel/);
		expect(sent).toHaveLength(2);
	});
});

describe("Schalter „Einheiten auf der Landing-Page“", () => {
	it("create_project meldet es, wenn Propstack den Schalter nicht übernimmt; update_project setzt ihn nachträglich", async () => {
		const stored: Record<string, unknown> = {};
		const { client } = fakeClient({
			createProject: (p) => {
				const { show_units_on_landing_page: _dropped, ...rest } = p as Record<string, unknown>;
				Object.assign(stored, rest);
				return { id: 801 };
			},
			getProject: () => ({ ...stored, broker: { id: 347158 }, id: 801, lat: 51.2, lng: 6.8, show_units_on_landing_page: stored.show_units_on_landing_page ?? null }),
			updateProject: (_id, p) => {
				// Einzel-PUT wird ebenfalls verworfen – nur ein späterer Aufruf (Flag unten) sitzt
				if (stored.accept) Object.assign(stored, p);
				return {};
			},
		});
		const deps = { client, db: fakeDb().db, now: NOW, user: USER };
		const created = await createProject(deps, { city: "Düsseldorf", marketing_type: "RENT", name: "Logistikhalle in (40) Düsseldorf", street: "Kappeler Straße", zip_code: "40597" });
		expect((created.result as { not_applied: string[] }).not_applied).toContain("show_units_on_landing_page");
		stored.accept = true;
		const updated = await updateProject(deps, { id: 801, show_units_on_landing_page: true });
		expect(updated.result).toMatchObject({ changed: ["show_units_on_landing_page"], updated: true });
		expect((updated.result as { not_applied?: string[] }).not_applied).toBeUndefined();
		expect(stored.show_units_on_landing_page).toBe(true);
	});
});
