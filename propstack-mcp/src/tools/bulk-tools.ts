import { z } from "zod";
import { type BulkItem, type BulkPlan, type BulkStore, D1BulkStore, type UndoStatus } from "../bulk/store";
import { PropstackClient, PropstackError } from "../propstack-client";
import { contactFilterShape, objectFilterShape } from "../propstack/filters";
import { validateCustomFields } from "../propstack/field-rules";
import { scalar } from "../propstack/mappers";
import { readUnit, UNVERIFIABLE, unitCustomValue, unitValue } from "../propstack/unit-state";
import { selectContacts, selectObjects, type ToolOutput } from "./read-tools";
import {
	CONTACT_KEYS,
	groupIdsOf,
	groupIdsOfUnit,
	same,
	updateContact,
	type updateContactInput,
	updateObject,
	type updateObjectInput,
	type WriteDeps,
} from "./write-tools";

// Phase 4: Massenänderungen über plan → apply_plan(plan_id) → undo_plan(plan_id).
// - plan schreibt nichts nach Propstack: Auswahl auflösen, Änderung prüfen, Vorschau, Plan in D1.
// - Plan-ID verfällt 10 min nach dem Planen (Spezifikation). Nur wer plant, darf ausführen.
// - apply_plan schreibt je Datensatz über dieselben Funktionen wie update_contact/update_object:
//   gleiche Regeln (Einzel-PUTs, Spiegelung, Preissperre, aktiv/inaktiv), Gegenlesen, Write-Log je Datensatz.
//   Arbeitet in Etappen (Propstack-Request-Budget je Tool-Aufruf) – so lange aufrufen, bis remaining = 0.
// - undo_plan stellt den Stand vorher wieder her – aber nur Felder, die seitdem niemand anders geändert hat.
//   Möglich bis 7 Tage nach dem Ausführen (Entscheidung Florian). Jeder Nutzer darf rückgängig machen.

type Raw = Record<string, unknown>;

export const PLAN_TTL_MINUTES = 10;
export const UNDO_DAYS = 7;
export const MAX_PLAN_ITEMS = 500;
/** Propstack-Requests je Tool-Aufruf (Client-Grenze 45; Cloudflare Free erlaubt 50 Subrequests). */
export const BULK_REQUEST_BUDGET = 40;
/** Schlechtester Fall je Datensatz (Lesen, Feldregistry, Schreiben, Einzel-PUTs, Zurücklesen; Undo +Lesen). */
const COST = { contacts: { apply: 4, undo: 5 }, objects: { apply: 10, undo: 12 } } as const;

const id = z.number().int().positive();
const tagIds = z.array(id).min(1).max(20);

export const changesShape = {
	add_tag_ids: tagIds.optional().describe("Nur Kontakte: Merkmale hinzufügen (list_tags entity=contacts)"),
	remove_tag_ids: tagIds.optional().describe("Nur Kontakte: Merkmale entfernen"),
	broker_id: id.optional().describe("Nur Kontakte: Betreuer setzen (list_reference kind=users)"),
	source_id: id.optional().describe("Nur Kontakte: Kontakt-Quelle setzen"),
	client_status_id: id.optional().describe("Nur Kontakte: Kontaktstatus setzen"),
	status_id: id.optional().describe("Nur Objekte: Objekt-Status (163672 Akquise … 163676 Abgeschlossen)"),
	rented: z.boolean().optional().describe("Nur Objekte: vermietet ja/nein (mit den Automatiken aus update_object)"),
	custom_fields: z.record(z.string(), z.unknown()).optional().describe("Custom-Felder {schlüssel: wert} wie bei update_contact/update_object; null leert"),
	public_price_confirmed: z.literal(true).optional().describe("Nur Objekte: öffentliche Preisfelder (mietpreis_*) – nur auf ausdrückliche Ansage"),
};

// Merkmale nur an Kontakten (Entscheidung Florian, 16.10.): an Objekten ignoriert Propstack Merkmal-Updates
// still (live: sub_group_ids und leere group_ids ohne Wirkung) und das Team braucht sie dort nicht.
const CONTACT_ONLY = ["broker_id", "source_id", "client_status_id", "add_tag_ids", "remove_tag_ids"];
const OBJECT_ONLY = ["status_id", "rented", "public_price_confirmed"];

