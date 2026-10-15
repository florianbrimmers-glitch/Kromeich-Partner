import { describe, expect, it } from "vitest";
import type { Page, PropstackClient } from "../src/propstack-client";
import { createReviewTask, nextWorkdayNine, toAscii } from "../src/review-task";
import { addImages, checkImageUrl, createProject, setProjectOwner } from "../src/tools/project-tools";

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
		listRelationships: () => page([]),
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
	it("ASCII und nächster Werktag 9:00", () => {
		expect(toAscii("Prüfung: Halle in (51) Köln – 5.000 m² für 5,50 €")).toBe("Pruefung: Halle in (51) Koeln - 5.000 m2 fuer 5,50 EUR");
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
		expect(sent).toMatchObject({ broker_id: 254958, is_reminder: true, property_ids: [1], title: "Pruefung: Halle" });
		expect(sent.body).toBe("<p>Objekt &lt;b&gt;1&lt;/b&gt;: Halle</p>");
		await createReviewTask(client, fakeDb().db, { lines: [], now: NOW(), test: true, title: "Halle", user: USER });
		expect(sent).toMatchObject({ broker_id: 347158, title: "[MCP-TEST] Pruefung: Halle" });
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
			getProject: () => ({ ...stored, broker: stored.broker_id ? { id: stored.broker_id } : null, id: 600 }),
			listRelationships: () => page([{ client_id: 17366550, id: 1, internal_name: "owner", project_id: 600 }]),
			updateProject: (_id, p) => {
				puts.push(p as Record<string, unknown>);
				if (!("relationships_attributes" in (p as object))) Object.assign(stored, p);
				return {};
			},
		});
		const out = await createProject(
			{ client, db: fakeDb().db, now: NOW, user: USER },
			{ ...input, courtage: "Provisionsfrei", owner_contact_id: 17366550, review_notes: ["Energieausweis fehlt"], test: true },
		);
		expect(stored).toMatchObject({ country: "DEU", for_rent: true, name: "MCP-TEST Logistikhalle in (40) Düsseldorf – Kappeler Straße" });
		expect(stored).not.toHaveProperty("note");
		expect(puts).toEqual([
			{ broker_id: 347158 },
			{ relationships_attributes: [{ internal_name: "owner", related_client_id: 17366550 }] },
		]);
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

	it("findet neue Verknüpfung auf der letzten Seite der Relationship-Liste", async () => {
		const pages: unknown[] = [];
		const { client } = fakeClient({
			getProject: () => ({ id: 1, name: "P" }),
			listRelationships: (q) => {
				const p = (q as { page: number }).page;
				pages.push(p);
				const rows = Array.from({ length: p === 12 ? 30 : 100 }, (_, i) => ({ client_id: 9, id: i, project_id: 9 }));
				if (p === 12) rows.push({ client_id: 2, id: 999, project_id: 1 });
				return { rows, total: 1131 };
			},
			updateProject: () => ({}),
		});
		const out = await setProjectOwner({ client, db: fakeDb().db, user: USER }, { contact_id: 2, project_id: 1 });
		expect(out.result).toMatchObject({ linked: true });
		expect(pages).toEqual([1, 12]);
	});

	it("bereits verknüpft zählt als erfolgreich", async () => {
		const { client } = fakeClient({
			getProject: () => ({ id: 1, name: "P" }),
			listRelationships: () => page([{ client_id: 2, project_id: 1 }]),
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
			{ object_id: 5, urls: ["https://x.de/ok1.jpg", "https://x.de/page.html", "https://x.de/weg.jpg", "https://x.de/ok2.jpg"] },
		);
		expect(sent).toEqual([
			{ imageable_id: 5, imageable_type: "Property", remote_photo_url: "https://x.de/ok1.jpg" },
			{ imageable_id: 5, imageable_type: "Property", remote_photo_url: "https://x.de/ok2.jpg" },
		]);
		expect(out.result).toMatchObject({ image_ids: [901, 902], rejected: [{ reason: expect.stringMatching(/kein Bild/) }, { reason: expect.stringMatching(/404/) }], uploaded: 2 });
	});

	it("genau ein Ziel", async () => {
		const { client } = fakeClient({});
		await expect(addImages({ client, db: fakeDb().db, fetchFn, user: USER }, { urls: ["https://x.de/ok.jpg"] })).rejects.toThrow(/Genau eins/);
	});

	it("checkImageUrl schickt User-Agent und fällt bei 405 auf GET zurück", async () => {
		const methods: string[] = [];
		const f = (async (_u: string, init: RequestInit) => {
			methods.push(String(init.method));
			expect((init.headers as Record<string, string>)["User-Agent"]).toMatch(/KromeichPropstackMCP/);
			return init.method === "HEAD" ? new Response(null, { status: 405 }) : new Response(null, { headers: { "content-type": "image/png" }, status: 206 });
		}) as unknown as typeof fetch;
		expect(await checkImageUrl("https://x.de/a.png", f)).toBeNull();
		expect(methods).toEqual(["HEAD", "GET"]);
	});
});
