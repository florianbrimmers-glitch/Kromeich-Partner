import { z } from "zod";
import { ALLOWED_HOSTED_DOMAIN } from "../config";
import { AuthRejection } from "./errors";

// Prüfung 3a: ID-Token gültig, hd == kromeichpartner.de, email_verified == true.

export const GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs";
const GOOGLE_ISSUERS = new Set(["https://accounts.google.com", "accounts.google.com"]);
const CLOCK_SKEW_SECONDS = 60;

export interface GoogleIdentity {
	email: string;
	name: string;
	subject: string;
}

const claimsSchema = z.object({
	aud: z.union([z.string(), z.array(z.string())]),
	email: z.string().optional(),
	email_verified: z.unknown().optional(),
	exp: z.number(),
	hd: z.string().optional(),
	iat: z.number().optional(),
	iss: z.string(),
	name: z.string().optional(),
	sub: z.string(),
});

/** Prüft die Claims eines (bereits signaturgeprüften) Google-ID-Tokens. */
export function checkIdTokenClaims(
	rawClaims: unknown,
	{ clientId, nowSeconds }: { clientId: string; nowSeconds: number },
): GoogleIdentity {
	const parsed = claimsSchema.safeParse(rawClaims);
	if (!parsed.success) throw new AuthRejection("Ungültiges Google-ID-Token.");
	const claims = parsed.data;

	if (!GOOGLE_ISSUERS.has(claims.iss)) throw new AuthRejection("ID-Token stammt nicht von Google.");
	const audiences = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
	if (!clientId || !audiences.includes(clientId)) {
		throw new AuthRejection("ID-Token ist nicht für diese Anwendung ausgestellt.");
	}
	if (claims.exp + CLOCK_SKEW_SECONDS < nowSeconds) throw new AuthRejection("ID-Token ist abgelaufen.");
	if (claims.iat !== undefined && claims.iat - CLOCK_SKEW_SECONDS > nowSeconds) {
		throw new AuthRejection("ID-Token ist noch nicht gültig.");
	}

	// hd fehlt bei privaten Gmail-Konten → abgelehnt.
	if (claims.hd?.toLowerCase() !== ALLOWED_HOSTED_DOMAIN) {
		throw new AuthRejection(`Nur Konten der Domain ${ALLOWED_HOSTED_DOMAIN} sind zugelassen.`);
	}
	// Streng: nur das boolesche true zählt.
	if (claims.email_verified !== true) throw new AuthRejection("Die E-Mail-Adresse ist bei Google nicht verifiziert.");
	if (!claims.email) throw new AuthRejection("Das ID-Token enthält keine E-Mail-Adresse.");

	return { email: claims.email, name: claims.name ?? claims.email, subject: claims.sub };
}

interface Jwk {
	kid?: string;
	kty: string;
	n?: string;
	e?: string;
	alg?: string;
}

function base64UrlDecode(input: string): Uint8Array<ArrayBuffer> {
	const base64 = input.replace(/-/g, "+").replace(/_/g, "/");
	const binary = atob(base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "="));
	const bytes = new Uint8Array(binary.length);
	for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
	return bytes;
}

function decodeJsonPart(part: string): unknown {
	return JSON.parse(new TextDecoder().decode(base64UrlDecode(part)));
}

async function fetchJwks(fetchFn: typeof fetch): Promise<Jwk[]> {
	const response = await fetchFn(GOOGLE_JWKS_URL);
	if (!response.ok) throw new Error(`Google-JWKS nicht abrufbar (${response.status})`);
	const body = (await response.json()) as { keys?: Jwk[] };
	return body.keys ?? [];
}

/**
 * Verifiziert Signatur (RS256 gegen Google-JWKS) und Claims eines Google-ID-Tokens.
 * Wirft AuthRejection bei ungültigem Token oder unzulässigem Konto.
 */
export async function verifyGoogleIdToken(
	idToken: string,
	options: { clientId: string; nowSeconds?: number; fetchFn?: typeof fetch },
): Promise<GoogleIdentity> {
	const parts = idToken.split(".");
	if (parts.length !== 3) throw new AuthRejection("Ungültiges Google-ID-Token.");
	const [headerPart, payloadPart, signaturePart] = parts;

	let header: { alg?: string; kid?: string };
	let claims: unknown;
	try {
		header = decodeJsonPart(headerPart) as { alg?: string; kid?: string };
		claims = decodeJsonPart(payloadPart);
	} catch {
		throw new AuthRejection("Ungültiges Google-ID-Token.");
	}
	if (header.alg !== "RS256" || !header.kid) throw new AuthRejection("Ungültiges Google-ID-Token.");

	const keys = await fetchJwks(options.fetchFn ?? fetch.bind(globalThis));
	const jwk = keys.find((key) => key.kid === header.kid && key.kty === "RSA");
	if (!jwk) throw new AuthRejection("Signaturschlüssel des ID-Tokens unbekannt.");

	const key = await crypto.subtle.importKey(
		"jwk",
		{ e: jwk.e, kty: jwk.kty, n: jwk.n, alg: "RS256", ext: true },
		{ hash: "SHA-256", name: "RSASSA-PKCS1-v1_5" },
		false,
		["verify"],
	);
	const valid = await crypto.subtle.verify(
		"RSASSA-PKCS1-v1_5",
		key,
		base64UrlDecode(signaturePart),
		new TextEncoder().encode(`${headerPart}.${payloadPart}`),
	);
	if (!valid) throw new AuthRejection("Signatur des ID-Tokens ist ungültig.");

	return checkIdTokenClaims(claims, {
		clientId: options.clientId,
		nowSeconds: options.nowSeconds ?? Math.floor(Date.now() / 1000),
	});
}
