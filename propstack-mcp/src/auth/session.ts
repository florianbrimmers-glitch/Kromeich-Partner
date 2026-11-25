import type { BrokerAlias } from "../config";
import { type BrokerIdentity, type BrokerSource, resolveBroker } from "./broker-lookup";
import { AuthRejection } from "./errors";
import { verifyGoogleIdToken } from "./google-id-token";

// Verschlüsselt im MCP-Token gespeichert und im McpAgent als this.props verfügbar.
// Bewusst ohne Google-Access-Token: Der Worker braucht nach dem Login keinen Google-Zugriff.
export type Props = {
	email: string;
	name: string;
	brokerId: number;
	/**
	 * Nur bei einer Ausnahme (BROKER_ALIASES): Name des Propstack-Nutzers, unter dem die Person schreibt.
	 * email und name sind dann die der Person, brokerId die des Propstack-Nutzers.
	 */
	brokerName?: string;
	/** Nur im Service-Zugang (src/service-access.ts): welcher Ablauf – z. B. „objekte-handler“. */
	service?: string;
	/** Nur im Service-Zugang: der Auftrag, um den es geht (Slack-Zeitstempel der Nachricht). */
	auftrag?: string;
};

/**
 * Wer etwas über Claude geschrieben hat – für Anlage- und Änderungsvermerke:
 * „über Claude (Propstack MCP) von <Name>“, im Service-Zugang „über Claude (objekte-handler, Slack <ts>) für <Name>“.
 */
export function viaClaude(user: Pick<Props, "name" | "service" | "auftrag">): string {
	return user.service ? `über Claude (${user.service}, Slack ${user.auftrag}) für ${user.name}` : `über Claude (Propstack MCP) von ${user.name}`;
}

const toProps = (broker: BrokerIdentity): Props => ({
	brokerId: broker.id,
	email: broker.email,
	name: broker.name,
	...(broker.brokerName ? { brokerName: broker.brokerName } : {}),
});

/** Name des Propstack-Nutzers, unter dem geschrieben wird (Betreuer, Aufgaben) – in aller Regel die Person selbst. */
export function brokerLabel(user: Pick<Props, "name" | "brokerName">): string {
	return user.brokerName ?? user.name;
}

/** Für whoami: als wer man angemeldet ist – und bei einer Ausnahme, unter wessen Propstack-Nutzer geschrieben wird. */
export function identityInfo(props: Props): Record<string, unknown> {
	const base = {
		email: props.email,
		name: props.name,
		propstack_user_id: props.brokerId,
		...(props.service ? { auftrag: props.auftrag, service: props.service } : {}),
	};
	if (!props.brokerName) return base;
	return {
		...base,
		propstack_user_name: props.brokerName,
		hinweis: `Du hast keinen eigenen Propstack-Nutzer. Was du über Claude schreibst, läuft in Propstack unter ${props.brokerName} (Betreuer, Aufgaben). In den Notizen und im Protokoll des Connectors steht dein Name.`,
	};
}

export interface AuthDeps {
	/** Nur für Tests: andere Ausnahmen als die hinterlegten (BROKER_ALIASES). */
	aliases?: Record<string, BrokerAlias>;
	client: BrokerSource;
	kv: KVNamespace;
	clientId: string;
	fetchFn?: typeof fetch;
	nowSeconds?: number;
}

/** Login: 3a (ID-Token + Domain) und danach 3b (Propstack-Nutzer). */
export async function authorizeLogin(idToken: string, deps: AuthDeps): Promise<Props> {
	const identity = await verifyGoogleIdToken(idToken, {
		clientId: deps.clientId,
		fetchFn: deps.fetchFn,
		nowSeconds: deps.nowSeconds,
	});
	return toProps(await resolveBroker(identity.email, deps));
}

export type RefreshResult =
	| { ok: true; props: Props }
	| { ok: false; kind: "rejected" | "unavailable"; message: string };

/**
 * Refresh: 3b erneut prüfen (Offboarding). Eine geänderte Propstack-ID wird übernommen,
 * damit Writes nie unter einer veralteten ID laufen.
 */
export async function recheckOnRefresh(
	props: Props,
	deps: Pick<AuthDeps, "aliases" | "client" | "kv">,
): Promise<RefreshResult> {
	try {
		return { ok: true, props: toProps(await resolveBroker(props.email, deps)) };
	} catch (error) {
		if (error instanceof AuthRejection) return { kind: "rejected", message: error.message, ok: false };
		// Propstack nicht erreichbar → fail closed, aber als vorübergehend kennzeichnen.
		return { kind: "unavailable", message: "Propstack-Nutzerprüfung derzeit nicht möglich.", ok: false };
	}
}
