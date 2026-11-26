import OAuthProvider, { GrantType, OAuthError } from "@cloudflare/workers-oauth-provider";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpAgent } from "agents/mcp";
import { env } from "cloudflare:workers";
import { purgeOldAuditEntries, retentionCutoff } from "./audit";
import { purgeOldBulkPlans } from "./bulk/store";
import { purgeOldDashboardStands } from "./dashboard/store";
import { authCheckMode } from "./auth/broker-lookup";
import { identityInfo, recheckOnRefresh, type Props } from "./auth/session";
import { ACCESS_TOKEN_TTL_SECONDS } from "./config";
import { GoogleHandler } from "./google-handler";
import { handleImageUpload } from "./image-upload";
import { PropstackClient } from "./propstack-client";
import { serviceAccess } from "./service-access";
import { registerReadTools, registerWriteTools, runTool, type ToolContext } from "./tools/register";
import { serviceServer } from "./tools/service-rules";
import { purgeOldWriteLog } from "./write-log";

export class PropstackMCP extends McpAgent<Env, Record<string, never>, Props> {
	server = new McpServer({
		name: "Propstack MCP – Kromeich",
		version: "0.18.0",
	});

	async init() {
		const ctx: ToolContext = { env: this.env, props: () => this.props! };
		// Service-Sitzungen (objekte-handler) bekommen nur die freigegebenen Werkzeuge – Menschen alle wie bisher
		const server = serviceServer(this.server, this.props);

		server.registerTool(
			"whoami",
			{
				description:
					"Zeigt, als wer du angemeldet bist: E-Mail, Name und Propstack-Nutzer-ID. Unter dieser ID laufen später alle Änderungen.",
				annotations: { readOnlyHint: true },
			},
			async () =>
				runTool(ctx, "whoami", {}, async (client) => {
					// Nur ob der zweite Schlüssel hinterlegt ist – nie der Wert.
					const firmen = this.env.PROPSTACK_API_KEY_V2?.trim() ? "bereit (zweiter Propstack-Schlüssel ist hinterlegt)" : "gesperrt (PROPSTACK_API_KEY_V2 fehlt im Server)";
					return { count: 1, result: { ...identityInfo(this.props!), firmen_und_verknuepfungen: firmen, anmeldepruefung: await authCheckMode(client) } };
				}),
		);

		registerReadTools(server, ctx);
		registerWriteTools(server, ctx);
	}
}

const mcpHandler = PropstackMCP.serve("/mcp");

const provider = new OAuthProvider({
	accessTokenTTL: ACCESS_TOKEN_TTL_SECONDS,
	apiHandler: mcpHandler,
	apiRoute: "/mcp",
	authorizeEndpoint: "/authorize",
	clientRegistrationEndpoint: "/register",
	defaultHandler: GoogleHandler as any,
	tokenEndpoint: "/token",
	// Bei jedem Refresh Prüfung 3b erneut (Offboarding = Propstack-Nutzer entfernen).
	tokenExchangeCallback: async ({ grantType, props }) => {
		if (grantType !== GrantType.REFRESH_TOKEN) return;
		const result = await recheckOnRefresh(props as Props, {
			client: new PropstackClient({ apiKey: env.PROPSTACK_API_KEY, apiKeyV2: env.PROPSTACK_API_KEY_V2 }),
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
	fetch: async (request: Request, env: Env, ctx: ExecutionContext) => {
		// Bild-Upload per Einmal-Adresse aus image_upload_url – das Token in der URL ist die Berechtigung.
		if (new URL(request.url).pathname.startsWith("/upload/images/")) return handleImageUpload(request, env);
		// Service-Zugang (objekte-handler): nur „Bearer svc.…“ an /mcp. Alles andere – auch ungültige Service-Tokens –
		// geht unverändert an den OAuth-Provider, der wie bisher mit 401 antwortet.
		const service = await serviceAccess(request, env, {
			client: new PropstackClient({ apiKey: env.PROPSTACK_API_KEY, apiKeyV2: env.PROPSTACK_API_KEY_V2 }),
			kv: env.OAUTH_KV,
		});
		if (service?.kind === "response") return service.response;
		if (service?.kind === "props") {
			// wie der OAuth-Provider: die Sitzungsdaten über ctx.props an den MCP-Handler geben
			(ctx as ExecutionContext & { props: unknown }).props = service.props;
			return mcpHandler.fetch(request, env, ctx);
		}
		return provider.fetch(request, env, ctx);
	},
	// Täglich: Audit- und Write-Log-Einträge älter als 12 Monate löschen, Dashboard-Zwischenspeicher älter als 24 Stunden.
	scheduled: async (_controller: ScheduledController, env: Env, ctx: ExecutionContext) => {
		ctx.waitUntil(
			Promise.all([
				purgeOldAuditEntries(env.AUDIT_DB),
				purgeOldWriteLog(env.AUDIT_DB),
				purgeOldBulkPlans(env.AUDIT_DB, retentionCutoff(new Date())),
				purgeOldDashboardStands(env.AUDIT_DB, new Date(Date.now() - 24 * 3_600_000).toISOString()),
			]).then(([audit, writes, plans, staende]) =>
				console.log(`Löschfrist: ${audit} Audit-, ${writes} Write-Log-Einträge, ${plans} Pläne und ${staende} Dashboard-Stände entfernt`),
			),
		);
	},
} satisfies ExportedHandler<Env>;
