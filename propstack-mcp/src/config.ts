// Sicherheitsrelevante Konstanten bewusst im Code statt als Variable:
// Eine fehlende oder falsch gesetzte Variable darf die Domain-Prüfung nie aushebeln.
export const ALLOWED_HOSTED_DOMAIN = "kromeichpartner.de";

export const PROPSTACK_BASE_URL = "https://api.propstack.de/v1";

// Laufzeit der MCP-Access-Tokens (Spezifikation: max. 1 h).
export const ACCESS_TOKEN_TTL_SECONDS = 60 * 60;

// KV-Cache Mail → Propstack-Nutzer (Spezifikation: TTL 1 h).
export const BROKER_CACHE_TTL_SECONDS = 60 * 60;
