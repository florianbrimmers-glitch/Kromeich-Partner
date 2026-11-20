import { z } from "zod";
import { BLOCKED_LOGIN_EMAILS, BROKER_ALIASES, type BrokerAlias, BROKER_CACHE_TTL_SECONDS } from "../config";
import { type PropstackClient, PropstackError } from "../propstack-client";
import { AuthRejection } from "./errors";

// Prüfung 3b: Zur Mail existiert ein Propstack-Nutzer (GET /v1/brokers), sonst Ablehnung.
// Die V1-Antwort kennt kein Aktiv-Flag. Deshalb seit v0.14.0 (Freigabe Florian, 20.11.2026) zusätzlich die zweite
// Schnittstelle (GET /v2/brokers): Der Nutzer muss dort aktiv, nicht gesperrt und nicht archiviert sein und darf kein
// technischer Nutzer sein. Die beiden Sammelpostfächer sind außerdem fest ausgesperrt (BLOCKED_LOGIN_EMAILS).

/** Quelle der Nutzerlisten. Ohne zweiten Schlüssel (hasV2Key) gilt nur die einfache Prüfung über /v1/brokers. */
export type BrokerSource = Pick<PropstackClient, "listBrokers"> & Partial<Pick<PropstackClient, "hasV2Key" | "listBrokersV2">>;

const NO_ACTIVE_USER = "Zu dieser E-Mail existiert kein aktiver Propstack-Nutzer. Zugriff verweigert.";
const SHARED_MAILBOX = "Sammelpostfächer und technische Propstack-Nutzer können den Connector nicht nutzen. Bitte mit dem eigenen Konto anmelden.";

export interface BrokerIdentity {
	id: number;
	name: string;
	email: string;
	/** Nur bei einer Ausnahme (BROKER_ALIASES): Name des Propstack-Nutzers, unter dem die Person schreibt. */
	brokerName?: string;
}

const brokerSchema = z.object({
	email: z.string().nullish(),
	first_name: z.string().nullish(),
	id: z.number().int(),
	last_name: z.string().nullish(),
	name: z.string().nullish(),
});
const brokerListSchema = z.array(z.unknown());
const cachedSchema = z.object({ email: z.string(), id: z.number().int(), name: z.string() });

// „v2:“ seit der strengen Prüfung – ältere Einträge (nur gegen /v1/brokers geprüft) zählen damit nicht mehr.
const CACHE_PREFIX = "propstack-broker:v2:";

const stateSchema = z.object({ active: z.unknown(), archived: z.unknown(), blocked: z.unknown(), id: z.number().int(), role: z.unknown() });
type BrokerStates = Map<number, z.infer<typeof stateSchema>>;

/**
 * Zustand aller Propstack-Nutzer laut zweiter Schnittstelle. null = sie steht nicht zur Verfügung (kein zweiter
 * Schlüssel, oder er ist ungültig bzw. darf die Nutzerliste nicht lesen) – dann gilt die einfache Prüfung wie vor
 * v0.14.0, statt alle auszusperren. Ein Ausfall oder eine leere bzw. unlesbare Antwort ist dagegen ein Fehler:
 * vorübergehend kommt niemand neu hinein, aber niemand wird deswegen abgemeldet.
 */
async function loadBrokerStates(client: BrokerSource): Promise<BrokerStates | null> {
	if (!client.hasV2Key || !client.listBrokersV2) return null;
	let raw: unknown;
	try {
		raw = await client.listBrokersV2();
	} catch (error) {
		if (error instanceof PropstackError && [401, 403, 404].includes(error.status)) {
			console.warn(`Strenge Nutzerprüfung nicht möglich (GET /v2/brokers → ${error.status}) – es gilt die einfache Prüfung.`);
			return null;
		}
		throw error;
	}
	const rows = Array.isArray(raw) ? raw : raw && typeof raw === "object" && Array.isArray((raw as { data?: unknown }).data) ? (raw as { data: unknown[] }).data : null;
	if (!rows) throw new Error("Unerwartetes Format von GET /v2/brokers");
	const states: BrokerStates = new Map();
	for (const item of rows) {
		const row = stateSchema.safeParse(item);
		if (row.success) states.set(row.data.id, row.data);
	}
	if (states.size === 0) throw new Error("GET /v2/brokers lieferte keine Nutzer");
	return states;
}

/** Nur aktive, nicht gesperrte, nicht archivierte Nutzer – und keine technischen. Ohne Zustandsliste (null) entfällt die Prüfung. */
function assertUsable(states: BrokerStates | null, id: number): void {
	if (!states) return;
	const state = states.get(id);
	if (!state || state.active !== true || state.blocked === true || state.archived === true) throw new AuthRejection(NO_ACTIVE_USER);
	if (state.role === "technical") throw new AuthRejection(SHARED_MAILBOX);
}

