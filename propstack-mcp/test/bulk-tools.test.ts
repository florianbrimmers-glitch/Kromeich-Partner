import { describe, expect, it } from "vitest";
import { MemoryBulkStore } from "../src/bulk/store";
import type { Page, PropstackClient, Query } from "../src/propstack-client";
import { applyPlan, planBulk, undoInput, undoPlan } from "../src/tools/bulk-tools";

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
		expect(world.puts.find((p) => p.id === 1)!.payload).toEqual({ broker_id: 1, sub_group_ids: [9] });
		expect(world.puts.find((p) => p.id === 2)!.payload).toEqual({ sub_group_ids: [9] });
		expect(world.contacts.get(2)!.broker_id).toBe(7);
		expect(store.rows[1].undo_note).toMatch(/broker_id \(inzwischen geändert\)/);
		expect((await store.getPlan(planId))!.status).toBe("undone");
	});

	it("Undo-Frist 7 Tage", async () => {
		const { db, planId, store, world } = await planned(1);
		await applyPlan({ client: world.makeClient(), db, now: () => T0, store, user: USER }, { plan_id: planId });
		await expect(undoPlan({ client: world.makeClient(), db, now: () => new Date(T0.getTime() + 8 * 86_400_000), store, user: USER }, { plan_id: planId })).rejects.toThrow(
			/Undo-Frist/,
		);
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

	it("Objekte: Status zurück, Custom-Rohwert zurück, Bemerkung nie, Merkmal nur wenn vom Plan gesetzt", () => {
		const out = undoInput(
			"objects",
			item(
				{ custom_fields: { bemerkung: "alt", lagerflache_verfugbar: "3.000 m²", status_logistik: "Inaktiv" }, status_id: 163672, tag_ids: [1, 9] },
				{ custom_fields: { bemerkung: "neu", lagerflache_verfugbar: "3.000 m² (vermietet)", status_logistik: "Aktiv" }, status_id: 163674 },
			),
			{ add_tag_ids: [9, 10], status_id: 163674 },
			current({ status_id: 163674 }, [1, 9, 10], { lagerflache_verfugbar: { value: "3.000 m² (vermietet)" }, status_logistik: { value: "Aktiv" } }),
		);
		expect(out.input).toEqual({
			custom_fields: { lagerflache_verfugbar: "3.000 m²", status_logistik: "Inaktiv" },
			id: 9,
			remove_tag_ids: [10],
			status_id: 163672,
		});
		expect(out.skipped).toContain("custom_fields.bemerkung (Bemerkungen werden nie zurückgesetzt)");
	});

	it("vorher leer → wird wieder geleert; vorher unbekannt → übersprungen", () => {
		const out = undoInput(
			"objects",
			item({ free_from: null, rented: "nicht lesbar" }, { free_from: "vermietet", rented: true }),
			{ rented: true },
			current({ free_from: "vermietet", rented: true }, []),
		);
		expect(out.input).toEqual({ free_from: null, id: 9 });
		expect(out.skipped).toEqual(["rented (vorheriger Wert unbekannt)"]);
	});
});
