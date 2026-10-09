import type { AuthRequest, OAuthHelpers } from "@cloudflare/workers-oauth-provider";
import { Hono } from "hono";
import { AuthRejection } from "./auth/errors";
import { exchangeCodeForIdToken, googleAuthorizeUrl } from "./auth/google-oauth";
import { authorizeLogin, type Props } from "./auth/session";
import { PropstackClient } from "./propstack-client";
import {
	addApprovedClient,
	bindStateToSession,
	createOAuthState,
	generateCSRFProtection,
	isClientApproved,
	OAuthError,
	renderApprovalDialog,
	sanitizeText,
	validateCSRFToken,
	validateOAuthState,
} from "./workers-oauth-utils";

const app = new Hono<{ Bindings: Env & { OAUTH_PROVIDER: OAuthHelpers } }>();

app.get("/authorize", async (c) => {
	const oauthReqInfo = await c.env.OAUTH_PROVIDER.parseAuthRequest(c.req.raw);
	const { clientId } = oauthReqInfo;
	if (!clientId) {
		return c.text("Invalid request", 400);
	}

	// Check if client is already approved
	if (await isClientApproved(c.req.raw, clientId, c.env.COOKIE_ENCRYPTION_KEY)) {
		// Skip approval dialog but still create secure state and bind to session
		const { stateToken } = await createOAuthState(oauthReqInfo, c.env.OAUTH_KV);
		const { setCookie: sessionBindingCookie } = await bindStateToSession(stateToken);
		return redirectToGoogle(c.req.raw, c.env, stateToken, {
			"Set-Cookie": sessionBindingCookie,
		});
	}

	// Generate CSRF protection for the approval form
	const { token: csrfToken, setCookie } = generateCSRFProtection();

	return renderApprovalDialog(c.req.raw, {
		client: await c.env.OAUTH_PROVIDER.lookupClient(clientId),
		csrfToken,
		server: {
			description:
				"Zugriff auf Propstack für Mitarbeitende der Kromeich GmbH. Anmeldung nur mit @kromeichpartner.de-Konto und aktivem Propstack-Nutzer.",
			name: "Propstack MCP – Kromeich",
		},
		setCookie,
		state: { oauthReqInfo },
	});
});

app.post("/authorize", async (c) => {
	try {
		// Read form data once
		const formData = await c.req.raw.formData();

		// Validate CSRF token
		validateCSRFToken(formData, c.req.raw);

		// Extract state from form data
		const encodedState = formData.get("state");
		if (!encodedState || typeof encodedState !== "string") {
			return c.text("Missing state in form data", 400);
		}

		let state: { oauthReqInfo?: AuthRequest };
		try {
			state = JSON.parse(atob(encodedState));
		} catch (_e) {
			return c.text("Invalid state data", 400);
		}

		if (!state.oauthReqInfo || !state.oauthReqInfo.clientId) {
			return c.text("Invalid request", 400);
		}

		// Add client to approved list
		const approvedClientCookie = await addApprovedClient(
			c.req.raw,
			state.oauthReqInfo.clientId,
			c.env.COOKIE_ENCRYPTION_KEY,
		);

		// Create OAuth state and bind it to this user's session
		const { stateToken } = await createOAuthState(state.oauthReqInfo, c.env.OAUTH_KV);
		const { setCookie: sessionBindingCookie } = await bindStateToSession(stateToken);

		// Set both cookies: approved client list + session binding
		const headers = new Headers();
		headers.append("Set-Cookie", approvedClientCookie);
		headers.append("Set-Cookie", sessionBindingCookie);

		return redirectToGoogle(c.req.raw, c.env, stateToken, Object.fromEntries(headers));
	} catch (error: any) {
		console.error("POST /authorize error:", error);
		if (error instanceof OAuthError) {
			return error.toResponse();
		}
		// Unexpected non-OAuth error
		return c.text(`Internal server error: ${error.message}`, 500);
	}
});