export const planBulkInput = {
	entity: z.enum(["contacts", "objects"]).describe("Kontakte oder Objekte"),
	ids: z.array(id).min(1).max(MAX_PLAN_ITEMS).optional().describe("Auswahl per ID-Liste"),
	contact_filter: z.strictObject(contactFilterShape).optional().describe("Auswahl per Filter wie bei search_contacts (nur entity=contacts)"),
	object_filter: z.strictObject(objectFilterShape).optional().describe("Auswahl per Filter wie bei search_objects (nur entity=objects)"),
	changes: z.strictObject(changesShape).describe("Was bei jedem ausgewählten Datensatz geändert wird"),
	description: z.string().trim().min(5).max(300).describe("Wozu? Ein Satz – wird protokolliert und in der Vorschau gezeigt"),
};

function newPlanId(): string {
	const bytes = crypto.getRandomValues(new Uint8Array(8));
	return Array.from(bytes, (b) => b.toString(36).padStart(2, "0")).join("").slice(0, 12);
}

function labelOf(row: Raw, entity: "contacts" | "objects"): string {
	if (entity === "contacts") {
		const name = scalar(row.name) ?? [scalar(row.first_name), scalar(row.last_name)].filter(Boolean).join(" ");
		return [name, scalar(row.company)].filter(Boolean).join(", ") || `Kontakt ${row.id}`;
	}
	return String(scalar(row.title) ?? scalar(row.name) ?? `Objekt ${scalar(row.id)}`);
}

export type BulkDeps = WriteDeps & { store?: BulkStore };

/** 5xx, Timeout/Netz, 429: vorübergehend – Datensatz bleibt offen und wird beim nächsten Aufruf erneut versucht.
 * Sicher, weil update_contact/update_object vorher den aktuellen Stand lesen und nur Abweichungen schreiben. */
function isTransient(error: unknown): boolean {
	return error instanceof PropstackError && (error.status === 0 || error.status >= 500 || error.status === 429);
}

function storeOf(deps: BulkDeps): BulkStore {
	if (deps.store) return deps.store;
	if (!deps.db) throw new PropstackError("Plan-Speicher nicht verfügbar – aus Sicherheitsgründen keine Massenänderung.", 0);
	return new D1BulkStore(deps.db);
}

// ---------- plan ----------

