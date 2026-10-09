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
	}
}
interface Env extends Cloudflare.Env {}
