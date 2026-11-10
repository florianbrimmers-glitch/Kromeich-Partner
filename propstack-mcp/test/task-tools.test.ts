import { describe, expect, it } from "vitest";
import { PropstackError, type PropstackClient } from "../src/propstack-client";
import { checkTask, createTask, taskBodyHtml, withBerlinOffset } from "../src/tools/task-tools";

const USER = { brokerId: 347158, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers" };
const NOW = () => new Date("2026-11-10T10:00:00Z"); // Dienstag
const BROKERS = [
	{ connected: true, id: 347158, name: "Florian Brimmers" },
	{ connected: true, id: 254958, name: "Lena Klinnert" },
	{ connected: false, id: 254960, name: "Propstack Admin" },
];

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

/** Client-Attrappe: merkt sich die gesendete Aufgabe und liefert sie beim Gegenlesen so zurück, wie Propstack es tut. */
function fakeClient(impl: Record<string, (...args: unknown[]) => unknown> = {}) {
	const calls: { method: string; args: unknown[] }[] = [];
	let sent: Record<string, unknown> = {};
	const defaults: Record<string, (...args: unknown[]) => unknown> = {
		createTask: (task) => {
			sent = task as Record<string, unknown>;
			return { activity_id: 9001, id: 501 };
		},
		getContact: (id) => ({ id, name: "Mileway Germany GmbH" }),
		getProject: (id) => ({ id, name: `Projekt ${id}` }),
		getTask: () => ({
			body: sent.body,
			broker_id: sent.broker_id,
			clients: ((sent.client_ids as number[] | undefined) ?? []).map((id) => ({ id })),
			due_date: "2026-11-11T09:00:00.000+01:00",
			id: 501,
			is_reminder: true,
			projects: ((sent.project_ids as number[] | undefined) ?? []).map((id) => ({ id })),
			title: sent.title,
			units: ((sent.property_ids as number[] | undefined) ?? []).map((id) => ({ id })),
		}),
		getUnit: (id) => ({ id, name: { label: "Name", value: `Objekt ${id}` } }),
		listBrokers: () => BROKERS,
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
	return { calls, client, sent: () => sent };
}

const BODY = "Worum geht es?\nDrei alte Datensätze liegen neben den neuen Projekten.\n\nMöglichkeiten:\n- archivieren\n- behalten & ergänzen";

describe("create_task – Hilfen", () => {
	it("Klartext wird schlichtes HTML: Absätze, Zeilenumbrüche, Sonderzeichen maskiert", () => {
		expect(taskBodyHtml(BODY)).toBe(
			"<p>Worum geht es?<br>Drei alte Datensätze liegen neben den neuen Projekten.</p><p>Möglichkeiten:<br>- archivieren<br>- behalten &amp; ergänzen</p>",
		);
		expect(taskBodyHtml("a\r\n\r\n\r\n  b  \n\n")).toBe("<p>a</p><p>b</p>");
		expect(taskBodyHtml("5 < 6 > 4")).toBe("<p>5 &lt; 6 &gt; 4</p>");
	});

	it("Fälligkeit bekommt den deutschen Zeitzonen-Versatz (Winter +01:00, Sommer +02:00)", () => {
		expect(withBerlinOffset("2026-11-11T09:00:00")).toBe("2026-11-11T09:00:00+01:00");
		expect(withBerlinOffset("2026-07-01T09:00:00")).toBe("2026-07-01T09:00:00+02:00");
	});

	it("Gegenlesen erkennt Abweichungen und unlesbare Antworten", () => {
		const sent = { body: "<p>Text</p>", broker_id: 254958, due_date: "2026-11-11T09:00:00+01:00", project_ids: [613128], property_ids: [2777862, 2778565], title: "Entscheidung" };
		// alles da – auch wenn Propstack die Zeit in UTC oder ohne Zeitzone liefert und IDs statt Datensätzen
		expect(checkTask({ body: "<p>Text</p>", broker_id: 254958, due_date: "2026-11-11T08:00:00Z", project_ids: [613128], property_ids: [2778565, 2777862], title: "Entscheidung" }, sent)).toEqual({ not_applied: [], not_verifiable: [] });
		expect(checkTask({ body: "<div>Text</div>", broker: { id: 254958 }, due_date: "2026-11-11T09:00:00", projects: [{ id: 613128 }], title: "Entscheidung", units: [{ id: 2777862 }, { id: 2778565 }] }, sent)).toEqual({ not_applied: [], not_verifiable: [] });
		// Abweichungen
		const off = checkTask({ body: "<p>Te</p>", broker_id: 347158, due_date: "2026-11-11T10:00:00+01:00", is_reminder: false, projects: [], title: "Entscheidung", units: [{ id: 2777862 }] }, sent);
		expect(off.not_applied).toEqual([
			"Empfänger",
			"Fälligkeit (gespeichert: 2026-11-11T10:00:00+01:00)",
			"Art „Aufgabe“ (als Notiz gespeichert)",
			"Text (von Propstack verändert gespeichert)",
			"Objekt 2778565 nicht verknüpft",
			"Projekt 613128 nicht verknüpft",
		]);
		// nichts Erkennbares in der Antwort
		expect(checkTask({ id: 1 }, sent)).toEqual({ not_applied: [], not_verifiable: ["Titel", "Empfänger", "Fälligkeit", "Text", "Verknüpfung Objekte", "Verknüpfung Projekte"] });
	});
});

describe("create_task", () => {
	it("legt die Aufgabe an: Empfänger, Fälligkeit, Verknüpfungen – und liest gegen", async () => {
		const { calls, client, sent } = fakeClient();
		const { db, rows, updates } = fakeDb();
		const out = await createTask(
			{ client, db, now: NOW, user: USER },
			{ assignee_id: 254958, body: BODY, contact_ids: [17475856], due_date: "2026-11-11", object_ids: [2777862, 2778565, 2777862], project_ids: [613128], title: "Entscheidung: alte Mileway-Datensätze" },
		);
		expect(sent()).toEqual({
			body: taskBodyHtml(BODY),
			broker_id: 254958,
			client_ids: [17475856],
			due_date: "2026-11-11T09:00:00+01:00",
			is_reminder: true,
			project_ids: [613128],
			property_ids: [2777862, 2778565], // doppelte ID nur einmal
			title: "Entscheidung: alte Mileway-Datensätze",
		});
		expect(out.result).toEqual({
			assigned_to: "Lena Klinnert",
			created: true,
			due: "2026-11-11 09:00",
			hint: "Aufgaben kann der Connector weder ändern noch löschen – Korrekturen direkt in Propstack.",
			id: 501,
			linked: {
				contacts: [{ id: 17475856, name: "Mileway Germany GmbH" }],
				objects: [
					{ id: 2777862, name: "Objekt 2777862" },
					{ id: 2778565, name: "Objekt 2778565" },
				],
				projects: [{ id: 613128, name: "Projekt 613128" }],
			},
			title: "Entscheidung: alte Mileway-Datensätze",
		});
		// erst prüfen, dann schreiben, dann gegenlesen
		expect(calls.map((c) => c.method)).toEqual(["listBrokers", "getUnit", "getUnit", "getProject", "getContact", "createTask", "getTask"]);
		// Write-Log: Eintrag vor dem Schreiben, Abschluss mit Aufgaben-ID
		expect(rows).toHaveLength(1);
		expect(rows[0]).toEqual(expect.arrayContaining(["create_task", "task", "create"]));
		expect(updates[0]).toEqual(expect.arrayContaining(["done", 501]));
	});

	it("ohne Angaben: an den Nutzer selbst, fällig am nächsten Werktag 9:00", async () => {
		const { client, sent } = fakeClient({ getTask: () => ({ body: "<p>Rückruf</p>", broker_id: 347158, due_date: "2026-10-19T09:00:00+02:00", title: "Kunde zurückrufen" }) });
		const out = await createTask({ client, db: fakeDb().db, now: () => new Date("2026-10-16T10:00:00Z"), user: USER }, { body: "Rückruf", title: "Kunde zurückrufen" });
		expect(sent()).toEqual({ body: "<p>Rückruf</p>", broker_id: 347158, due_date: "2026-10-19T09:00:00+02:00", is_reminder: true, title: "Kunde zurückrufen" }); // Fr → Mo, Sommerzeit
		expect(out.result).toMatchObject({ assigned_to: "Florian Brimmers", due: "2026-10-19 09:00", id: 501 });
		expect(out.result).not.toHaveProperty("linked");
		expect(out.result).not.toHaveProperty("not_applied");
	});

	it("Testaufgabe: Kennzeichnung im Titel, geht an den Nutzer selbst statt an den Empfänger", async () => {
		const { client, sent } = fakeClient();
		const out = await createTask({ client, db: fakeDb().db, now: NOW, user: USER }, { assignee_id: 254958, body: "Test", test: true, title: "Probe der Aufgabe" });
		expect(sent()).toMatchObject({ broker_id: 347158, title: "[MCP-TEST] Probe der Aufgabe" });
		expect(out.result).toMatchObject({ assigned_to: "Florian Brimmers", title: "[MCP-TEST] Probe der Aufgabe" });
	});

	it("weist vor dem Schreiben ab: unbekannter oder inaktiver Empfänger, Datum, HTML, fehlende Datensätze", async () => {
		const run = async (input: Record<string, unknown>, impl: Record<string, (...args: unknown[]) => unknown> = {}) => {
			const { calls, client } = fakeClient(impl);
			const { db, rows } = fakeDb();
			const error = await createTask({ client, db, now: NOW, user: USER }, { body: "Text", title: "Titel der Aufgabe", ...input } as never).catch((e) => e);
			expect(error).toBeInstanceOf(PropstackError);
			// nichts geschrieben, kein Write-Log-Eintrag
			expect(calls.some((c) => c.method === "createTask")).toBe(false);
			expect(rows).toHaveLength(0);
			return (error as Error).message;
		};
		expect(await run({ assignee_id: 999 })).toMatch(/Den Nutzer 999 gibt es in Propstack nicht/);
		expect(await run({ assignee_id: 254960 })).toMatch(/Propstack Admin hat keinen aktiven Propstack-Zugang/);
		expect(await run({ due_date: "2026-11-09" })).toMatch(/liegt in der Vergangenheit/);
		expect(await run({ due_date: "2026-02-30" })).toMatch(/kein gültiges Datum/);
		expect(await run({ body: "Bitte <b>prüfen</b>" })).toMatch(/enthält HTML/);
		const notFound = () => {
			throw new PropstackError("Nicht gefunden (404)", 404);
		};
		expect(await run({ object_ids: [1, 2], project_ids: [3] }, { getProject: notFound, getUnit: (id) => (id === 2 ? notFound() : { id, name: "A" }) })).toBe(
			"Nicht gefunden: Objekt 2, Projekt 3. Es wurde keine Aufgabe angelegt.",
		);
		// andere Fehler beim Prüfen (z. B. Propstack nicht erreichbar) brechen ebenfalls ab
		expect(
			await run({ object_ids: [1] }, {
				getUnit: () => {
					throw new PropstackError("Propstack-Serverfehler (502)", 502);
				},
			}),
		).toMatch(/502/);
	});

	it("heute fällig ist erlaubt (deutsches Datum, nicht UTC)", async () => {
		const { client, sent } = fakeClient();
		// 23:30 UTC am 10.11. ist in Deutschland schon der 11.11.
		await createTask({ client, db: fakeDb().db, now: () => new Date("2026-11-10T23:30:00Z"), user: USER }, { body: "Text", due_date: "2026-11-11", title: "Titel der Aufgabe" });
		expect(sent().due_date).toBe("2026-11-11T09:00:00+01:00");
		const error = await createTask({ client, db: fakeDb().db, now: () => new Date("2026-11-10T23:30:00Z"), user: USER }, { body: "Text", due_date: "2026-11-10", title: "Titel der Aufgabe" }).catch((e) => e);
		expect((error as Error).message).toMatch(/Vergangenheit/);
	});

	it("ohne Write-Log wird nichts angelegt", async () => {
		const { calls, client } = fakeClient();
		const error = await createTask({ client, db: undefined, now: NOW, user: USER }, { body: "Text", title: "Titel der Aufgabe" }).catch((e) => e);
		expect((error as Error).message).toMatch(/Write-Log nicht verfügbar/);
		expect(calls.some((c) => c.method === "createTask")).toBe(false);
	});

	it("Fehler von Propstack beim Anlegen: wird protokolliert und gemeldet", async () => {
		const { client } = fakeClient({
			createTask: () => {
				throw new PropstackError('Propstack-Anfrage fehlgeschlagen (422): {"title":["muss ausgefüllt werden"]}', 422);
			},
		});
		const { db, updates } = fakeDb();
		const error = await createTask({ client, db, now: NOW, user: USER }, { body: "Text", title: "Titel der Aufgabe" }).catch((e) => e);
		expect((error as Error).message).toMatch(/422/);
		expect(updates[0]).toEqual(expect.arrayContaining(["failed"]));
	});

	it("Gegenlesen: Abweichungen und Unprüfbares werden gemeldet, mit Feldnamen statt Werten", async () => {
		// Propstack hat den Empfänger nicht übernommen und liefert die Verknüpfungen in unbekannter Form
		const first = fakeClient({ getTask: () => ({ body: "<p>Text</p>", broker_id: 347158, due_date: "2026-11-11T09:00:00+01:00", geheim: "Wert", title: "Titel der Aufgabe" }) });
		const db1 = fakeDb();
		const out = await createTask({ client: first.client, db: db1.db, now: NOW, user: USER }, { assignee_id: 254958, body: "Text", due_date: "2026-11-11", object_ids: [5], title: "Titel der Aufgabe" });
		expect(out.result).toMatchObject({
			id: 501,
			not_applied: ["Empfänger"],
			not_verifiable: ["Verknüpfung Objekte"],
			readback_fields: ["body", "broker_id", "due_date", "geheim", "title"],
		});
		expect(JSON.stringify(out.result)).not.toContain("Wert");
		expect(db1.updates[0]).toEqual(expect.arrayContaining(["done_with_gaps"]));

		// Gegenlesen scheitert (z. B. fehlendes Leserecht): Aufgabe ist angelegt, aber nicht geprüft
		const second = fakeClient({
			getTask: () => {
				throw new PropstackError("Propstack hat den Zugriff verweigert (403). Fehlt dem API-Key das Leserecht für diesen Bereich?", 403);
			},
		});
		const unread = await createTask({ client: second.client, db: fakeDb().db, now: NOW, user: USER }, { body: "Text", title: "Titel der Aufgabe" });
		expect(unread.result).toMatchObject({ created: true, id: 501 });
		expect((unread.result as { not_verifiable: string[] }).not_verifiable[0]).toMatch(/^Gegenlesen nicht möglich \(Propstack hat den Zugriff verweigert \(403\)/);

		// keine ID in der Antwort
		const third = fakeClient({ createTask: () => ({}) });
		const noId = await createTask({ client: third.client, db: fakeDb().db, now: NOW, user: USER }, { body: "Text", title: "Titel der Aufgabe" });
		expect((noId.result as { not_verifiable: string[] }).not_verifiable[0]).toMatch(/keine Aufgaben-ID/);
		expect(third.calls.some((c) => c.method === "getTask")).toBe(false);
	});
});
