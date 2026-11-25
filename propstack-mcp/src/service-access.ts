import { type BrokerSource, resolveServiceBroker } from "./auth/broker-lookup";
import { AuthRejection } from "./auth/errors";
import { serviceSecret, verifyServiceToken } from "./auth/service-token";
import type { Props } from "./auth/session";

// Service-Zugang an /mcp (siehe src/auth/service-token.ts): ein zweiter Weg neben OAuth, nur für Tokens mit „svc.“.
// Alles andere – kein Token, OAuth-Tokens, andere Pfade, ungültige Service-Tokens – geht unverändert an den
// OAuth-Provider, der wie bisher mit 401 antwortet.

export type ServiceAccess = { kind: "props"; props: Props } | { kind: "response"; response: Response } | null;

const isMcpPath = (pathname: string) => pathname === "/mcp" || pathname.startsWith("/mcp/");

function jsonError(status: number, error: string, description: string, headers: Record<string, string> = {}): Response {
	return new Response(JSON.stringify({ error, error_description: description }), {
		headers: { "Content-Type": "application/json", ...headers },
		status,
	});
}

/**
 * Prüft eine Anfrage auf den Service-Zugang.
 * - null: kein Service-Token, Weg aus oder Token ungültig → der OAuth-Provider antwortet (401 wie heute).
 * - props: gültiges Token, Propstack-Nutzer geprüft → Sitzung wie die eines angemeldeten Nutzers.
 * - response: Token gültig, aber der Nutzer darf nicht (403) oder Propstack ist nicht erreichbar (503).
 */
export async function serviceAccess(
	request: Request,
	env: Pick<Env, "SERVICE_TOKEN_SECRET">,
	deps: { client: BrokerSource; kv: KVNamespace; nowSeconds?: number },
): Promise<ServiceAccess> {
	if (!isMcpPath(new URL(request.url).pathname)) return null;
	const header = request.headers.get("Authorization") ?? "";
	if (!header.startsWith("Bearer svc.")) return null;
	const secret = serviceSecret(env);
	if (!secret) return null;
	const claims = await verifyServiceToken(header.slice("Bearer ".length), secret, deps.nowSeconds ?? Math.floor(Date.now() / 1000));
	if (!claims) return null;

	try {
		const broker = await resolveServiceBroker(claims.broker_id, deps);
		return {
			kind: "props",
			props: { auftrag: claims.ts, brokerId: broker.id, email: broker.email, name: broker.name, service: claims.sub },
		};
	} catch (error) {
		if (error instanceof AuthRejection) {
			console.warn(`Service-Zugang abgelehnt (${claims.sub}, broker_id ${claims.broker_id}):`, error.message);
			return { kind: "response", response: jsonError(403, "forbidden", error.message) };
		}
		console.error("Service-Zugang: Nutzerprüfung nicht möglich", error);
		return {
			kind: "response",
			response: jsonError(503, "temporarily_unavailable", "Propstack-Nutzerprüfung derzeit nicht möglich.", { "Retry-After": "60" }),
		};
	}
}
