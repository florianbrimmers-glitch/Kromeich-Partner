import { PROPSTACK_BASE_URL } from "./config";

export class PropstackError extends Error {
	constructor(
		message: string,
		readonly status: number,
	) {
		super(message);
		this.name = "PropstackError";
	}
}

export interface PropstackClientOptions {
	apiKey: string;
	baseUrl?: string;
	fetchFn?: typeof fetch;
	sleep?: (ms: number) => Promise<void>;
	maxRetries?: number;
	timeoutMs?: number;
}

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Wartezeit vor dem nächsten Versuch nach einem 429.
 * Retry-After (Sekunden) hat Vorrang, sonst exponentiell 1 s, 2 s, 4 s … (max. 30 s).
 */
export function retryDelayMs(attempt: number, retryAfter: string | null): number {
	const seconds = retryAfter === null ? Number.NaN : Number(retryAfter);
	if (Number.isFinite(seconds) && seconds >= 0) return Math.min(seconds, 30) * 1000;
	return Math.min(1000 * 2 ** attempt, 30_000);
}

/**
 * Minimaler Propstack-Client. Bewusst nur explizite Methoden, kein generischer Passthrough.
 */
export class PropstackClient {
	private readonly apiKey: string;
	private readonly baseUrl: string;
	private readonly fetchFn: typeof fetch;
	private readonly sleep: (ms: number) => Promise<void>;
	private readonly maxRetries: number;
	private readonly timeoutMs: number;

	constructor(options: PropstackClientOptions) {
		if (!options.apiKey) throw new Error("PROPSTACK_API_KEY fehlt");
		this.apiKey = options.apiKey;
		this.baseUrl = options.baseUrl ?? PROPSTACK_BASE_URL;
		this.fetchFn = options.fetchFn ?? fetch.bind(globalThis);
		this.sleep = options.sleep ?? defaultSleep;
		this.maxRetries = options.maxRetries ?? 3;
		this.timeoutMs = options.timeoutMs ?? 15_000;
	}

	/** GET /v1/brokers – alle Nutzer des Accounts (laut Doku nicht paginiert). */
	async listBrokers(): Promise<unknown> {
		return this.get("/brokers");
	}

	private async get(path: string): Promise<unknown> {
		for (let attempt = 0; ; attempt++) {
			let response: Response;
			try {
				response = await this.fetchFn(`${this.baseUrl}${path}`, {
					headers: { Accept: "application/json", "X-API-KEY": this.apiKey },
					method: "GET",
					signal: AbortSignal.timeout(this.timeoutMs),
				});
			} catch (error) {
				throw new PropstackError(`Propstack nicht erreichbar: ${(error as Error).message}`, 0);
			}

			if (response.status === 429 && attempt < this.maxRetries) {
				await this.sleep(retryDelayMs(attempt, response.headers.get("retry-after")));
				continue;
			}
			if (!response.ok) {
				throw new PropstackError(describeStatus(response.status), response.status);
			}
			return response.json();
		}
	}
}

function describeStatus(status: number): string {
	if (status === 429) return "Propstack-Rate-Limit erreicht (429), auch nach mehreren Versuchen";
	if (status === 401 || status === 403) return `Propstack hat den API-Key abgelehnt (${status})`;
	if (status >= 500) return `Propstack-Serverfehler (${status})`;
	return `Propstack-Anfrage fehlgeschlagen (${status})`;
}
