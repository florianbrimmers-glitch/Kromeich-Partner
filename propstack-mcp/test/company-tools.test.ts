import { describe, expect, it } from "vitest";
import { companyCore, companyDuplicates, companySearchTerms, findCompanyRecord, strictCompanyName } from "../src/propstack/companies";
import { type Page, PropstackClient, PropstackError, type Query } from "../src/propstack-client";
import { createCompany, createContactLinked, linkContactCompany } from "../src/tools/company-tools";
import { getContact } from "../src/tools/read-tools";

// Firmen-Datensätze und die Verknüpfung Person ↔ Firma (v0.11.0, Entscheidung Florian vom 12.11.2026).
// Die Zeilen in den Tests sind so aufgebaut, wie Propstack sie liefert – nur lesend nachgesehen am 12.11.2026:
//   - Kontakte: is_company, name, company, first_name (Goodman Germany GmbH 17366550, Stefan Prange 35124656)
//   - Suche: jedes Wort der Eingabe muss vorkommen („Goodman Germany AG“ findet „Goodman Germany GmbH“ nicht)
//   - Verknüpfungen: je Verknüpfung zwei Zeilen; GET /v2/relationships?client_id=… liefert nur die der eigenen Seite.
//     Oberfläche (Bildschirmfoto 13.11.2026): Eine Kontaktseite zeigt die Zeilen, in denen der Kontakt der verknüpfte
//     ist – wie GET /v1/contacts/:id?include=relationships. Richtig ist deshalb: Zeile der Person „Mitarbeiter“
//     (erscheint an der Firma), Gegenzeile „Firma“ (erscheint am Kontakt, von Propstack ergänzt, Kategorie 5787).

type Raw = Record<string, unknown>;
const page = (rows: Raw[]): Page => ({ rows, total: rows.length });
const woerter = (text: string) =>
	text
		.toLowerCase()
		.split(/\s+/)
		.map((wort) => wort.replace(/[^a-z0-9äöüß]/g, ""))
		.filter(Boolean);