export async function planBulk(deps: BulkDeps, input: z.infer<z.ZodObject<typeof planBulkInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	const store = storeOf(deps);
	const now = deps.now?.() ?? new Date();
	const entity = input.entity;
	const changes = input.changes as Raw;

	const selections = [input.ids, input.contact_filter, input.object_filter].filter((x) => x !== undefined).length;
	if (selections !== 1) throw new PropstackError("Genau eine Auswahl angeben: ids, contact_filter oder object_filter.", 400);
	if (entity === "contacts" && input.object_filter) throw new PropstackError("object_filter passt nicht zu entity=contacts.", 400);
	if (entity === "objects" && input.contact_filter) throw new PropstackError("contact_filter passt nicht zu entity=objects.", 400);
	const keys = Object.keys(changes).filter((k) => changes[k] !== undefined && k !== "public_price_confirmed");
	if (!keys.length) throw new PropstackError("Keine Änderung angegeben.", 400);
	const wrong = keys.filter((k) => (entity === "contacts" ? OBJECT_ONLY : CONTACT_ONLY).includes(k));
	if (wrong.length) throw new PropstackError(`Für ${entity === "contacts" ? "Kontakte" : "Objekte"} nicht möglich: ${wrong.join(", ")}.`, 400);
	const both = (changes.add_tag_ids as number[] | undefined)?.filter((t) => (changes.remove_tag_ids as number[] | undefined)?.includes(t)) ?? [];
	if (both.length) throw new PropstackError(`Merkmal gleichzeitig hinzufügen und entfernen: ${both.join(", ")}.`, 400);

	// Custom-Felder jetzt prüfen – lieber vor dem Lauf abweisen als 500-mal danach
	await validateCustomFields(client, entity === "contacts" ? "for_clients" : "for_properties", changes.custom_fields as Raw | undefined, undefined, {
		publicPriceConfirmed: changes.public_price_confirmed === true,
	});

	let rows: Raw[];
	if (input.ids) {
		rows = [...new Set(input.ids)].map((i) => ({ id: i }));
		if (entity === "objects") {
			// Titel für die Vorschau holen (100 je Abfrage); fehlende IDs melden statt still zu übergehen
			const found = new Map<number, Raw>();
			for (let i = 0; i < rows.length; i += 100) {
				const page = await client.searchUnits({ archived: "-1", per: 100, property_ids: rows.slice(i, i + 100).map((r) => r.id as number) });
				for (const row of page.rows) found.set(Number(scalar(row.id)), row);
			}
			const missing = rows.filter((r) => !found.has(r.id as number)).map((r) => r.id);
			if (missing.length) throw new PropstackError(`Diese Objekt-IDs gibt es nicht: ${missing.slice(0, 20).join(", ")}${missing.length > 20 ? " …" : ""}.`, 400);
			rows = rows.map((r) => found.get(r.id as number)!);
		}
	} else if (input.contact_filter) {
		rows = await selectContacts(client, input.contact_filter, MAX_PLAN_ITEMS);
	} else {
		rows = await selectObjects(client, input.object_filter!, MAX_PLAN_ITEMS);
	}
	if (!rows.length) return { count: 0, result: { planned: false, note: "Keine Datensätze passen zur Auswahl – nichts geplant." } };
	if (rows.length > MAX_PLAN_ITEMS) {
		throw new PropstackError(`${rows.length} Treffer – höchstens ${MAX_PLAN_ITEMS} je Plan. Filter enger setzen oder in mehrere Pläne aufteilen.`, 400);
	}

	// Vorschau: bei Merkmalen schon sichtbar, wie viele bereits passen (Listen liefern die Merkmale mit)
	let alreadyOk = 0;
	const tagOnly = keys.every((k) => k === "add_tag_ids" || k === "remove_tag_ids");
	if (tagOnly) {
		for (const row of rows) {
			if (!("groups" in row || "property_groups" in row || "group_ids" in row)) continue;
			const tags = groupIdsOf(row);
			const adds = ((changes.add_tag_ids as number[]) ?? []).every((t) => tags.includes(t));
			const removes = ((changes.remove_tag_ids as number[]) ?? []).every((t) => !tags.includes(t));
			if (adds && removes) alreadyOk++;
		}
	}

	const planId = newPlanId();
	const plan: BulkPlan = {
		applied_by: null,
		applied_ts: null,
		broker_id: user.brokerId,
		changes,
		created_ts: now.toISOString(),
		description: input.description,
		entity,
		expires_ts: new Date(now.getTime() + PLAN_TTL_MINUTES * 60_000).toISOString(),
		id: planId,
		status: "planned",
		total: rows.length,
		undo_until: null,
		undone_by: null,
		undone_ts: null,
		user_email: user.email,
	};
	await store.createPlan(
		plan,
		rows.map((row) => ({ entity_id: Number(scalar(row.id)), label: labelOf(row, entity) })),
	);

	const perCall = Math.floor(BULK_REQUEST_BUDGET / COST[entity].apply);
	return {
		count: rows.length,
		result: {
			plan_id: planId,
			expires_at: plan.expires_ts,
			entity,
			description: input.description,
			changes,
			total: rows.length,
			already_matching: tagOnly ? alreadyOk : undefined,
			sample: rows.slice(0, 10).map((row) => ({ id: Number(scalar(row.id)), label: labelOf(row, entity) })),
			estimated_calls: Math.ceil(rows.length / perCall),
			next: `NICHTS ist geändert. Dem Nutzer Auswahl, Anzahl und Änderung zeigen und ausdrücklich bestätigen lassen – erst dann apply_plan mit plan_id. Die ID verfällt um ${plan.expires_ts}.`,
		},
	};
}

// ---------- apply_plan ----------

export const planIdInput = {
	plan_id: z.string().trim().regex(/^[a-z0-9]{6,20}$/).describe("plan_id aus plan"),
};

function itemInput(entity: "contacts" | "objects", entityId: number, changes: Raw): Raw {
	const pick = (keys: string[]) => Object.fromEntries(keys.filter((k) => changes[k] !== undefined).map((k) => [k, changes[k]]));
	return entity === "contacts"
		? { id: entityId, ...pick(["add_tag_ids", "remove_tag_ids", "broker_id", "source_id", "client_status_id", "custom_fields"]) }
		: { id: entityId, ...pick(["status_id", "rented", "custom_fields", "public_price_confirmed"]) };
}