async function redirectToGoogle(
	request: Request,
	env: Env,
	stateToken: string,
	headers: Record<string, string> = {},
) {
	return new Response(null, {
		headers: {
			...headers,
			location: googleAuthorizeUrl({
				clientId: env.GOOGLE_CLIENT_ID,
				redirectUri: new URL("/callback", request.url).href,
				state: stateToken,
			}),
		},
		status: 302,
	});
}

/**
 * OAuth Callback Endpoint
 *
 * This route handles the callback from Google after user authentication.
 * It exchanges the temporary code for a Google ID token, runs checks 3a/3b
 * and stores the Propstack identity as 'props' on the token passed
 * down to the client. It ends by redirecting the client back to _its_ callback URL
 *
 * SECURITY: This endpoint validates that the state parameter from Google
 * matches both:
 * 1. A valid state token in KV (proves it was created by our server)
 * 2. The __Host-CONSENTED_STATE cookie (proves THIS browser consented to it)
 *
 * This prevents CSRF attacks where an attacker's state token is injected
 * into a victim's OAuth flow.
 */
app.get("/callback", async (c) => {
	// Validate OAuth state with session binding
	// This checks both KV storage AND the session cookie
	let oauthReqInfo: AuthRequest;
	let clearSessionCookie: string;

	try {
		const result = await validateOAuthState(c.req.raw, c.env.OAUTH_KV);
		oauthReqInfo = result.oauthReqInfo;
		clearSessionCookie = result.clearCookie;
	} catch (error: any) {
		if (error instanceof OAuthError) {
			return error.toResponse();
		}
		// Unexpected non-OAuth error
		return c.text("Internal server error", 500);
	}

	if (!oauthReqInfo.clientId) {
		return c.text("Invalid OAuth request data", 400);
	}

	// Exchange the code for an access token
	const code = c.req.query("code");
	if (!code) {
		return c.text("Missing code", 400);
	}

	let props: Props;
	try {
		const idToken = await exchangeCodeForIdToken({
			clientId: c.env.GOOGLE_CLIENT_ID,
			clientSecret: c.env.GOOGLE_CLIENT_SECRET,
			code,
			redirectUri: new URL("/callback", c.req.url).href,
		});
		// 3a (ID-Token, hd, email_verified) + 3b (Propstack-Nutzer)
		props = await authorizeLogin(idToken, {
			client: new PropstackClient({ apiKey: c.env.PROPSTACK_API_KEY }),
			clientId: c.env.GOOGLE_CLIENT_ID,
			kv: c.env.OAUTH_KV,
		});
	} catch (error) {
		if (error instanceof AuthRejection) {
			console.warn("Login abgelehnt:", error.message);
			return rejectionPage(error.message, 403, clearSessionCookie);
		}
		console.error("Login fehlgeschlagen:", error);
		return rejectionPage(
			"Die Anmeldung konnte gerade nicht geprüft werden. Bitte später erneut versuchen.",
			503,
			clearSessionCookie,
		);
	}

	// Return back to the MCP client a new token
	const { redirectTo } = await c.env.OAUTH_PROVIDER.completeAuthorization({
		metadata: {
			label: props.name,
		},
		props,
		request: oauthReqInfo,
		scope: oauthReqInfo.scope,
		userId: props.email,
	});

	// Clear the session binding cookie (one-time use) by creating response with headers
	const headers = new Headers({ Location: redirectTo });
	if (clearSessionCookie) {
		headers.set("Set-Cookie", clearSessionCookie);
	}

	return new Response(null, {
		status: 302,
		headers,
	});
});

function rejectionPage(message: string, status: number, clearSessionCookie: string): Response {
	const html = `<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Zugriff verweigert</title></head>
<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem">
<h1>Zugriff verweigert</h1><p>${sanitizeText(message)}</p></body></html>`;
	const headers = new Headers({ "Content-Type": "text/html; charset=utf-8" });
	if (clearSessionCookie) headers.set("Set-Cookie", clearSessionCookie);
	return new Response(html, { headers, status });
}

export { app as GoogleHandler };
