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

export type QueryValue = string | number | boolean | null | undefined | Array<string | number>;
export type Query = Record<string, QueryValue>;

export interface Page {
	rows: Record<string, unknown>[];
	/** meta.total_count, falls Propstack ihn liefert (with_meta=1). */
	total: number | null;
}

export interface PropstackClientOptions {
	apiKey: string;
	baseUrl?: string;
	fetchFn?: typeof fetch;
	sleep?: (ms: number) => Promise<void>;
	maxRetries?: number;
	timeoutMs?: number;
	/** Obergrenze an Propstack-Requests je Client-Instanz (= je Tool-Aufruf). */
	maxRequests?: number;
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
 * Query-String bauen. Arrays werden Rails-typisch als `key[]=a&key[]=b` übergeben.
 * Wo die Doku kommagetrennte Werte verlangt (z. B. /units?status=1,2), übergibt der
 * Aufrufer bereits einen String. Leere Werte werden weggelassen.
 */
export function buildQuery(query: Query = {}): string {
	const params = new URLSearchParams();
	for (const [key, value] of Object.entries(query)) {
		if (value === undefined || value === null || value === "") continue;
		if (Array.isArray(value)) {
			for (const item of value) params.append(`${key}[]`, String(item));
		} else if (typeof value === "boolean") {
			params.append(key, value ? "1" : "0");
		} else {
			params.append(key, String(value));
		}
	}
	const text = params.toString();
	return text ? `?${text}` : "";
}

/** Antwort ist je nach Endpunkt eine nackte Liste oder {"data": [...], "meta": {...}}. */
export function toPage(payload: unknown): Page {
	const raw = Array.isArray(payload)
		? payload
		: payload && typeof payload === "object" && Array.isArray((payload as { data?: unknown }).data)
			? (payload as { data: unknown[] }).data
			: [];
	const meta = !Array.isArray(payload) && payload && typeof payload === "object" ? (payload as { meta?: unknown }).meta : undefined;
	const total =
		meta && typeof meta === "object" && typeof (meta as { total_count?: unknown }).total_count === "number"
			? (meta as { total_count: number }).total_count
			: null;
	return {
		rows: raw.filter((row): row is Record<string, unknown> => !!row && typeof row === "object"),
		total,
	};
}

export type GroupEntity = "for_clients" | "for_properties" | "for_activities";
export type CustomFieldEntity = "for_clients" | "for_properties" | "for_projects" | "for_deals";

/**
 * Propstack-Client – nur lesend und nur explizit definierte Endpunkte.
 * Kein generischer Passthrough (harte Regel der Spezifikation).
 */
export class PropstackClient {
	private readonly apiKey: string;
	private readonly baseUrl: string;
	private readonly fetchFn: typeof fetch;
	private readonly sleep: (ms: number) => Promise<void>;
	private readonly maxRetries: number;
	private readonly timeoutMs: number;
	private readonly maxRequests: number;
	private requestCount = 0;

	constructor(options: PropstackClientOptions) {
		if (!options.apiKey) throw new Error("PROPSTACK_API_KEY fehlt");
		this.apiKey = options.apiKey;
		this.baseUrl = options.baseUrl ?? PROPSTACK_BASE_URL;
		this.fetchFn = options.fetchFn ?? fetch.bind(globalThis);
		this.sleep = options.sleep ?? defaultSleep;
		this.maxRetries = options.maxRetries ?? 3;
		this.timeoutMs = options.timeoutMs ?? 15_000;
		this.maxRequests = options.maxRequests ?? 45;
	}

	get requestsUsed(): number {
		return this.requestCount;
	}

	/** GET /v1/brokers – alle Nutzer des Accounts (laut Doku nicht paginiert). */
	async listBrokers(): Promise<unknown> {
		return this.get("/brokers");
	}

	/** GET /v1/contacts – Kontakte suchen (paginiert, with_meta liefert total_count). */
	async searchContacts(query: Query): Promise<Page> {
		return toPage(await this.get(`/contacts${buildQuery({ ...query, with_meta: 1 })}`));
	}

	/** GET /v1/contacts/:id */
	async getContact(id: number): Promise<unknown> {
		return this.get(`/contacts/${id}`);
	}

	/** GET /v1/units – Objekte suchen. */
	async searchUnits(query: Query): Promise<Page> {
		return toPage(await this.get(`/units${buildQuery({ ...query, with_meta: 1 })}`));
	}

	/** GET /v1/units/:id?new=1 – Detailansicht inkl. Custom-Feldern. */
	async getUnit(id: number): Promise<unknown> {
		return this.get(`/units/${id}?new=1`);
	}

	/** GET /v1/client_properties – Deals suchen. */
	async searchDeals(query: Query): Promise<Page> {
		return toPage(await this.get(`/client_properties${buildQuery({ ...query, with_meta: 1 })}`));
	}

	/** GET /v1/deal_pipelines – Pipelines inkl. Phasen. */
	async listDealPipelines(): Promise<Page> {
		return toPage(await this.get("/deal_pipelines"));
	}

	/** GET /v1/groups?entity=… – Merkmale. */
	async listGroups(entity: GroupEntity): Promise<Page> {
		return toPage(await this.get(`/groups${buildQuery({ entity })}`));
	}

	/** GET /v1/super_groups?entity=…&include=groups – Obermerkmale mit Merkmalen. */
	async listSuperGroups(entity: GroupEntity): Promise<Page> {
		return toPage(await this.get(`/super_groups${buildQuery({ entity, include: "groups" })}`));
	}

	/** GET /v1/custom_field_groups?entity=… */
	async listCustomFieldGroups(entity: CustomFieldEntity): Promise<Page> {
		return toPage(await this.get(`/custom_field_groups${buildQuery({ entity })}`));
	}

	/** GET /v1/property_statuses */
	async listPropertyStatuses(): Promise<Page> {
		return toPage(await this.get("/property_statuses"));
	}

	/** GET /v1/contact_sources */
	async listContactSources(): Promise<Page> {
		return toPage(await this.get("/contact_sources"));
	}

	/** GET /v1/projects */
	async listProjects(): Promise<Page> {
		return toPage(await this.get("/projects"));
	}

	private async get(path: string): Promise<unknown> {
		for (let attempt = 0; ; attempt++) {
			if (this.requestCount >= this.maxRequests) {
				throw new PropstackError(
					`Abfrage zu umfangreich (mehr als ${this.maxRequests} Propstack-Anfragen). Bitte Filter enger setzen.`,
					0,
				);
			}
			this.requestCount++;
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
	if (status === 401 || status === 403) {
		return `Propstack hat den Zugriff verweigert (${status}). Fehlt dem API-Key das Leserecht für diesen Bereich?`;
	}
	if (status === 404) return "Nicht gefunden (404)";
	if (status >= 500) return `Propstack-Serverfehler (${status})`;
	return `Propstack-Anfrage fehlgeschlagen (${status})`;
}
