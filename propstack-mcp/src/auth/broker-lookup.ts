import { z } from "zod";
import { BROKER_ALIASES, type BrokerAlias, BROKER_CACHE_TTL_SECONDS } from "../config";
import type { PropstackClient } from "../propstack-client";
import { AuthRejection } from "./errors";

// Prüfung 3b: Zur Mail existiert ein Propstack-Nutzer (GET /v1/brokers), sonst Ablehnung.
// Die V1-Antwort kennt kein Aktiv-Flag: Jeder Nutzer, den /v1/brokers liefert, gilt als aktiv.

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
 * Ausnahme auflösen: Die Person schreibt unter dem Propstack-Nutzer einer Kollegin. Der muss genau so existieren,
 * wie er hinterlegt ist (E-Mail und ID) – sonst Ablehnung, nie ein anderer Nutzer.
 */
function resolveAlias(rawBrokers: unknown, email: string, alias: BrokerAlias): BrokerIdentity {
	const target = matchBroker(rawBrokers, alias.propstackEmail);
	if (!target || target.id !== alias.propstackId) {
		throw new AuthRejection(
			"Für diese E-Mail ist eine Ausnahme hinterlegt, aber der zugehörige Propstack-Nutzer existiert so nicht mehr. Zugriff verweigert – bitte an Florian wenden.",
		);
	}
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
	deps: { aliases?: Record<string, BrokerAlias>; client: Pick<PropstackClient, "listBrokers">; kv: KVNamespace },
): Promise<BrokerIdentity> {
	const wanted = normalizeEmail(email);
	const key = CACHE_PREFIX + wanted;

	const cached = cachedSchema.safeParse(await deps.kv.get(key, "json"));
	if (cached.success) return cached.data;

	const brokers = await deps.client.listBrokers();
	const broker = matchBroker(brokers, email);
	if (broker) {
		await deps.kv.put(key, JSON.stringify(broker), { expirationTtl: BROKER_CACHE_TTL_SECONDS });
		return broker;
	}
	const aliases = deps.aliases ?? BROKER_ALIASES;
	const alias = Object.prototype.hasOwnProperty.call(aliases, wanted) ? aliases[wanted] : undefined;
	if (alias) return resolveAlias(brokers, wanted, alias);
	throw new AuthRejection("Zu dieser E-Mail existiert kein aktiver Propstack-Nutzer. Zugriff verweigert.");
}
