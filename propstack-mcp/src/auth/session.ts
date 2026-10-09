import type { PropstackClient } from "../propstack-client";
import { resolveBroker } from "./broker-lookup";
import { AuthRejection } from "./errors";
import { verifyGoogleIdToken } from "./google-id-token";

// Verschlüsselt im MCP-Token gespeichert und im McpAgent als this.props verfügbar.
// Bewusst ohne Google-Access-Token: Der Worker braucht nach dem Login keinen Google-Zugriff.
export type Props = {
	email: string;
	name: string;
	brokerId: number;
};

export interface AuthDeps {
	client: Pick<PropstackClient, "listBrokers">;
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
	const broker = await resolveBroker(identity.email, deps);
	return { brokerId: broker.id, email: broker.email, name: broker.name };
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
	deps: Pick<AuthDeps, "client" | "kv">,
): Promise<RefreshResult> {
	try {
		const broker = await resolveBroker(props.email, deps);
		return { ok: true, props: { brokerId: broker.id, email: broker.email, name: broker.name } };
	} catch (error) {
		if (error instanceof AuthRejection) return { kind: "rejected", message: error.message, ok: false };
		// Propstack nicht erreichbar → fail closed, aber als vorübergehend kennzeichnen.
		return { kind: "unavailable", message: "Propstack-Nutzerprüfung derzeit nicht möglich.", ok: false };
	}
}