const USER = { brokerId: 347158, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers" };
const NOW = () => new Date("2026-11-12T18:00:00Z");

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

/** Propstack im Kleinen: Kontakte (V1-Sicht), Verknüpfungen (V2) und ein Mitschnitt aller Aufrufe. */
function welt(start: Raw[] = [], optionen: { v2Key?: boolean } = {}) {
	const kontakte = new Map<number, Raw>(start.map((k) => [k.id as number, { ...k }]));
	const verknuepfungen: Raw[] = [];
	const aufrufe: { methode: string; args: unknown[] }[] = [];
	let naechsteId = 9000;
	const merke = (methode: string, ...args: unknown[]) => aufrufe.push({ args, methode });
	/** Eine Verknüpfung, wie Propstack sie führt: die angelegte Zeile und die Gegenrichtung mit der passenden Bezeichnung. */
	const paar = (von: number, zu: number, id: number, name: string | null = "Mitarbeiter") => {
		const gegen = name === "Firma" ? "Mitarbeiter" : name === "Mitarbeiter" ? "Firma" : null;
		verknuepfungen.push(
			{ client_id: von, id, internal_name: "associate", name, related_client_id: zu, relationship_category_id: null },
			{ client_id: zu, id: id + 1, internal_name: "associate", name: gegen, related_client_id: von, relationship_category_id: 5787 },
		);
	};
	const client = {
		createClientV2: async (payload: Raw) => {
			merke("createClientV2", payload);
			const id = ++naechsteId;
			const { commercial, group_ids, ...rest } = payload;
			kontakte.set(id, { ...rest, groups: ((group_ids as number[]) ?? []).map((g) => ({ id: g })), id, is_company: commercial === true, name: payload.company ?? payload.last_name });
			return { id };
		},
		createGroup: async (...args: unknown[]) => {
			merke("createGroup", ...args);
			return {};
		},
		createRelationshipV2: async (body: Raw) => {
			merke("createRelationshipV2", body);
			const id = 500 + verknuepfungen.length;
			paar(body.client_id as number, body.related_client_id as number, id, body.name as string);
			return { id };
		},
		// wie Propstack: der Kontakt samt den Zeilen, in denen er der verknüpfte ist – das zeigt auch seine Kontaktseite
		getContactRelationships: async (id: number) => {
			merke("getContactRelationships", id);
			const kontakt = kontakte.get(id);
			if (!kontakt) throw new PropstackError("Nicht gefunden (404)", 404);
			const relationships = verknuepfungen
				.filter((v) => v.related_client_id === id)
				.map((v) => ({ client: { id: v.client_id, name: String(kontakte.get(v.client_id as number)?.name ?? "") }, id: v.id, internal_name: v.internal_name, name: v.name, project: null, property: null, related_client: { id, name: kontakt.name } }));
			return { ...structuredClone(kontakt), relationships };
		},
		getContact: async (id: number) => {
			merke("getContact", id);
			const kontakt = kontakte.get(id);
			if (!kontakt) throw new PropstackError("Nicht gefunden (404)", 404);
			return structuredClone(kontakt);
		},
		hasV2Key: optionen.v2Key ?? true,
		listGroups: async () => page([{ id: 722243, name: "MCP-TEST" }]),
		listRelationshipsV2: async (query: Query) => {
			merke("listRelationshipsV2", query);
			return page(verknuepfungen.filter((v) => v.client_id === query.client_id && v.internal_name === query.internal_name));
		},
		searchContacts: async (query: Query) => {
			merke("searchContacts", query);
			// Suche nach Telefonnummer: Kandidaten liefern – verglichen wird im Connector, unabhängig von der Schreibweise
			if (query.phone_number !== undefined) return page([...kontakte.values()].filter((k) => k.office_cell || k.office_phone));
			if (typeof query.q !== "string") return page([]);
			// wie Propstack: jedes Wort der Eingabe muss als Wortanfang in Name oder Firma vorkommen
			const gesucht = woerter(query.q);
			return page([...kontakte.values()].filter((k) => gesucht.length > 0 && gesucht.every((wort) => woerter(`${k.name} ${k.company ?? ""}`).some((w) => w.startsWith(wort)))));
		},
		updateClientV2: async (id: number, payload: Raw) => {
			merke("updateClientV2", id, payload);
			const kontakt = kontakte.get(id)!;
			if (payload.commercial === true) kontakt.is_company = true;
			return {};
		},
	};
	return { aufrufe, client: client as unknown as PropstackClient, kontakte, paar, roh: client, verknuepfungen };
}

const GOODMAN = { company: "Goodman Germany GmbH", id: 17366550, is_company: true, name: "Goodman Germany GmbH" };
const STEFAN = { company: "Goodman Germany GmbH", first_name: "Stefan", id: 35124656, is_company: false, last_name: "Prange", name: "Stefan Prange" };

describe("Firmen-Dubletten", () => {
	it("gleicher Name blockiert – Punkte, Groß-/Kleinschreibung und Rechtsform zählen nicht", () => {
		expect(companyDuplicates("goodman germany", [GOODMAN]).duplicates).toEqual([{ id: 17366550, name: "Goodman Germany GmbH", reason: "gleicher Firmenname" }]);
		expect(companyDuplicates("LIT AG", [{ company: "L.I.T. AG", id: 1, is_company: true, name: "L.I.T. AG" }]).duplicates.map((d) => d.id)).toEqual([1]);
		expect(companyDuplicates("Müller GmbH & Co.KG", [{ company: "Müller GmbH & Co. KG", id: 2, is_company: true, name: "Müller GmbH & Co. KG" }]).duplicates.map((d) => d.id)).toEqual([2]);
		expect(strictCompanyName("L.I.T. AG")).toBe("litag");
	});

	it("Altlast „X (X)“ (Nachname = Firma) wird als dieselbe Firma erkannt", () => {
		const altlast = { company: null, id: 3, is_company: true, name: "ALCARO Invest GmbH (ALCARO Invest GmbH)" };
		expect(companyDuplicates("Alcaro Invest", [altlast]).duplicates.map((d) => d.id)).toEqual([3]);
	});

	it("Personen zählen nicht – auch nicht, wenn sie fälschlich als Firma markiert sind", () => {
		const falschMarkiert = { company: "Goodman Germany GmbH", first_name: "Max", id: 4, is_company: true, name: "Max Muster (Goodman Germany GmbH)" };
		expect(companyDuplicates("Goodman Germany GmbH", [STEFAN, falschMarkiert])).toEqual({ duplicates: [], warnings: [] });
	});

	it("ähnlicher Name (kürzer oder länger) ist ein Hinweis, keine Blockade", () => {
		const r = companyDuplicates("Goodman", [GOODMAN]);
		expect(r.duplicates).toEqual([]);
		expect(r.warnings).toEqual(["Ähnlicher Firmen-Datensatz: Goodman Germany GmbH (17366550) – bitte prüfen, ob es dieselbe Firma ist."]);
		expect(companyDuplicates("Goodman Germany Logistics GmbH", [GOODMAN]).warnings).toHaveLength(1);
		// nur ein Wortanfang reicht nicht: „Good“ ist nicht „Goodman“
		expect(companyDuplicates("Good", [GOODMAN])).toEqual({ duplicates: [], warnings: [] });
		expect(companyDuplicates("Prologis", [GOODMAN])).toEqual({ duplicates: [], warnings: [] });
	});

	it("Suchbegriffe: ganzer Name, Name ohne Rechtsform, erstes Wort – jeder nur einmal", () => {
		expect(companyCore("Goodman Germany GmbH & Co. KG")).toBe("Goodman Germany");
		expect(companyCore("Müller e.K.")).toBe("Müller");
		expect(companySearchTerms("Goodman Germany GmbH & Co. KG")).toEqual(["Goodman Germany GmbH & Co. KG", "Goodman Germany", "Goodman"]);
		expect(companySearchTerms("  goodman   germany ")).toEqual(["goodman germany", "goodman"]);
		expect(companySearchTerms("Goodman")).toEqual(["Goodman"]);
		expect(companySearchTerms("LIT AG")).toEqual(["LIT AG", "LIT"]);
		// ein kurzes erstes Wort („Die“) wäre als Suche wertlos
		expect(companySearchTerms("Die Bahn GmbH")).toEqual(["Die Bahn GmbH", "Die Bahn"]);
		// besteht der Name nur aus einer Rechtsform, bleibt es bei der Eingabe
		expect(companySearchTerms("AG")).toEqual(["AG"]);
	});

	it("findCompanyRecord: nur bei genau einem Treffer", async () => {
		const eine = welt([GOODMAN, STEFAN]);
		expect(await findCompanyRecord(eine.client, "Goodman Germany")).toEqual({ id: 17366550, name: "Goodman Germany GmbH" });
		expect(eine.aufrufe).toEqual([
			{ args: [{ archived: "-1", page: 1, per: 50, q: "Goodman Germany" }], methode: "searchContacts" },
			{ args: [{ archived: "-1", page: 1, per: 50, q: "Goodman" }], methode: "searchContacts" },
		]);
		const zwei = welt([GOODMAN, { ...GOODMAN, id: 99 }]);
		expect(await findCompanyRecord(zwei.client, "Goodman Germany GmbH")).toBeNull();
		expect(await findCompanyRecord(welt([STEFAN]).client, "Goodman Germany GmbH")).toBeNull();
	});

	it("andere Rechtsform in der Eingabe: Die Suche mit dem ganzen Namen findet nichts – die ohne Rechtsform schon", async () => {
		// live 12.11.2026: q „Goodman Germany AG“ → 0 Treffer, q „Goodman Germany“ → Goodman Germany GmbH
		const w = welt([GOODMAN, STEFAN]);
		expect((await w.roh.searchContacts({ q: "Goodman Germany AG" })).rows).toEqual([]);
		expect(await findCompanyRecord(w.client, "Goodman Germany AG")).toEqual({ id: 17366550, name: "Goodman Germany GmbH" });
		expect(await findCompanyRecord(w.client, "Goodman Germany GmbH & Co. KG")).toEqual({ id: 17366550, name: "Goodman Germany GmbH" });
	});
});

describe("create_company", () => {
	it("legt die Firma mit einem Aufruf als Firmen-Datensatz an: Betreuer = Nutzer, Herkunftsnotiz, Test-Merkmal, Write-Log, Gegenlesen", async () => {
		const w = welt([STEFAN]);
		const { db, rows, updates } = fakeDb();
		const out = await createCompany(
			{ client: w.client, db, now: NOW, user: USER },
			{ city: "Köln", country: "Deutschland", description: "Testfirma", house_number: "1a", name: "MCP-TEST Musterfirma GmbH", phone_office: "0221 4710199", street: "Teststraße", test: true, website: "https://example.com", zip_code: "50667" },
		);
		const gesendet = w.aufrufe.find((a) => a.methode === "createClientV2")!.args[0];
		expect(gesendet).toEqual({
			broker_id: 347158,
			commercial: true,
			company: "MCP-TEST Musterfirma GmbH",
			description: "Testfirma\n\nAngelegt über Claude (Propstack MCP) von Florian Brimmers am 2026-11-12.",
			group_ids: [722243],
			office_city: "Köln",
			office_country: "Deutschland",
			office_house_number: "1a",
			office_phone: "+49 221 4710199",
			office_street: "Teststraße",
			office_url: "https://example.com",
			office_zip_code: "50667",
		});
		// kein Nachname (sonst zeigt Propstack „X (X)“) und keine E-Mail
		expect(gesendet).not.toHaveProperty("last_name");
		expect(gesendet).not.toHaveProperty("email");
		expect(out.result).toEqual({
			broker: "Florian Brimmers",
			created: true,
			id: 9001,
			is_company: true,
			name: "MCP-TEST Musterfirma GmbH",
			next: "Personen dieser Firma mit link_contact_company verknüpfen.",
			not_applied: undefined,
			note: undefined,
			override_reason: undefined,
			phone_adjusted: ["phone_office: „0221 4710199“ → „+49 221 4710199“ (auf +49 umgestellt)"],
			test: true,
			warnings: undefined,
		});
		// Write-Log: Eintrag vor dem Schreiben, Abschluss danach
		expect(rows[0].slice(1, 6)).toEqual(["florian.brimmers@kromeichpartner.de", 347158, "create_company", "contact", null]);
		expect(JSON.stringify(updates)).toMatch(/"done"|done/);
		// drei Suchen (ganzer Name, ohne Rechtsform, erstes Wort), ein Schreibzugriff, einmal Gegenlesen
		expect(w.aufrufe.map((a) => a.methode)).toEqual(["searchContacts", "searchContacts", "searchContacts", "createClientV2", "getContact"]);
		expect(w.aufrufe.slice(0, 3).map((a) => (a.args[0] as Raw).q)).toEqual(["MCP-TEST Musterfirma GmbH", "MCP-TEST Musterfirma", "MCP-TEST"]);
	});

	it("die Telefonnummer der Firma wird bereinigt: keine 0 nach der Ländervorwahl", async () => {
		const w = welt();
		const out = await createCompany({ client: w.client, db: fakeDb().db, now: NOW, user: USER }, { name: "Neue Firma GmbH", phone_office: "+49 (0)221 4710199" });
		expect(w.aufrufe.find((a) => a.methode === "createClientV2")!.args[0]).toMatchObject({ office_phone: "+49 221 4710199" });
		expect(out.result).toMatchObject({ created: true, phone_adjusted: ["phone_office: „+49 (0)221 4710199“ → „+49 221 4710199“ (0 nach der Ländervorwahl entfernt)"] });
	});

	it("gibt es die Firma schon, wird nichts angelegt – der vorhandene Datensatz kommt zurück", async () => {
		const w = welt([GOODMAN]);
		const { db, rows } = fakeDb();
		const out = await createCompany({ client: w.client, db, now: NOW, user: USER }, { name: "Goodman Germany" });
		expect(out.result).toMatchObject({ blocked: "Dublette", created: false, duplicates: [{ id: 17366550, name: "Goodman Germany GmbH", reason: "gleicher Firmenname" }] });
		expect(w.aufrufe.every((a) => a.methode === "searchContacts")).toBe(true);
		expect(rows).toEqual([]);
	});

	it("dieselbe Firma mit anderer Rechtsform oder längerem Zusatz wird trotz der wortgenauen Propstack-Suche gefunden", async () => {
		const w = welt([GOODMAN]);
		const deps = { client: w.client, db: fakeDb().db, now: NOW, user: USER };
		for (const name of ["Goodman Germany AG", "Goodman Germany GmbH & Co. KG", "GOODMAN GERMANY"]) {
			expect((await createCompany(deps, { name })).result, name).toMatchObject({ blocked: "Dublette", created: false, duplicates: [{ id: 17366550 }] });
		}
		expect(w.aufrufe.some((a) => a.methode === "createClientV2")).toBe(false);
	});

	it("findet mehr als eine Suche denselben Datensatz, steht der Hinweis trotzdem nur einmal da", async () => {
		// „Goodman Germany Logistics GmbH“ wird über „Goodman Germany“ und über „Goodman“ gefunden
		const lang = { company: "Goodman Germany Logistics GmbH", id: 5, is_company: true, name: "Goodman Germany Logistics GmbH" };
		const out = await createCompany({ client: welt([lang]).client, db: fakeDb().db, now: NOW, user: USER }, { name: "Goodman Germany" });
		expect((out.result as Raw).warnings).toEqual(["Ähnlicher Firmen-Datensatz: Goodman Germany Logistics GmbH (5) – bitte prüfen, ob es dieselbe Firma ist."]);
	});

	it("kürzer benannter Datensatz („Goodman“) taucht über die Suche nach dem ersten Wort als Hinweis auf", async () => {
		// so steht es im Konto: 17366550 „Goodman Germany GmbH“ und 36103370 „Goodman“
		const kurz = { company: "Goodman", id: 36103370, is_company: true, name: "Goodman" };
		const out = await createCompany({ client: welt([kurz]).client, db: fakeDb().db, now: NOW, user: USER }, { name: "Goodman Germany Logistics GmbH" });
		expect(out.result).toMatchObject({ created: true, warnings: ["Ähnlicher Firmen-Datensatz: Goodman (36103370) – bitte prüfen, ob es dieselbe Firma ist."] });
	});

	it("mit Begründung lässt sich eine gleichnamige andere Firma anlegen; eine zu kurze Begründung wird abgewiesen", async () => {
		const w = welt([GOODMAN]);
		const deps = { client: w.client, db: fakeDb().db, now: NOW, user: USER };
		await expect(createCompany(deps, { allow_duplicate_reason: "andere", name: "Goodman Germany GmbH" })).rejects.toThrow(/echte Begründung/);
		const out = await createCompany(deps, { allow_duplicate_reason: "Gleichnamige Firma in Österreich, andere Gesellschaft", name: "Goodman Germany GmbH" });
		expect(out.result).toMatchObject({ created: true, override_reason: "Gleichnamige Firma in Österreich, andere Gesellschaft" });
	});

	it("ähnliche Firma: wird angelegt, der Hinweis steht im Ergebnis", async () => {
		const out = await createCompany({ client: welt([GOODMAN]).client, db: fakeDb().db, now: NOW, user: USER }, { name: "Goodman" });
		expect(out.result).toMatchObject({ created: true, warnings: ["Ähnlicher Firmen-Datensatz: Goodman Germany GmbH (17366550) – bitte prüfen, ob es dieselbe Firma ist."] });
	});

	it("setzt Propstack die Kennzeichnung als Firma nicht, wird sie einzeln nachgesetzt – wie im täglichen Import", async () => {
		const w = welt();
		w.roh.createClientV2 = async (payload: Raw) => {
			w.aufrufe.push({ args: [payload], methode: "createClientV2" });
			w.kontakte.set(9001, { ...payload, id: 9001, is_company: false, name: payload.company });
			return { id: 9001 };
		};
		const out = await createCompany({ client: w.client, db: fakeDb().db, now: NOW, user: USER }, { name: "Neue Firma GmbH" });
		expect(w.aufrufe.find((a) => a.methode === "updateClientV2")!.args).toEqual([9001, { commercial: true, company: "Neue Firma GmbH", last_name: null }]);
		expect(out.result).toMatchObject({ created: true, is_company: true });
		expect((out.result as Raw).not_applied).toBeUndefined();
	});

	it("bleibt der Datensatz trotzdem ohne Kennzeichnung, steht das unter not_applied", async () => {
		const w = welt();
		w.roh.createClientV2 = async (payload: Raw) => {
			w.kontakte.set(9001, { ...payload, id: 9001, is_company: false, name: payload.company });
			return { id: 9001 };
		};
		w.roh.updateClientV2 = async () => ({});
		const { db, updates } = fakeDb();
		const out = await createCompany({ client: w.client, db, now: NOW, user: USER }, { name: "Neue Firma GmbH" });
		expect(out.result).toMatchObject({ created: true, is_company: false, not_applied: ["commercial (der Datensatz ist nicht als Firma gekennzeichnet – bitte in Propstack prüfen)"] });
		expect(JSON.stringify(updates)).toMatch(/done_with_gaps/);
	});

	it("ohne zweiten Schlüssel: klare Meldung, kein Aufruf", async () => {
		const w = welt([], { v2Key: false });
		await expect(createCompany({ client: w.client, db: fakeDb().db, now: NOW, user: USER }, { name: "Neue Firma GmbH" })).rejects.toThrow(/fehlt dem Server der zweite Propstack-Schlüssel \(PROPSTACK_API_KEY_V2\)/);
		expect(w.aufrufe).toEqual([]);
	});

	it("lehnt Propstack ab, wird der Fehler protokolliert und durchgereicht", async () => {
		const w = welt();
		w.roh.createClientV2 = async () => {
			throw new PropstackError("Propstack hat den Zugriff verweigert (403). Dem zweiten Schlüssel (PROPSTACK_API_KEY_V2) fehlt vermutlich das Recht für diesen Bereich – oder er ist ungültig.", 403);
		};
		const { db, updates } = fakeDb();
		await expect(createCompany({ client: w.client, db, now: NOW, user: USER }, { name: "Neue Firma GmbH" })).rejects.toThrow(/PROPSTACK_API_KEY_V2/);
		expect(JSON.stringify(updates)).toMatch(/failed/);
	});
});

describe("link_contact_company", () => {
	const deps = (w: ReturnType<typeof welt>) => ({ client: w.client, db: fakeDb().db, now: NOW, user: USER });
	const IDS = { company_id: 17366550, contact_id: 35124656 };
	const schreibt = (w: ReturnType<typeof welt>) => w.aufrufe.some((a) => a.methode === "createRelationshipV2");
	const VERTAUSCHT = "Die Verknüpfung ist vertauscht beschriftet: Am Kontakt steht die Firma als „Mitarbeiter“, an der Firma die Person als „Firma“ – üblich ist es umgekehrt. Korrigieren lässt sich das nur in Propstack.";

	it("verknüpft Person und Firma: Die Zeile der Person heißt „Mitarbeiter“ – am Kontakt erscheint die Firma dadurch als „Firma“ – und liest gegen", async () => {
		const w = welt([GOODMAN, STEFAN]);
		const { db, rows, updates } = fakeDb();
		const out = await linkContactCompany({ client: w.client, db, now: NOW, user: USER }, IDS);
		// name beschreibt client_id und wird am anderen Kontakt angezeigt (Oberfläche geprüft am 13.11.2026).
		// Mit name "Firma" – so in 0.11.0 bis 0.12.0 – stand am Kontakt die Firma als „Mitarbeiter“.
		expect(w.aufrufe.find((a) => a.methode === "createRelationshipV2")!.args[0]).toEqual({ client_id: 35124656, internal_name: "associate", name: "Mitarbeiter", related_client_id: 17366550 });
		expect(out).toEqual({
			count: 1,
			result: {
				already_linked: undefined,
				company: { id: 17366550, name: "Goodman Germany GmbH" },
				contact: { id: 35124656, name: "Stefan Prange" },
				label: "Firma",
				label_at_company: "Mitarbeiter",
				linked: true,
				relationship_id: 500,
				warnings: undefined,
			},
		});
		expect(w.verknuepfungen.map((v) => [v.client_id, v.name, v.related_client_id])).toEqual([
			[35124656, "Mitarbeiter", 17366550],
			[17366550, "Firma", 35124656],
		]);
		expect(rows[0].slice(3, 6)).toEqual(["link_contact_company", "contact", 35124656]);
		expect(JSON.stringify(updates)).toMatch(/done/);
		expect(JSON.stringify(updates)).not.toMatch(/done_with_gaps|failed/);
		// Person samt angezeigten Verknüpfungen und Firma lesen, eigene Zeilen nachsehen, schreiben, beides gegenlesen
		expect(w.aufrufe.map((a) => a.methode)).toEqual(["getContactRelationships", "getContact", "listRelationshipsV2", "createRelationshipV2", "getContactRelationships", "listRelationshipsV2"]);
		expect(w.aufrufe[2].args[0]).toEqual({ client_id: 35124656, internal_name: "associate", per: 100 });
	});

	it("schon verknüpft: nichts wird geschrieben und nichts protokolliert – egal, von welcher Seite die Verknüpfung angelegt wurde", async () => {
		// vom Import: Zeile der Person zuerst
		const vonPerson = welt([GOODMAN, STEFAN]);
		vonPerson.paar(35124656, 17366550, 7985856);
		const { db, rows } = fakeDb();
		const a = await linkContactCompany({ client: vonPerson.client, db, now: NOW, user: USER }, IDS);
		expect(a).toEqual({
			count: 0,
			result: {
				already_linked: true,
				company: { id: 17366550, name: "Goodman Germany GmbH" },
				contact: { id: 35124656, name: "Stefan Prange" },
				label: "Firma",
				label_at_company: "Mitarbeiter",
				linked: true,
				relationship_id: 7985856,
				warnings: undefined,
			},
		});
		expect(schreibt(vonPerson)).toBe(false);
		expect(rows).toEqual([]);

		// von Hand am Kontakt angelegt: Zeile der Firma („Firma“) zuerst, die der Person ergänzt Propstack
		const vonFirma = welt([GOODMAN, STEFAN]);
		vonFirma.paar(17366550, 35124656, 7946127, "Firma");
		const b = await linkContactCompany(deps(vonFirma), IDS);
		expect(b.result).toMatchObject({ already_linked: true, label: "Firma", label_at_company: "Mitarbeiter", linked: true, relationship_id: 7946128 });
		expect((b.result as Raw).warnings).toBeUndefined();
		expect(schreibt(vonFirma)).toBe(false);
	});

	it("vertauscht beschriftete Verknüpfung (Zeile der Person heißt „Firma“): gilt als verknüpft, wird aber gemeldet", async () => {
		// so legten es der Connector 0.11.0–0.12.0 und der Import am 12./13.11.2026 an – und so stehen rund 2.000 ältere im Konto
		const w = welt([GOODMAN, STEFAN]);
		w.paar(35124656, 17366550, 7135440, "Firma");
		const out = await linkContactCompany(deps(w), IDS);
		expect(out.result).toMatchObject({ already_linked: true, label: "Mitarbeiter", label_at_company: "Firma", linked: true, relationship_id: 7135440, warnings: [VERTAUSCHT] });
		expect(schreibt(w)).toBe(false);
	});

	it("vorhandene Verknüpfung mit anderer oder ohne Bezeichnung: gilt als verknüpft, die Bezeichnungen werden genannt, keine Warnung", async () => {
		const vertreter = welt([GOODMAN, STEFAN]);
		vertreter.paar(35124656, 17366550, 10, "Vertreter");
		const a = (await linkContactCompany(deps(vertreter), IDS)).result as Raw;
		expect(a).toMatchObject({ already_linked: true, label_at_company: "Vertreter", linked: true });
		expect(a.label).toBeUndefined();
		expect(a.warnings).toBeUndefined();
		const ohne = welt([GOODMAN, STEFAN]);
		ohne.paar(35124656, 17366550, 20, null);
		const b = (await linkContactCompany(deps(ohne), IDS)).result as Raw;
		expect(b).toMatchObject({ already_linked: true, linked: true, relationship_id: 20 });
		expect(b.label).toBeUndefined();
		expect(b.warnings).toBeUndefined();
	});

	it("halbe Verknüpfung (nur eine der zwei Zeilen, z. B. nach einem Löschen in Propstack): gilt als vorhanden, nichts wird doppelt angelegt", async () => {
		// live 12.11.2026: Löschen entfernt nur eine Zeile – die andere bleibt stehen
		const nurFirma = welt([GOODMAN, STEFAN]);
		nurFirma.verknuepfungen.push({ client_id: 17366550, id: 6825243, internal_name: "associate", name: "Firma", related_client_id: 35124656 });
		const a = (await linkContactCompany(deps(nurFirma), IDS)).result as Raw;
		expect(a).toMatchObject({ already_linked: true, label: "Firma", linked: true, relationship_id: 6825243 });
		expect(a.label_at_company).toBeUndefined();
		expect(schreibt(nurFirma)).toBe(false);

		const nurPerson = welt([GOODMAN, STEFAN]);
		nurPerson.verknuepfungen.push({ client_id: 35124656, id: 6825242, internal_name: "associate", name: "Mitarbeiter", related_client_id: 17366550 });
		const b = (await linkContactCompany(deps(nurPerson), IDS)).result as Raw;
		expect(b).toMatchObject({ already_linked: true, label_at_company: "Mitarbeiter", linked: true, relationship_id: 6825242 });
		expect(b.label).toBeUndefined();
		expect(schreibt(nurPerson)).toBe(false);
	});

	it("Verknüpfungen mit anderen Kontakten oder anderer Art (z. B. Eigentümer) zählen nicht", async () => {
		const w = welt([GOODMAN, STEFAN]);
		w.paar(35124656, 999, 30); // dieselbe Person, andere Firma
		w.paar(777, 17366550, 40); // andere Person, dieselbe Firma
		w.verknuepfungen.push({ client_id: 35124656, id: 79, internal_name: "owner", name: null, related_client_id: 17366550 });
		const out = await linkContactCompany(deps(w), IDS);
		expect(out.result).toMatchObject({ label: "Firma", linked: true, relationship_id: 505 });
		expect((out.result as Raw).already_linked).toBeUndefined();
		expect(schreibt(w)).toBe(true);
	});

	it("vertauscht oder falsch: Firma als contact_id, Person als company_id, zweimal derselbe Datensatz – abgewiesen ohne Schreibzugriff", async () => {
		const w = welt([GOODMAN, STEFAN, { ...STEFAN, id: 2, name: "Anna Muster" }]);
		await expect(linkContactCompany(deps(w), { company_id: 35124656, contact_id: 17366550 })).rejects.toThrow(/Goodman Germany GmbH \(17366550\) ist selbst ein Firmen-Datensatz/);
		await expect(linkContactCompany(deps(w), { company_id: 2, contact_id: 35124656 })).rejects.toThrow(/Anna Muster \(2\) ist kein Firmen-Datensatz, sondern eine Person/);
		await expect(linkContactCompany(deps(w), { company_id: 5, contact_id: 5 })).rejects.toThrow(/derselbe Datensatz/);
		await expect(linkContactCompany(deps(w), { company_id: 17366550, contact_id: 404 })).rejects.toThrow(/Nicht gefunden/);
		expect(w.aufrufe.some((x) => x.methode === "createRelationshipV2" || x.methode === "listRelationshipsV2")).toBe(false);
	});

	it("Person, die fälschlich als Firma markiert ist (hat einen Vornamen): als Firma abgewiesen, als Person verknüpfbar", async () => {
		const falsch = { company: "Goodman Germany GmbH", first_name: "Max", id: 4, is_company: true, last_name: "Muster", name: "Max Muster (Goodman Germany GmbH)" };
		const w = welt([GOODMAN, STEFAN, falsch]);
		await expect(linkContactCompany(deps(w), { company_id: 4, contact_id: 35124656 })).rejects.toThrow(/\(4\) ist kein Firmen-Datensatz/);
		expect(schreibt(w)).toBe(false);
		expect((await linkContactCompany(deps(w), { company_id: 17366550, contact_id: 4 })).result).toMatchObject({ label: "Firma", linked: true });
	});

	it("422 von Propstack: gibt es die Verknüpfung inzwischen, gilt sie als vorhanden – sonst wird der Fehler gemeldet", async () => {
		const vorhanden = welt([GOODMAN, STEFAN]);
		vorhanden.roh.createRelationshipV2 = async () => {
			vorhanden.paar(35124656, 17366550, 80);
			throw new PropstackError("Propstack-Anfrage fehlgeschlagen (422): bereits verknüpft", 422);
		};
		const { db, updates } = fakeDb();
		expect((await linkContactCompany({ client: vorhanden.client, db, now: NOW, user: USER }, IDS)).result).toMatchObject({ already_linked: true, label: "Firma", linked: true, relationship_id: 80 });
		expect(JSON.stringify(updates)).not.toMatch(/failed/);

		const fehler = welt([GOODMAN, STEFAN]);
		fehler.roh.createRelationshipV2 = async () => {
			throw new PropstackError("Propstack-Anfrage fehlgeschlagen (422): Kontakt muss demselben Shop angehören", 422);
		};
		const zweite = fakeDb();
		await expect(linkContactCompany({ client: fehler.client, db: zweite.db, now: NOW, user: USER }, IDS)).rejects.toThrow(/demselben Shop/);
		expect(JSON.stringify(zweite.updates)).toMatch(/failed/);

		// ein anderer Fehler als 422 wird nie als „gibt es schon“ gedeutet
		const stoerung = welt([GOODMAN, STEFAN]);
		stoerung.roh.createRelationshipV2 = async () => {
			stoerung.paar(35124656, 17366550, 90);
			throw new PropstackError("Propstack-Serverfehler (500)", 500);
		};
		await expect(linkContactCompany(deps(stoerung), IDS)).rejects.toThrow(/500/);
	});

	it("steht die angelegte Zeile beim Gegenlesen nicht da, heißt es linked: false statt eines falschen Erfolgs", async () => {
		const w = welt([GOODMAN, STEFAN]);
		w.roh.createRelationshipV2 = async () => ({ id: 1 }); // angenommen, aber nicht gespeichert
		const { db, updates } = fakeDb();
		const out = await linkContactCompany({ client: w.client, db, now: NOW, user: USER }, IDS);
		expect(out.count).toBe(0);
		expect(out.result).toMatchObject({ linked: false, note: expect.stringContaining("ließ sich aber nicht bestätigen") });
		expect(JSON.stringify(updates)).toMatch(/done_with_gaps/);
		expect(JSON.stringify(updates)).toMatch(/steht beim Gegenlesen nicht in Propstack/);
	});

	it("lässt sich nicht gegenlesen (Propstack gestört): „nicht prüfbar“", async () => {
		const w = welt([GOODMAN, STEFAN]);
		let abfragen = 0;
		w.roh.listRelationshipsV2 = async () => {
			if (++abfragen > 1) throw new PropstackError("Propstack-Serverfehler (502)", 502);
			return page([]);
		};
		const { db, updates } = fakeDb();
		const out = await linkContactCompany({ client: w.client, db, now: NOW, user: USER }, IDS);
		expect(out.result).toMatchObject({ linked: "nicht prüfbar" });
		expect(JSON.stringify(updates)).toMatch(/nicht prüfbar \(Propstack-Serverfehler \(502\)\)/);
	});

	it("steht am Kontakt eine andere Firma als Text, kommt ein Hinweis – verknüpft wird trotzdem", async () => {
		const w = welt([GOODMAN, { ...STEFAN, company: "Prologis Germany" }]);
		const out = await linkContactCompany(deps(w), IDS);
		expect(out.result).toMatchObject({
			linked: true,
			warnings: ["Am Kontakt steht als Firma „Prologis Germany“, der Firmen-Datensatz heißt „Goodman Germany GmbH“ – bitte prüfen, ob es dieselbe Firma ist."],
		});
		// gleiche Firma in anderer Schreibweise oder gar kein Firmentext: kein Hinweis
		for (const company of ["goodman germany", "Goodman Germany AG", null]) {
			const gleich = welt([GOODMAN, { ...STEFAN, company }]);
			expect(((await linkContactCompany(deps(gleich), IDS)).result as Raw).warnings, String(company)).toBeUndefined();
		}
	});

	it("ohne zweiten Schlüssel: klare Meldung, kein Aufruf", async () => {
		const w = welt([GOODMAN, STEFAN], { v2Key: false });
		await expect(linkContactCompany(deps(w), IDS)).rejects.toThrow(/PROPSTACK_API_KEY_V2/);
		expect(w.aufrufe).toEqual([]);
	});
});

describe("create_contact: Firma automatisch verknüpfen (Entscheidung Florian, 12.11.2026)", () => {
	/** Wie welt(), aber mit den Aufrufen, die create_contact zusätzlich braucht. */
	function kontaktWelt(start: Raw[], v2Key = true) {
		const w = welt(start, { v2Key });
		Object.assign(w.roh, {
			createContact: async (kontakt: Raw) => {
				w.aufrufe.push({ args: [kontakt], methode: "createContact" });
				w.kontakte.set(8000, { ...kontakt, id: 8000, is_company: false, name: `${kontakt.first_name} ${kontakt.last_name}` });
				return { id: 8000 };
			},
			listCustomFieldGroups: async () => page([]),
		});
		return w;
	}
	const eingabe = { company: "Goodman Germany GmbH", first_name: "Erika", last_name: "Neu" };
	const lauf = async (w: ReturnType<typeof kontaktWelt>, input: Raw = eingabe) => {
		const log = fakeDb();
		const out = await createContactLinked({ client: w.client, db: log.db, now: NOW, user: USER }, input as never);
		return { link: (out.result as Raw).company_link as Raw | undefined, log, result: out.result as Raw };
	};
	const schreibZugriffe = (w: ReturnType<typeof kontaktWelt>) => w.aufrufe.map((a) => a.methode).filter((m) => /^create|^update/.test(m));

	it("gibt es die Firma, wird die neue Person ohne weiteres Zutun mit ihr verknüpft", async () => {
		const w = kontaktWelt([GOODMAN]);
		const { link, log, result } = await lauf(w);
		expect(result).toMatchObject({ created: true, id: 8000 });
		expect(link).toEqual({
			company: { id: 17366550, name: "Goodman Germany GmbH" },
			company_created: undefined,
			company_not_applied: undefined,
			label: "Firma",
			linked: true,
			note: undefined,
			warnings: undefined,
		});
		expect(schreibZugriffe(w)).toEqual(["createContact", "createRelationshipV2"]);
		expect(w.verknuepfungen.map((v) => [v.client_id, v.name, v.related_client_id])).toEqual([
			[8000, "Mitarbeiter", 17366550],
			[17366550, "Firma", 8000],
		]);
		// im Write-Log steht die Verknüpfung unter dem Tool, das sie ausgelöst hat
		expect(log.rows.map((r) => r[3])).toEqual(["create_contact", "create_contact"]);
	});

	it("andere Schreibweise oder Rechtsform am Kontakt: verknüpft wird mit der vorhandenen Firma, keine zweite entsteht", async () => {
		for (const company of ["Goodman Germany AG", "goodman germany", "Goodman Germany GmbH & Co. KG"]) {
			const w = kontaktWelt([GOODMAN]);
			const { link } = await lauf(w, { ...eingabe, company });
			expect(link, company).toMatchObject({ company: { id: 17366550 }, linked: true });
			expect(schreibZugriffe(w), company).toEqual(["createContact", "createRelationshipV2"]);
		}
	});

	it("gibt es die Firma noch nicht, wird sie angelegt – mit der Geschäftsadresse des Kontakts und dem Test-Merkmal – und verknüpft", async () => {
		const w = kontaktWelt([]);
		const { link, log } = await lauf(w, { ...eingabe, city: "Köln", company: "Neue Firma GmbH", country: "Deutschland", house_number: "1a", phone_office: "0221 1", street: "Teststraße", test: true, zip_code: "50667" });
		expect(w.aufrufe.find((a) => a.methode === "createClientV2")!.args[0]).toEqual({
			broker_id: 347158,
			commercial: true,
			company: "Neue Firma GmbH",
			description: "Angelegt über Claude (Propstack MCP) von Florian Brimmers am 2026-11-12.",
			group_ids: [722243],
			office_city: "Köln",
			office_country: "Deutschland",
			office_house_number: "1a",
			office_street: "Teststraße",
			office_zip_code: "50667",
		});
		expect(link).toMatchObject({ company: { id: 9001, name: "Neue Firma GmbH" }, company_created: true, label: "Firma", linked: true });
		expect(schreibZugriffe(w)).toEqual(["createContact", "createClientV2", "createRelationshipV2"]);
		expect(w.verknuepfungen[0]).toMatchObject({ client_id: 8000, name: "Mitarbeiter", related_client_id: 9001 });
		// Kontakt, Firma und Verknüpfung stehen einzeln im Write-Log, alle unter create_contact
		expect(log.rows.map((r) => r[3])).toEqual(["create_contact", "create_contact", "create_contact"]);
	});

	it("gibt es nur eine ähnlich benannte Firma, wird keine neue angelegt und nichts geraten – der Kontakt entsteht trotzdem", async () => {
		// so ist im Konto „Goodman“ (36103370) neben „Goodman Germany GmbH“ entstanden: Der Import hat einfach angelegt
		const kurz = { company: "Goodman", id: 36103370, is_company: true, name: "Goodman" };
		const w = kontaktWelt([kurz]);
		const { link, result } = await lauf(w);
		expect(result).toMatchObject({ created: true, id: 8000 });
		expect(link).toEqual({
			hint: expect.stringMatching(/keinen gleichnamigen, aber einen ähnlich benannten Firmen-Datensatz – deshalb keine neue Firma angelegt.*contact_id 8000/),
			linked: false,
			similar: ["Ähnlicher Firmen-Datensatz: Goodman (36103370) – bitte prüfen, ob es dieselbe Firma ist."],
		});
		expect(schreibZugriffe(w)).toEqual(["createContact"]);
	});

	it("passen mehrere Firmen-Datensätze, wird nur verknüpft, wenn genau einer exakt so heißt – sonst kommen die Kandidaten zurück", async () => {
		const ag = { company: "Goodman Germany AG", id: 99, is_company: true, name: "Goodman Germany AG" };
		const eindeutig = kontaktWelt([GOODMAN, ag]);
		expect((await lauf(eindeutig)).link).toMatchObject({ company: { id: 17366550 }, linked: true });

		const mehrdeutig = kontaktWelt([GOODMAN, { ...GOODMAN, id: 98 }]);
		const { link } = await lauf(mehrdeutig);
		expect(link).toEqual({
			candidates: [
				{ id: 17366550, name: "Goodman Germany GmbH" },
				{ id: 98, name: "Goodman Germany GmbH" },
			],
			hint: expect.stringContaining("Mehrere Firmen-Datensätze passen"),
			linked: false,
		});
		expect(schreibZugriffe(mehrdeutig)).toEqual(["createContact"]);
	});

	it("ohne Firma am Kontakt, bei abgewiesener Dublette oder ohne zweiten Schlüssel passiert an Firmen nichts", async () => {
		const ohneFirma = kontaktWelt([GOODMAN]);
		const a = await lauf(ohneFirma, { first_name: "Erika", last_name: "Neu" });
		expect(a.result).toMatchObject({ created: true });
		expect(a.result).not.toHaveProperty("company_link");
		expect(ohneFirma.aufrufe.filter((x) => x.methode === "searchContacts").map((x) => (x.args[0] as Raw).q)).toEqual(["Erika Neu"]);

		const dublette = kontaktWelt([GOODMAN, { company: "Goodman Germany GmbH", first_name: "Erika", id: 7, is_company: false, last_name: "Neu", name: "Erika Neu" }]);
		const b = await lauf(dublette);
		expect(b.result).toMatchObject({ blocked: "Dublette", created: false });
		expect(b.result).not.toHaveProperty("company_link");
		expect(schreibZugriffe(dublette)).toEqual([]);

		const ohneSchluessel = kontaktWelt([GOODMAN], false);
		const c = await lauf(ohneSchluessel);
		expect(c.result).toMatchObject({ created: true });
		expect(c.link).toEqual({ hint: expect.stringContaining("PROPSTACK_API_KEY_V2"), linked: false });
		expect(schreibZugriffe(ohneSchluessel)).toEqual(["createContact"]);
	});

	it("Telefonnummern werden beim Anlegen bereinigt: keine 0 nach der Ländervorwahl – und eine solche Mobilnummer gilt als Mobilnummer", async () => {
		// Befund Florian, 13.11.2026. Vorher: „+49 (0) 171 …“ wurde als „keine deutsche Mobilnummer“ abgewiesen und landete im Festnetz-Feld.
		const w = kontaktWelt([]);
		const { result } = await lauf(w, { first_name: "Erika", last_name: "Neu", mobile: "+49 (0) 171 3920055", phone_office: "+49(0)2151 123456" });
		expect(result).toMatchObject({
			created: true,
			phone_adjusted: [
				"mobile: „+49 (0) 171 3920055“ → „+49 171 3920055“ (0 nach der Ländervorwahl entfernt)",
				"phone_office: „+49(0)2151 123456“ → „+49 2151 123456“ (0 nach der Ländervorwahl entfernt)",
			],
		});
		expect(w.aufrufe.find((a) => a.methode === "createContact")!.args[0]).toMatchObject({ office_cell: "+49 171 3920055", office_phone: "+49 2151 123456" });
		// richtig geschriebene internationale Nummern bleiben, wie sie sind – ohne Hinweis
		const ok = kontaktWelt([]);
		const sauber = await lauf(ok, { first_name: "Erika", last_name: "Neu", mobile: "+49 171 3920055", phone_office: "+49 221 4710-198" });
		expect(sauber.result).not.toHaveProperty("phone_adjusted", expect.anything());
		expect(ok.aufrufe.find((a) => a.methode === "createContact")!.args[0]).toMatchObject({ office_cell: "+49 171 3920055", office_phone: "+49 221 4710-198" });
	});

	it("einheitlich mit Ländervorwahl: Nummern ohne Vorwahl bekommen die des Landes – ohne Landesangabe +49, und das Ergebnis sagt es", async () => {
		// Entscheidung Florian, 13.11.2026
		const ohneLand = kontaktWelt([]);
		const a = await lauf(ohneLand, { first_name: "Erika", last_name: "Neu", mobile: "0171 3920055", phone_office: "(0221) 4710199" });
		expect(ohneLand.aufrufe.find((x) => x.methode === "createContact")!.args[0]).toMatchObject({ office_cell: "+49 171 3920055", office_phone: "+49 221 4710199" });
		expect(a.result).toMatchObject({
			phone_adjusted: [
				"mobile: „0171 3920055“ → „+49 171 3920055“ (auf +49 umgestellt – kein Land angegeben, als deutsche Nummer gewertet)",
				"phone_office: „(0221) 4710199“ → „+49 221 4710199“ (auf +49 umgestellt – kein Land angegeben, als deutsche Nummer gewertet)",
			],
		});
		// mit Land: dessen Vorwahl
		const wien = kontaktWelt([]);
		const b = await lauf(wien, { country: "Österreich", first_name: "Erika", last_name: "Neu", phone_office: "01 2345678" });
		expect(wien.aufrufe.find((x) => x.methode === "createContact")!.args[0]).toMatchObject({ office_phone: "+43 1 2345678" });
		expect(b.result).toMatchObject({ phone_adjusted: ["phone_office: „01 2345678“ → „+43 1 2345678“ (auf +43 umgestellt)"] });
		// Land, das der Connector nicht kennt: Nummer bleibt, kein Hinweis
		const fern = kontaktWelt([]);
		const c = await lauf(fern, { country: "Südafrika", first_name: "Erika", last_name: "Neu", phone_office: "021 1234567" });
		expect(fern.aufrufe.find((x) => x.methode === "createContact")!.args[0]).toMatchObject({ office_phone: "021 1234567" });
		expect(c.result).not.toHaveProperty("phone_adjusted", expect.anything());
		// „00“ wird zu „+“
		const nullnull = kontaktWelt([]);
		const d = await lauf(nullnull, { first_name: "Erika", last_name: "Neu", phone_office: "0049 221 4710199" });
		expect(d.result).toMatchObject({ phone_adjusted: ["phone_office: „0049 221 4710199“ → „+49 221 4710199“ (00 durch + ersetzt)"] });
	});

	it("dieselbe Mobilnummer mit „(0)“ geschrieben wird als Dublette erkannt", async () => {
		const vorhanden = { first_name: "Karl", id: 5, is_company: false, last_name: "Alt", name: "Karl Alt", office_cell: "0171 3920055" };
		const w = kontaktWelt([vorhanden]);
		const { result } = await lauf(w, { first_name: "Erika", last_name: "Neu", mobile: "+49 (0) 171 3920055" });
		expect(result).toMatchObject({ blocked: "Dublette", created: false, duplicates: [expect.objectContaining({ id: 5 })] });
		expect(schreibZugriffe(w)).toEqual([]);
	});

	it("scheitert etwas an der Firma, bleibt der Kontakt angelegt – das Ergebnis sagt, was fehlt und wie es nachgeholt wird", async () => {
		// Suche gestört
		const suche = kontaktWelt([GOODMAN]);
		const original = suche.roh.searchContacts;
		suche.roh.searchContacts = async (query: Query) => {
			if (query.q === "Goodman Germany GmbH") throw new PropstackError("Propstack-Serverfehler (502)", 502);
			return original(query);
		};
		const a = await lauf(suche);
		expect(a.result).toMatchObject({ created: true, id: 8000 });
		expect(a.link).toMatchObject({ hint: expect.stringMatching(/Der Kontakt ist angelegt, die Verknüpfung mit der Firma nicht: Propstack-Serverfehler \(502\).*link_contact_company \(contact_id 8000\)/), linked: false });

		// Firma lässt sich nicht anlegen
		const anlegen = kontaktWelt([]);
		anlegen.roh.createClientV2 = async () => {
			throw new PropstackError("Propstack hat den Zugriff verweigert (403).", 403);
		};
		const b = await lauf(anlegen);
		expect(b.result).toMatchObject({ created: true });
		expect(b.link).toMatchObject({ hint: expect.stringContaining("403"), linked: false });
		expect(b.link).not.toHaveProperty("company_created", true);
		expect(JSON.stringify(b.log.updates)).toMatch(/failed/);

		// Firma angelegt, Verknüpfen scheitert: Die neue Firma wird genannt, damit sie nicht noch einmal entsteht
		const verknuepfen = kontaktWelt([]);
		verknuepfen.roh.createRelationshipV2 = async () => {
			throw new PropstackError("Propstack-Anfrage fehlgeschlagen (422): related_client_id is invalid", 422);
		};
		const c = await lauf(verknuepfen, { ...eingabe, company: "Neue Firma GmbH" });
		expect(c.link).toMatchObject({ company: { id: 9001, name: "Neue Firma GmbH" }, company_created: true, hint: expect.stringContaining("related_client_id is invalid"), linked: false });

		// Verknüpfung nicht bestätigt: kein falscher Erfolg
		const unbestaetigt = kontaktWelt([GOODMAN]);
		unbestaetigt.roh.createRelationshipV2 = async () => ({ id: 1 });
		expect((await lauf(unbestaetigt)).link).toMatchObject({ linked: false, note: expect.stringContaining("ließ sich aber nicht bestätigen") });
	});
});

describe("get_contact: verknüpfte Kontakte", () => {
	it("zeigt an der Firma die verknüpften Personen und an der Person die Firma – mit der Bezeichnung, die Propstack daneben anzeigt, und einer einzigen Anfrage", async () => {
		const abrufe: number[] = [];
		const client = {
			getContactRelationships: async (id: number) => {
				abrufe.push(id);
				return id === 17366550
					? { ...GOODMAN, relationships: [{ client: { id: 35124656, name: "Stefan Prange" }, internal_name: "associate", name: "Mitarbeiter", project: null, property: null }] }
					: { ...STEFAN, relationships: [{ client: { id: 17366550, name: "Goodman Germany GmbH" }, internal_name: "associate", name: "Firma", project: null, property: null }] };
			},
			listBrokers: async () => [],
		} as never;
		expect((await getContact(client, { id: 17366550 })).result).toMatchObject({ is_company: true, linked_contacts: [{ id: 35124656, label: "Mitarbeiter", name: "Stefan Prange" }] });
		expect((await getContact(client, { id: 35124656 })).result).toMatchObject({ linked_contacts: [{ id: 17366550, label: "Firma", name: "Goodman Germany GmbH" }], name: "Stefan Prange" });
		expect(abrufe).toEqual([17366550, 35124656]);
	});
});

describe("PropstackClient: V2-Schnittstelle", () => {
	function mitschnitt(antwort: (url: string, init: RequestInit) => Response = () => new Response(JSON.stringify({ id: 1 }), { status: 201 })) {
		const gesehen: { url: string; methode: string; schluessel: string | null; body: unknown }[] = [];
		const fetchFn = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
			gesehen.push({ body: init.body ? JSON.parse(String(init.body)) : undefined, methode: init.method ?? "GET", schluessel: new Headers(init.headers).get("x-api-key"), url: String(input) });
			return antwort(String(input), init);
		}) as unknown as typeof fetch;
		return { fetchFn, gesehen };
	}

	it("V2-Aufrufe gehen an /v2 mit dem zweiten Schlüssel und ohne Hülle; V1 bleibt bei /v1 mit dem ersten", async () => {
		const { fetchFn, gesehen } = mitschnitt();
		const client = new PropstackClient({ apiKey: "v1-schluessel", apiKeyV2: " v2-schluessel\n", fetchFn });
		expect(client.hasV2Key).toBe(true);
		await client.createClientV2({ commercial: true, company: "X GmbH" });
		await client.updateClientV2(7, { commercial: true });
		await client.createRelationshipV2({ client_id: 1, internal_name: "associate", related_client_id: 2 });
		await client.listRelationshipsV2({ client_id: 1, internal_name: "associate", per: 100 });
		await client.getContact(5);
		expect(gesehen).toEqual([
			{ body: { commercial: true, company: "X GmbH" }, methode: "POST", schluessel: "v2-schluessel", url: "https://api.propstack.de/v2/clients" },
			{ body: { commercial: true }, methode: "PUT", schluessel: "v2-schluessel", url: "https://api.propstack.de/v2/clients/7" },
			{ body: { client_id: 1, internal_name: "associate", related_client_id: 2 }, methode: "POST", schluessel: "v2-schluessel", url: "https://api.propstack.de/v2/relationships" },
			{ body: undefined, methode: "GET", schluessel: "v2-schluessel", url: "https://api.propstack.de/v2/relationships?client_id=1&internal_name=associate&per=100" },
			{ body: undefined, methode: "GET", schluessel: "v1-schluessel", url: "https://api.propstack.de/v1/contacts/5" },
		]);
		// alle Aufrufe zählen in dasselbe Budget
		expect(client.requestsUsed).toBe(5);
	});

	it("ohne zweiten Schlüssel: klare Meldung, kein Netzaufruf – V1 läuft weiter", async () => {
		const { fetchFn, gesehen } = mitschnitt();
		for (const apiKeyV2 of [undefined, "", "   "]) {
			const client = new PropstackClient({ apiKey: "v1-schluessel", apiKeyV2, fetchFn });
			expect(client.hasV2Key).toBe(false);
			await expect(client.createClientV2({ commercial: true })).rejects.toThrow("Für Firmen und Verknüpfungen zwischen Kontakten fehlt dem Server der zweite Propstack-Schlüssel (PROPSTACK_API_KEY_V2).");
			await expect(client.listRelationshipsV2({ client_id: 1 })).rejects.toThrow(/PROPSTACK_API_KEY_V2/);
			expect(client.requestsUsed).toBe(0);
		}
		expect(gesehen).toEqual([]);
	});

	it("verweigert Propstack den Zugriff, nennt die Meldung den zweiten Schlüssel – bei V1 bleibt der bisherige Text", async () => {
		const { fetchFn } = mitschnitt(() => new Response("{}", { status: 403 }));
		const client = new PropstackClient({ apiKey: "v1", apiKeyV2: "v2", fetchFn });
		await expect(client.createRelationshipV2({})).rejects.toThrow(
			"Propstack hat den Zugriff verweigert (403). Dem zweiten Schlüssel (PROPSTACK_API_KEY_V2) fehlt vermutlich das Recht für diesen Bereich – oder er ist ungültig.",
		);
		await expect(client.listRelationshipsV2({ client_id: 1 })).rejects.toThrow(/PROPSTACK_API_KEY_V2/);
		await expect(client.getContact(1)).rejects.toThrow("Propstack hat den Zugriff verweigert (403). Fehlt dem API-Key das Leserecht für diesen Bereich?");
	});

	it("Validierungsfehler der V2-Schnittstelle kommt mit Propstacks Text durch – der steht dort unter details", async () => {
		// so antwortet V2 (live 12.11.2026): {"status":400,"message":"validation_error","details":"internal_name does not have a valid value"}
		const { fetchFn } = mitschnitt(() => new Response(JSON.stringify({ details: "related_client_id is invalid", message: "validation_error", status: 422 }), { status: 422 }));
		const client = new PropstackClient({ apiKey: "v1", apiKeyV2: "v2", fetchFn });
		await expect(client.createRelationshipV2({})).rejects.toMatchObject({ message: "Propstack-Anfrage fehlgeschlagen (422): related_client_id is invalid", status: 422 });
		// V1 meldet weiter unter errors
		const v1 = mitschnitt(() => new Response(JSON.stringify({ errors: ["E-Mail ist bereits vergeben"], message: "ignoriert" }), { status: 422 }));
		await expect(new PropstackClient({ apiKey: "v1", fetchFn: v1.fetchFn }).createContact({})).rejects.toMatchObject({ message: 'Propstack-Anfrage fehlgeschlagen (422): ["E-Mail ist bereits vergeben"]' });
	});
});
