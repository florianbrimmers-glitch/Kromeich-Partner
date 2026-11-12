import type { PropstackClient } from "../propstack-client";
import { scalar } from "./mappers";

// Objekt zuverlässig lesen (Notion-Feld-Mapping, Korrekturen 27/31/34/36):
// - Der Einzel-GET liefert rs_category, Flächen, hall_height, floor_load, plot_area,
//   price_on_inquiry, broker_id und property_status_id gar nicht.
// - Belastbar ist GET /v1/units?expand=1&per=100&property_ids[]=ID.
// - Status nur über status.id, Betreuer über broker.id, lat/lng nur im Einzel-GET.
// - Frisch angelegte Objekte fehlen im expand-Kanal kurz → Retry 1,5 s / 4 s.

type Raw = Record<string, unknown>;

export const UNVERIFIABLE = Symbol("nicht prüfbar");

export interface UnitState {
	/** Zeile aus dem expand=1-Kanal (fehlt, wenn Propstack sie noch nicht liefert). */
	row?: Raw;
	/** Einzel-GET. */
	detail: Raw;
}

export const FRESH_RETRY_DELAYS_MS = [1500, 4000];

export async function readUnit(
	client: Pick<PropstackClient, "getUnit" | "searchUnits">,
	id: number,
	options: { fresh?: boolean; sleep?: (ms: number) => Promise<void> } = {},
): Promise<UnitState> {
	const detailRaw = await client.getUnit(id);
	const detail = detailRaw && typeof detailRaw === "object" && !Array.isArray(detailRaw) ? (detailRaw as Raw) : {};
	const delays = options.fresh ? [0, ...FRESH_RETRY_DELAYS_MS] : [0];
	const sleep = options.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
	for (const delay of delays) {
		if (delay) await sleep(delay);
		try {
			const page = await client.searchUnits({ archived: "-1", expand: 1, per: 100, property_ids: [id] });
			// Gegenprobe: genau die angefragte ID muss zurückkommen
			const row = page.rows.find((r) => Number(scalar(r.id)) === id);
			if (row) return { detail, row };
		} catch {
			// expand-Kanal nicht verfügbar → mit dem Einzel-GET weiter (eingeschränkt prüfbar)
			break;
		}
	}
	return { detail };
}

function customOf(source: Raw | undefined, key: string): unknown {
	if (!source) return undefined;
	const custom = source.custom_fields;
	if (custom && typeof custom === "object" && !Array.isArray(custom) && key in (custom as Raw)) return (custom as Raw)[key];
	return undefined;
}

/** Aktueller Wert eines Standardfelds – oder UNVERIFIABLE, wenn kein belastbarer Kanal ihn liefert. */
export function unitValue(state: UnitState, key: string): unknown {
	const { detail, row } = state;
	if (key === "property_status_id") {
		const status = (detail.status ?? detail.property_status) as Raw | undefined;
		return status && typeof status === "object" ? status.id : (detail.property_status_id ?? null);
	}
	if (key === "broker_id") {
		const broker = detail.broker as Raw | undefined;
		if (broker && typeof broker === "object") return broker.id;
		if ("broker_id" in detail) return detail.broker_id;
		return row && "broker_id" in row ? row.broker_id : UNVERIFIABLE;
	}
	if (key === "lat" || key === "lng") return key in detail ? detail[key] : UNVERIFIABLE;
	if (row && key in row) return row[key];
	if (key in detail) return detail[key];
	// price_on_inquiry steht im Einzel-GET verschachtelt unter furnishings
	const furnishings = detail.furnishings as Raw | undefined;
	if (furnishings && typeof furnishings === "object" && key in furnishings) return furnishings[key];
	// Feld in keinem Kanal enthalten → lieber „nicht prüfbar“ als ein falscher Alarm
	return UNVERIFIABLE;
}

/** Aktueller Wert eines Custom-Felds. Der Einzel-GET ist für custom_fields belastbar. */
export function unitCustomValue(state: UnitState, key: string): unknown {
	const fromDetail = customOf(state.detail, key);
	if (fromDetail !== undefined) return fromDetail;
	const fromRow = customOf(state.row, key) ?? state.row?.[key];
	if (fromRow !== undefined) return fromRow;
	return state.row || state.detail.custom_fields ? null : UNVERIFIABLE;
}

/** Beides zusammen für die Anzeige: Einzel-GET hat Vorrang, expand ergänzt fehlende Felder. */
export function mergedUnit(state: UnitState): Raw {
	const merged: Raw = { ...(state.row ?? {}) };
	for (const [key, value] of Object.entries(state.detail)) {
		if (value !== null && value !== undefined) merged[key] = value;
		else if (!(key in merged)) merged[key] = value;
	}
	return merged;
}
