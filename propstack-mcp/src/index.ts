import OAuthProvider, { GrantType, OAuthError } from "@cloudflare/workers-oauth-provider";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpAgent } from "agents/mcp";
import { env } from "cloudflare:workers";
import { recheckOnRefresh, type Props } from "./auth/session";
import { ACCESS_TOKEN_TTL_SECONDS } from "./config";
import { GoogleHandler } from "./google-handler";
import { PropstackClient } from "./propstack-client";

export class PropstackMCP extends McpAgent<Env, Record<string, never>, Props> {
	server = new McpServer({
		name: "Propstack MCP – Kromeich",
		version: "0.1.0",
	});

	async init() {
		this.server.registerTool(
			"whoami",
			{
				description:
					"Zeigt, als wer du angemeldet bist: E-Mail, Name und Propstack-Nutzer-ID. Unter dieser ID laufen später alle Änderungen.",
				annotations: { readOnlyHint: true },
			},
			async () => {
				const { email, name, brokerId } = this.props!;
				const result = { email, name, propstack_user_id: brokerId };
				return {
					content: [{ text: JSON.stringify(result), type: "text" }],
					structuredContent: result,
				};
			},
		);
	}
}

export default new OAuthProvider({
	accessTokenTTL: ACCESS_TOKEN_TTL_SECONDS,
	apiHandler: PropstackMCP.serve("/mcp"),
	apiRoute: "/mcp",
	authorizeEndpoint: "/authorize",
	clientRegistrationEndpoint: "/register",
	defaultHandler: GoogleHandler as any,
	tokenEndpoint: "/token",
	// Bei jedem Refresh Prüfung 3b erneut (Offboarding = Propstack-Nutzer entfernen).
	tokenExchangeCallback: async ({ grantType, props }) => {
		if (grantType !== GrantType.REFRESH_TOKEN) return;
		const result = await recheckOnRefresh(props as Props, {
			client: new PropstackClient({ apiKey: env.PROPSTACK_API_KEY }),
			kv: env.OAUTH_KV,
		});
		if (result.ok) return { newProps: result.props };
		if (result.kind === "rejected") {
			throw new OAuthError("invalid_grant", { description: result.message });
		}
		throw new OAuthError("temporarily_unavailable", {
			description: result.message,
			headers: { "Retry-After": "60" },
			statusCode: 503,
		});
	},
});