async function runOne(
	deps: BulkDeps,
	entity: "contacts" | "objects",
	input: Raw,
	logTool: string,
): Promise<{ result: Raw; snapshot: { before: Raw; after: Raw } | null }> {
	let snapshot: { before: Raw; after: Raw } | null = null;
	const itemDeps: WriteDeps = { ...deps, capture: (s) => (snapshot = s), logTool };
	const out =
		entity === "contacts"
			? await updateContact(itemDeps, input as z.infer<z.ZodObject<typeof updateContactInput>>)
			: await updateObject(itemDeps, input as z.infer<z.ZodObject<typeof updateObjectInput>>);
	return { result: (out.result ?? {}) as Raw, snapshot };
}

function summary(counts: { status: Record<string, number>; undo: Record<string, number> }) {
	const s = counts.status;
	return {
		done: (s.done ?? 0) + (s.done_with_gaps ?? 0),
		with_gaps: s.done_with_gaps || undefined,
		unchanged: s.unchanged || undefined,
		failed: s.failed || undefined,
		remaining: s.pending ?? 0,
	};
}

export async function applyPlan(deps: BulkDeps, input: z.infer<z.ZodObject<typeof planIdInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	const store = storeOf(deps);
	const now = deps.now?.() ?? new Date();
	const plan = await store.getPlan(input.plan_id);
	if (!plan) throw new PropstackError("Plan nicht gefunden.", 404);
	if (plan.user_email !== user.email) throw new PropstackError("Nur wer den Plan erstellt hat, kann ihn ausführen.", 403);
	if (plan.status === "applied" || plan.status === "undoing" || plan.status === "undone") {
		throw new PropstackError(`Plan ist bereits ${plan.status === "applied" ? "ausgeführt" : "rückgängig gemacht"}.`, 400);
	}
	if (plan.status === "expired" || (plan.status === "planned" && new Date(plan.expires_ts) < now)) {
		await store.updatePlan(plan.id, { status: "expired" });
		throw new PropstackError(`Plan-ID abgelaufen (${PLAN_TTL_MINUTES} min). Bitte neu planen – der Bestand kann sich geändert haben.`, 400);
	}
	if (plan.status === "planned") await store.updatePlan(plan.id, { applied_by: user.email, status: "applying" });

	const cost = COST[plan.entity].apply;
	let processed = 0;
	let interrupted: string | null = null;
	for (;;) {
		const [item] = await store.items(plan.id, "pending", 1);
		if (!item || client.requestsUsed + cost > BULK_REQUEST_BUDGET) break;
		processed++;
		try {
			const { result, snapshot } = await runOne(deps, plan.entity, itemInput(plan.entity, item.entity_id, plan.changes), `apply_plan:${plan.id}`);
			const gaps = [...((result.not_applied as string[]) ?? []), ...((result.write_errors as string[]) ?? [])];
			await store.updateItem(plan.id, item.entity_id, {
				before: snapshot?.before ?? null,
				changed: snapshot?.after ?? null,
				error: null,
				not_applied: gaps.length ? gaps : null,
				status: result.updated === false ? "unchanged" : gaps.length ? "done_with_gaps" : "done",
			});
		} catch (error) {
			if (isTransient(error)) {
				// Propstack gestört → anhalten, Datensatz offen lassen (Live-Befund 16.10.: 502 mitten im Lauf)
				processed--;
				interrupted = (error as Error).message;
				await store.updateItem(plan.id, item.entity_id, { error: `Vorübergehend: ${interrupted}`.slice(0, 500) });
				break;
			}
			await store.updateItem(plan.id, item.entity_id, { error: (error as Error).message.slice(0, 500), status: "failed" });
		}
	}

	const counts = await store.counts(plan.id);
	const progress = summary(counts);
	if (progress.remaining === 0) {
		await store.updatePlan(plan.id, {
			applied_ts: now.toISOString(),
			status: "applied",
			undo_until: new Date(now.getTime() + UNDO_DAYS * 86_400_000).toISOString(),
		});
	}
	const errors = await store.recentErrors(plan.id, "apply", 10);
	return {
		count: processed,
		result: {
			plan_id: plan.id,
			finished: progress.remaining === 0,
			processed_now: processed,
			total: plan.total,
			...progress,
			problems: errors.length ? errors : undefined,
			next:
				progress.remaining === 0
					? `Fertig. Rückgängig bis ${new Date(now.getTime() + UNDO_DAYS * 86_400_000).toISOString().slice(0, 10)} mit undo_plan möglich.`
					: interrupted
						? `Angehalten – Propstack gestört (${interrupted}). Noch ${progress.remaining} offen; in ein paar Minuten apply_plan mit derselben plan_id erneut aufrufen. Bereits erledigte Datensätze werden nicht doppelt geschrieben.`
						: `Noch ${progress.remaining} offen – apply_plan mit derselben plan_id erneut aufrufen (ohne erneute Rückfrage).`,
		},
	};
}

