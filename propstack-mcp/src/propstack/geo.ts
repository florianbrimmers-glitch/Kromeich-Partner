// Geokoordinaten (Entscheidung Florian, 16.10.: mit dem Trick aus dem Notion-Feld-Mapping einbauen).
// Notion-Korrektur 34: lat haftet sofort; lng haftet oft erst nach gerundeten Vorwerten → lng in Stufen
// schreiben (1, 2, 3, 4 Nachkommastellen, dann exakt). Kontrolle nur über den Einzel-GET – der expand-Kanal
// liefert danach veraltete Zwischenwerte.
// Quelle der Koordinaten: angegeben > von Propstack selbst ermittelt > Nominatim (OpenStreetMap), wie im Team-Ablauf.

export interface Coordinates {
	lat: number;
	lng: number;
}

export interface CoordinateResult {
	lat?: number;
	lng?: number;
	source: "angegeben" | "Propstack" | "OpenStreetMap" | "keine";
	precision?: string;
	verified: boolean;
	note?: string;
}

const TOLERANCE = 0.00002; // ≈ 2 m

export function close(a: unknown, b: number): boolean {
	return typeof a === "number" && Number.isFinite(a) && Math.abs(a - b) <= TOLERANCE;
}

export function coordsOf(raw: Record<string, unknown> | undefined): Partial<Coordinates> {
	const num = (v: unknown) => (typeof v === "number" ? v : typeof v === "string" && v.trim() ? Number(v) : undefined);
	const lat = num(raw?.lat);
	const lng = num(raw?.lng);
	return { lat: Number.isFinite(lat) ? lat : undefined, lng: Number.isFinite(lng) ? lng : undefined };
}

const USER_AGENT = "KromeichPropstackMCP/1.0 (+https://kromeichpartner.de)";

/** Adresse → Koordinaten über Nominatim. Ohne Hausnummer: Straßenmitte (wird als Genauigkeit gemeldet). */
export async function geocode(
	address: { street: string; house_number?: string; zip_code: string; city: string },
	fetchFn: typeof fetch = fetch,
): Promise<(Coordinates & { precision: string }) | null> {
	const params = new URLSearchParams({
		city: address.city,
		countrycodes: "de",
		format: "json",
		limit: "1",
		postalcode: address.zip_code,
		street: [address.house_number, address.street].filter(Boolean).join(" "),
	});
	try {
		const response = await fetchFn(`https://nominatim.openstreetmap.org/search?${params}`, {
			headers: { Accept: "application/json", "User-Agent": USER_AGENT },
			signal: AbortSignal.timeout(8000),
		});
		if (!response.ok) return null;
		const rows = (await response.json()) as { lat?: string; lon?: string }[];
		const lat = Number(rows[0]?.lat);
		const lng = Number(rows[0]?.lon);
		if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
		const round = (v: number) => Math.round(v * 1e6) / 1e6;
		return { lat: round(lat), lng: round(lng), precision: address.house_number ? "Hausnummer" : "Straße (keine Hausnummer)" };
	} catch {
		return null;
	}
}

/** Schreibt lat/lng mit dem Stufen-Trick und prüft per Einzel-GET. */
export async function writeCoordinates(
	read: () => Promise<Partial<Coordinates>>,
	put: (body: Partial<Coordinates>) => Promise<unknown>,
	target: Coordinates,
): Promise<{ verified: boolean; lat?: number; lng?: number; error?: string }> {
	try {
		const current = await read();
		if (!close(current.lat, target.lat)) await put({ lat: target.lat });
		if (!close(current.lng, target.lng)) {
			for (const digits of [1, 2, 3, 4]) {
				const factor = 10 ** digits;
				await put({ lng: Math.round(target.lng * factor) / factor });
			}
			await put({ lng: target.lng });
		}
		const after = await read();
		return { lat: after.lat, lng: after.lng, verified: close(after.lat, target.lat) && close(after.lng, target.lng) };
	} catch (error) {
		return { error: (error as Error).message, verified: false };
	}
}

/**
 * Koordinaten für einen frisch angelegten oder geänderten Datensatz sicherstellen.
 * provided: vom Nutzer angegeben (hat Vorrang). Sonst: was Propstack selbst ermittelt hat; fehlt das → Nominatim.
 */
export async function ensureCoordinates(options: {
	provided?: Partial<Coordinates>;
	current: Partial<Coordinates>;
	address?: { street: string; house_number?: string; zip_code: string; city: string };
	read: () => Promise<Partial<Coordinates>>;
	put: (body: Partial<Coordinates>) => Promise<unknown>;
	fetchFn?: typeof fetch;
}): Promise<CoordinateResult> {
	const { provided, current } = options;
	if (provided?.lat !== undefined && provided.lng !== undefined) {
		const result = await writeCoordinates(options.read, options.put, { lat: provided.lat, lng: provided.lng });
		return { ...result, source: "angegeben", note: result.error };
	}
	if (current.lat !== undefined && current.lng !== undefined && (current.lat !== 0 || current.lng !== 0)) {
		return { lat: current.lat, lng: current.lng, source: "Propstack", verified: true };
	}
	if (!options.address) return { source: "keine", verified: false, note: "Keine Koordinaten und keine Adresse." };
	const found = await geocode(options.address, options.fetchFn);
	if (!found) return { source: "keine", verified: false, note: "Adresse nicht gefunden (OpenStreetMap) – Koordinaten bitte nachtragen." };
	const result = await writeCoordinates(options.read, options.put, found);
	return { ...result, precision: found.precision, source: "OpenStreetMap", note: result.error };
}
