import { describe, expect, it } from "vitest";
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
		listCustomFieldGroups: () =>
			page([
				{
					custom_fields: [
						{ field_type: "Number", name: "hallenhohe" },
						{ custom_options: [{ name: "Ja" }, { name: "Nein" }], field_type: "Dropdown", name: "spekulative_entwicklung" },
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
		title: "MCP Test Halle",
		unit_id: "Unit 9",
		zip_code: "51381",
	};

	it("legt an mit Betreuer, Test-Merkmal, validierten Custom-Feldern und prüft Status zurück", async () => {
		let sent: Record<string, unknown> = {};
		const { client } = fakeClient({
			createUnit: (payload) => {
				sent = payload as Record<string, unknown>;
				return { id: 900 };
			},
			getUnit: () => ({
				...sent,
				custom_fields: { hallenhohe: { pretty_value: "10,5", value: 10.5 } },
				id: 900,
				property_groups: [{ id: 999 }],
				status: { id: 163672, name: "Akquise" },
				title: { label: "Überschrift", value: "MCP Test Halle" },
			}),
		});
		const out = await createObject(
			{ client, db: fakeDb().db, now: NOW, user: USER },
			{ ...input, custom_fields: { hallenhohe: "10,5" }, status_id: 163672, test: true },
		);
		expect(sent).toMatchObject({ broker_id: 347158, group_ids: [999], partial_custom_fields: { hallenhohe: 10.5 }, property_status_id: 163672 });
		expect(out.result).toMatchObject({ created: true, id: 900, title: "MCP Test Halle" });
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
	});

	it("Dublette blockiert ohne Override", async () => {
		const { client, calls } = fakeClient({
			searchUnits: () => page([{ ...input, id: 10, unit_id: "Unit 9" }]),
		});
		const out = await createObject({ client, db: fakeDb().db, now: NOW, user: USER }, input);
		expect(out.result).toMatchObject({ blocked: "Dublette", duplicates: [{ id: 10 }] });
		expect(calls.some((c) => c.method === "createUnit")).toBe(false);
	});

	it("ungültige Custom-Felder werden vor dem Write abgewiesen", async () => {
		const { client, calls } = fakeClient({});
		await expect(
			createObject({ client, db: fakeDb().db, now: NOW, user: USER }, { ...input, custom_fields: { gibtsnicht: 1, spekulative_entwicklung: "Vielleicht" } }),
		).rejects.toThrow(/unbekanntes Feld "gibtsnicht".*spekulative_entwicklung/);
		expect(calls.some((c) => c.method === "createUnit")).toBe(false);
	});

	it("update_object: Statuswechsel mit Snapshot, Gegenlesen", async () => {
		const { db, rows } = fakeDb();
		let status = 163674;
		const { client } = fakeClient({
			getUnit: () => ({ id: 5231702, status: { id: status }, title: "SCHLE99" }),
			updateUnit: (_id, payload) => {
				status = (payload as { property_status_id: number }).property_status_id;
				return {};
			},
		});
		const out = await updateObject({ client, db, now: NOW, user: USER }, { id: 5231702, status_id: 163675 });
		expect(out.result).toMatchObject({ changed: ["status_id"], updated: true });
		expect(JSON.parse(rows[0][7] as string)).toEqual({ property_status_id: 163674 });
	});
});

describe("Hilfsfunktionen", () => {
	it("notApplied vergleicht label/value, pretty_value und Zahlen", () => {
		expect(notApplied({ price: 100, title: "A" }, { price: "100.0", title: { label: "x", value: "A" } })).toEqual([]);
		expect(notApplied({ title: "A" }, {})).toEqual(["title"]);
		expect(notApplied({}, { custom_fields: { a: { pretty_value: "Ja", value: true } } }, { a: true })).toEqual([]);
	});

	it("validateCustomFields wandelt Zahlen mit Komma", async () => {
		const { client } = fakeClient({});
		expect(await validateCustomFields(client, "for_properties", { hallenhohe: "10,5", spekulative_entwicklung: "Ja" })).toEqual({
			hallenhohe: 10.5,
			spekulative_entwicklung: "Ja",
		});
	});
});
