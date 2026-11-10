import { PropstackError } from "../propstack-client";

// Gesamtfläche = Hallenfläche + Mezzaninefläche, ohne Büro (Team-How-to, Regel seit 13.08.2026).
// Ansage Florian, 10.11.2026: Sie soll IMMER gerechnet werden. Anlass war der Mileway-Lauf vom 09.11.,
// bei dem elf Einheiten die Bürofläche in der Gesamtfläche trugen.

/** Custom-Feld, in dem die Mezzaninefläche steht (Parameter mezzanine_area). */
export const MEZZANINE_KEY = "mezzanineflache_gesamt";

const TOLERANCE = 0.005;
const round2 = (n: number) => Math.round(n * 100) / 100;
const show = (n: number) => new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(n);

/**
 * Fläche aus einem Propstack-Wert lesen: 1050, "1050", "1.050 m²", "1.050,5 m²", {value: 1050} → Zahl.
 * Alles andere (leer, „0 m² (vermietet)“, Text) → undefined.
 */
export function areaNumber(value: unknown): number | undefined {
	const raw = value && typeof value === "object" && !Array.isArray(value) && "value" in (value as Record<string, unknown>) ? (value as Record<string, unknown>).value : value;
	if (typeof raw === "number") return Number.isFinite(raw) ? raw : undefined;
	if (typeof raw !== "string") return undefined;
	const text = raw.replace(/m²|m2|qm/gi, "").trim();
	if (!/^\d[\d.,]*$/.test(text)) return undefined;
	// deutsche Schreibweise: Punkt als Tausendertrenner, Komma als Dezimalzeichen
	const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : /^\d{1,3}(\.\d{3})+$/.test(text) ? text.replace(/\./g, "") : text;
	const number = Number(normalized);
	return Number.isFinite(number) ? number : undefined;
}

/**
 * Gerechnete Gesamtfläche – oder undefined, wenn es keine Hallenfläche gibt (dann gilt die Regel nicht,
 * z. B. bei einer reinen Bürofläche). Ein abweichend mitgegebener Wert wird abgewiesen, nicht still ersetzt.
 */
export function computedTotal(hall: number | undefined, mezzanine: number | undefined, requested?: unknown): number | undefined {
	if (typeof hall !== "number" || !(hall > 0)) return undefined;
	const total = round2(hall + (mezzanine ?? 0));
	if (typeof requested === "number" && Math.abs(requested - total) > TOLERANCE) {
		throw new PropstackError(
			`Die Gesamtfläche rechnet der Connector immer selbst: Hallenfläche ${show(hall)} m² + Mezzanine ${show(mezzanine ?? 0)} m² = ${show(total)} m² (ohne Büro). Angegeben waren ${show(requested)} m². Bitte total_floor_space weglassen – oder Hallen- bzw. Mezzaninefläche berichtigen, falls die nicht stimmen.`,
			400,
		);
	}
	return total;
}

/** Weicht eine gespeicherte Gesamtfläche vom gerechneten Wert ab? */
export function totalDiffers(stored: number | undefined, computed: number): boolean {
	return stored !== undefined && Math.abs(stored - computed) > TOLERANCE;
}

export const showArea = show;
