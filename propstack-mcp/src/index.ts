import OAuthProvider, { GrantType, OAuthError } from "@cloudflare/workers-oauth-provider";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpAgent } from "agents/mcp";
import { env } from "cloudflare:workers";
import { purgeOldAuditEntries } from "./audit";
import { recheckOnRefresh, type Props } from "./auth/session";
import { ACCESS_TOKEN_TTL_SECONDS } from "./config";
import { GoogleHandler } from "./google-handler";
import { PropstackClient } from "./propstack-client";
import { registerReadTools, runTool, type ToolContext } from "./tools/register";

export class PropstackMCP extends McpAgent<Env, Record<string, never>, Props> {
	server = new McpServer({
		name: "Propstack MCP – Kromeich",
		version: "0.2.0",
	});

	async init() {
		const ctx: ToolContext = { env: this.env, props: () => this.props! };

		this.server.registerTool(
			"whoami",
			{
				description:
					"Zeigt, als wer du angemeldet bist: E-Mail, Name und Propstack-Nutzer-ID. Unter dieser ID laufen später alle Änderungen.",
				annotations: { readOnlyHint: true },
			},
			async () =>
				runTool(ctx, "whoami", {}, async () => {
					const { email, name, brokerId } = this.props!;
					return { count: 1, result: { email, name, propstack_user_id: brokerId } };
				}),
		);

		registerReadTools(this.server, ctx);
	}
}

const provider = new OAuthProvider({
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

export default {
	fetch: (request: Request, env: Env, ctx: ExecutionContext) => provider.fetch(request, env, ctx),
	// Täglich: Audit-Einträge älter als 12 Monate löschen.
	scheduled: async (_controller: ScheduledController, env: Env, ctx: ExecutionContext) => {
		ctx.waitUntil(
			purgeOldAuditEntries(env.AUDIT_DB).then((deleted) => console.log(`Audit-Log: ${deleted} alte Einträge gelöscht`)),
		);
	},
} satisfies ExportedHandler<Env>;
