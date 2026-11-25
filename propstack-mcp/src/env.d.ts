// Bindings und Secrets des Workers.
// Secrets werden ausschließlich per `wrangler secret put` gesetzt (lokal: .dev.vars).
declare namespace Cloudflare {
	interface Env {
		OAUTH_KV: KVNamespace;
		MCP_OBJECT: DurableObjectNamespace;
		GOOGLE_CLIENT_ID: string;
		GOOGLE_CLIENT_SECRET: string;
		COOKIE_ENCRYPTION_KEY: string;
		PROPSTACK_API_KEY: string;
		/** Schlüssel für die V2-Schnittstelle (Firmen, Verknüpfungen zwischen Kontakten). Fehlt er, sind nur diese Tools gesperrt. */
		PROPSTACK_API_KEY_V2?: string;
		/**
		 * Secret für den Service-Zugang (objekte-handler, src/auth/service-token.ts). Fehlt es oder ist es kürzer als
		 * 32 Zeichen, ist der Zugang aus. Derselbe Wert liegt als Repository-Secret beim GitHub-Workflow.
		 */
		SERVICE_TOKEN_SECRET?: string;
		AUDIT_DB: D1Database;
	}
}
interface Env extends Cloudflare.Env {}
