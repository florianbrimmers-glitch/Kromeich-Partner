import { z } from "zod";
import { BROKER_CACHE_TTL_SECONDS } from "../config";
import type { PropstackClient } from "../propstack-client";
import { AuthRejection } from "./errors";

// Prüfung 3b: Zur Mail existiert ein Propstack-Nutzer (GET /v1/brokers), sonst Ablehnung.
// Die V1-Antwort kennt kein Aktiv-Flag: Jeder Nutzer, den /v1/brokers liefert, gilt als aktiv.

export interface BrokerIdentity {
	id: number;
	name: string;
	email: string;
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

const CACHE_PREFIX = "propstack-broker:";

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
 * Löst Mail → Propstack-Nutzer auf. Cache-first (KV, TTL 1 h).
 * Nur Treffer werden gecacht, damit neu angelegte Nutzer sofort durchkommen.
 */
export async function resolveBroker(
	email: string,
	deps: { client: Pick<PropstackClient, "listBrokers">; kv: KVNamespace },
): Promise<BrokerIdentity> {
	const key = CACHE_PREFIX + normalizeEmail(email);

	const cached = cachedSchema.safeParse(await deps.kv.get(key, "json"));
	if (cached.success) return cached.data;

	const broker = matchBroker(await deps.client.listBrokers(), email);
	if (!broker) {
		throw new AuthRejection(
			"Zu dieser E-Mail existiert kein aktiver Propstack-Nutzer. Zugriff verweigert.",
		);
	}
	await deps.kv.put(key, JSON.stringify(broker), { expirationTtl: BROKER_CACHE_TTL_SECONDS });
	return broker;
}
