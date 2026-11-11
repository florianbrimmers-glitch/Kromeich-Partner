import { beforeEach, describe, expect, it, vi } from "vitest";

// Kein Netz in Tests: Geokodierung (OpenStreetMap) findet nichts
beforeEach(() => {
	vi.stubGlobal("fetch", async () => new Response("[]", { status: 200 }));
});
import { MemoryBulkStore } from "../src/bulk/store";
import { type Page, type PropstackClient, PropstackError, type Query } from "../src/propstack-client";
import { UNVERIFIABLE } from "../src/propstack/unit-state";
import { applyPlan, costOf, planBulk, undoInput, undoPlan } from "../src/tools/bulk-tools";

const page = (rows: Record<string, unknown>[]): Page => ({ rows, total: rows.length });
const USER = { brokerId: 347158, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers" };
const OTHER = { brokerId: 259613, email: "denise@kromeichpartner.de", name: "Denise Kromeich" };
const T0 = new Date("2026-10-15T12:00:00Z");

function fakeDb() {
	const writes: unknown[][] = [];
	const db = {
		prepare: (sql: string) => ({
			bind: (...args: unknown[]) => ({
				run: async () => {
					if (sql.startsWith("INSERT")) writes.push(args);
					return { meta: { changes: 1, last_row_id: writes.length } };
				},
			}),
		}),
	} as unknown as D1Database;
	return { db, writes };
}

/** Simuliertes Propstack mit Kontakten (Merkmale, Betreuer) und Request-Zähler wie der echte Client. */
function contactWorld(count: number) {
	const contacts = new Map<number, { id: number; name: string; groups: { id: number }[]; broker_id: number }>();
	for (let i = 1; i <= count; i++) contacts.set(i, { broker_id: 1, groups: [{ id: 5 }], id: i, name: `Kontakt ${i}` });
	const puts: { id: number; payload: Record<string, unknown> }[] = [];
	const makeClient = () => {
		let used = 0;
		const count = <T>(v: T) => {
			used++;
			return v;
		};
		return {
			getContact: async (id: number) => count(structuredClone(contacts.get(id)) ?? null),
			listCustomFieldGroups: async () => count(page([])),
			get requestsUsed() {
				return used;
			},
			searchContacts: async (q: Query) => count(q.page && Number(q.page) > 1 ? page([]) : page([...contacts.values()])),
			updateContact: async (id: number, payload: Record<string, unknown>) => {
				used++;
				puts.push({ id, payload });
				const c = contacts.get(id)!;
				for (const t of (payload.add_group_ids as number[]) ?? []) c.groups.push({ id: t });
				for (const t of (payload.sub_group_ids as number[]) ?? []) c.groups = c.groups.filter((g) => g.id !== t);
				if (payload.broker_id) c.broker_id = payload.broker_id as number;
				return {};
			},
		} as unknown as PropstackClient;
	};
	return { contacts, makeClient, puts };
}

describe("plan", () => {
	it("plant per Filter, schreibt nichts nach Propstack, zeigt Vorschau", async () => {
		const world = contactWorld(3);
		world.contacts.get(2)!.groups.push({ id: 9 });
		const store = new MemoryBulkStore();
		const out = await planBulk(
			{ client: world.makeClient(), db: fakeDb().db, now: () => T0, store, user: USER },
			{ changes: { add_tag_ids: [9] }, contact_filter: { tag_ids: [5] }, description: "Messe-Kontakte taggen", entity: "contacts" },
		);
		const result = out.result as Record<string, unknown>;
		expect(result).toMatchObject({ already_matching: 1, entity: "contacts", expires_at: "2026-10-15T12:10:00.000Z", total: 3 });
		expect(String(result.next)).toMatch(/NICHTS ist geändert.*bestätigen/);
		expect(world.puts).toEqual([]);
		expect(store.rows).toHaveLength(3);
	});

	it("weist unklare oder falsche Pläne ab", async () => {
		const world = contactWorld(1);
		const deps = { client: world.makeClient(), db: fakeDb().db, now: () => T0, store: new MemoryBulkStore(), user: USER };
		await expect(planBulk(deps, { changes: { add_tag_ids: [9] }, contact_filter: {}, description: "xxxxx", entity: "contacts", ids: [1] })).rejects.toThrow(/Genau eine Auswahl/);
		await expect(planBulk(deps, { changes: { status_id: 163674 }, description: "xxxxx", entity: "contacts", ids: [1] })).rejects.toThrow(/nicht möglich: status_id/);
		await expect(planBulk(deps, { changes: { add_tag_ids: [9], remove_tag_ids: [9] }, description: "xxxxx", entity: "contacts", ids: [1] })).rejects.toThrow(/gleichzeitig/);
		await expect(planBulk(deps, { changes: {}, description: "xxxxx", entity: "contacts", ids: [1] })).rejects.toThrow(/Keine Änderung/);
		await expect(planBulk(deps, { changes: { add_tag_ids: [9] }, description: "xxxxx", entity: "objects", ids: [1] })).rejects.toThrow(
			/Für Objekte nicht möglich: add_tag_ids/,
		);
	});

	it("mehr als 500 Treffer → abgelehnt", async () => {
		const world = contactWorld(501);
		await expect(
			planBulk(
				{ client: world.makeClient(), db: fakeDb().db, now: () => T0, store: new MemoryBulkStore(), user: USER },
				{ changes: { add_tag_ids: [9] }, contact_filter: {}, description: "alle taggen", entity: "contacts" },
			),
		).rejects.toThrow(/501 Treffer – höchstens 500/);
	});
});

describe("apply_plan / undo_plan", () => {
	async function planned(count: number) {
		const world = contactWorld(count);
		const store = new MemoryBulkStore();
		const { db } = fakeDb();
		const out = await planBulk(
			{ client: world.makeClient(), db, now: () => T0, store, user: USER },
			{ changes: { add_tag_ids: [9], broker_id: 2 }, description: "Übergabe an Denise", entity: "contacts", ids: Array.from({ length: count }, (_, i) => i + 1) },
		);
		return { db, planId: (out.result as { plan_id: string }).plan_id, store, world };
	}

	it("führt in Etappen aus (Request-Budget), sichert den Stand vorher, Write-Log je Datensatz", async () => {
		const { db, planId, store, world } = await planned(15);
		const first = (await applyPlan({ client: world.makeClient(), db, now: () => T0, store, user: USER }, { plan_id: planId })).result as Record<string, unknown>;
		expect(first).toMatchObject({ finished: false, processed_now: 13, remaining: 2 }); // 3 Requests je Kontakt, Budget 40
		const second = (await applyPlan({ client: world.makeClient(), db, now: () => new Date(T0.getTime() + 20 * 60_000), store, user: USER }, { plan_id: planId }))
			.result as Record<string, unknown>;
		expect(second).toMatchObject({ done: 15, finished: true, remaining: 0 });
		expect(world.puts[0]).toEqual({ id: 1, payload: { add_group_ids: [9], broker_id: 2 } });
		expect(store.rows[0].before).toEqual({ broker_id: 1, tag_ids: [5] });
		expect((await store.getPlan(planId))!).toMatchObject({ status: "applied", undo_until: "2026-10-22T12:20:00.000Z" });
		await expect(applyPlan({ client: world.makeClient(), db, now: () => T0, store, user: USER }, { plan_id: planId })).rejects.toThrow(/bereits ausgeführt/);
	});

	it("Plan-ID verfällt nach 10 Minuten; nur der Planer darf ausführen", async () => {
		const { db, planId, store, world } = await planned(2);
		await expect(applyPlan({ client: world.makeClient(), db, now: () => T0, store, user: OTHER }, { plan_id: planId })).rejects.toThrow(/Nur wer den Plan erstellt/);
		await expect(applyPlan({ client: world.makeClient(), db, now: () => new Date(T0.getTime() + 11 * 60_000), store, user: USER }, { plan_id: planId })).rejects.toThrow(
			/abgelaufen/,
		);
		expect(world.puts).toEqual([]);
	});

	it("undo stellt her, überspringt inzwischen geänderte Felder, jeder darf rückgängig machen", async () => {
		const { db, planId, store, world } = await planned(3);
		await applyPlan({ client: world.makeClient(), db, now: () => T0, store, user: USER }, { plan_id: planId });
		// Kontakt 2: jemand hat den Betreuer inzwischen von Hand geändert
		world.contacts.get(2)!.broker_id = 7;
		world.puts.length = 0;
		const out = (await undoPlan({ client: world.makeClient(), db, now: () => new Date(T0.getTime() + 86_400_000), store, user: OTHER }, { plan_id: planId }))
			.result as Record<string, unknown>;
		expect(out).toMatchObject({ finished: true, partial: 1, undone: 2 });
		expect(out.next).toBe("Fertig. Nicht alles wurde zurückgesetzt – die Gründe stehen je Datensatz unter problems.");
		expect(world.puts.find((p) => p.id === 1)!.payload).toEqual({ broker_id: 1, sub_group_ids: [9] });
		expect(world.puts.find((p) => p.id === 2)!.payload).toEqual({ sub_group_ids: [9] });
		expect(world.contacts.get(2)!.broker_id).toBe(7);
		expect(store.rows[1].undo_note).toMatch(/broker_id \(inzwischen geändert\)/);
		expect((await store.getPlan(planId))!.status).toBe("undone");
	});

	it("Propstack-Störung (502): anhalten, Datensatz bleibt offen, nächster Aufruf macht weiter (Live-Befund 16.10.)", async () => {
		const { db, planId, store, world } = await planned(3);
		let outage = true;
		const flaky = () => {
			const c = world.makeClient();
			const original = c.updateContact.bind(c);
			(c as unknown as { updateContact: unknown }).updateContact = async (id: number, payload: Record<string, unknown>) => {
				if (outage && id === 2) throw new PropstackError("Propstack-Serverfehler (502)", 502);
				return original(id, payload);
			};
			return c;
		};
		const first = (await applyPlan({ client: flaky(), db, now: () => T0, store, user: USER }, { plan_id: planId })).result as Record<string, unknown>;
		expect(first).toMatchObject({ done: 1, finished: false, remaining: 2 });
		expect(String(first.next)).toMatch(/Angehalten – Propstack gestört/);
		outage = false;
		const second = (await applyPlan({ client: flaky(), db, now: () => T0, store, user: USER }, { plan_id: planId })).result as Record<string, unknown>;
		expect(second).toMatchObject({ done: 3, finished: true });
		expect(store.rows.every((r) => r.status === "done" && r.error === null)).toBe(true);
	});

	it("Undo-Frist 7 Tage", async () => {
		const { db, planId, store, world } = await planned(1);
		await applyPlan({ client: world.makeClient(), db, now: () => T0, store, user: USER }, { plan_id: planId });
		await expect(undoPlan({ client: world.makeClient(), db, now: () => new Date(T0.getTime() + 8 * 86_400_000), store, user: USER }, { plan_id: planId })).rejects.toThrow(
			/Undo-Frist/,
		);
	});
});

describe("Objekte: Texte und Provision übertragen (Ersatz für „Daten auf Einheiten übertragen“)", () => {
	function unitWorld() {
		const units = new Map<number, Record<string, unknown>>([
			[1, { courtage: null, courtage_note: null, furnishing_note: "alt", id: 1, marketing_type: "RENT", title: "Unit 1" }],
			[2, { courtage: "Provisionsfrei", courtage_note: null, furnishing_note: "- LED\n- Sprinkler", id: 2, marketing_type: "RENT", title: "Unit 2" }],
		]);
		const puts: { id: number; payload: Record<string, unknown> }[] = [];
		const makeClient = () => {
			let used = 0;
			return {
				getUnit: async (id: number) => (used++, { custom_fields: {}, id, title: units.get(id)!.title }),
				listCustomFieldGroups: async () => (used++, page([])),
				get requestsUsed() {
					return used;
				},
				searchUnits: async (q: Query) => {
					used++;
					const ids = (q.property_ids as number[] | undefined) ?? [...units.keys()];
					return page(ids.filter((i) => units.has(i)).map((i) => Object.fromEntries(Object.entries(units.get(i)!).map(([k, v]) => [k, k === "id" ? v : { label: k, value: v }]))));
				},
				updateUnit: async (id: number, payload: Record<string, unknown>) => {
					used++;
					puts.push({ id, payload });
					Object.assign(units.get(id)!, payload);
					return {};
				},
			} as unknown as PropstackClient;
		};
		return { makeClient, puts, units };
	}

	it("plant per Projekt-Filter, prüft die Texte vorab, schreibt nur Abweichungen, Undo stellt den alten Text her", async () => {
		const world = unitWorld();
		const store = new MemoryBulkStore();
		const { db } = fakeDb();
		const deps = () => ({ client: world.makeClient(), db, now: () => T0, store, user: USER });
		// Verstoß gegen die Team-Regeln fällt beim Planen auf, nicht erst beim Ausführen
		await expect(
			planBulk(deps(), { changes: { furnishing_note: "LED, Sprinkler, Rampen" }, description: "Ausstattung übertragen", entity: "objects", object_filter: { project_id: 7 } }),
		).rejects.toThrow(/Aufzählung/);
		await expect(planBulk(deps(), { changes: { courtage: "Provisionsfrei" }, description: "xxxxx", entity: "contacts", ids: [1] })).rejects.toThrow(/nicht möglich: courtage/);

		const out = await planBulk(deps(), {
			changes: { commission: "provisionsfrei", furnishing_note: "- LED\n- Sprinkler" },
			description: "Provision und Ausstattung vom Projekt übertragen",
			entity: "objects",
			object_filter: { project_id: 7 },
		});
		const planId = (out.result as { plan_id: string }).plan_id;
		const applied = (await applyPlan(deps(), { plan_id: planId })).result as Record<string, unknown>;
		expect(applied).toMatchObject({ done: 2, finished: true });
		expect(world.puts).toEqual([
			{ id: 1, payload: { courtage: "Provisionsfrei", courtage_note: "Die Anmietung erfolgt provisionsfrei für den Mieter.", furnishing_note: "- LED\n- Sprinkler" } },
			{ id: 2, payload: { courtage_note: "Die Anmietung erfolgt provisionsfrei für den Mieter." } },
		]);
		world.puts.length = 0;
		const undone = (await undoPlan(deps(), { plan_id: planId })).result as Record<string, unknown>;
		expect(world.units.get(1)).toMatchObject({ courtage: null, courtage_note: null, furnishing_note: "alt" });
		// Sauberer Lauf: kein „teilweise“, kein Problem und kein Satz über fremde Änderungen (Live-Befund 11.11.2026)
		expect(undone).toMatchObject({ finished: true, undone: 2 });
		expect(undone.partial).toBeUndefined();
		expect(undone.problems).toBeUndefined();
		expect(undone.next).toBe("Fertig.");
	});
});

describe("Objekte: „Gebäudefläche gesamt“ angleichen (Sammelfunktion, 11.11.2026)", () => {
	const DEFS = page([
		{
			custom_fields: [
				{ field_type: "Number", name: "gebaudeflache_gesamt", unit: "sqm" },
				{ field_type: "Number", name: "gebaudeflache_verfugbar", unit: "sqm" },
				{ field_type: "Number", name: "mezzanineflache_gesamt", unit: "sqm" },
				{ field_type: "String", name: "bemerkung" },
			],
		},
	]);

	/** Acht Einheiten wie im Hillwood-Bestand: „Gebäudefläche gesamt“ inklusive Büro; Nr. 7 stimmt schon, bei Nr. 8 passt die Gesamtfläche nicht. */
	function areaWorld() {
		const units = new Map<number, { stored: Record<string, unknown>; custom: Record<string, unknown> }>();
		for (let i = 1; i <= 8; i++) {
			const hall = 8000 + i * 100;
			const mezzanine = 500 + i;
			units.set(i, {
				custom: { gebaudeflache_gesamt: i === 7 ? hall + mezzanine : hall + mezzanine + 300, mezzanineflache_gesamt: `${mezzanine} m²` },
				stored: { industrial_area: hall, marketing_type: "RENT", rented: false, title: `Halle ${i}`, total_floor_space: i === 8 ? hall + mezzanine + 300 : hall + mezzanine },
			});
		}
		const puts: { id: number; payload: Record<string, unknown> }[] = [];
		const perClient: number[] = [];
		const makeClient = () => {
			let used = 0;
			const slot = perClient.push(0) - 1;
			const count = <T>(value: T) => {
				used++;
				perClient[slot] = used;
				return value;
			};
			return {
				getUnit: async (id: number) =>
					count({ custom_fields: Object.fromEntries(Object.entries(units.get(id)!.custom).map(([k, v]) => [k, { pretty_value: String(v), value: v }])), id, title: units.get(id)!.stored.title }),
				listCustomFieldGroups: async () => count(DEFS),
				get requestsUsed() {
					return used;
				},
				searchUnits: async (q: Query) => {
					const ids = ((q.property_ids as number[] | undefined) ?? [...units.keys()]).filter((i) => units.has(i));
					return count(page(ids.map((i) => ({ id: i, ...Object.fromEntries(Object.entries(units.get(i)!.stored).map(([k, v]) => [k, q.expand ? { label: k, value: v } : v])) }))));
				},
				updateUnit: async (id: number, payload: Record<string, unknown>) => {
					puts.push({ id, payload });
					const { partial_custom_fields, ...rest } = payload as { partial_custom_fields?: Record<string, unknown> };
					Object.assign(units.get(id)!.stored, rest);
					Object.assign(units.get(id)!.custom, partial_custom_fields ?? {});
					return count({});
				},
			} as unknown as PropstackClient;
		};
		return { makeClient, perClient, puts, units };
	}

	it("costOf: Pläne, die nur Custom-Felder anfassen, brauchen weniger Anfragen je Objekt", () => {
		expect(costOf("objects", { align_building_area: true }, "apply")).toBe(6);
		expect(costOf("objects", { align_building_area: true, custom_fields: { wgk: "WGK 3" } }, "undo")).toBe(8);
		expect(costOf("objects", { align_building_area: true, rented: true }, "apply")).toBe(10);
		expect(costOf("objects", { status_id: 163676 }, "undo")).toBe(12);
		expect(costOf("contacts", { custom_fields: { x: 1 } }, "apply")).toBe(4);
	});

	it("jedes Objekt bekommt seinen eigenen Wert; sechs je Aufruf; Unstimmiges wird gemeldet, nicht geändert; Undo stellt den alten Wert her", async () => {
		const world = areaWorld();
		const store = new MemoryBulkStore();
		const { db } = fakeDb();
		const deps = () => ({ client: world.makeClient(), db, now: () => T0, store, user: USER });
		await expect(planBulk(deps(), { changes: { align_building_area: true }, description: "xxxxx", entity: "contacts", ids: [1] })).rejects.toThrow(/nicht möglich: align_building_area/);

		const planned = (await planBulk(deps(), { changes: { align_building_area: true }, description: "Gebäudefläche gesamt angleichen", entity: "objects", ids: [1, 2, 3, 4, 5, 6, 7, 8] })).result as {
			plan_id: string;
			estimated_calls: number;
			total: number;
		};
		expect(planned).toMatchObject({ estimated_calls: 2, total: 8 });
		expect(world.puts).toEqual([]);

		// Erster Aufruf: sechs Objekte, höchstens 40 Propstack-Anfragen
		const first = (await applyPlan(deps(), { plan_id: planned.plan_id })).result as Record<string, unknown>;
		expect(first).toMatchObject({ finished: false, processed_now: 6, remaining: 2 });
		expect(world.perClient[world.perClient.length - 1]).toBeLessThanOrEqual(40);
		expect(world.puts.map((p) => p.id)).toEqual([1, 2, 3, 4, 5, 6]);
		expect(world.puts[0].payload).toEqual({
			partial_custom_fields: {
				bemerkung: expect.stringMatching(/angeglichen \(Halle \+ Mezzanine, ohne Büro\): 8\.601 m² statt 8\.901 m²\.$/),
				gebaudeflache_gesamt: 8601,
			},
		});
		expect(world.units.get(6)!.custom.gebaudeflache_gesamt).toBe(8600 + 506);

		// Zweiter Aufruf: Nr. 7 stimmt schon (unverändert), Nr. 8 wird gemeldet und bleibt, wie sie ist
		const second = (await applyPlan(deps(), { plan_id: planned.plan_id })).result as { problems: { error?: string }[] } & Record<string, unknown>;
		expect(second).toMatchObject({ done: 6, failed: 1, finished: true, unchanged: 1 });
		expect(JSON.stringify(second.problems)).toMatch(/Gesamtfläche \(9\.608 m²\) ist nicht Hallenfläche \+ Mezzanine \(9\.308 m²\)/);
		expect(world.units.get(8)!.custom.gebaudeflache_gesamt).toBe(9608);
		expect(world.puts).toHaveLength(6);

		// Undo: alter Wert kommt zurück. Der Vermerk der Sammeländerung bleibt stehen und bekommt einen über das
		// Rückgängigmachen – und das zählt als „rückgängig“, nicht als „teilweise“ (Live-Befund 11.11.2026).
		const undoFirst = (await undoPlan(deps(), { plan_id: planned.plan_id })).result as Record<string, unknown>;
		expect(undoFirst).toMatchObject({ finished: false, processed_now: 5 });
		expect(world.perClient[world.perClient.length - 1]).toBeLessThanOrEqual(40);
		const undoLast = (await undoPlan(deps(), { plan_id: planned.plan_id })).result as Record<string, unknown>;
		expect(undoLast).toMatchObject({ finished: true, undone: 6 });
		expect(undoLast.partial).toBeUndefined();
		expect(undoLast.problems).toBeUndefined();
		expect(undoLast.next).toBe(
			"Fertig. Die Vermerke der Sammeländerung bleiben in der Bemerkung stehen; wo zurückgesetzt wurde, steht darunter ein Vermerk über das Rückgängigmachen.",
		);
		expect(world.units.get(1)!.custom.gebaudeflache_gesamt).toBe(8901);
		expect(world.units.get(6)!.custom.gebaudeflache_gesamt).toBe(8600 + 506 + 300);
		expect(String(world.units.get(1)!.custom.bemerkung)).toMatch(
			/angeglichen \(Halle \+ Mezzanine, ohne Büro\): 8\.601 m² statt 8\.901 m²\.[\s\S]*\nSammeländerung vom 2026-10-15 rückgängig gemacht: Gebäudefläche gesamt wieder 8\.901 m²\.$/,
		);
	});

	it("Undo nach einer Unterbrechung: was den alten Wert schon wieder trägt, ist rückgängig – kein Problem, kein zweiter Vermerk", async () => {
		const world = areaWorld();
		const store = new MemoryBulkStore();
		const { db } = fakeDb();
		const deps = () => ({ client: world.makeClient(), db, now: () => T0, store, user: USER });
		const planned = (await planBulk(deps(), { changes: { align_building_area: true }, description: "Gebäudefläche gesamt angleichen", entity: "objects", ids: [1, 2] })).result as { plan_id: string };
		await applyPlan(deps(), { plan_id: planned.plan_id });
		// Einheit 2: Der erste Undo-Versuch hat geschrieben, die Antwort ging verloren – der Wert steht schon wieder auf alt
		world.units.get(2)!.custom.gebaudeflache_gesamt = 8200 + 502 + 300;
		const remarkBefore = String(world.units.get(2)!.custom.bemerkung);
		world.puts.length = 0;
		const out = (await undoPlan(deps(), { plan_id: planned.plan_id })).result as Record<string, unknown>;
		expect(out).toMatchObject({ finished: true, undone: 2 });
		expect(out.problems).toBeUndefined();
		expect(world.puts.map((p) => p.id)).toEqual([1]);
		expect(world.units.get(2)!.custom.bemerkung).toBe(remarkBefore);
	});
});

describe("undoInput", () => {
	const current = (values: Record<string, unknown>, tags: number[], custom: Record<string, unknown> = {}) => ({
		custom: (k: string) => custom[k],
		tags,
		value: (k: string) => values[k],
	});
	const item = (before: Record<string, unknown>, changed: Record<string, unknown>) => ({
		before,
		changed,
		entity_id: 9,
		error: null,
		label: null,
		not_applied: null,
		plan_id: "p",
		pos: 0,
		status: "done" as const,
		undo_note: null,
		undo_status: null,
	});

	const DAY = "2026-11-11";

	it("Objekte: Status zurück, Custom-Rohwert zurück, Merkmal nur wenn vom Plan gesetzt; die Bemerkung bleibt und bekommt einen Vermerk", () => {
		const out = undoInput(
			"objects",
			item(
				{ custom_fields: { bemerkung: "alt", lagerflache_verfugbar: "3.000 m²", status_logistik: "Inaktiv" }, status_id: 163672, tag_ids: [1, 9] },
				{ custom_fields: { bemerkung: "neu", lagerflache_verfugbar: "3.000 m² (vermietet)", status_logistik: "Aktiv" }, status_id: 163674 },
			),
			{ add_tag_ids: [9, 10], status_id: 163674 },
			current({ status_id: 163674 }, [1, 9, 10], { lagerflache_verfugbar: { value: "3.000 m² (vermietet)" }, status_logistik: { value: "Aktiv" } }),
			DAY,
		);
		expect(out.input).toEqual({
			bemerkung_append: "Sammeländerung vom 2026-11-11 rückgängig gemacht: Merkmale, status_id, lagerflache_verfugbar, status_logistik.",
			custom_fields: { lagerflache_verfugbar: "3.000 m²", status_logistik: "Inaktiv" },
			id: 9,
			remove_tag_ids: [10],
			status_id: 163672,
		});
		// Die stehen gebliebene Bemerkung ist Absicht und kein übersprungenes Feld (Live-Befund 11.11.2026)
		expect(out.skipped).toEqual([]);
	});

	it("Angleichung zurücknehmen: Vermerk nennt die alten Flächen; ohne Vermerk der Sammeländerung auch keiner beim Undo", () => {
		const before = { custom_fields: { bemerkung: "alt", gebaudeflache_gesamt: 3000, gebaudeflache_verfugbar: null } };
		const changed = { custom_fields: { bemerkung: "alt\n\nangeglichen", gebaudeflache_gesamt: 2500, gebaudeflache_verfugbar: 2500 } };
		const now = { gebaudeflache_gesamt: { pretty_value: "2.500 m²", value: "2500.0" }, gebaudeflache_verfugbar: { value: 2500 } };
		const out = undoInput("objects", item(before, changed), { align_building_area: true }, current({}, [], now), DAY);
		expect(out.input).toEqual({
			bemerkung_append: "Sammeländerung vom 2026-11-11 rückgängig gemacht: Gebäudefläche gesamt wieder 3.000 m², Gebäudefläche verfügbar wieder leer.",
			custom_fields: { gebaudeflache_gesamt: 3000, gebaudeflache_verfugbar: null },
			id: 9,
		});
		// Die Bemerkung ist gerade nicht lesbar → nicht anfassen, die Werte kommen trotzdem zurück
		const unreadable = undoInput("objects", item(before, changed), { align_building_area: true }, current({}, [], { ...now, bemerkung: UNVERIFIABLE }), DAY);
		expect(unreadable.input).toEqual({ custom_fields: { gebaudeflache_gesamt: 3000, gebaudeflache_verfugbar: null }, id: 9 });
		// Der Plan hat keinen Vermerk hinterlassen → das Undo auch nicht
		const silent = undoInput(
			"objects",
			item({ custom_fields: { gebaudeflache_gesamt: 3000 } }, { custom_fields: { gebaudeflache_gesamt: 2500 } }),
			{ custom_fields: { gebaudeflache_gesamt: 2500 } },
			current({}, [], now),
			DAY,
		);
		expect(silent.input).toEqual({ custom_fields: { gebaudeflache_gesamt: 3000 }, id: 9 });
		// Kontakte haben kein Änderungsprotokoll: Dort bleibt ein Custom-Feld „bemerkung“ ein übersprungenes Feld und wird gemeldet
		const contact = undoInput(
			"contacts",
			item({ custom_fields: { bemerkung: "alt", branche: "Logistik" } }, { custom_fields: { bemerkung: "neu", branche: "Handel" } }),
			{ custom_fields: { bemerkung: "neu", branche: "Handel" } },
			current({}, [], { branche: "Handel" }),
			DAY,
		);
		expect(contact.input).toEqual({ custom_fields: { branche: "Logistik" }, id: 9 });
		expect(contact.skipped).toEqual(["custom_fields.bemerkung (Bemerkungen werden nie zurückgesetzt)"]);
	});

	it("trägt ein Feld den alten Wert schon wieder, ist das kein Problem (Wiederholung nach einer Unterbrechung)", () => {
		const out = undoInput(
			"objects",
			item({ custom_fields: { bemerkung: "alt", gebaudeflache_gesamt: 8901 }, status_id: 163672 }, { custom_fields: { bemerkung: "neu", gebaudeflache_gesamt: 8601 }, status_id: 163674 }),
			{ align_building_area: true, status_id: 163674 },
			current({ status_id: 163672 }, [], { gebaudeflache_gesamt: { value: 8901 } }),
			DAY,
		);
		expect(out).toMatchObject({ already: ["status_id", "custom_fields.gebaudeflache_gesamt"], restored: [], skipped: [] });
		expect(out.input).toEqual({ id: 9 });
		// Ein dritter Wert dagegen heißt: jemand anders hat geändert → übersprungen und gemeldet
		const foreign = undoInput(
			"objects",
			item({ custom_fields: { gebaudeflache_gesamt: 8901 } }, { custom_fields: { gebaudeflache_gesamt: 8601 } }),
			{ align_building_area: true },
			current({}, [], { gebaudeflache_gesamt: { value: 9100 } }),
			DAY,
		);
		expect(foreign).toMatchObject({ already: [], restored: [], skipped: ["custom_fields.gebaudeflache_gesamt (inzwischen geändert)"] });
	});

	it("vorher leer → wird wieder geleert; vorher unbekannt → übersprungen", () => {
		const out = undoInput(
			"objects",
			item({ free_from: null, rented: "nicht lesbar" }, { free_from: "vermietet", rented: true }),
			{ rented: true },
			current({ free_from: "vermietet", rented: true }, []),
			DAY,
		);
		expect(out.input).toEqual({ free_from: null, id: 9 });
		expect(out.skipped).toEqual(["rented (vorheriger Wert unbekannt)"]);
	});

	it("Gesamtfläche wird beim Undo nicht zurückgeschrieben, sondern neu gerechnet", () => {
		// Der Plan hat die Mezzanine geändert; update_object hat die Gesamtfläche mitgezogen
		const now = current({ industrial_area: 5000, total_floor_space: 6000 }, [], { mezzanineflache_gesamt: { value: 1000 } });
		const changes = { custom_fields: { mezzanineflache_gesamt: 1000 } };
		const consistent = undoInput(
			"objects",
			item({ custom_fields: { mezzanineflache_gesamt: 800 }, total_floor_space: 5800 }, { custom_fields: { mezzanineflache_gesamt: 1000 }, total_floor_space: 6000 }),
			changes,
			now,
			DAY,
		);
		expect(consistent.input).toEqual({ custom_fields: { mezzanineflache_gesamt: 800 }, id: 9 });
		expect(consistent.skipped).toEqual([]);
		// Vorher stand eine Gesamtfläche inklusive Büro: Die kommt bewusst nicht wieder, und das wird gemeldet
		const legacy = undoInput(
			"objects",
			item({ custom_fields: { mezzanineflache_gesamt: 800 }, total_floor_space: 6400 }, { custom_fields: { mezzanineflache_gesamt: 1000 }, total_floor_space: 6000 }),
			changes,
			now,
			DAY,
		);
		expect(legacy.input).toEqual({ custom_fields: { mezzanineflache_gesamt: 800 }, id: 9 });
		expect(legacy.skipped).toEqual(["total_floor_space (wird aus Hallenfläche + Mezzanine gerechnet, vorher 6400 m²)"]);
		// Ohne Hallenfläche gilt die Regel nicht – dann wird der alte Wert normal zurückgesetzt
		const office = undoInput("objects", item({ total_floor_space: 199 }, { total_floor_space: 250 }), {}, current({ total_floor_space: 250 }, []), DAY);
		expect(office.input).toEqual({ id: 9, total_floor_space: 199 });
	});
});