/** Für whoami: Welche Anmeldeprüfung gilt gerade? */
export async function authCheckMode(client: BrokerSource): Promise<string> {
	try {
		return (await loadBrokerStates(client))
			? "streng (nur aktive, nicht gesperrte Propstack-Nutzer; keine Sammelpostfächer)"
			: "einfach (zweite Propstack-Schnittstelle nicht nutzbar: Nutzerliste ohne Aktiv-Prüfung; die beiden Sammelpostfächer bleiben ausgesperrt)";
	} catch {
		return "derzeit nicht prüfbar (Propstack antwortet nicht wie erwartet)";
	}
}

export function normalizeEmail(email: string): string {
	return email.trim().toLowerCase();
}

/**
 * Sucht genau einen Nutzer mit dieser Mail. Mehrdeutige Treffer werden abgelehnt,
 * damit nie unter einer falschen Propstack-ID geschrieben wird.
 */
export function matchBroker(rawBrokers: unknown, email: string): BrokerIdentity | null {
	const list = brokerListSchema.safeParse(rawBrokers);
	if (!list.success) throw new Error("Unerwartetes Format von GET /v1/brokers");

	const wanted = normalizeEmail(email);
	const matches: BrokerIdentity[] = [];
	for (const raw of list.data) {
		const broker = brokerSchema.safeParse(raw);
		if (!broker.success || !broker.data.email) continue;
		if (normalizeEmail(broker.data.email) !== wanted) continue;
		const { first_name, last_name, name } = broker.data;
		const fullName = name || [first_name, last_name].filter(Boolean).join(" ") || wanted;
		matches.push({ email: wanted, id: broker.data.id, name: fullName });
	}

	if (matches.length > 1) {
		throw new AuthRejection(
			"Zu dieser E-Mail gibt es mehrere Propstack-Nutzer. Bitte an Florian wenden.",
		);
	}
	return matches[0] ?? null;
}

/**
 * Ausnahme auflösen: Die Person schreibt unter dem Propstack-Nutzer einer Kollegin. Der muss genau so existieren,
 * wie er hinterlegt ist (E-Mail und ID) – sonst Ablehnung, nie ein anderer Nutzer.
 */
function resolveAlias(rawBrokers: unknown, email: string, alias: BrokerAlias, states: BrokerStates | null): BrokerIdentity {
	const target = matchBroker(rawBrokers, alias.propstackEmail);
	if (!target || target.id !== alias.propstackId) {
		throw new AuthRejection(
			"Für diese E-Mail ist eine Ausnahme hinterlegt, aber der zugehörige Propstack-Nutzer existiert so nicht mehr. Zugriff verweigert – bitte an Florian wenden.",
		);
	}
	assertUsable(states, target.id);
	return { brokerName: target.name, email, id: target.id, name: alias.name };
}

/**
 * Löst Mail → Propstack-Nutzer auf. Cache-first (KV, TTL 1 h).
 * Nur Treffer werden gecacht, damit neu angelegte Nutzer sofort durchkommen.
 * Ein eigener Propstack-Nutzer geht einer Ausnahme (BROKER_ALIASES) immer vor. Ausnahmen werden nie gecacht:
 * Ist der Eintrag entfernt, endet der Zugang beim nächsten Refresh.
 */
export async function resolveBroker(
	email: string,
	deps: { aliases?: Record<string, BrokerAlias>; client: BrokerSource; kv: KVNamespace },
): Promise<BrokerIdentity> {
	const wanted = normalizeEmail(email);
	// vor Cache und Propstack: Sammelpostfächer kommen nie durch
	if (BLOCKED_LOGIN_EMAILS.includes(wanted)) throw new AuthRejection(SHARED_MAILBOX);
	const key = CACHE_PREFIX + wanted;

	const cached = cachedSchema.safeParse(await deps.kv.get(key, "json"));
	if (cached.success) return cached.data;

	const [brokers, states] = await Promise.all([deps.client.listBrokers(), loadBrokerStates(deps.client)]);
	const broker = matchBroker(brokers, email);
	if (broker) {
		assertUsable(states, broker.id);
		await deps.kv.put(key, JSON.stringify(broker), { expirationTtl: BROKER_CACHE_TTL_SECONDS });
		return broker;
	}
	const aliases = deps.aliases ?? BROKER_ALIASES;
	const alias = Object.prototype.hasOwnProperty.call(aliases, wanted) ? aliases[wanted] : undefined;
	if (alias) return resolveAlias(brokers, wanted, alias, states);
	throw new AuthRejection(NO_ACTIVE_USER);
}