// ---------- undo_plan ----------

const CONTACT_INPUT_KEY = Object.fromEntries(Object.entries(CONTACT_KEYS).map(([input, propstack]) => [propstack, input]));

interface Current {
	value(key: string): unknown;
	custom(key: string): unknown;
	tags: number[];
}

async function readCurrent(client: PropstackClient, entity: "contacts" | "objects", entityId: number): Promise<Current> {
	if (entity === "contacts") {
		const raw = ((await client.getContact(entityId)) ?? {}) as Raw;
		return {
			custom: (k) => (raw.custom_fields as Raw | undefined)?.[k],
			tags: groupIdsOf(raw),
			value: (k) => raw[k],
		};
	}
	const state = await readUnit(client, entityId);
	return {
		custom: (k) => unitCustomValue(state, k),
		tags: groupIdsOfUnit(state),
		value: (k) => unitValue(state, k === "status_id" ? "property_status_id" : k),
	};
}

/** Undo-Eingabe: nur Felder, deren aktueller Wert noch dem nach apply_plan entspricht. */
export function undoInput(
	entity: "contacts" | "objects",
	item: BulkItem,
	changes: Raw,
	current: Current,
): { input: Raw; restored: string[]; skipped: string[] } {
	const before = item.before ?? {};
	const after = item.changed ?? {};
	const input: Raw = { id: item.entity_id };
	const restored: string[] = [];
	const skipped: string[] = [];

	// Merkmale: nur zurücknehmen, was der Plan wirklich verändert hat
	if (Array.isArray(before.tag_ids)) {
		const had = before.tag_ids as number[];
		const add: number[] = [];
		const remove: number[] = [];
		for (const t of (changes.add_tag_ids as number[]) ?? []) {
			if (had.includes(t)) continue;
			if (current.tags.includes(t)) remove.push(t);
			else skipped.push(`Merkmal ${t} (schon entfernt)`);
		}
		for (const t of (changes.remove_tag_ids as number[]) ?? []) {
			if (!had.includes(t)) continue;
			if (!current.tags.includes(t)) add.push(t);
			else skipped.push(`Merkmal ${t} (schon wieder gesetzt)`);
		}
		if (add.length) input.add_tag_ids = add;
		if (remove.length) input.remove_tag_ids = remove;
		if (add.length || remove.length) restored.push("Merkmale");
	}

	for (const [key, old] of Object.entries(before)) {
		if (key === "tag_ids" || key === "custom_fields" || key === "description") continue;
		if (!(key in after)) continue;
		const inputKey = entity === "contacts" ? (CONTACT_INPUT_KEY[key] ?? key) : key;
		if (old === "nicht lesbar") {
			skipped.push(`${inputKey} (vorheriger Wert unbekannt)`);
			continue;
		}
		const now = current.value(key);
		if (now !== UNVERIFIABLE && !same(after[key], now)) {
			skipped.push(`${inputKey} (inzwischen geändert)`);
			continue;
		}
		input[inputKey] = old ?? null;
		restored.push(inputKey);
	}

	const customBefore = (before.custom_fields ?? {}) as Raw;
	const customAfter = (after.custom_fields ?? {}) as Raw;
	const custom: Raw = {};
	for (const [key, old] of Object.entries(customBefore)) {
		if (!(key in customAfter)) continue;
		if (old === "nicht lesbar") {
			skipped.push(`custom_fields.${key} (vorheriger Wert unbekannt)`);
			continue;
		}
		if (key === "bemerkung") {
			skipped.push("custom_fields.bemerkung (Bemerkungen werden nie zurückgesetzt)");
			continue;
		}
		const now = current.custom(key);
		if (now !== UNVERIFIABLE && !same(customAfter[key], now)) {
			skipped.push(`custom_fields.${key} (inzwischen geändert)`);
			continue;
		}
		custom[key] = old ?? null;
		restored.push(`custom_fields.${key}`);
	}
	if (Object.keys(custom).length) input.custom_fields = custom;
	if (entity === "objects" && changes.public_price_confirmed === true && Object.keys(custom).length) input.public_price_confirmed = true;
	return { input, restored, skipped };
}

