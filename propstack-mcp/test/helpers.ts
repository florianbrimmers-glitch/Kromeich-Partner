// Test-Hilfen: echter RSA-Schlüssel + signierte JWTs, In-Memory-KV.

export const CLIENT_ID = "test-client.apps.googleusercontent.com";
export const NOW = 1_800_000_000;

function base64Url(bytes: Uint8Array): string {
	let binary = "";
	for (const byte of bytes) binary += String.fromCharCode(byte);
	return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const encodeJson = (value: unknown) => base64Url(new TextEncoder().encode(JSON.stringify(value)));

export async function createSigner(kid = "test-kid") {
	const keyPair = (await crypto.subtle.generateKey(
		{ hash: "SHA-256", modulusLength: 2048, name: "RSASSA-PKCS1-v1_5", publicExponent: new Uint8Array([1, 0, 1]) },
		true,
		["sign", "verify"],
	)) as CryptoKeyPair;
	const publicJwk = (await crypto.subtle.exportKey("jwk", keyPair.publicKey)) as JsonWebKey;

	const sign = async (claims: Record<string, unknown>, header: Record<string, unknown> = {}) => {
		const head = encodeJson({ alg: "RS256", kid, typ: "JWT", ...header });
		const body = encodeJson(claims);
		const signature = await crypto.subtle.sign(
			"RSASSA-PKCS1-v1_5",
			keyPair.privateKey,
			new TextEncoder().encode(`${head}.${body}`),
		);
		return `${head}.${body}.${base64Url(new Uint8Array(signature))}`;
	};

	const jwksFetch = (async () =>
		new Response(JSON.stringify({ keys: [{ ...publicJwk, alg: "RS256", kid, use: "sig" }] }), {
			headers: { "Content-Type": "application/json" },
		})) as unknown as typeof fetch;

	return { jwksFetch, sign };
}

export function validClaims(overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return {
		aud: CLIENT_ID,
		email: "florian.brimmers@kromeichpartner.de",
		email_verified: true,
		exp: NOW + 3600,
		hd: "kromeichpartner.de",
		iat: NOW,
		iss: "https://accounts.google.com",
		name: "Florian Brimmers",
		sub: "1234567890",
		...overrides,
	};
}

export class MemoryKV {
	readonly store = new Map<string, string>();
	readonly ttls = new Map<string, number | undefined>();

	async get(key: string, type?: "json") {
		const value = this.store.get(key);
		if (value === undefined) return null;
		return type === "json" ? JSON.parse(value) : value;
	}

	async put(key: string, value: string, options?: { expirationTtl?: number }) {
		this.store.set(key, value);
		this.ttls.set(key, options?.expirationTtl);
	}

	asKV(): KVNamespace {
		return this as unknown as KVNamespace;
	}
}

export const BROKERS = [
	{ email: "florian.brimmers@kromeichpartner.de", first_name: "Florian", id: 111, last_name: "Brimmers", name: "Florian Brimmers" },
	{ email: "Lena.Klinnert@KromeichPartner.de", first_name: "Lena", id: 254958, last_name: "Klinnert", name: "Lena Klinnert" },
	{ email: null, id: 999, name: "Ohne Mail" },
];

export function brokerClient(brokers: unknown = BROKERS) {
	let calls = 0;
	return {
		get calls() {
			return calls;
		},
		listBrokers: async () => {
			calls++;
			return brokers;
		},
	};
}
