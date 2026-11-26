import { describe, expect, it } from "vitest";
import { PropstackClient } from "../src/propstack-client";
import { failuresOf } from "../src/tools/failures";

// Auftrag 26.11.2026 (Objekte Handler): Scheitert ein Teilschritt von create_object, soll das maschinenlesbar im
// Ergebnis stehen – nicht nur in Texten, die die KI hoffentlich weitergibt.

describe("fehlgeschlagen: maschinenlesbare Liste der Teilschritte", () => {
	it("übersetzt Schreibfehler, nicht übernommene Felder und Verknüpfungen und eine fehlende Prüfaufgabe", () => {
		expect(
			failuresOf({
				missing: ["lat/lng", "owner (nicht prüfbar)", "contact_person (nicht prüfbar)", "tag MCP-TEST", "hall_height"],
				reviewTask: { error: "Prüfaufgabe nicht angelegt: Propstack-Serverfehler (502)" },
				writeErrors: ["Ansprechpartner: Propstack-Serverfehler (502)", "floor_load: abgelehnt"],
				coordinatesNote: "Adresse nicht gefunden",
			}),
		).toEqual([
			{ grund: "Propstack-Serverfehler (502)", schritt: "Ansprechpartner verknüpfen" },
			{ grund: "abgelehnt", schritt: "Feld floor_load" },
			{ grund: "Adresse nicht gefunden", schritt: "Koordinaten" },
			{ grund: "nicht prüfbar", schritt: "Eigentümer verknüpfen" },
			// „contact_person (nicht prüfbar)“ fehlt hier: derselbe Schritt steht schon mit dem genaueren Grund drin
			{ grund: "nicht übernommen", schritt: "Merkmal MCP-TEST" },
			{ grund: "nicht übernommen", schritt: "Feld hall_height" },
			{ grund: "Prüfaufgabe nicht angelegt: Propstack-Serverfehler (502)", schritt: "Prüfaufgabe" },
		]);
	});

	it("versteht auch die Schreibweise von create_project", () => {
		expect(failuresOf({ missing: ["owner nicht gefunden", "contact_person nicht prüfbar"] })).toEqual([
			{ grund: "nicht gefunden", schritt: "Eigentümer verknüpfen" },
			{ grund: "nicht prüfbar", schritt: "Ansprechpartner verknüpfen" },
		]);
	});

	it("alles geklappt → leere Liste", () => {
		expect(failuresOf({ missing: [], reviewTask: { id: 1 }, writeErrors: [] })).toEqual([]);
		expect(failuresOf({})).toEqual([]);
	});
});

describe("Cloudflare-Grenze für Unteraufrufe", () => {
	// Live 26.11.2026, Einheiten 6581032 ff.: „Propstack nicht erreichbar (Too many subrequests by single Worker
	// invocation …). Status der Änderung unklar“ – irreführend: Die Anfrage wurde gar nicht abgeschickt.
	const limit = () => {
		throw new Error("Too many subrequests by single Worker invocation. To configure this limit, refer to https://developers.cloudflare.com/workers/wrangler/configuration/#limits");
	};

	it("Lesen und Schreiben nennen die Grenze und sagen, dass nichts abgeschickt wurde", async () => {
		const client = new PropstackClient({ apiKey: "k", fetchFn: limit as unknown as typeof fetch, sleep: async () => {} });
		for (const call of [() => client.getUnit(1), () => client.updateUnit(1, { lat: 1 })]) {
			const error = (await call().catch((e: Error) => e)) as Error;
			expect(error.message).toMatch(/Cloudflare-Grenze für Unteraufrufe/);
			expect(error.message).toMatch(/nicht abgeschickt/);
			expect(error.message).not.toMatch(/Status der Änderung unklar/);
		}
	});

	it("andere Netzfehler bleiben „Status unklar“", async () => {
		const client = new PropstackClient({ apiKey: "k", fetchFn: (() => Promise.reject(new Error("network down"))) as unknown as typeof fetch, sleep: async () => {} });
		const error = (await client.updateUnit(1, { lat: 1 }).catch((e: Error) => e)) as Error;
		expect(error.message).toMatch(/Status der Änderung unklar/);
	});
});
