/**
 * Lesetest gegen das echte Propstack - schreibt nichts.
 * Laeuft nur mit PROPSTACK_OBJ_KEY in der Umgebung, sonst uebersprungen.
 */
import { describe, expect, it } from "vitest";
import { flach, Propstack } from "../src/propstack";

const KEY = process.env.PROPSTACK_OBJ_KEY;
const d = KEY ? describe : describe.skip;

d("Propstack live (nur lesen)", () => {
	const ps = new Propstack(KEY!, KEY!);
	it("liest eine Einheit vollstaendig inkl. Einzelfeldern", async () => {
		const u = await ps.einheit(6174824); // Paul-Thomas-Strasse 50, Halle 1
		expect(u.unit_id).toBe("Halle 1");
		expect(u.rs_category).toBe("HALL");
		expect(u["cf.lagerflache"]).toBe(3475);
		expect(u.status_id).toBe(163674);
		expect(Array.isArray(u.bilder)).toBe(true);
	}, 60000);
	it("meldet fehlende IDs statt sie zu verschlucken", async () => {
		const { fehlend } = await ps.einheitenVoll([6174824, 1]);
		expect(fehlend).toEqual([1]);
	}, 60000);
	it("Feld-Registry kennt Typ und Einheit", async () => {
		const r = await ps.registry();
		expect(r.get("lagerflache")?.field_type).toBe("Number");
		expect(r.get("mezzanineflache")?.unit).toBe("euro");
	}, 60000);
	it("Suche findet Einheiten per q", async () => {
		const { zeilen } = await import("../src/propstack");
		const z = zeilen(await ps.raw("GET", "/units?expand=1&per=100&q=Paul-Thomas"));
		expect(z.map((x: any) => flach(x).id)).toContain(6174824);
	}, 60000);
});
