import { z } from "zod";

// Service-Token für Abläufe ohne Menschen (Auftrag Florian, 25.11.2026: GitHub-Workflow „Objekte Handler“).
// Der Workflow ruft den Connector über die Claude-API auf (MCP-Connector mit authorization_token); Anthropic schickt
// das Token als „Authorization: Bearer svc.<payload>.<signatur>“ an /mcp.
//   payload  = base64url ohne Padding von {"sub","broker_id","ts","iat","exp"}
//   signatur = base64url ohne Padding von HMAC-SHA256(SERVICE_TOKEN_SECRET, "svc." + payload)
// Geprüft wird bei jedem Aufruf: Wird das Secret gelöscht oder getauscht, gilt kein altes Token mehr.

export const SERVICE_SUBJECTS = ["objekte-handler"] as const;
export type ServiceSubject = (typeof SERVICE_SUBJECTS)[number];

/** Höchste Laufzeit eines Tokens (exp − iat). */
export const SERVICE_TOKEN_MAX_LIFETIME_SECONDS = 1800;
/** So weit darf iat in der Zukunft liegen (Uhren der Runner). */
export const SERVICE_TOKEN_MAX_CLOCK_SKEW_SECONDS = 60;
/** Kürzere Secrets gelten als nicht gesetzt – ein zu kurzes Secret ließe sich erraten. */
export const SERVICE_SECRET_MIN_LENGTH = 32;
const MAX_TOKEN_LENGTH = 2048;
const TOKEN_PATTERN = /^svc\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$/;

const claimsSchema = z.strictObject({
	sub: z.enum(SERVICE_SUBJECTS),
	broker_id: z.number().int().positive(),
	// Slack-Zeitstempel der Nachricht, um die es geht („1764099999.123456“) – landet in Notizen und Protokoll
	ts: z.string().regex(/^\d{9,11}\.\d{6}$/),
	iat: z.number().int(),
	exp: z.number().int(),
});
export type ServiceClaims = z.infer<typeof claimsSchema>;

/** Das Secret aus der Umgebung – oder null: Dann ist der Service-Zugang aus (fail closed). */
export function serviceSecret(env: Pick<Env, "SERVICE_TOKEN_SECRET">): string | null {
	const secret = env.SERVICE_TOKEN_SECRET?.trim() ?? "";
	if (secret === "") return null;
	if (secret.length < SERVICE_SECRET_MIN_LENGTH) {
		console.warn(`SERVICE_TOKEN_SECRET ist kürzer als ${SERVICE_SECRET_MIN_LENGTH} Zeichen – der Service-Zugang bleibt aus.`);
		return null;
	}
	return secret;
}

const encoder = new TextEncoder();

function toBase64Url(bytes: Uint8Array): string {
	let binary = "";
	for (const byte of bytes) binary += String.fromCharCode(byte);
	return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64Url(text: string): Uint8Array | null {
	if (!/^[A-Za-z0-9_-]+$/.test(text) || text.length % 4 === 1) return null;
	try {
		const binary = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4));
		return Uint8Array.from(binary, (char) => char.charCodeAt(0));
	} catch {
		return null;
	}
}

function hmacKey(secret: string, usage: "sign" | "verify"): Promise<CryptoKey> {
	return crypto.subtle.importKey("raw", encoder.encode(secret), { hash: "SHA-256", name: "HMAC" }, false, [usage]);
}

/** Token bauen – so, wie es der Workflow tut. Im Connector nur für Tests und Doku. */
export async function signServiceToken(claims: ServiceClaims, secret: string): Promise<string> {
	const payload = toBase64Url(encoder.encode(JSON.stringify(claims)));
	const signature = new Uint8Array(await crypto.subtle.sign("HMAC", await hmacKey(secret, "sign"), encoder.encode(`svc.${payload}`)));
	return `svc.${payload}.${toBase64Url(signature)}`;
}

/**
 * Token prüfen. null bei jedem Fehler – ohne Hinweis, woran es lag (der Aufrufer bekommt 401 wie bei jedem
 * ungültigen Token). Die Signatur wird mit crypto.subtle.verify geprüft (zeitkonstant), bevor der Inhalt gelesen wird.
 */
export async function verifyServiceToken(token: string, secret: string, nowSeconds: number): Promise<ServiceClaims | null> {
	if (token.length > MAX_TOKEN_LENGTH) return null;
	const match = TOKEN_PATTERN.exec(token);
	if (!match) return null;
	const [, payload, signatureText] = match;
	const signature = fromBase64Url(signatureText);
	if (!signature) return null;
	const valid = await crypto.subtle.verify("HMAC", await hmacKey(secret, "verify"), signature, encoder.encode(`svc.${payload}`));
	if (!valid) return null;

	const raw = fromBase64Url(payload);
	if (!raw) return null;
	let parsed: unknown;
	try {
		parsed = JSON.parse(new TextDecoder().decode(raw));
	} catch {
		return null;
	}
	const claims = claimsSchema.safeParse(parsed);
	if (!claims.success) return null;
	const { exp, iat } = claims.data;
	if (exp <= nowSeconds) return null;
	if (exp <= iat || exp - iat > SERVICE_TOKEN_MAX_LIFETIME_SECONDS) return null;
	if (iat > nowSeconds + SERVICE_TOKEN_MAX_CLOCK_SKEW_SECONDS) return null;
	return claims.data;
}
