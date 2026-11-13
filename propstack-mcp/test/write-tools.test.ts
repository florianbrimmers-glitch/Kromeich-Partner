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
	personName,
} from "../src/propstack/dedupe";
import { type Page, type PropstackClient, PropstackError, type Query } from "../src/propstack-client";
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

	// Live-Befund 12.11.2026: Propstack stellt dem Anzeigenamen den akademischen Titel voran ("Dr. Max MCP-Testkontakt
	// Abnahme"). Der Vergleich lief gegen diesen Anzeigenamen – „Max …“ bei derselben Firma wurde deshalb als neuer
	// Kontakt angelegt (38363864 neben 38363861), ohne Blockade und ohne Warnung.
	describe("akademischer Titel im Anzeigenamen (Zeilen so, wie Propstack sie liefert)", () => {
		const drMax = { academic_title: "Dr.", company: "MCP-TEST Musterfirma GmbH", first_name: "Max", id: 38363861, last_name: "MCP-Testkontakt Abnahme", name: "Dr. Max MCP-Testkontakt Abnahme" };

		it("gleicher Name + gleiche Firma blockiert, auch wenn der vorhandene Kontakt einen Titel trägt (Groß-/Kleinschreibung egal)", () => {
			const r = contactDuplicates({ company: "MCP-Test Musterfirma GmbH", first_name: "max", last_name: "MCP-Testkontakt Abnahme" }, { ...none, byName: [drMax] });
			expect(r.duplicates).toEqual([{ id: 38363861, name: "Dr. Max MCP-Testkontakt Abnahme", reason: "gleicher Name und gleiche Firma (MCP-TEST Musterfirma GmbH)" }]);
		});

		it("ohne Firma: Warnung statt Stille", () => {
			const r = contactDuplicates({ first_name: "Max", last_name: "MCP-Testkontakt Abnahme" }, { ...none, byName: [drMax] });
			expect(r.duplicates).toEqual([]);
			expect(r.warnings).toEqual(["Gleicher Name wie Dr. Max MCP-Testkontakt Abnahme (38363861), Firma MCP-TEST Musterfirma GmbH."]);
		});

		it("Titel im Vornamen der Eingabe („Dr. Max“) oder mehrere Titel („Prof. Dr.“, „Dipl.-Ing.“) ändern nichts", () => {
			for (const first_name of ["Dr. Max", "Prof. Dr. Max", "Dipl.-Ing. Max", "Dr. med. Max"]) {
				const r = contactDuplicates({ company: "MCP-TEST Musterfirma", first_name, last_name: "MCP-Testkontakt Abnahme" }, { ...none, byName: [drMax] });
				expect(r.duplicates.map((d) => d.id), first_name).toEqual([38363861]);
			}
		});

		it("Zeile ohne Vor- und Nachnamen: der Titel wird aus dem Anzeigenamen entfernt", () => {
			const r = contactDuplicates({ company: "GB Logistics", first_name: "Anna", last_name: "Muster" }, { ...none, byName: [{ company: "GB Logistics GmbH", id: 5, name: "Prof. Dr. Anna Muster" }] });
			expect(r.duplicates.map((d) => d.id)).toEqual([5]);
		});

		it("andere Person bleibt eine andere Person; ein Name, der nur aus einem Titelwort besteht, wird nicht leer", () => {
			expect(contactDuplicates({ company: "MCP-TEST Musterfirma GmbH", first_name: "Moritz", last_name: "MCP-Testkontakt Abnahme" }, { ...none, byName: [drMax] })).toEqual({ duplicates: [], warnings: [] });
			expect(personName("Dr. Max Muster")).toBe("max muster");
			expect(personName("Mag")).toBe("mag");
			expect(personName("Dr. Dr")).toBe("dr");
			expect(personName("Ingrid Ing")).toBe("ingrid ing");
		});
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
						// „Bezug“ und „Bezug (Datum)“ folgen „Verfügbar ab“ (Typen wie live, 11.11.2026)
						{ field_type: "String", name: "bezug" },
						{ field_type: "Date", name: "bezug_datum" },
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
						// Provisionsfelder der Feldgruppe „Webseite“ (Feld-Mapping, Korrektur 29; Typen wie live)
						{ field_type: "String", name: "provision_extern" },
						{ field_type: "String", name: "provision_interne_notiz" },
						{ field_type: "String", name: "provision_intern" },
						{ field_type: "String", name: "provision" },
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
		expect(sent).toMatchObject({ broker_id: 347158, email: "anna.test@example.com", group_ids: [999], office_cell: "+49 171 1234567" });
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

	it("Telefonnummer ohne Ländervorwahl: bekommt die Vorwahl des am Kontakt gespeicherten Landes – ein neu angegebenes Land geht vor", async () => {
		// Entscheidung Florian, 13.11.2026: einheitlich mit Ländervorwahl
		const lauf = async (gespeichert: Record<string, unknown>, input: Record<string, unknown>) => {
			let sent: Record<string, unknown> = {};
			const { client } = fakeClient({
				getContact: () => ({ ...current, ...gespeichert, ...sent }),
				updateContact: (_id, payload) => {
					sent = payload as Record<string, unknown>;
					return {};
				},
			});
			const out = await updateContact({ client, db: fakeDb().db, now: NOW, user: USER }, { id: 7, ...input });
			return { result: out.result as Record<string, unknown>, sent };
		};
		const wien = await lauf({ office_country: "Österreich" }, { phone_office: "01 2345678" });
		expect(wien.sent).toEqual({ office_phone: "+43 1 2345678" });
		expect(wien.result).toMatchObject({ phone_adjusted: ["phone_office: „01 2345678“ → „+43 1 2345678“ (auf +43 umgestellt)"], updated: true });
		// kein Land gespeichert: als deutsche Nummer gewertet
		const ohne = await lauf({}, { phone_office: "0221 4710199" });
		expect(ohne.sent).toEqual({ office_phone: "+49 221 4710199" });
		expect((ohne.result.phone_adjusted as string[])[0]).toContain("kein Land angegeben, als deutsche Nummer gewertet");
		// das im selben Aufruf angegebene Land geht dem gespeicherten vor
		const umzug = await lauf({ office_country: "Österreich" }, { country: "Schweiz", phone_office: "044 123 45 67" });
		expect(umzug.sent).toMatchObject({ office_country: "Schweiz", office_phone: "+41 44 123 45 67" });
		// steht die Nummer schon so da, wird nichts geschrieben
		const gleich = await lauf({ office_phone: "+49 221 4710199" }, { phone_office: "0221 4710199" });
		expect(gleich.sent).toEqual({});
		expect(gleich.result).toMatchObject({ updated: false });
	});

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

	it("Notiz wird nicht doppelt angehängt, wenn derselbe Text schon dasteht", async () => {
		const noted = { ...current, description: "Alte Notiz\n\nErgänzt über Claude (Propstack MCP) von Lena Klinnert am 2026-09-01.\nRückruf vereinbart" };
		let sent: Record<string, unknown> | undefined;
		const { client, calls } = fakeClient({
			getContact: () => ({ ...noted, ...(sent ?? {}) }),
			updateContact: (_id, payload) => {
				sent = payload as Record<string, unknown>;
				return {};
			},
		});
		const deps = { client, db: fakeDb().db, now: NOW, user: USER };
		// nur die Notiz, die schon dasteht → gar kein Write
		const same = await updateContact(deps, { id: 7, note_append: "Rückruf vereinbart" });
		expect(same.result).toMatchObject({ already_present: ["note_append (steht schon in der Notiz)"], updated: false });
		expect(calls.some((c) => c.method === "updateContact")).toBe(false);
		// zusammen mit einer echten Änderung: die Änderung wird geschrieben, die Notiz nicht
		const mixed = await updateContact(deps, { id: 7, note_append: "Rückruf vereinbart", position: "CFO" });
		expect(sent).toEqual({ position: "CFO" });
		expect(mixed.result).toMatchObject({ already_present: ["note_append (steht schon in der Notiz)"], changed: ["position"], updated: true });
		// ein anderer Text wird angehängt
		await updateContact(deps, { id: 7, note_append: "Rückruf am 12.11. erledigt" });
		expect(String(sent?.description)).toMatch(/Rückruf vereinbart\n\nErgänzt über Claude .* am 2026-10-14\.\nRückruf am 12\.11\. erledigt$/);
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
		// beim Ändern heißt es „updated: false“ – nicht „created: false“ wie beim Anlegen
		expect(out.result).toMatchObject({ blocked: "Dublette", updated: false });
		expect(out.result).not.toHaveProperty("created");
		expect(calls.some((c) => c.method === "updateContact")).toBe(false);
	});

	// Live-Befund 12.11.2026: Propstack speichert als Kontaktstatus und als Quelle jede Zahl – auch 999999999.
	// Erkennbar beim Gegenlesen: Nur zu einer gültigen ID liefert Propstack das zugehörige Objekt mit.
	describe("Kontaktstatus und Quelle, die es nicht gibt", () => {
		/** Propstack wie live: speichert jede ID, liefert das Objekt dazu aber nur für bekannte IDs. */
		function propstack(start: Record<string, unknown>, bekannt: { status?: number[]; quelle?: number[] } = {}) {
			let stand: Record<string, unknown> = { ...start };
			const puts: Record<string, unknown>[] = [];
			const lesen = () => ({
				...stand,
				client_source: (bekannt.quelle ?? []).includes(stand.client_source_id as number) ? { id: stand.client_source_id, name: "Homepage" } : null,
				client_status: (bekannt.status ?? []).includes(stand.client_status_id as number) ? { id: stand.client_status_id, name: "Aktiv" } : null,
			});
			const { client } = fakeClient({
				getContact: lesen,
				updateContact: (_id, payload) => {
					puts.push(payload as Record<string, unknown>);
					stand = { ...stand, ...(payload as Record<string, unknown>) };
					return {};
				},
			});
			return { client, lesen, puts };
		}

		it("ungültiger Status: wird zurückgenommen (Feld geleert), steht unter not_applied und nicht unter changed", async () => {
			const { db, updates } = fakeDb();
			const p = propstack({ id: 7, name: "Anna Muster", position: "CEO" });
			const out = await updateContact({ client: p.client, db, now: NOW, user: USER }, { client_status_id: 999999999, id: 7, position: "CFO" });
			expect(p.puts).toEqual([{ client_status_id: 999999999, position: "CFO" }, { client_status_id: null }]);
			expect(p.lesen()).toMatchObject({ client_status_id: null, position: "CFO" });
			expect(out.result).toMatchObject({
				changed: ["position"],
				not_applied: ["client_status_id (Den Kontaktstatus 999999999 gibt es in Propstack nicht – nicht übernommen)"],
				updated: true,
			});
			// im Write-Log als Lücke vermerkt
			expect(JSON.stringify(updates)).toMatch(/done_with_gaps/);
		});

		it("ungültige Quelle: der vorherige gültige Wert wird wiederhergestellt", async () => {
			const p = propstack({ client_source_id: 211511, id: 7, name: "Anna Muster" }, { quelle: [211511] });
			const out = await updateContact({ client: p.client, db: fakeDb().db, now: NOW, user: USER }, { id: 7, source_id: 999999999 });
			expect(p.puts).toEqual([{ client_source_id: 999999999 }, { client_source_id: 211511 }]);
			// nichts hat sich geändert → updated: false (live am 12.11.2026 stand hier noch „updated: true“ bei leerem changed)
			expect(out.result).toMatchObject({
				changed: [],
				not_applied: ["client_source_id (Die Kontakt-Quelle 999999999 gibt es in Propstack nicht – nicht übernommen, vorheriger Wert wiederhergestellt)"],
				updated: false,
			});
		});

		it("war schon der vorherige Wert ungültig, wird das Feld geleert statt den Müll wiederherzustellen", async () => {
			const p = propstack({ client_status_id: 999999999, id: 7, name: "Anna Muster" });
			await updateContact({ client: p.client, db: fakeDb().db, now: NOW, user: USER }, { client_status_id: 888888888, id: 7 });
			expect(p.puts).toEqual([{ client_status_id: 888888888 }, { client_status_id: null }]);
		});

		it("gültige Werte bleiben stehen – kein zweiter Schreibvorgang", async () => {
			const p = propstack({ id: 7, name: "Anna Muster" }, { quelle: [211511], status: [42] });
			const out = await updateContact({ client: p.client, db: fakeDb().db, now: NOW, user: USER }, { client_status_id: 42, id: 7, source_id: 211511 });
			expect(p.puts).toEqual([{ client_source_id: 211511, client_status_id: 42 }]);
			expect(out.result).toMatchObject({ changed: ["client_source_id", "client_status_id"], updated: true });
			expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
		});

		it("Status gilt auch als gültig, wenn Propstack ihn im Feld status statt client_status mitliefert", async () => {
			const puts: Record<string, unknown>[] = [];
			const { client } = fakeClient({
				getContact: () => ({ client_status: null, client_status_id: puts.length ? 42 : null, id: 7, name: "Anna Muster", status: puts.length ? { id: 42, name: "Aktiv" } : {} }),
				updateContact: (_id, payload) => {
					puts.push(payload as Record<string, unknown>);
					return {};
				},
			});
			const out = await updateContact({ client, db: fakeDb().db, now: NOW, user: USER }, { client_status_id: 42, id: 7 });
			expect(puts).toEqual([{ client_status_id: 42 }]);
			expect(out.result).toMatchObject({ changed: ["client_status_id"], updated: true });
		});

		it("schlägt das Zurücksetzen fehl, steht das in der Meldung", async () => {
			let aufrufe = 0;
			const { client } = fakeClient({
				getContact: () => ({ client_status: null, client_status_id: aufrufe ? 999999999 : null, id: 7, name: "Anna Muster" }),
				updateContact: () => {
					if (++aufrufe === 2) throw new PropstackError("Propstack-Serverfehler (502)", 502);
					return {};
				},
			});
			const out = await updateContact({ client, db: fakeDb().db, now: NOW, user: USER }, { client_status_id: 999999999, id: 7 });
			expect((out.result as { not_applied: string[] }).not_applied[0]).toBe(
				"client_status_id (Den Kontaktstatus 999999999 gibt es in Propstack nicht – nicht übernommen) – das Zurücksetzen ist fehlgeschlagen (Propstack-Serverfehler (502)), bitte in Propstack prüfen",
			);
		});

		it("beim Anlegen: ungültige Quelle wird geleert und gemeldet, der Kontakt bleibt angelegt", async () => {
			const puts: Record<string, unknown>[] = [];
			const { client } = fakeClient({
				createContact: () => ({ id: 77 }),
				getContact: () => ({ broker_id: USER.brokerId, client_source: null, client_source_id: 999999999, id: 77, last_name: "Neu", name: "Neu" }),
				updateContact: (_id, payload) => {
					puts.push(payload as Record<string, unknown>);
					return {};
				},
			});
			const out = await createContact({ client, db: fakeDb().db, now: NOW, user: USER }, { last_name: "Neu", source_id: 999999999 });
			expect(puts).toEqual([{ client_source_id: null }]);
			expect(out.result).toMatchObject({ created: true, id: 77, not_applied: ["client_source_id (Die Kontakt-Quelle 999999999 gibt es in Propstack nicht – nicht übernommen)"] });
		});
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
			// Kategorie: Propstack leitet sie beim Schreiben der Objektart ab – bei Grundstück (TRADE_SITE) aber als „Wohnen“
			// (live 13.11.2026, Testobjekt 6396742: COMMERCIAL → LIVING). Direkt gesetzt bleibt sie stehen.
			if ("rs_type" in payload && !("object_type" in payload)) {
				stored.object_type = ["INDUSTRY", "OFFICE", "STORE", "GASTRONOMY", "SPECIAL_PURPOSE"].includes(String(payload.rs_type)) ? "COMMERCIAL" : "LIVING";
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
			{ ...input, custom_fields: { lagerflache: 4800 }, hall_height: 10, industrial_area: 5000, usable_floor_space: 400 },
		);
		expect(unit.posted().partial_custom_fields).toMatchObject({
			buroflache: 400,
			// Gesamtfläche = Halle (+ Mezzanine), die 400 m² Büro zählen nicht mit
			gebaudeflache_gesamt: 5000,
			gebaudeflache_verfugbar: 5000,
			hallenhohe: 10,
			lagerflache: 4800, // explizit übergeben hat Vorrang
			lagerflache_gesamt: 5000,
			lagerflache_verfugbar: "5.000 m²",
			preisangabe: "auf Anfrage",
		});
		expect(unit.posted().partial_custom_fields).not.toHaveProperty("mezzanineflache");
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
	});

	it("Gesamtfläche beim Anlegen: immer gerechnet, eine mitgegebene Summe inklusive Büro wird abgewiesen", async () => {
		const unit = fakeUnit();
		const { client } = fakeClient(unit.impl);
		const deps = { client, db: fakeDb().db, now: NOW, sleep, user: USER };
		// So entstand der Fehler im Mileway-Lauf vom 09.11.2026: Halle + Büro als Gesamtfläche
		await expect(createObject(deps, { ...input, industrial_area: 5000, total_floor_space: 5400, usable_floor_space: 400 })).rejects.toThrow(
			/Die Gesamtfläche rechnet der Connector immer selbst: Hallenfläche 5\.000 m² \+ Mezzanine 0 m² = 5\.000 m² \(ohne Büro\)\. Angegeben waren 5\.400 m²/,
		);
		expect(unit.posted()).toEqual({}); // nichts angelegt
		// Der richtige Wert darf mitkommen (ältere Tool-Listen schicken ihn noch)
		const out = await createObject(deps, { ...input, industrial_area: 5000, total_floor_space: 5000, usable_floor_space: 400 });
		expect(unit.stored.total_floor_space).toBe(5000);
		expect((out.result as { derived?: string[] }).derived).toBeUndefined();
		// Ohne Hallenfläche gilt die Regel nicht, z. B. bei einer reinen Bürofläche
		const office = fakeUnit();
		const officeClient = fakeClient(office.impl).client;
		await createObject({ ...deps, client: officeClient }, { ...input, rs_type: "OFFICE", total_floor_space: 199, usable_floor_space: 199 });
		expect(office.stored.total_floor_space).toBe(199);
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

	it("Grundstück: Propstack trägt als Kategorie „Wohnen“ ein – der Connector setzt „Gewerbe“ nach und sagt es (Befund 13.11.2026)", async () => {
		const unit = fakeUnit();
		const { client } = fakeClient(unit.impl);
		const { db, rows } = fakeDb();
		const out = await createObject({ client, db, now: NOW, sleep, user: USER }, { ...input, rs_category: "TRADE_SITE", rs_type: "TRADE_SITE" });
		// die Kategorie wird einzeln geschrieben – nach Objektart und Unterart, damit Propstack sie nicht wieder ableitet
		expect(unit.puts).toContainEqual({ object_type: "COMMERCIAL" });
		expect(unit.puts.findIndex((p) => "object_type" in p)).toBeGreaterThan(unit.puts.findIndex((p) => "rs_category" in p));
		expect(unit.stored).toMatchObject({ object_type: "COMMERCIAL", rs_category: "TRADE_SITE", rs_type: "TRADE_SITE" });
		expect(out.result).toMatchObject({ category_note: "Kategorie Gewerbe gesetzt – Propstack hatte zur Objektart TRADE_SITE „Wohnen“ eingetragen.", created: true });
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();
		expect(JSON.parse(rows[0][8] as string)).toMatchObject({ kategorie_sicherstellen: "COMMERCIAL" });
	});

	it("Halle: Die Kategorie stimmt schon – kein zusätzlicher Schreibzugriff, kein Hinweis", async () => {
		const unit = fakeUnit();
		const { client } = fakeClient(unit.impl);
		const out = await createObject({ client, db: fakeDb().db, now: NOW, sleep, user: USER }, input);
		expect(unit.puts.some((p) => "object_type" in p)).toBe(false);
		expect(out.result as Record<string, unknown>).not.toHaveProperty("category_note", expect.anything());
	});

	it("update_object: Wechsel der Objektart auf Grundstück zieht die Kategorie nach; dieselbe Objektart erneut genannt berichtigt einen Altfall", async () => {
		const unit = fakeUnit();
		Object.assign(unit.stored, { marketing_type: "RENT", object_type: "COMMERCIAL", rs_category: "HALL", rs_type: "INDUSTRY", title: "Alt" });
		const { client } = fakeClient(unit.impl);
		const { db, rows } = fakeDb();
		const out = await updateObject({ client, db, now: NOW, sleep, user: USER }, { id: 900, rs_category: "TRADE_SITE", rs_type: "TRADE_SITE" });
		expect(unit.puts).toEqual([{ rs_type: "TRADE_SITE" }, { rs_category: "TRADE_SITE" }, { object_type: "COMMERCIAL" }]);
		expect(unit.stored).toMatchObject({ object_type: "COMMERCIAL", rs_category: "TRADE_SITE", rs_type: "TRADE_SITE" });
		expect(out.result).toMatchObject({ updated: true, warnings: ["Kategorie Gewerbe gesetzt – Propstack hatte zur Objektart TRADE_SITE „Wohnen“ eingetragen."] });
		expect((out.result as { changed: string[] }).changed).toEqual(["rs_type", "rs_category", "object_type (Kategorie)"]);
		expect(JSON.parse(rows[0][8] as string)).toMatchObject({ kategorie_sicherstellen: "COMMERCIAL" });

		// Altfall: Grundstück steht auf Wohnen (so angelegt mit Connector bis v0.12.1) – rs_type erneut nennen genügt
		const alt = fakeUnit();
		Object.assign(alt.stored, { marketing_type: "RENT", object_type: "LIVING", rs_category: "TRADE_SITE", rs_type: "TRADE_SITE", title: "Alt" });
		const zweiter = fakeDb();
		const again = await updateObject({ client: fakeClient(alt.impl).client, db: zweiter.db, now: NOW, sleep, user: USER }, { id: 900, rs_type: "TRADE_SITE" });
		expect(alt.puts).toEqual([{ object_type: "COMMERCIAL" }]);
		expect(again.result).toMatchObject({ changed: ["object_type (Kategorie)"], updated: true });
		// Stand vorher steht im Write-Log
		expect(JSON.parse(zweiter.rows[0][7] as string)).toMatchObject({ object_type: "LIVING" });

		// stimmt die Kategorie schon und ändert sich sonst nichts: kein Schreibzugriff
		const passt = fakeUnit();
		Object.assign(passt.stored, { marketing_type: "RENT", object_type: "COMMERCIAL", rs_category: "TRADE_SITE", rs_type: "TRADE_SITE", title: "Alt" });
		const nichts = await updateObject({ client: fakeClient(passt.impl).client, db: fakeDb().db, now: NOW, sleep, user: USER }, { id: 900, rs_type: "TRADE_SITE" });
		expect(passt.puts).toEqual([]);
		expect(nichts.result).toMatchObject({ updated: false });
	});

	it("update_object ohne Objektart lässt die Kategorie in Ruhe – auch wenn sie nicht zur Objektart passt", async () => {
		const unit = fakeUnit();
		Object.assign(unit.stored, { marketing_type: "RENT", object_type: "LIVING", rs_category: "TRADE_SITE", rs_type: "TRADE_SITE", title: "Alt" });
		const out = await updateObject({ client: fakeClient(unit.impl).client, db: fakeDb().db, now: NOW, sleep, user: USER }, { id: 900, plot_area: 12000 });
		expect(unit.puts.some((p) => "object_type" in p)).toBe(false);
		expect(out.result).toMatchObject({ updated: true });
	});

	it("hält die Kategorie nicht, steht das unter not_applied statt eines stillen Erfolgs", async () => {
		const unit = fakeUnit();
		Object.assign(unit.stored, { marketing_type: "RENT", object_type: "LIVING", rs_category: "TRADE_SITE", rs_type: "TRADE_SITE", title: "Alt" });
		const impl = { ...unit.impl, updateUnit: (_id: unknown, payload: unknown) => unit.puts.push(payload as Record<string, unknown>) }; // Propstack nimmt an, speichert aber nicht
		const { db, updates } = fakeDb();
		const out = await updateObject({ client: fakeClient(impl).client, db, now: NOW, sleep, user: USER }, { id: 900, rs_type: "TRADE_SITE" });
		expect((out.result as { not_applied?: string[] }).not_applied).toEqual(["object_type (Kategorie Gewerbe – Propstack zeigt weiter „Wohnen“)"]);
		expect(JSON.stringify(updates)).toMatch(/done_with_gaps/);
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
					// „Bezug“ folgt „Verfügbar ab“
					bezug: "vermietet",
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
		// Die fehlende Gesamtfläche wird dabei gleich mitgerechnet (Halle + Mezzanine) und gespiegelt
		expect(unit.puts).toEqual([
			{ partial_custom_fields: { gebaudeflache_gesamt: 5000, gebaudeflache_verfugbar: 5000, lagerflache_gesamt: 5000, lagerflache_verfugbar: "5.000 m²" } },
			{ total_floor_space: 5000 },
		]);
		expect(out.result).toMatchObject({ updated: true });
		// Zweiter Aufruf mit denselben Werten: nichts mehr zu schreiben
		const again = unit.puts.length;
		await updateObject({ client, db: fakeDb().db, now: NOW, sleep, user: USER }, { id: 900, industrial_area: 5000 });
		expect(unit.puts.length).toBe(again);
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
		// … und zusätzlich im Feld „Provision interne Notiz“ (Feld-Mapping, Korrektur 29)
		expect((w.posted().partial_custom_fields as Record<string, unknown>).provision_interne_notiz).toBe("Tischregel 50/50");
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

	it("übernimmt Propstack die interne Notiz nicht: kein Ausweichen ins Feld „Bemerkung“ – der Text steht im Hinweis und in der Prüfaufgabe", async () => {
		const w = world(PROJECT, { dropNote: true });
		const out = await createObject({ client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER }, { ...standalone, mandate: "Alleinmandat" });
		// einzeln nachgesetzt …
		expect(w.puts).toEqual(expect.arrayContaining([{ note: "Angelegt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-14.\nMandat: Alleinmandat" }]));
		// … aber nie in die Bemerkung geschrieben: dort stehen nur Änderungsvermerke, das Feld liest kaum jemand
		// (Entscheidung Florian, 10.11.2026)
		expect(w.puts.some((p) => "partial_custom_fields" in p)).toBe(false);
		expect(w.custom.bemerkung).toBe("Angelegt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-14.");
		const result = out.result as { internal_note_hint: string; not_applied: string[] };
		expect(result.internal_note_hint).toMatch(/nicht übernommen – bitte von Hand unter „Interne Notizen“ eintragen:\nMandat: Alleinmandat/);
		expect(result.not_applied).toContain("note");
		// der Text geht nicht verloren: er steht in der Prüfaufgabe
		expect(String(w.task()!.body)).toMatch(/Mandat: Alleinmandat/);
	});

	it("Provision gehört vollständig auf jede Einheit (Feld-Mapping, Korrektur 29): „Provision extern“ und „Provision interne Notiz“", async () => {
		const w = world();
		const out = await createObject(
			{ client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER },
			{ ...standalone, commission: "provisionsfrei", internal_commission: "Provisionsfrei bestätigt (Eigentümer, 10.11.2026)" },
		);
		const custom = w.posted().partial_custom_fields as Record<string, unknown>;
		expect(custom).toMatchObject({ provision_extern: "Provisionsfrei", provision_interne_notiz: "Provisionsfrei bestätigt (Eigentümer, 10.11.2026)" });
		// nie gesetzt: bricht eine Automatisierung bzw. ist im Bestand ungenutzt
		for (const key of ["provisionspflichtig", "provision", "provision_intern"]) expect(custom).not.toHaveProperty(key);
		// die Regelung steht auch in der internen Notiz (How-to)
		expect(String(w.posted().note)).toMatch(/Provision intern: Provisionsfrei bestätigt \(Eigentümer, 10\.11\.2026\)/);
		const result = out.result as { howto_not_provided: string[]; mirrored_custom_fields: string[] };
		expect(result.howto_not_provided).not.toContain("Provisionsregelung intern (Herkunft der Provisionsaussage, Sonderregeln)");
		expect(result.mirrored_custom_fields).toEqual(expect.arrayContaining(["provision_extern", "provision_interne_notiz"]));
	});

	it("Staffel → „provisionspflichtig für den Mieter“; eine Einheit im Projekt übernimmt die Aussage des Projekts; Kauf bleibt unberührt", async () => {
		const deps = (w: ReturnType<typeof world>) => ({ client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER });
		const scale = world();
		await createObject(deps(scale), { ...standalone, commission: "staffel" });
		expect((scale.posted().partial_custom_fields as Record<string, unknown>).provision_extern).toBe("provisionspflichtig für den Mieter");

		// Einheit im Projekt: die Provision kommt vom Projekt („Provisionsfrei“) – das Custom-Feld folgt
		const inProject = world();
		const unit = await createObject(deps(inProject), { industrial_area: 10000, marketing_type: "RENT", project_id: 604473, rs_type: "INDUSTRY", unit_id: "Unit 1" });
		expect((inProject.posted().partial_custom_fields as Record<string, unknown>).provision_extern).toBe("Provisionsfrei");
		// fehlt die interne Regelung, steht das unter „nicht angegeben“ – auch bei Einheiten im Projekt
		expect((unit.result as { howto_not_provided: string[] }).howto_not_provided).toContain("Provisionsregelung intern (Herkunft der Provisionsaussage, Sonderregeln)");

		// Kauf: „für den Mieter“ passt nicht → das Feld bleibt leer
		const sale = world();
		await createObject(deps(sale), { ...standalone, courtage: "Provisionspflichtig", marketing_type: "BUY" });
		expect(sale.posted().partial_custom_fields).not.toHaveProperty("provision_extern");
	});

	it("update_object: geänderte Provision zieht „Provision extern“ nach; Staffel bei stehendem „Provisionsfrei“ wird abgewiesen", async () => {
		const w = world();
		Object.assign(w.stored, { courtage: "Provisionsfrei", marketing_type: "RENT", title: "Halle" });
		Object.assign(w.custom, { provision_extern: "Provisionsfrei" });
		const deps = { client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER };
		// das How-to nennt für provisionspflichtige Objekte keinen Text für die Außenprovision → der Nutzer muss ihn ansagen
		await expect(updateObject(deps, { commission: "staffel", id: 900 })).rejects.toThrow(/widerspricht der Staffel/);
		expect(w.puts).toEqual([]);

		const out = await updateObject(deps, { commission: "staffel", courtage: "Provisionspflichtig", id: 900, internal_commission: "Tischregel, gedeckelt bei 3 NKM" });
		expect(w.stored.courtage).toBe("Provisionspflichtig");
		expect(w.custom).toMatchObject({ provision_extern: "provisionspflichtig für den Mieter", provision_interne_notiz: "Tischregel, gedeckelt bei 3 NKM" });
		expect(String(w.stored.note)).toMatch(/Provision intern: Tischregel, gedeckelt bei 3 NKM/);
		expect((out.result as { changed: string[] }).changed).toEqual(expect.arrayContaining(["custom_fields.provision_extern", "custom_fields.provision_interne_notiz"]));

		// ohne Änderung an der Provision bleibt „Provision extern“ unberührt
		w.puts.length = 0;
		await updateObject(deps, { free_from: "sofort", id: 900 });
		expect(w.puts).toEqual([{ free_from: "sofort", partial_custom_fields: { bezug: "sofort" } }]);

		// internal_commission und das Custom-Feld zugleich: Widerspruch
		await expect(updateObject(deps, { custom_fields: { provision_interne_notiz: "x" }, id: 900, internal_commission: "y" })).rejects.toThrow(/gleichzeitig angegeben/);
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
		// Hallenfläche geändert → die Gesamtfläche wird neu gerechnet, nicht nur angemahnt
		const recalculated = await updateObject(deps, { id: 900, industrial_area: 9000 });
		expect(w.stored).toMatchObject({ industrial_area: 9000, total_floor_space: 9000 });
		expect((recalculated.result as { changed: string[] }).changed).toEqual(expect.arrayContaining(["industrial_area", "total_floor_space"]));
	});

	it("Gesamtfläche wird immer aus Halle + Mezzanine gerechnet (Ansage Florian, 10.11.2026)", async () => {
		const w = world();
		// Altbestand wie im Mileway-Lauf: Büro in der Gesamtfläche, Mezzanine als Text im Custom-Feld
		Object.assign(w.stored, { industrial_area: 5165, marketing_type: "RENT", rented: false, title: "Halle", total_floor_space: 6585 });
		Object.assign(w.custom, { mezzanineflache_gesamt: "1.050 m²" });
		const deps = { client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER };

		// 1) Nur etwas anderes geändert: Flächen bleiben unberührt, der Widerspruch wird gemeldet
		const untouched = await updateObject(deps, { ground_level_doors: 2, id: 900 });
		expect(w.stored.total_floor_space).toBe(6585);
		expect((untouched.result as { warnings: string[] }).warnings.join(" ")).toMatch(/Gesamtfläche \(6\.585 m²\) ist nicht Hallenfläche \+ Mezzanine \(6\.215 m²\)/);

		// 2) Ein abweichender Wert wird abgewiesen, nichts geschrieben
		const putsBefore = w.puts.length;
		await expect(updateObject(deps, { id: 900, total_floor_space: 6585 })).rejects.toThrow(
			/rechnet der Connector immer selbst: Hallenfläche 5\.165 m² \+ Mezzanine 1\.050 m² = 6\.215 m²/,
		);
		expect(w.puts.length).toBe(putsBefore);

		// 3) Hallenfläche gesetzt → Gesamtfläche = neue Halle + gespeicherte Mezzanine
		const hall = await updateObject(deps, { id: 900, industrial_area: 4115 });
		expect(w.stored).toMatchObject({ industrial_area: 4115, total_floor_space: 5165 });
		expect((hall.result as { changed: string[] }).changed).toEqual(expect.arrayContaining(["industrial_area", "total_floor_space"]));
		expect(w.custom).toMatchObject({ gebaudeflache_gesamt: 5165 });

		// 4) Mezzanine gesetzt → Gesamtfläche = gespeicherte Halle + neue Mezzanine
		await updateObject(deps, { id: 900, mezzanine_area: 1375 });
		expect(w.stored.total_floor_space).toBe(5490);

		// 5) Der gerechnete Wert darf mitgegeben werden – so lässt sich ein Altbestand sofort berichtigen
		w.stored.total_floor_space = 9999;
		await updateObject(deps, { id: 900, total_floor_space: 5490 });
		expect(w.stored.total_floor_space).toBe(5490);

		// 6) Mezzanine über custom_fields geleert → Gesamtfläche = Halle
		await updateObject(deps, { custom_fields: { mezzanineflache_gesamt: null }, id: 900 });
		expect(w.stored.total_floor_space).toBe(4115);

		// 7) Steht im Mezzanine-Feld ein Text statt einer Zahl, wird nicht gerechnet, sondern nachgefragt
		w.custom.mezzanineflache_gesamt = "ca. 1.000 m²";
		const before = w.puts.length;
		await expect(updateObject(deps, { id: 900, industrial_area: 4200 })).rejects.toThrow(/gespeicherte Mezzaninefläche \(„ca\. 1\.000 m²“\) ist keine lesbare Zahl/);
		expect(w.puts.length).toBe(before);
		// andere Änderungen gehen weiter, ohne falschen Alarm zur Gesamtfläche
		const other = await updateObject(deps, { ground_level_doors: 3, id: 900 });
		expect(JSON.stringify((other.result as { warnings?: string[] }).warnings ?? [])).not.toMatch(/Gesamtfläche/);
		// mit ausdrücklicher Mezzanine wird gerechnet
		await updateObject(deps, { id: 900, industrial_area: 4200, mezzanine_area: 1000 });
		expect(w.stored).toMatchObject({ industrial_area: 4200, total_floor_space: 5200 });
	});

	it("„Bezug“ und „Bezug (Datum)“ folgen „Verfügbar ab“ (Ansage Florian, 11.11.2026)", async () => {
		const w = world();
		// Stand wie nach dem Hillwood-Update vom 10.11.: „Verfügbar ab“ gepflegt, „Bezug“ alt
		Object.assign(w.stored, { free_from: "Q1 2027", marketing_type: "RENT", rented: false, title: "Halle" });
		Object.assign(w.custom, { bezug: "Q1 2027" });
		const deps = { client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER };
		const lastPut = () => w.puts[w.puts.length - 1];

		// 1) Datum: Text nach „Bezug“, Datum nach „Bezug (Datum)“
		const dated = await updateObject(deps, { free_from: "01.04.2027", id: 900 });
		expect(lastPut()).toEqual({ free_from: "01.04.2027", partial_custom_fields: { bezug: "01.04.2027", bezug_datum: "2027-04-01" } });
		expect((dated.result as { changed: string[] }).changed).toEqual(["free_from", "custom_fields.bezug", "custom_fields.bezug_datum"]);

		// 2) Kein Datum mehr im Text: das alte Datum wird geleert, nicht stehen gelassen
		await updateObject(deps, { free_from: "Q3 2027", id: 900 });
		expect(lastPut()).toEqual({ free_from: "Q3 2027", partial_custom_fields: { bezug: "Q3 2027", bezug_datum: null } });

		// 3) Altbestand: „Verfügbar ab“ stimmt schon, „Bezug“ ist leer → der unveränderte Wert zieht „Bezug“ nach
		w.custom.bezug = null;
		const healed = await updateObject(deps, { free_from: "Q3 2027", id: 900 });
		expect(lastPut()).toEqual({ partial_custom_fields: { bezug: "Q3 2027" } });
		expect((healed.result as { changed: string[] }).changed).toEqual(["custom_fields.bezug"]);
		// … und beim nächsten Mal gibt es nichts mehr zu tun
		expect((await updateObject(deps, { free_from: "Q3 2027", id: 900 })).result).toMatchObject({ updated: false });

		// 4) Ein Aufruf ohne free_from lässt „Bezug“ in Ruhe
		w.custom.bezug = "abweichend";
		const before = w.puts.length;
		await updateObject(deps, { ground_level_doors: 2, id: 900 });
		expect(JSON.stringify(w.puts.slice(before))).not.toContain("bezug");
		expect(w.custom.bezug).toBe("abweichend");

		// 5) Vermietet: „Verfügbar ab“ und „Bezug“ = „vermietet“, ein Datum verschwindet
		w.custom.bezug_datum = "2027-04-01";
		await updateObject(deps, { id: 900, rented: true });
		expect(w.stored.free_from).toBe("vermietet");
		expect(w.custom).toMatchObject({ bezug: "vermietet", bezug_datum: null });

		// 6) Wieder verfügbar ohne free_from: Hinweis, dass „vermietet“ noch dasteht
		const back = await updateObject(deps, { id: 900, rented: false });
		expect((back.result as { warnings: string[] }).warnings.join(" ")).toMatch(/„Verfügbar ab“ steht aber noch auf „vermietet“ – bitte free_from angeben/);
		// mit free_from ist alles stimmig, kein Hinweis
		w.stored.rented = true;
		const available = await updateObject(deps, { free_from: "sofort", id: 900, rented: false });
		expect(w.stored.free_from).toBe("sofort");
		expect(w.custom.bezug).toBe("sofort");
		expect(JSON.stringify((available.result as { warnings?: string[] }).warnings ?? [])).not.toMatch(/vermietet/);

		// 7) Ausdrücklich abweichendes „Bezug“: wird geschrieben wie angegeben – aber gemeldet
		const explicit = await updateObject(deps, { custom_fields: { bezug: "Frühjahr 2027" }, free_from: "01.04.2027", id: 900 });
		expect(w.custom).toMatchObject({ bezug: "Frühjahr 2027", bezug_datum: "2027-04-01" });
		expect((explicit.result as { warnings: string[] }).warnings.join(" ")).toMatch(/„Bezug“ \(„Frühjahr 2027“\) weicht von „Verfügbar ab“ \(„01\.04\.2027“\) ab/);
		// nur „Bezug“ ohne free_from: Abgleich gegen den gespeicherten Wert
		const alone = await updateObject(deps, { custom_fields: { bezug: "Sommer 2027" }, id: 900 });
		expect((alone.result as { warnings: string[] }).warnings.join(" ")).toMatch(/weicht von „Verfügbar ab“ \(„01\.04\.2027“\) ab/);
	});

	it("create_object: „Bezug“ und „Bezug (Datum)“ werden beim Anlegen mitgesetzt", async () => {
		const w = world();
		const out = await createObject(
			{ client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER },
			{ city: "Hillscheid", free_from: "ab 01.07.2027", marketing_type: "RENT", rs_type: "INDUSTRY", street: "Am Scheid", title: "Logistikhalle in (56) Hillscheid", zip_code: "56204" },
		);
		expect(w.custom).toMatchObject({ bezug: "ab 01.07.2027", bezug_datum: "2027-07-01" });
		expect((out.result as { mirrored_custom_fields: string[] }).mirrored_custom_fields).toEqual(expect.arrayContaining(["bezug", "bezug_datum"]));
		expect((out.result as { not_applied?: string[] }).not_applied).toBeUndefined();

		// ohne Datum im Text nur „Bezug“; vermietet angelegt → „vermietet“
		const rented = world();
		await createObject(
			{ client: rented.client, db: fakeDb().db, now: NOW, sleep, user: USER },
			{ city: "Hillscheid", marketing_type: "RENT", rented: true, rs_type: "INDUSTRY", street: "Am Scheid", title: "Logistikhalle in (56) Hillscheid", zip_code: "56204" },
		);
		expect(rented.custom.bezug).toBe("vermietet");
		expect("bezug_datum" in rented.custom).toBe(false);
	});

	it("align_building_area: „Gebäudefläche gesamt“ wird an die Gesamtfläche angeglichen (Entscheidung Florian, 11.11.2026)", async () => {
		const w = world();
		// Stand wie im Hillwood-Bestand seit August 2026: „Gebäudefläche gesamt“ noch inklusive Büro
		Object.assign(w.stored, { industrial_area: 10410, marketing_type: "RENT", rented: false, title: "Halle", total_floor_space: 11269, usable_floor_space: 352 });
		Object.assign(w.custom, { gebaudeflache_gesamt: 11621, mezzanineflache_gesamt: "859 m²" });
		const deps = { client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER };
		const lastPut = () => w.puts[w.puts.length - 1];

		// 1) Nur das eine Feld und ein Vermerk mit altem und neuem Wert; ein leeres „verfügbar“ bleibt leer
		const out = await updateObject(deps, { align_building_area: true, id: 900 });
		expect(lastPut()).toEqual({
			partial_custom_fields: {
				bemerkung: expect.stringMatching(/Gebäudefläche gesamt an die Gesamtfläche angeglichen \(Halle \+ Mezzanine, ohne Büro\): 11\.269 m² statt 11\.621 m²\.$/),
				gebaudeflache_gesamt: 11269,
			},
		});
		expect((out.result as { changed: string[] }).changed).toEqual(["custom_fields.gebaudeflache_gesamt", "bemerkung (angehängt)"]);
		expect("gebaudeflache_verfugbar" in w.custom).toBe(false);
		expect(w.stored.total_floor_space).toBe(11269);

		// 2) Schon angeglichen → nichts zu tun
		const puts = w.puts.length;
		expect((await updateObject(deps, { align_building_area: true, id: 900 })).result).toMatchObject({ updated: false });
		expect(w.puts.length).toBe(puts);

		// 2b) Der Wert wird zurückgestellt (z. B. über undo_plan) und am selben Tag erneut angeglichen: wieder ein Vermerk –
		// das ist eine neue Änderung, kein wiederholter Aufruf (Befund 11.11.2026: vorher blieb der zweite Vermerk aus)
		w.custom.gebaudeflache_gesamt = 11621;
		const repeat = (await updateObject(deps, { align_building_area: true, id: 900 })).result as { changed: string[]; already_present?: string[] };
		expect(repeat.changed).toEqual(["custom_fields.gebaudeflache_gesamt", "bemerkung (angehängt)"]);
		expect(repeat.already_present).toBeUndefined();
		expect(String(w.custom.bemerkung).match(/11\.269 m² statt 11\.621 m²\./g)).toHaveLength(2);
		// Ein mitgegebener Vermerk bleibt dabei doppelt-geschützt: steht er heute schon da, kommt nur der Angleich-Vermerk dazu
		await updateObject(deps, { bemerkung_append: "Flächen laut Exposé geprüft.", id: 900 });
		w.custom.gebaudeflache_gesamt = 11621;
		const mixed = (await updateObject(deps, { align_building_area: true, bemerkung_append: "Flächen laut Exposé geprüft.", id: 900 })).result as {
			changed: string[];
			already_present?: string[];
		};
		expect(mixed.changed).toEqual(["custom_fields.gebaudeflache_gesamt", "bemerkung (angehängt)"]);
		expect(mixed.already_present).toEqual(["bemerkung_append (derselbe Vermerk steht heute schon in der Bemerkung)"]);
		expect(String(w.custom.bemerkung).match(/Flächen laut Exposé geprüft\./g)).toHaveLength(1);
		expect(String(w.custom.bemerkung).match(/11\.269 m² statt 11\.621 m²\./g)).toHaveLength(3);

		// 3) Ist „verfügbar“ schon befüllt und die Einheit nicht vermietet, zieht es mit; bei vermieteten bleibt es stehen
		Object.assign(w.custom, { gebaudeflache_gesamt: 11621, gebaudeflache_verfugbar: 11621 });
		await updateObject({ ...deps, now: () => new Date("2026-10-15T09:00:00Z") }, { align_building_area: true, id: 900 });
		expect(w.custom).toMatchObject({ gebaudeflache_gesamt: 11269, gebaudeflache_verfugbar: 11269 });
		Object.assign(w.custom, { gebaudeflache_gesamt: 11621, gebaudeflache_verfugbar: 11621 });
		w.stored.rented = true;
		await updateObject({ ...deps, now: () => new Date("2026-10-16T09:00:00Z") }, { align_building_area: true, id: 900 });
		expect(w.custom).toMatchObject({ gebaudeflache_gesamt: 11269, gebaudeflache_verfugbar: 11621 });
		w.stored.rented = false;

		// 4) Stimmt die Gesamtfläche selbst nicht, wird nichts weitergetragen – erst berichtigen
		w.stored.total_floor_space = 11621;
		w.custom.gebaudeflache_gesamt = 12000;
		const before = w.puts.length;
		await expect(updateObject(deps, { align_building_area: true, id: 900 })).rejects.toThrow(
			/Gesamtfläche \(11\.621 m²\) ist nicht Hallenfläche \+ Mezzanine \(11\.269 m²\).*total_floor_space: 11269/,
		);
		expect(w.puts.length).toBe(before);
		// … zusammen mit der Berichtigung in einem Aufruf geht es
		await updateObject(deps, { align_building_area: true, id: 900, total_floor_space: 11269 });
		expect(w.stored.total_floor_space).toBe(11269);
		expect(w.custom.gebaudeflache_gesamt).toBe(11269);

		// 5) Mezzanine nicht lesbar oder keine Gesamtfläche → abgewiesen statt geraten
		w.custom.mezzanineflache_gesamt = "ca. 900 m²";
		await expect(updateObject(deps, { align_building_area: true, id: 900 })).rejects.toThrow(/Mezzaninefläche \(„ca\. 900 m²“\) ist keine lesbare Zahl/);
		const empty = world();
		Object.assign(empty.stored, { marketing_type: "RENT", rented: false, title: "Büro" });
		await expect(updateObject({ ...deps, client: empty.client }, { align_building_area: true, id: 900 })).rejects.toThrow(/keine Gesamtfläche gespeichert/);

		// 6) Ein ausdrücklich mitgegebener Wert hat Vorrang (kein automatischer Vermerk)
		const explicit = world();
		Object.assign(explicit.stored, { industrial_area: 5000, marketing_type: "RENT", rented: false, title: "Halle", total_floor_space: 5000 });
		Object.assign(explicit.custom, { gebaudeflache_gesamt: 5400 });
		await updateObject({ ...deps, client: explicit.client }, { align_building_area: true, custom_fields: { gebaudeflache_gesamt: 5100 }, id: 900 });
		expect(explicit.custom.gebaudeflache_gesamt).toBe(5100);
		expect(explicit.custom.bemerkung).toBeUndefined();
	});

	it("Notizen werden nicht doppelt angehängt (Ansage Florian, 11.11.2026)", async () => {
		const w = world();
		Object.assign(w.stored, { marketing_type: "RENT", rented: false, title: "Halle" });
		const deps = { client: w.client, db: fakeDb().db, now: NOW, sleep, user: USER };
		const parking = "Stellplatzmieten laut Hillwood (Mail vom 10.11.2026): Pkw 50 €, Lkw 100 € je Stellplatz und Monat, netto.";
		const vermerk = "Hillwood-Update November 2026: Verfügbarkeit und interne Mieten aktualisiert.";

		// 1) Erster Aufruf: beides wird angehängt
		const first = await updateObject(deps, { bemerkung_append: vermerk, id: 900, internal_note: parking });
		expect((first.result as { changed: string[]; already_present?: string[] }).changed).toEqual(["internal_note (angehängt)", "bemerkung (angehängt)"]);
		expect((first.result as { already_present?: string[] }).already_present).toBeUndefined();
		const note = String(w.stored.note);
		const bemerkung = String(w.custom.bemerkung);
		expect(note).toBe(`Ergänzt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-14.\n${parking}`);

		// 2) Derselbe Aufruf noch einmal (z. B. nach einem verlorenen Aufruf): nichts wird geschrieben
		const puts = w.puts.length;
		const again = await updateObject(deps, { bemerkung_append: vermerk, id: 900, internal_note: parking });
		expect(again.result).toMatchObject({
			already_present: ["internal_note (steht schon in der internen Notiz)", "bemerkung_append (derselbe Vermerk steht heute schon in der Bemerkung)"],
			updated: false,
		});
		expect(w.puts.length).toBe(puts);
		expect(w.stored.note).toBe(note);
		expect(w.custom.bemerkung).toBe(bemerkung);

		// 3) Zusammen mit einer echten Änderung: die Änderung ja, die Notizen nicht
		const mixed = await updateObject(deps, { bemerkung_append: vermerk, ground_level_doors: 2, id: 900, internal_note: parking });
		expect((mixed.result as { changed: string[] }).changed).toEqual(["custom_fields.anzahl_rampentore_2"]);
		expect((mixed.result as { already_present: string[] }).already_present).toHaveLength(2);
		expect(w.stored.note).toBe(note);

		// 4) Nur der neue Teil kommt dazu (Mandat neu, Stellplatzmieten schon da)
		const partly = await updateObject(deps, { id: 900, internal_note: parking, mandate: "kein Alleinmandat" });
		expect(String(w.stored.note)).toBe(`${note}\n\nErgänzt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-14.\nMandat: kein Alleinmandat`);
		expect((partly.result as { already_present: string[] }).already_present).toEqual(["internal_note (1 von 2 Teilen standen schon in der internen Notiz)"]);

		// 5) Ein kurzer Text, der nur Teil einer vorhandenen Zeile ist, gilt nicht als vorhanden
		await updateObject(deps, { id: 900, internal_note: "Stellplatzmieten laut Hillwood" });
		expect(String(w.stored.note)).toMatch(/\nStellplatzmieten laut Hillwood$/);

		// 6) Bemerkung ist ein Änderungsprotokoll: derselbe Vermerk an einem späteren Tag ist ein neuer Eintrag
		const later = await updateObject({ ...deps, now: () => new Date("2026-10-15T09:00:00Z") }, { bemerkung_append: vermerk, id: 900 });
		expect((later.result as { changed: string[] }).changed).toEqual(["bemerkung (angehängt)"]);
		expect(String(w.custom.bemerkung)).toBe(`${bemerkung}\n\nErgänzt über Claude (Propstack MCP) von Florian Brimmers am 2026-10-15.\n${vermerk}`);
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

