import { z } from "zod";

// Gemeinsame Parameter-Bausteine der Tools.
// Nachsichtig bei Ziffernfolgen und true/false als Text: Clients mit veralteter Tool-Liste kennen neue
// Parameter nicht und schicken sie als Text (Live-Befund Oktober 2026). Das veröffentlichte Schema
// bleibt integer bzw. boolean; alles andere (z. B. "5.000", "abc", true als ID) wird weiter abgewiesen.

const digits = (v: unknown) => (typeof v === "string" && /^\d{1,15}$/.test(v.trim()) ? Number(v.trim()) : v);

/** Propstack-ID. */
export const id = z.preprocess(digits, z.number().int().positive());

/** Anzahl (Tore, Stellplätze …). */
export const count = z.preprocess(digits, z.number().int().nonnegative().max(100_000));

/** Ja/Nein. */
export const flag = z.preprocess((v) => (v === "true" ? true : v === "false" ? false : v), z.boolean());

export const optionalText = (max: number) => z.string().trim().min(1).max(max).optional();
