import { beforeEach, describe, expect, it, vi } from "vitest";

// Kein Netz in Tests: Geokodierung (OpenStreetMap) findet nichts
beforeEach(() => {
	vi.stubGlobal("fetch", async () => new Response("[]", { status: 200 }));
});
import {
	contactDuplicates,
	isGenericEmail,
	isMobile,
	isSystemEmail,
	normalizePhone,
	normalizeStreet,
	objectDuplicates,
} from "../src/propstack/dedupe";
import type { Page, PropstackClient, Query } from "../src/propstack-client";
import { createContact, createObject, notApplied, updateContact, updateObject, validateCustomFields } from "../src/tools/write-tools";

const page = (rows: Record<string, unknown>[]): Page => ({ rows, total: rows.length });
const USER = { brokerId: 347158, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers" };
const NOW = () => new Date("2026-10-14T10:00:00Z");

// ---------- Normalisierung ----------

describe("Normalisierung", () => {
	it("Telefon: deutsche Formate → 49…, Mobil erkennen", () => {
		expect(normalizePhone("0163 3000-969")).toBe("491633000969");
		expect(normalizePhone("+49 (163) 3000 969")).toBe("491633000969");
		expect(normalizePhone("0049 2436 8029997")).toBe("4924368029997");
		expect(isMobile("+49 163 3000 969")).toBe(true);
		expect(isMobile("02436 802 9997")).toBe(false);
	});

	it("generische und Systemadressen", () => {
		expect(isGenericEmail("Info@firma.de")).toBe(true);
		expect(isGenericEmail("vertrieb@firma.de")).toBe(true);
		expect(isGenericEmail("anna.muster@firma.de")).toBe(false);
		expect(isSystemEmail("comments-noreply@docs.google.com")).toBe(true);
		expect(isSystemEmail("no-reply@x.de")).toBe(true);
		expect(isSystemEmail("norbert@x.de")).toBe(false);
	});

	it("Straßen: Straße/Str./strasse gleich", () => {
		expect(normalizeStreet("Schlebuscher Straße")).toBe(normalizeStreet("Schlebuscher Str."));
		expect(normalizeStreet("Hauptstraße")).toBe(normalizeStreet("Hauptstr"));
		expect(normalizeStreet("Hauptstraße")).not.toBe(normalizeStreet("Hauptweg"));
	});
});

// ---------- Dublettenregeln ----------

describe("Kontakt-Dubletten", () => {
	const none = { byEmail: [], byMobile: [], byName: [], byPhone: [] };
	const anna = { company: "GB Logistics GmbH", email: "anna@gb.de", id: 1, name: "Anna Muster" };

	it("gleiche persönliche E-Mail blockiert", () => {
		const r = contactDuplicates({ email: "ANNA@gb.de", last_name: "Muster" }, { ...none, byEmail: [anna] });
		expect(r.duplicates).toEqual([{ id: 1, name: "Anna Muster", reason: "gleiche E-Mail anna@gb.de" }]);
	});

	it("E-Mail-Filter wird nicht blind vertraut (falsche Treffer zählen nicht)", () => {
		const r = contactDuplicates({ email: "neu@gb.de" }, { ...none, byEmail: [anna] });
		expect(r.duplicates).toEqual([]);
	});

	it("info@ blockiert nicht, warnt aber", () => {
		const r = contactDuplicates({ email: "info@gb.de", last_name: "Neu" }, { ...none, byEmail: [{ email: "info@gb.de", id: 2, name: "Zentrale" }] });
		expect(r.duplicates).toEqual([]);
		expect(r.warnings.join(" ")).toMatch(/allgemeine Firmenadresse.*Zentrale/s);
	});

	it("noreply-Absender werden als Systemadresse gemeldet", () => {
		expect(contactDuplicates({ email: "comments-noreply@docs.google.com" }, none).warnings[0]).toMatch(/Systemadresse/);
	});

	it("ohne E-Mail: Mobil blockiert, Festnetz warnt (Entscheidung Florian)", () => {
		const r = contactDuplicates(
			{ last_name: "Neu", mobile: "0163 3000969", phone: "02436 8020" },
			{ ...none, byMobile: [{ id: 3, name: "Konstantin Brockmann" }], byPhone: [{ id: 4, name: "Zentrale GB" }] },
		);
		expect(r.duplicates.map((d) => d.id)).toEqual([3]);
		expect(r.warnings.join(" ")).toMatch(/Festnetznummer.*Zentrale GB/);
	});

	it("mit persönlicher E-Mail blockiert Mobil nicht, sondern warnt", () => {
		const r = contactDuplicates({ email: "k.neu@gb.de", mobile: "0163 3000969" }, { ...none, byMobile: [{ id: 3, name: "K" }] });
		expect(r.duplicates).toEqual([]);
		expect(r.warnings[0]).toMatch(/Mobilnummer/);
	});

	it("Name + Firma (Rechtsform egal) blockiert, Name ohne Firma warnt", () => {
		const byName = [anna, { id: 9, name: "Anna Muster" }];
		const r = contactDuplicates({ company: "GB Logistics", first_name: "Anna", last_name: "Muster" }, { ...none, byName });
		expect(r.duplicates.map((d) => d.id)).toEqual([1]);
		expect(r.warnings.join(" ")).toMatch(/Gleicher Name wie Anna Muster \(9\)/);
	});

	it("eigener Datensatz zählt beim Update nicht", () => {
		expect(contactDuplicates({ email: "anna@gb.de" }, { ...none, byEmail: [anna] }, 1).duplicates).toEqual([]);
	});
});

describe("Objekt-Dubletten", () => {
	const existing = [
		{ house_number: "99", id: 10, marketing_type: "RENT", street: "Schlebuscher Straße", title: "SCHLE99", unit_id: "Unit 1", zip_code: "51381" },
		{ house_number: "99", id: 11, marketing_type: "RENT", street: "Schlebuscher Straße", title: "SCHLE99", unit_id: "Unit 2", zip_code: "51381" },
	];

	it("gleiche Adresse + Vermarktungsart + Einheit blockiert (Schreibweise egal)", () => {
		const r = objectDuplicates({ house_number: "99", marketing_type: "RENT", street: "Schlebuscher Str.", unit_id: "unit 1", zip_code: "51381" }, existing);
		expect(r.duplicates.map((d) => d.id)).toEqual([10]);
		expect(r.warnings[0]).toMatch(/Weitere Einheit.*11/);
	});

	it("Einheit im Projekt: Geschwister-Einheiten werden nicht gemeldet, fremde Objekte an der Adresse gebündelt", () => {
		const rows = [
			...existing.map((row) => ({ ...row, project_id: 7 })),
			...[21, 22, 23, 24, 25].map((id) => ({ ...existing[0], id, project_id: { label: "Projekt", value: 8 }, unit_id: `Fremd ${id}` })),
		];
		const candidate = { house_number: "99", marketing_type: "RENT", project_id: 7, street: "Schlebuscher Straße", unit_id: "Unit 3", zip_code: "51381" };
		const r = objectDuplicates(candidate, rows);
		expect(r.duplicates).toEqual([]);
		expect(r.warnings).toHaveLength(4);
		expect(r.warnings[0]).toMatch(/Weitere Einheit an derselben Adresse: .*\(21, Fremd 21, RENT\)/);
		expect(r.warnings[3]).toBe("… und 2 weitere Objekte an derselben Adresse.");
		// gleiche Einheit im selben Projekt blockiert weiterhin
		expect(objectDuplicates({ ...candidate, unit_id: "Unit 1" }, rows).duplicates.map((d) => d.id)).toEqual([10]);
	});

	it("andere Vermarktungsart ist nur ein Hinweis", () => {
		const r = objectDuplicates({ house_number: "99", marketing_type: "BUY", street: "Schlebuscher Straße", unit_id: "Unit 1", zip_code: "51381" }, existing);
		expect(r.duplicates).toEqual([]);
		expect(r.warnings.join(" ")).toMatch(/anderer Vermarktungsart/);
	});

	it("Geokoordinaten innerhalb 30 m zählen als gleiche Adresse", () => {
		const geo = [{ ...existing[0], house_number: "99a", lat: 51.0490515, lng: 7.0171615 }];
		const r = objectDuplicates(
			{ house_number: "101", lat: 51.04906, lng: 7.01718, marketing_type: "RENT", street: "Schlebuscher Straße", unit_id: "Unit 1", zip_code: "51381" },
			geo,
		);
		expect(r.duplicates).toHaveLength(1);
	});
});

// ---------- Tools mit simuliertem Propstack und D1 ----------

interface Call {
	method: string;
	args: unknown[];
}

function fakeDb(fail = false) {
	const rows: unknown[][] = [];
	const updates: unknown[][] = [];
	const db = {
		prepare: (sql: string) => ({
			bind: (...args: unknown[]) => ({
				run: async () => {
					if (fail) throw new Error("D1 down");
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
	const calls: Call[] = [];
	const defaults: Record<string, (...args: unknown[]) => unknown> = {
		createGroup: () => ({}),
		createTask: () => ({ id: 4711 }),
		getProject: () => ({ furnishing_note: "- 10 Rampen\n- LED", id: 603710, location_note: "Direkt an der A48." }),
		listCustomFieldGroups: () =>
			page([
				{
					custom_fields: [
						{ field_type: "Number", name: "hallenhohe" },
						{ field_type: "Number", name: "lagerflache", unit: "sqm" },
						{ field_type: "Number", name: "mezzanineflache", unit: "euro" },
						{ field_type: "String", name: "provisionspflichtig" },
						{ field_type: "Number", name: "lagerflache_gesamt", unit: "sqm" },
						{ field_type: "String", name: "lagerflache_verfugbar" },
						{ field_type: "Number", name: "buroflache", unit: "sqm" },
						{ field_type: "Number", name: "gebaudeflache_gesamt", unit: "sqm" },
						{ field_type: "Number", name: "gebaudeflache_verfugbar", unit: "sqm" },
						{ field_type: "String", name: "preisangabe" },
						{ field_type: "String", name: "status_logistik" },
						{ field_type: "Boolean", name: "kein_automatischer_exposeversand" },
						{ field_type: "String", name: "beleuchtung_halle" },
						{ field_type: "String", name: "beleuchtung" },
						{ field_type: "Number", name: "mietpreis_hallenflache" },
						{ field_type: "Number", name: "intern_mietpreis_hallenflache" },
						{ field_type: "String", name: "bemerkung" },
						// Felder aus dem Team-How-to (Typen wie live, 09.11.2026)
						{ field_type: "Number", name: "lagerflache_teilbar_ab", unit: "sqm" },
						{ field_type: "Number", name: "buroflache_teilbar_ab", unit: "sqm" },
						{ field_type: "Number", name: "mezzanineflache_gesamt", unit: "sqm" },
						{ field_type: "Number", name: "mezzanineflache_verfugbar", unit: "sqm" },
						{ field_type: "Number", name: "mezzanineflache_teilbar_ab", unit: "sqm" },
						{ field_type: "Number", name: "stellplatze_verfugbar" },
						{ field_type: "Number", name: "lkw_stellplatze_gesamt" },
						{ field_type: "String", name: "ramepntore" },
						{ field_type: "Number", name: "anzahl_rampentore_2" },
						{ field_type: "String", name: "wgk" },
						{ field_type: "String", name: "sprinkleranlage" },
						{ field_type: "String", name: "heizungsart_halle" },
						{ field_type: "String", name: "zertifizierung" },
						{ field_type: "Number", name: "intern_mietpreis_buro", unit: "euro" },
						{ field_type: "Number", name: "intern_mietpreis_mezzanine", unit: "euro" },
						{ custom_options: [{ id: 1, name: "Ja" }, { id: 2, name: "Nein" }], field_type: "Dropdown", name: "spekulative_entwicklung" },
						{ custom_options: [{ id: 7, name: "Aktiv" }, { id: 8, name: "Inaktiv" }], field_type: "Multiselect", name: "aktiv" },
					],
				},
			]),
		listGroups: () => page([{ id: 999, name: "MCP-TEST" }]),
		searchContacts: () => page([]),
		searchUnits: () => page([]),
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

describe("create_contact", () => {
	it("legt an: Betreuer = Nutzer, Herkunftsnotiz, Test-Merkmal, Snapshot vor dem Write, Gegenlesen", async () => {
		const { db, rows, updates } = fakeDb();
		let sent: Record<string, unknown> = {};
		const { client, calls } = fakeClient({
			createContact: (payload) => {
				sent = payload as Record<string, unknown>;
				return { id: 500, ok: true };
			},
			getContact: () => ({ ...sent, groups: [{ id: 999, name: "MCP-TEST" }], id: 500, name: "Anna Test" }),
		});
		const out = await createContact(
			{ client, db, now: NOW, user: USER },
			{ email: "anna.test@example.com", first_name: "Anna", last_name: "Test", mobile: "0171 1234567", test: true },
		);
		expect(out.result).toMatchObject({ broker: "Florian Brimmers", created: true, id: 500, test: true });
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
		expect(sent).toMatchObject({ broker_id: 347158, email: "anna.test@example.com", group_ids: [999], office_cell: "0171 1234567" });
		expect(sent.description).toMatch(/Angelegt über Claude \(Propstack MCP\) von Florian Brimmers am 2026-10-14/);
		// Reihenfolge: Write-Log vor createContact
		expect(rows).toHaveLength(1);
		expect(calls.findIndex((c) => c.method === "createContact")).toBeGreaterThan(-1);
		expect(updates[0]?.[0]).toBe("done");
	});

	it("meldet Felder, die Propstack still verworfen hat", async () => {
		const { db, updates } = fakeDb();
		const { client } = fakeClient({
			createContact: () => ({ id: 501 }),
			getContact: () => ({ broker_id: 347158, id: 501, last_name: "Test", name: "Test" }),
		});
		const out = await createContact({ client, db, now: NOW, user: USER }, { last_name: "Test", position: "CEO" });
		expect(out.result).toMatchObject({ not_applied: ["position"] });
		expect(updates[0]?.[0]).toBe("done_with_gaps");
	});

	it("Dublette per E-Mail: nichts angelegt, auch nicht mit Override (Propstack-Upsert)", async () => {
		const { db, rows } = fakeDb();
		const { client, calls } = fakeClient({
			searchContacts: (q) => ((q as Query).email ? page([{ email: "anna@gb.de", id: 1, name: "Anna" }]) : page([])),
		});
		const out = await createContact(
			{ client, db, now: NOW, user: USER },
			{ allow_duplicate_reason: "Andere Person, gleiche Mail weil Sekretariat", email: "anna@gb.de", last_name: "X" },
		);
		expect(out.result).toMatchObject({ blocked: "Dublette", created: false });
		expect((out.result as { hint: string }).hint).toMatch(/über die E-Mail zusammen/);
		expect(calls.some((c) => c.method === "createContact")).toBe(false);
		expect(rows).toHaveLength(0);
	});

	it("Dublette per Mobilnummer: Override nur mit echter Begründung, wird protokolliert", async () => {
		const { db, rows } = fakeDb();
		const impl = {
			createContact: () => ({ id: 502 }),
			getContact: () => ({ broker_id: 347158, id: 502, last_name: "Neu", name: "Neu", office_cell: "0171 1234567" }),
			searchContacts: (q: unknown) => ((q as Query).phone_number ? page([{ id: 3, name: "Alt" }]) : page([])),
		};
		const blocked = await createContact({ client: fakeClient(impl).client, db, now: NOW, user: USER }, { last_name: "Neu", mobile: "0171 1234567" });
		expect(blocked.result).toMatchObject({ blocked: "Dublette" });

		await expect(
			createContact({ client: fakeClient(impl).client, db, now: NOW, user: USER }, { allow_duplicate_reason: "passt", last_name: "Neu", mobile: "0171 1234567" }),
		).rejects.toThrow(/echte Begründung/);

		const ok = await createContact(
			{ client: fakeClient(impl).client, db, now: NOW, user: USER },
			{ allow_duplicate_reason: "Vater und Sohn teilen sich das Firmenhandy", last_name: "Neu", mobile: "0171 1234567" },
		);
		expect(ok.result).toMatchObject({ created: true, override_reason: "Vater und Sohn teilen sich das Firmenhandy" });
		expect(rows[0][10]).toBe("Vater und Sohn teilen sich das Firmenhandy");
	});

	it("Unterkontakt-Dublette (Propstack blockt, Suche findet sie nicht) → klare Blockade statt Fehler", async () => {
		const { client } = fakeClient({
			createContact: () => {
				throw new Error('Propstack-Anfrage fehlgeschlagen (400): ["tj@pprheinland.de ist bereits als Unterkontakt bei Kontakt Christian Weber hinterlegt"]');
			},
		});
		const out = await createContact({ client, db: fakeDb().db, now: NOW, user: USER }, { email: "tj@pprheinland.de", last_name: "Jung" });
		expect(out.result).toMatchObject({ blocked: "Dublette", created: false, duplicates: [{ name: "Christian Weber" }] });
	});

	it("Festnetz-Mobilnummer wird abgewiesen", async () => {
		const { client } = fakeClient({});
		await expect(createContact({ client, db: fakeDb().db, now: NOW, user: USER }, { last_name: "X", mobile: "02436 8020" })).rejects.toThrow(
			/keine deutsche Mobilnummer/,
		);
	});

	it("fail-closed: ohne Write-Log wird nicht nach Propstack geschrieben", async () => {
		const { client, calls } = fakeClient({ createContact: () => ({ id: 1 }) });
		await expect(createContact({ client, db: fakeDb(true).db, now: NOW, user: USER }, { last_name: "X" })).rejects.toThrow(/Write-Log/);
		expect(calls.some((c) => c.method === "createContact")).toBe(false);
	});

	it("Fehler beim Write wird im Write-Log als failed vermerkt", async () => {
		const { db, updates } = fakeDb();
		const { client } = fakeClient({
			createContact: () => {
				throw new Error("Propstack-Serverfehler (500)");
			},
		});
		await expect(createContact({ client, db, now: NOW, user: USER }, { last_name: "X" })).rejects.toThrow(/500/);
		expect(updates[0]?.[0]).toBe("failed");
	});
});

describe("update_contact", () => {
	const current = {
		description: "Alte Notiz",
		email: "anna@gb.de",
		groups: [{ id: 5, name: "Investor" }],
		id: 7,
		name: "Anna Muster",
		position: "CEO",
	};

	it("schreibt nur Änderungen, hängt Notiz an, sichert vorherigen Stand", async () => {
		const { db, rows } = fakeDb();
		let sent: Record<string, unknown> = {};
		const { client } = fakeClient({
			getContact: () => (Object.keys(sent).length ? { ...current, ...sent, groups: [{ id: 5 }, { id: 6 }] } : current),
			updateContact: (_id, payload) => {
				sent = payload as Record<string, unknown>;
				return {};
			},
		});
		const out = await updateContact(
			{ client, db, now: NOW, user: USER },
			{ add_tag_ids: [6, 5], id: 7, note_append: "Rückruf vereinbart", position: "CEO" },
		);
		expect(sent).toEqual({
			add_group_ids: [6],
			description: expect.stringMatching(/^Alte Notiz\n\nErgänzt über Claude .* Florian Brimmers am 2026-10-14\.\nRückruf vereinbart$/),
		});
		expect(out.result).toMatchObject({ changed: ["add_tags", "note"], updated: true });
		const before = JSON.parse(rows[0][7] as string);
		expect(before).toEqual({ description: "Alte Notiz", tag_ids: [5] });
	});

	it("keine Änderung → kein Write", async () => {
		const { client, calls } = fakeClient({ getContact: () => current });
		const out = await updateContact({ client, db: fakeDb().db, now: NOW, user: USER }, { id: 7, position: "CEO" });
		expect(out.result).toMatchObject({ updated: false });
		expect(calls.some((c) => c.method === "updateContact")).toBe(false);
	});

	it("neue E-Mail eines anderen Kontakts blockiert", async () => {
		const { client, calls } = fakeClient({
			getContact: () => current,
			searchContacts: () => page([{ email: "bob@gb.de", id: 8, name: "Bob" }]),
		});
		const out = await updateContact({ client, db: fakeDb().db, now: NOW, user: USER }, { email: "bob@gb.de", id: 7 });
		expect(out.result).toMatchObject({ blocked: "Dublette" });
		expect(calls.some((c) => c.method === "updateContact")).toBe(false);
	});
});

describe("create_object / update_object", () => {
	const input = {
		city: "Leverkusen",
		house_number: "99",
		marketing_type: "RENT" as const,
		rs_type: "INDUSTRY",
		street: "Schlebuscher Straße",
		title: "Logistikhalle in (51) Leverkusen",
		unit_id: "Unit 9",
		zip_code: "51381",
	};

	/** Simuliertes Propstack-Objekt mit dem echten Verhalten laut Notion-Feld-Mapping. */
	function fakeUnit(options: { lagExpand?: number; dropInMulti?: boolean } = {}) {
		const stored: Record<string, unknown> = {};
		const custom: Record<string, unknown> = {};
		const puts: Record<string, unknown>[] = [];
		let posted: Record<string, unknown> = {};
		let expandCalls = 0;
		const solo = ["rs_category", "total_floor_space", "industrial_area", "hall_height", "floor_load", "broker_id", "rented", "property_status_id"];
		const apply = (payload: Record<string, unknown>) => {
			const keys = Object.keys(payload).filter((k) => k !== "partial_custom_fields" && k !== "group_ids");
			for (const key of keys) {
				// Propstack verwirft kritische Felder im POST und in Multi-Feld-PUTs still
				if (options.dropInMulti !== false && solo.includes(key) && keys.length > 1) continue;
				stored[key] = payload[key];
			}
			Object.assign(custom, payload.partial_custom_fields ?? {});
			if (payload.group_ids) stored.group_ids = payload.group_ids;
		};
		const impl = {
			createUnit: (payload: unknown) => {
				posted = payload as Record<string, unknown>;
				const p = { ...(payload as Record<string, unknown>) };
				// POST: auch Einzelfelder fallen raus
				for (const key of solo) delete p[key];
				apply(p);
				return { id: 900 };
			},
			getUnit: () => ({
				// Einzel-GET: kein rs_category, keine Flächen, kein broker_id/property_status_id – dafür status/broker
				broker: stored.broker_id ? { id: stored.broker_id } : null,
				custom_fields: Object.fromEntries(Object.entries(custom).map(([k, v]) => [k, { pretty_value: String(v), value: v }])),
				id: 900,
				property_groups: ((stored.group_ids as number[]) ?? []).map((id) => ({ id })),
				status: stored.property_status_id ? { id: stored.property_status_id } : null,
				title: stored.title,
			}),
			searchUnits: (q: unknown) => {
				const query = q as Query;
				if (!query.expand) return page([]);
				expandCalls++;
				if (expandCalls <= (options.lagExpand ?? 0)) return page([]);
				const row: Record<string, unknown> = { id: { label: "ID", value: 900 } };
				for (const [k, v] of Object.entries(stored)) row[k] = { label: k, value: v };
				for (const k of solo) if (!(k in row)) row[k] = { label: k, value: null };
				return page([row]);
			},
			updateUnit: (_id: unknown, payload: unknown) => {
				puts.push(payload as Record<string, unknown>);
				apply(payload as Record<string, unknown>);
				return {};
			},
		};
		return { custom, impl, posted: () => posted, puts, stored, expandCalls: () => expandCalls };
	}

	const sleeps: number[] = [];
	const sleep = async (ms: number) => {
		sleeps.push(ms);
	};

	it("legt an: kritische Felder einzeln nachgesetzt, Herkunft in bemerkung, Gegenlesen über expand", async () => {
		const unit = fakeUnit({ lagExpand: 1 });
		const { client } = fakeClient(unit.impl);
		const { db, updates } = fakeDb();
		const out = await createObject(
			{ client, db, now: NOW, sleep, user: USER },
			{ ...input, custom_fields: { hallenhohe: 10.5, spekulative_entwicklung: "ja" }, industrial_area: 5863, rs_category: "HALL", status_id: 163672, test: true },
		);
		const posted = unit.posted();
		expect(posted).not.toHaveProperty("other_note");
		expect(posted).not.toHaveProperty("object_type");
		expect(posted).toMatchObject({ group_ids: [999], price_on_inquiry: true, title: "Logistikhalle in (51) Leverkusen" });
		expect(posted.partial_custom_fields).toMatchObject({
			bemerkung: "Angelegt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-14.",
			hallenhohe: 10.5,
			spekulative_entwicklung: 1,
		});
		// Gesamtfläche = Halle + Mezzanine (How-to), wenn nicht angegeben
		expect(unit.puts).toEqual([{ rs_category: "HALL" }, { industrial_area: 5863 }, { property_status_id: 163672 }, { broker_id: 347158 }, { total_floor_space: 5863 }]);
		expect(out.result).toMatchObject({ derived: ["total_floor_space = Hallenfläche + Mezzaninefläche"] });
		expect(out.result).toMatchObject({ created: true, id: 900, title: "Logistikhalle in (51) Leverkusen" });
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
		expect((out.result as { not_verifiable?: string[] }).not_verifiable).toBeUndefined();
		expect(sleeps).toContain(1500);
		expect(updates[0]?.[0]).toBe("done");
		// Testdaten: Prüfaufgabe an den Nutzer selbst, nicht an Lena
		expect(out.result).toMatchObject({ review_task: { assigned_to: "Florian Brimmers", due: "2026-10-15T09:00:00", id: 4711 } });
	});

	it("spiegelt Standardflächen in die Custom-Felder, die Exposé und Team lesen (Skill: alle Varianten)", async () => {
		const unit = fakeUnit();
		const { client } = fakeClient(unit.impl);
		const out = await createObject(
			{ client, db: fakeDb().db, now: NOW, sleep, user: USER },
			{ ...input, custom_fields: { lagerflache: 4800 }, hall_height: 10, industrial_area: 5000, total_floor_space: 5400, usable_floor_space: 400 },
		);
		expect(unit.posted().partial_custom_fields).toMatchObject({
			buroflache: 400,
			gebaudeflache_gesamt: 5400,
			gebaudeflache_verfugbar: 5400,
			hallenhohe: 10,
			lagerflache: 4800, // explizit übergeben hat Vorrang
			lagerflache_gesamt: 5000,
			lagerflache_verfugbar: "5.000 m²",
			preisangabe: "auf Anfrage",
		});
		expect(unit.posted().partial_custom_fields).not.toHaveProperty("mezzanineflache");
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
	});

	it("vermietet anlegen: Fläche „(vermietet)“, free_from, status_logistik/aktiv Inaktiv (Team-Prozess)", async () => {
		const unit = fakeUnit();
		const { client } = fakeClient(unit.impl);
		await createObject({ client, db: fakeDb().db, now: NOW, sleep, user: USER }, { ...input, industrial_area: 3475, rented: true });
		expect(unit.posted()).toMatchObject({ free_from: "vermietet" });
		expect(unit.posted().partial_custom_fields).toMatchObject({
			aktiv: [8],
			lagerflache: 3475,
			lagerflache_gesamt: 3475,
			lagerflache_verfugbar: "3.475 m² (vermietet)",
			status_logistik: "Inaktiv",
		});
		// Number-Feld bekommt keinen „(vermietet)“-Text und keine 0
		expect(unit.posted().partial_custom_fields).not.toHaveProperty("gebaudeflache_verfugbar");
	});

	it("aktiv nur bei Status Vermarktung; Akquise bleibt inaktiv; Testobjekte ohne Exposéversand; 0 m² abgewiesen", async () => {
		const unit = fakeUnit();
		const { client } = fakeClient(unit.impl);
		const deps = { client, db: fakeDb().db, now: NOW, sleep, user: USER };
		await createObject(deps, { ...input, industrial_area: 1000, status_id: 163674 });
		expect(unit.posted().partial_custom_fields).toMatchObject({ aktiv: [7], lagerflache_verfugbar: "1.000 m²", status_logistik: "Aktiv" });
		await createObject(deps, { ...input, industrial_area: 1000, status_id: 163672, test: true });
		expect(unit.posted().partial_custom_fields).toMatchObject({ aktiv: [8], kein_automatischer_exposeversand: true, status_logistik: "Inaktiv" });
		await expect(createObject(deps, { ...input, custom_fields: { lagerflache: 0 } })).rejects.toThrow(/0 m²/);
	});

	it("meldet Felder, die trotz Einzel-PUT nicht haften, und Fehler einzelner PUTs", async () => {
		const unit = fakeUnit();
		const failing = {
			...unit.impl,
			updateUnit: (_id: unknown, payload: unknown) => {
				const p = payload as Record<string, unknown>;
				if ("hall_height" in p) throw new Error("Propstack-Anfrage fehlgeschlagen (400)");
				if ("floor_load" in p) return {}; // HTTP 200, aber verworfen
				return unit.impl.updateUnit(_id, payload);
			},
		};
		const { client } = fakeClient(failing);
		const { db, updates } = fakeDb();
		const out = await createObject({ client, db, now: NOW, sleep, user: USER }, { ...input, floor_load: 5, hall_height: 10 });
		expect(out.result).toMatchObject({ not_applied: expect.arrayContaining(["floor_load", "hall_height"]), write_errors: [expect.stringMatching(/^hall_height: .*400/)] });
		expect(updates[0]?.[0]).toBe("done_with_gaps");
	});

	it("Mietobjekt: öffentlicher Preis wird abgewiesen, gesperrte Custom-Felder auch", async () => {
		const { client, calls } = fakeClient(fakeUnit().impl);
		const deps = { client, db: fakeDb().db, now: NOW, sleep, user: USER };
		await expect(createObject(deps, { ...input, price: 5500 })).rejects.toThrow(/intern_mietpreis/);
		await expect(createObject(deps, { ...input, custom_fields: { provisionspflichtig: "ja" } })).rejects.toThrow(/provisionspflichtig" gesperrt/);
		await expect(createObject(deps, { ...input, custom_fields: { mezzanineflache: 300 } })).rejects.toThrow(/Euro/);
		await expect(createObject(deps, { ...input, custom_fields: { bemerkung: "x" } })).rejects.toThrow(/bemerkung_append/);
		expect(calls.some((c) => c.method === "createUnit")).toBe(false);
	});

	it("öffentliche Preise nur mit Bestätigung (Entscheidung Florian); intern immer", async () => {
		const unit = fakeUnit();
		const { client, calls } = fakeClient(unit.impl);
		const deps = { client, db: fakeDb().db, now: NOW, sleep, user: USER };
		const buy = { ...input, marketing_type: "BUY" as const };
		await expect(createObject(deps, { ...buy, price: 2_500_000 })).rejects.toThrow(/öffentliche Preise/);
		await expect(createObject(deps, { ...input, custom_fields: { mietpreis_hallenflache: 6.5 } })).rejects.toThrow(/öffentlicher Preis.*intern_mietpreis_hallenflache/);
		expect(calls.some((c) => c.method === "createUnit")).toBe(false);

		await createObject(deps, { ...input, custom_fields: { intern_mietpreis_hallenflache: 6.5 } });
		expect(unit.posted()).toMatchObject({ price_on_inquiry: true });
		await createObject(deps, { ...buy, house_number: "100", price: 2_500_000, public_price_confirmed: true, unit_id: "Unit 10" });
		expect(unit.posted()).toMatchObject({ price: 2_500_000, price_on_inquiry: false });
		await createObject(deps, { ...input, base_rent: 18_000, house_number: "101", public_price_confirmed: true, unit_id: "Unit 11" });
		expect(unit.posted()).toMatchObject({ base_rent: 18_000, price_on_inquiry: false });
	});

	it("Status Reserviert gilt als aktiv", async () => {
		const unit = fakeUnit();
		const { client } = fakeClient(unit.impl);
		await createObject({ client, db: fakeDb().db, now: NOW, sleep, user: USER }, { ...input, industrial_area: 1000, status_id: 163675 });
		expect(unit.posted().partial_custom_fields).toMatchObject({ aktiv: [7], status_logistik: "Aktiv" });
	});

	it("Zahlen nur nackt: Komma-Text und Tausenderpunkt werden abgewiesen", async () => {
		const { client } = fakeClient(fakeUnit().impl);
		const deps = { client, db: fakeDb().db, now: NOW, sleep, user: USER };
		await expect(createObject(deps, { ...input, custom_fields: { hallenhohe: "10,5" } })).rejects.toThrow(/nackte Zahl/);
		await expect(createObject(deps, { ...input, custom_fields: { lagerflache: 6.417 } })).rejects.toThrow(/Tausenderpunkt.*6417/);
	});

	it("Eigentümer an der Einheit (Gegenprobe), Beleuchtung in beide Felder, angegebene Koordinaten mit Stufen-Trick", async () => {
		const unit = fakeUnit();
		let relationshipCalls = 0;
		const coordPuts: Record<string, unknown>[] = [];
		const coords: Record<string, number> = {};
		const impl = {
			...unit.impl,
			getContact: () => ({ id: 35208656, name: "JJW Hillscheid Grundbesitz GmbH" }),
			getUnit: () => ({ ...(unit.impl.getUnit() as Record<string, unknown>), ...coords }),
			updateUnit: (id: unknown, payload: unknown) => {
				const p = payload as Record<string, unknown>;
				if ("relationships_attributes" in p) {
					relationshipCalls++;
					if (relationshipCalls > 1) throw new Error('Propstack-Anfrage fehlgeschlagen (400): ["Relationships property ist bereits mit dem Kontakt verbunden"]');
					return {};
				}
				if ("lat" in p || "lng" in p) {
					coordPuts.push(p);
					Object.assign(coords, p);
					return {};
				}
				return unit.impl.updateUnit(id, payload);
			},
		};
		const { client } = fakeClient(impl);
		const out = await createObject(
			{ client, db: fakeDb().db, now: NOW, sleep, user: USER },
			{ ...input, custom_fields: { beleuchtung_halle: "LED" }, lat: 50.4367, lng: 7.7047, owner_contact_id: 35208656 },
		);
		expect(out.result).toMatchObject({
			coordinates: { source: "angegeben", verified: true },
			owner: { id: 35208656, linked: true },
		});
		expect(unit.posted().partial_custom_fields).toMatchObject({ beleuchtung: "LED", beleuchtung_halle: "LED" });
		expect(coordPuts[0]).toEqual({ lat: 50.4367 });
		expect(coordPuts[coordPuts.length - 1]).toEqual({ lng: 7.7047 });
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
	});

	it("Einheit im Projekt: keine eigene Prüfaufgabe, solange alles übernommen wurde", async () => {
		const unit = fakeUnit();
		const { client, calls } = fakeClient(unit.impl);
		const out = await createObject({ client, db: fakeDb().db, now: NOW, sleep, user: USER }, { ...input, project_id: 603710 });
		expect(out.result).toMatchObject({
			inherited_from_project: ["location_note", "furnishing_note"],
			review_task: { covered_by: "Prüfaufgabe des Projekts 603710" },
		});
		expect(unit.posted()).toMatchObject({ furnishing_note: "- 10 Rampen\n- LED", location_note: "Direkt an der A48." });
		expect(calls.some((c) => c.method === "createTask")).toBe(false);
	});

	it("Dublette blockiert ohne Override", async () => {
		const { client, calls } = fakeClient({
			searchUnits: () => page([{ ...input, id: 10, unit_id: "Unit 9" }]),
		});
		const out = await createObject({ client, db: fakeDb().db, now: NOW, sleep, user: USER }, input);
		expect(out.result).toMatchObject({ blocked: "Dublette", duplicates: [{ id: 10 }] });
		expect(calls.some((c) => c.method === "createUnit")).toBe(false);
	});

	it("ungültige Custom-Felder werden vor dem Write abgewiesen", async () => {
		const { client, calls } = fakeClient({});
		await expect(
			createObject({ client, db: fakeDb().db, now: NOW, sleep, user: USER }, { ...input, custom_fields: { gibtsnicht: 1, spekulative_entwicklung: "Vielleicht" } }),
		).rejects.toThrow(/unbekanntes Feld "gibtsnicht".*spekulative_entwicklung.*Ja \(1\)/);
		expect(calls.some((c) => c.method === "createUnit")).toBe(false);
	});

	it("update_object: Status und rented einzeln, Bemerkung angehängt, Snapshot vorher", async () => {
		const unit = fakeUnit();
		Object.assign(unit.stored, { broker_id: 347158, industrial_area: 5000, marketing_type: "RENT", property_status_id: 163674, title: "SCHLE99" });
		Object.assign(unit.custom, { bemerkung: "Alte Bemerkung" });
		const { client } = fakeClient(unit.impl);
		const { db, rows } = fakeDb();
		const out = await updateObject(
			{ client, db, now: NOW, sleep, user: USER },
			{ bemerkung_append: "Eigentümer will 6 €/m²", id: 900, rented: true, status_id: 163676, title: "SCHLE99" },
		);
		expect(unit.puts).toEqual([
			{
				free_from: "vermietet",
				partial_custom_fields: {
					aktiv: [8],
					bemerkung: expect.stringMatching(/^Alte Bemerkung\n\nErgänzt über Claude .* am 2026-10-14\.\nEigentümer will 6 €\/m²$/),
					lagerflache: 5000,
					lagerflache_gesamt: 5000,
					lagerflache_verfugbar: "5.000 m² (vermietet)",
					status_logistik: "Inaktiv",
				},
			},
			{ rented: true },
			{ property_status_id: 163676 },
		]);
		expect(out.result).toMatchObject({ updated: true });
		expect((out.result as { changed: string[] }).changed).toEqual(expect.arrayContaining(["rented", "status_id", "free_from", "bemerkung (angehängt)", "custom_fields.lagerflache_verfugbar"]));
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
		expect(JSON.parse(rows[0][7] as string)).toMatchObject({ custom_fields: { bemerkung: "Alte Bemerkung" }, free_from: "nicht lesbar", rented: null, status_id: 163674 });
	});

	it("update_object: zieht fehlende Flächen-Varianten auch bei unveränderter Standardfläche nach", async () => {
		const unit = fakeUnit();
		Object.assign(unit.stored, { industrial_area: 5000, marketing_type: "RENT", rented: false, title: "Alt" });
		Object.assign(unit.custom, { lagerflache: 5000 });
		const { client } = fakeClient(unit.impl);
		const out = await updateObject({ client, db: fakeDb().db, now: NOW, sleep, user: USER }, { id: 900, industrial_area: 5000 });
		expect(unit.puts).toEqual([{ partial_custom_fields: { lagerflache_gesamt: 5000, lagerflache_verfugbar: "5.000 m²" } }]);
		expect(out.result).toMatchObject({ updated: true });
	});

	it("update_object: Kaufpreis bei Mietobjekt abgewiesen, keine Änderung → kein Write", async () => {
		const unit = fakeUnit();
		Object.assign(unit.stored, { marketing_type: "RENT", title: "SCHLE99" });
		const { client, calls } = fakeClient(unit.impl);
		const deps = { client, db: fakeDb().db, now: NOW, sleep, user: USER };
		await expect(updateObject(deps, { id: 900, price: 100 })).rejects.toThrow(/öffentliche Preise.*fragen/);
		await expect(updateObject(deps, { id: 900, price: 100, public_price_confirmed: true })).rejects.toThrow(/nur bei BUY/);
		const out = await updateObject(deps, { id: 900, title: "SCHLE99" });
		expect(out.result).toMatchObject({ updated: false });
		expect(calls.some((c) => c.method === "updateUnit")).toBe(false);
	});
});

describe("create_object / update_object – Team-How-to", () => {
	const sleep = async () => {};
	const standalone = { city: "Herford", house_number: "8", marketing_type: "RENT" as const, rs_type: "INDUSTRY", street: "Röntgenstraße", title: "Logistikhalle in (32) Herford", zip_code: "32052" };
	const PROJECT = {
		city: "Hillscheid",
		courtage: "Provisionsfrei",
		courtage_note: "Die Anmietung erfolgt provisionsfrei für den Mieter.",
		description_note: "Built-to-Suit-Logistikimmobilie mit ca. 30.000 m² Hallenfläche.",
		furnishing_note: "- 30 Verladestellen\n- LED",
		id: 604473,
		lat: 50.4109821,
		lng: 7.6811256,
		location_note: "Autobahnen:\nA48: ca. 5,6 km",
		name: "BTS-Logistikhalle in (56) Hillscheid",
		street: "Am Scheid",
		title: "Logistikhalle in (56) Hillscheid",
		zip_code: "56204",
	};

	/** Simuliertes Objekt: speichert alles, kennt Verknüpfungen (lehnt Doppelte ab) und Koordinaten. */
	function world(project: Record<string, unknown> = PROJECT, options: { dropNote?: boolean; showLinks?: boolean } = {}) {
		const stored: Record<string, unknown> = {};
		const custom: Record<string, unknown> = {};
		const coords: Record<string, number> = {};
		const links: string[] = [];
		const puts: Record<string, unknown>[] = [];
		let posted: Record<string, unknown> = {};
		let task: Record<string, unknown> | undefined;
		const apply = (payload: Record<string, unknown>) => {
			for (const [key, value] of Object.entries(payload)) {
				if (key === "partial_custom_fields") Object.assign(custom, value);
				else if (key === "lat" || key === "lng") coords[key] = value as number;
				else if (key !== "relationships_attributes") stored[key] = value;
			}
		};
		const { client, calls } = fakeClient({
			createTask: (t) => {
				task = t as Record<string, unknown>;
				return { id: 4711 };
			},
			createUnit: (payload) => {
				posted = payload as Record<string, unknown>;
				apply(posted);
				return { id: 900 };
			},
			getContact: (id) => (id === 111 ? { company: "JJW Hillscheid Grundbesitz GmbH", id: 111, name: "JJW Hillscheid Grundbesitz GmbH" } : { id: 222, name: "Tobias Jung" }),
			getProject: () => project,
			getUnit: () => ({
				broker: stored.broker_id ? { id: stored.broker_id } : null,
				custom_fields: Object.fromEntries(Object.entries(custom).map(([k, v]) => [k, { pretty_value: String(v), value: v }])),
				id: 900,
				note: options.dropNote ? null : (stored.note ?? null),
				property_groups: ((stored.group_ids as number[]) ?? []).map((id) => ({ id })),
				relationships: options.showLinks ? links.map((l) => ({ client_id: (JSON.parse(l) as { related_client_id: number }).related_client_id, internal_name: (JSON.parse(l) as { internal_name: string }).internal_name, name: null })) : undefined,
				status: stored.property_status_id ? { id: stored.property_status_id } : null,
				title: stored.title,
				...coords,
			}),
			searchUnits: (q) => {
				if (!(q as Query).expand) return page([]);
				const row: Record<string, unknown> = { id: { label: "ID", value: 900 }, note: { label: "Notiz", value: null } };
				for (const [k, v] of Object.entries(stored)) row[k] = { label: k, value: k === "note" && options.dropNote ? null : v };
				return page([row]);
			},
			updateUnit: (_id, payload) => {
				const body = payload as { relationships_attributes?: unknown[] };
				puts.push(body as Record<string, unknown>);
				if (body.relationships_attributes) {
					const key = JSON.stringify(body.relationships_attributes[0]);
					if (links.includes(key)) throw new Error('Propstack-Anfrage fehlgeschlagen (400): ["Relationships property ist bereits mit dem Kontakt verbunden"]');
					links.push(key);
					return {};
				}
				apply(body as Record<string, unknown>);
				return {};
			},
		});
		return { calls, client, coords, custom, links, posted: () => posted, puts, stored, task: () => task };
	}

	it("Einheit im Projekt: Adresse, Überschrift, Beschreibung, Lage, Ausstattung, Provision und Koordinaten kommen vom Projekt", async () => {
		const w = world();
		const out = await createObject(
			{ client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER },
			{ industrial_area: 10000, marketing_type: "RENT", project_id: 604473, rs_category: "HALL", rs_type: "INDUSTRY", unit_id: "Unit 1" },
		);
		expect(w.posted()).toMatchObject({
			city: "Hillscheid",
			courtage: "Provisionsfrei",
			courtage_note: "Die Anmietung erfolgt provisionsfrei für den Mieter.",
			description_note: PROJECT.description_note,
			furnishing_note: PROJECT.furnishing_note,
			location_note: PROJECT.location_note,
			street: "Am Scheid",
			title: "Logistikhalle in (56) Hillscheid",
			unit_id: "Unit 1",
			zip_code: "56204",
		});
		expect(out.result).toMatchObject({
			coordinates: { lat: 50.4109821, lng: 7.6811256, source: "Projekt", verified: true },
			inherited_from_project: ["address", "title", "description_note", "location_note", "furnishing_note", "courtage", "courtage_note"],
			review_task: { covered_by: "Prüfaufgabe des Projekts 604473" },
		});
		// Lücken laut How-to stehen im Ergebnis, auch ohne eigene Prüfaufgabe
		expect((out.result as { howto_not_provided: string[] }).howto_not_provided).toEqual(expect.arrayContaining(["Eigentümer", "Hallenhöhe (m UKB)", "Rampentore", "Verfügbar ab"]));
		expect((out.result as { howto_not_provided: string[] }).howto_not_provided).not.toContain("Provision");
		expect((out.result as { howto_not_provided: string[] }).howto_not_provided).not.toContain("Lage");
	});

	it("Einheit im Projekt braucht eine Einheitennummer; eigene Provision schlägt die des Projekts", async () => {
		const w = world();
		const deps = { client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER };
		await expect(createObject(deps, { marketing_type: "RENT", project_id: 604473, rs_type: "INDUSTRY" })).rejects.toThrow(/unit_id/);
		await createObject(deps, { commission: "staffel", marketing_type: "RENT", project_id: 604473, rs_type: "INDUSTRY", unit_id: "Unit 2" });
		expect(w.posted().courtage).toBeUndefined();
		expect(String(w.posted().courtage_note)).toMatch(/^Bei Mietverträgen mit einer Laufzeit von weniger als fünf/);
	});

	it("Einzelobjekt ohne Pflichtangaben wird abgewiesen", async () => {
		const w = world();
		await expect(createObject({ client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER }, { marketing_type: "RENT", rs_type: "INDUSTRY", title: "Halle" })).rejects.toThrow(
			/Pflichtangaben fehlen: street, zip_code, city/,
		);
	});

	it("wichtige Felder aus dem How-to landen in den Feldern, die das Team in Propstack sieht", async () => {
		const w = world();
		const out = await createObject(
			{ client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER },
			{
				...standalone,
				active: true,
				car_parking: 400,
				certification: "DGNB Gold",
				dock_doors: 10,
				ground_level_doors: 1,
				hall_divisible_from: 5000,
				heating: "Wärmepumpe",
				industrial_area: 10000,
				internal_rent_hall: 6.8,
				lighting: "LED",
				mezzanine_area: 800,
				sprinkler: "vorhanden",
				truck_parking: 12,
				wgk: "WGK 1–3",
			},
		);
		expect(w.posted().partial_custom_fields).toMatchObject({
			aktiv: [7],
			anzahl_rampentore_2: 1,
			beleuchtung: "LED",
			beleuchtung_halle: "LED",
			heizungsart_halle: "Wärmepumpe",
			intern_mietpreis_hallenflache: 6.8,
			lagerflache_teilbar_ab: 5000,
			lkw_stellplatze_gesamt: 12,
			mezzanineflache_gesamt: 800,
			mezzanineflache_verfugbar: 800,
			ramepntore: "10", // Textfeld in Propstack
			sprinkleranlage: "vorhanden",
			status_logistik: "Aktiv",
			stellplatze_verfugbar: 400,
			wgk: "WGK 1–3",
			zertifizierung: "DGNB Gold",
		});
		// Gesamtfläche = Halle + Mezzanine
		expect(w.stored.total_floor_space).toBe(10800);
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
		const missing = (out.result as { howto_not_provided: string[] }).howto_not_provided;
		for (const present of ["Rampentore", "Ebenerdige Tore", "Beleuchtung", "Mietpreise (intern)", "Hallenfläche teilbar ab"]) expect(missing).not.toContain(present);
		expect(missing).toEqual(expect.arrayContaining(["Eigentümer", "Interne Notiz: Exposé-/Website-Link", "Mezzaninefläche teilbar ab", "Grundstücksfläche"]));
	});

	it("How-to-Parameter und dasselbe Custom-Feld gleichzeitig → abgewiesen; aktiv und vermietet widersprechen sich", async () => {
		const w = world();
		const deps = { client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER };
		await expect(createObject(deps, { ...standalone, custom_fields: { ramepntore: "9" }, dock_doors: 10 })).rejects.toThrow(/dock_doors und custom_fields\.ramepntore gleichzeitig/);
		await expect(createObject(deps, { ...standalone, active: true, rented: true })).rejects.toThrow(/widersprechen sich/);
		expect(w.calls.some((c) => c.method === "createUnit")).toBe(false);
	});

	it("Eigentümer und Ansprechpartner werden verknüpft; interne Notiz strukturiert in die Bemerkung; Prüfaufgabe nennt Lücken", async () => {
		const w = world();
		const out = await createObject(
			{ client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER },
			{ ...standalone, contact_person_id: 222, internal_commission: "Tischregel 50/50", mandate: "Alleinmandat", owner_contact_id: 111, source_link: "https://example.org/expose.pdf" },
		);
		// wie von Hand hinterlegt: verknüpfter Kontakt ohne Bezeichnung
		expect(w.links).toEqual([JSON.stringify({ internal_name: "owner", related_client_id: 111 }), JSON.stringify({ internal_name: "partner", related_client_id: 222 })]);
		expect(out.result).toMatchObject({ contact_person: { id: 222, linked: true, name: "Tobias Jung" }, owner: { id: 111, linked: true } });
		// Interne Notiz ins Feld „Notiz“ (= „Interne Notizen“ im How-to); die Bemerkung trägt nur den Herkunftsvermerk
		expect(String(w.posted().note).split("\n")).toEqual([
			"Angelegt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-14.",
			"Exposé/Website: https://example.org/expose.pdf",
			"Mandat: Alleinmandat",
			"Provision intern: Tischregel 50/50",
		]);
		expect((w.posted().partial_custom_fields as Record<string, unknown>).bemerkung).toBe("Angelegt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-14.");
		expect((out.result as { not_applied?: string[]; internal_note_hint?: string }).not_applied).toBeUndefined();
		expect((out.result as { internal_note_hint?: string }).internal_note_hint).toBeUndefined();
		// Der Ansprechpartner steht NICHT mehr als ID im Custom-Feld (stand im Exposé-Risiko, Handanlagen nutzen es nicht)
		expect(w.posted().partial_custom_fields).not.toHaveProperty("ansprechpartner_vermietung");
		const body = String(w.task()!.body);
		expect(body).toMatch(/Eigentümer: JJW Hillscheid Grundbesitz GmbH \(111\)/);
		expect(body).toMatch(/Ansprechpartner: Tobias Jung \(222\)/);
		expect(body).toMatch(/Nicht angegeben \(laut How-to wichtig\)/);
		expect(body).toMatch(/Wesentlicher Energieträger/);
	});

	it("übernimmt Propstack die interne Notiz nicht, landet der Text in der Bemerkung – nichts geht verloren", async () => {
		const w = world(PROJECT, { dropNote: true });
		const out = await createObject({ client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER }, { ...standalone, mandate: "Alleinmandat" });
		expect(w.puts).toEqual(
			expect.arrayContaining([
				{ note: "Angelegt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-14.\nMandat: Alleinmandat" }, // einzeln nachgesetzt
				{ partial_custom_fields: { bemerkung: "Angelegt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-14.\nMandat: Alleinmandat" } },
			]),
		);
		expect((out.result as { internal_note_hint: string }).internal_note_hint).toMatch(/steht stattdessen im Feld „Bemerkung“/);
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
	});

	it("Verknüpfungen an Einheiten werden gegengelesen (relationships im Einzel-GET) – ohne zweiten Schreibversuch", async () => {
		const w = world(PROJECT, { showLinks: true });
		const out = await createObject({ client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER }, { ...standalone, contact_person_id: 222, owner_contact_id: 111 });
		expect(out.result).toMatchObject({ contact_person: { linked: true }, owner: { linked: true } });
		// je Rolle genau ein PUT – keine Gegenprobe nötig
		expect(w.puts.filter((p) => "relationships_attributes" in p)).toHaveLength(2);
	});

	it("Ansprechpartner = Eigentümer: nur einmal verknüpfen", async () => {
		const w = world();
		const out = await createObject({ client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER }, { ...standalone, contact_person_id: 111, owner_contact_id: 111 });
		expect(w.links).toEqual([JSON.stringify({ internal_name: "owner", related_client_id: 111 })]);
		expect(out.result).toMatchObject({ contact_person: { linked: true, note: expect.stringMatching(/als Eigentümer verknüpft/) } });
	});

	it("Texte: Eigentümername, Preis und Komma-Kette werden abgewiesen; Übernommenes vom Projekt nur gemeldet", async () => {
		const w = world({ ...PROJECT, description_note: "Ein Projekt der JJW Hillscheid Grundbesitz GmbH, Miete 6,80 €/m²." });
		const deps = { client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER };
		await expect(createObject(deps, { ...standalone, description_note: "Halle der JJW Hillscheid Grundbesitz GmbH.", owner_contact_id: 111 })).rejects.toThrow(/nennt den Eigentümer/);
		await expect(createObject(deps, { ...standalone, description_note: "Für 6,80 €/m² zu mieten." })).rejects.toThrow(/enthält einen Preis/);
		await expect(createObject(deps, { ...standalone, furnishing_note: "LED, Sprinkler, Rampen" })).rejects.toThrow(/Aufzählung/);
		await expect(createObject(deps, { ...standalone, title: "Logistikhalle in (33) Herford" })).rejects.toThrow(/\(33\) passt nicht zur PLZ 32052/);
		// streng nach How-to: Überschrift ohne „(XX)“, Lage ohne km, Adresse im Text
		await expect(createObject(deps, { ...standalone, title: "Moderne Logistikhalle" })).rejects.toThrow(/ohne „\(32\)“/);
		await expect(createObject(deps, { ...standalone, location_note: "Sehr gute Anbindung." })).rejects.toThrow(/es fehlen die Entfernungen in km/);
		await expect(createObject(deps, { ...standalone, description_note: "Halle an der Röntgenstraße 8." })).rejects.toThrow(/die Adresse darf in Exposé-Texten nicht vorkommen/);
		expect(w.calls.some((c) => c.method === "createUnit")).toBe(false);
		// Alttext des Projekts blockiert die Einheit nicht, wird aber gemeldet
		const out = await createObject(deps, { marketing_type: "RENT", owner_contact_id: 111, project_id: 604473, rs_type: "INDUSTRY", unit_id: "Unit 3" });
		const warnings = (out.result as { text_warnings: string[] }).text_warnings.join(" ");
		expect(warnings).toMatch(/Vom Projekt übernommen – Beschreibung: nennt den Eigentümer/);
		expect(warnings).toMatch(/Vom Projekt übernommen – Beschreibung: enthält einen Preis/);
	});

	it("update_object: nur Koordinaten ändern funktioniert (vorher fälschlich als „nichts geändert“ abgebrochen)", async () => {
		const w = world();
		Object.assign(w.stored, { marketing_type: "RENT", title: "Halle" });
		Object.assign(w.coords, { lat: 50.4367, lng: 7.7047 });
		const { db, rows, updates } = fakeDb();
		const out = await updateObject({ client: w.client, db, now: NOW, sleep, user: USER }, { id: 900, lat: 50.4109821, lng: 7.6811256 });
		expect(w.coords).toEqual({ lat: 50.4109821, lng: 7.6811256 });
		// Write-Log: Stand vorher und Anfrage enthalten die Koordinaten (Korrektur an Bestandsobjekten nachvollziehbar)
		expect(JSON.parse(rows[0][7] as string)).toEqual({ lat: 50.4367, lng: 7.7047 });
		expect(JSON.parse(rows[0][8] as string)).toMatchObject({ lat: 50.4109821, lng: 7.6811256 });
		expect(out.result).toMatchObject({ changed: ["lat/lng"], coordinates: { source: "angegeben", verified: true }, updated: true });
		expect(updates[0]?.[0]).toBe("done");
	});

	it("update_object: How-to-Felder und Aktiv nur bei echter Änderung; interne Angaben werden an die Bemerkung angehängt", async () => {
		const w = world();
		Object.assign(w.stored, { marketing_type: "RENT", rented: false, title: "Halle" });
		Object.assign(w.stored, { note: "Tippgeber: 25 %" });
		Object.assign(w.custom, { bemerkung: "Alt", ramepntore: "10" });
		const deps = { client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER };
		const out = await updateObject(deps, { active: true, dock_doors: 10, ground_level_doors: 2, id: 900, source_link: "https://example.org/expose.pdf" });
		expect(w.puts).toEqual([
			{
				// vorhandene Notiz bleibt, Neues wird angehängt; die Bemerkung wird nicht angefasst
				note: "Tippgeber: 25 %\n\nErgänzt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-14.\nExposé/Website: https://example.org/expose.pdf",
				partial_custom_fields: { aktiv: [7], anzahl_rampentore_2: 2, status_logistik: "Aktiv" },
			},
		]);
		expect((out.result as { changed: string[] }).changed).toEqual(expect.arrayContaining(["custom_fields.anzahl_rampentore_2", "internal_note (angehängt)"]));
		// Geänderter Text gegen die Regeln → abgewiesen, unveränderter Alttext bleibt unberührt
		await expect(updateObject(deps, { description_note: "Miete 6,80 € je m²", id: 900 })).rejects.toThrow(/enthält einen Preis/);
		const hint = await updateObject(deps, { id: 900, industrial_area: 9000 });
		expect((hint.result as { warnings: string[] }).warnings.join(" ")).toMatch(/Gesamtfläche/);
	});
});

describe("Hilfsfunktionen", () => {
	it("notApplied vergleicht label/value, pretty_value und Zahlen", () => {
		expect(notApplied({ price: 100, title: "A" }, { price: "100.0", title: { label: "x", value: "A" } })).toEqual([]);
		expect(notApplied({ title: "A" }, {})).toEqual(["title"]);
		expect(notApplied({}, { custom_fields: { a: { pretty_value: "Ja", value: true } } }, { a: true })).toEqual([]);
	});

	it("validateCustomFields: Auswahlwerte als Option-ID, Zahlen unverändert, null leert", async () => {
		const { client } = fakeClient({});
		expect(await validateCustomFields(client, "for_properties", { aktiv: ["Aktiv"], hallenhohe: 10.5, spekulative_entwicklung: 2, provisionspflichtig: null })).toEqual({
			expect: { aktiv: [{ id: 7, name: "Aktiv" }], hallenhohe: 10.5, provisionspflichtig: null, spekulative_entwicklung: { id: 2, name: "Nein" } },
			send: { aktiv: [7], hallenhohe: 10.5, provisionspflichtig: null, spekulative_entwicklung: 2 },
		});
	});

	it("notApplied erkennt Auswahlwerte über ID oder Klartext", () => {
		expect(notApplied({}, { custom_fields: { s: { pretty_value: "Ja", value: 1 } } }, { s: { id: 1, name: "Ja" } })).toEqual([]);
		expect(notApplied({}, { custom_fields: { a: { pretty_value: "Aktiv, Inaktiv", value: [7, 8] } } }, { a: [{ id: 8, name: "Inaktiv" }] })).toEqual([]);
		expect(notApplied({}, { custom_fields: { s: { value: 2 } } }, { s: { id: 1, name: "Ja" } })).toEqual(["custom_fields.s"]);
	});
});