export async function undoPlan(deps: BulkDeps, input: z.infer<z.ZodObject<typeof planIdInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	const store = storeOf(deps);
	const now = deps.now?.() ?? new Date();
	const plan = await store.getPlan(input.plan_id);
	if (!plan) throw new PropstackError("Plan nicht gefunden.", 404);
	if (plan.status === "planned" || plan.status === "expired") throw new PropstackError("Plan wurde nie ausgeführt – nichts rückgängig zu machen.", 400);
	if (plan.status === "undone") throw new PropstackError("Plan ist bereits rückgängig gemacht.", 400);
	const deadline = plan.undo_until ?? new Date(new Date(plan.created_ts).getTime() + UNDO_DAYS * 86_400_000).toISOString();
	if (new Date(deadline) < now) {
		throw new PropstackError(`Undo-Frist (${UNDO_DAYS} Tage) abgelaufen. Der Stand vorher steht weiterhin im Write-Log.`, 400);
	}
	if (plan.status !== "undoing") await store.updatePlan(plan.id, { status: "undoing", undone_by: user.email });

	const cost = COST[plan.entity].undo;
	let processed = 0;
	let interrupted: string | null = null;
	for (;;) {
		const [item] = await store.items(plan.id, "undoable", 1);
		if (!item || client.requestsUsed + cost > BULK_REQUEST_BUDGET) break;
		processed++;
		try {
			const current = await readCurrent(client, plan.entity, item.entity_id);
			const { input: undo, restored, skipped } = undoInput(plan.entity, item, plan.changes, current);
			if (!restored.length) {
				await store.updateItem(plan.id, item.entity_id, { undo_note: skipped.join("; ") || "nichts zurückzusetzen", undo_status: "skipped" });
				continue;
			}
			const { result } = await runOne(deps, plan.entity, undo, `undo_plan:${plan.id}`);
			const gaps = [...((result.not_applied as string[]) ?? []), ...((result.write_errors as string[]) ?? [])];
			const status: UndoStatus = skipped.length || gaps.length ? "partial" : "undone";
			await store.updateItem(plan.id, item.entity_id, {
				undo_note: [...skipped, ...gaps.map((g) => `nicht übernommen: ${g}`)].join("; ") || null,
				undo_status: status,
			});
		} catch (error) {
			if (isTransient(error)) {
				processed--;
				interrupted = (error as Error).message;
				await store.updateItem(plan.id, item.entity_id, { undo_note: `Vorübergehend: ${interrupted}`.slice(0, 500) });
				break;
			}
			await store.updateItem(plan.id, item.entity_id, { undo_note: (error as Error).message.slice(0, 500), undo_status: "failed" });
		}
	}

	const remaining = (await store.items(plan.id, "undoable", 1)).length > 0;
	const counts = await store.counts(plan.id);
	if (!remaining) await store.updatePlan(plan.id, { status: "undone", undone_ts: now.toISOString() });
	const problems = await store.recentErrors(plan.id, "undo", 10);
	const u = counts.undo;
	return {
		count: processed,
		result: {
			plan_id: plan.id,
			finished: !remaining,
			processed_now: processed,
			undone: u.undone ?? 0,
			partial: u.partial || undefined,
			skipped: u.skipped || undefined,
			failed: u.failed || undefined,
			problems: problems.length ? problems : undefined,
			interrupted: interrupted ?? undefined,
			next: interrupted
				? `Angehalten – Propstack gestört (${interrupted}). In ein paar Minuten undo_plan mit derselben plan_id erneut aufrufen.`
				: remaining
					? "undo_plan mit derselben plan_id erneut aufrufen."
					: "Fertig. Übersprungene Felder wurden inzwischen von jemand anderem geändert und bleiben so.",
		},
	};
}
