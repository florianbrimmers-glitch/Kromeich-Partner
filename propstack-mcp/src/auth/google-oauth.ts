import { ALLOWED_HOSTED_DOMAIN } from "../config";

const GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth";
const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";

export function googleAuthorizeUrl({
	clientId,
	redirectUri,
	state,
}: {
	clientId: string;
	redirectUri: string;
	state: string;
}): string {
	const url = new URL(GOOGLE_AUTHORIZE_URL);
	url.searchParams.set("client_id", clientId);
	url.searchParams.set("redirect_uri", redirectUri);
	url.searchParams.set("scope", "openid email profile");
	url.searchParams.set("response_type", "code");
	url.searchParams.set("state", state);
	// Nur ein Hinweis für die Kontoauswahl. Verbindlich ist die serverseitige Prüfung (3a).
	url.searchParams.set("hd", ALLOWED_HOSTED_DOMAIN);
	url.searchParams.set("prompt", "select_account");
	return url.href;
}

/** Tauscht den Code gegen ein ID-Token. Das Google-Access-Token wird nicht weiterverwendet. */
export async function exchangeCodeForIdToken({
	clientId,
	clientSecret,
	code,
	redirectUri,
}: {
	clientId: string;
	clientSecret: string;
	code: string;
	redirectUri: string;
}): Promise<string> {
	const response = await fetch(GOOGLE_TOKEN_URL, {
		body: new URLSearchParams({
			client_id: clientId,
			client_secret: clientSecret,
			code,
			grant_type: "authorization_code",
			redirect_uri: redirectUri,
		}).toString(),
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		method: "POST",
	});
	if (!response.ok) {
		console.error("Google-Token-Tausch fehlgeschlagen", response.status, await response.text());
		throw new Error("Google-Token-Tausch fehlgeschlagen");
	}
	const body = (await response.json()) as { id_token?: string };
	if (!body.id_token) throw new Error("Google hat kein ID-Token geliefert");
	return body.id_token;
}
