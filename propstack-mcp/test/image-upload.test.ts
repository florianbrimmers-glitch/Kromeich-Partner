import { describe, expect, it } from "vitest";
import { handleImageUpload, imageUploadUrl, newUploadToken, sniffImage, type UploadGrant } from "../src/image-upload";
import type { PropstackClient } from "../src/propstack-client";

const USER = { brokerId: 347158, email: "florian.brimmers@kromeichpartner.de", name: "Florian Brimmers" };
const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 0x10, 0x4a, 0x46, 0x49, 0x46, 0, 1]);
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);

function fakeKv() {
	const store = new Map<string, string>();
	const kv = {
		delete: async (k: string) => void store.delete(k),
		get: async (k: string, type?: string) => {
			const v = store.get(k);
			return v === undefined ? null : type === "json" ? JSON.parse(v) : v;
		},
		put: async (k: string, v: string) => void store.set(k, v),
	} as unknown as KVNamespace;
	return { kv, store };
}

function fakeDb() {
	const rows: unknown[][] = [];
	const updates: unknown[][] = [];
	const db = {
		prepare: (sql: string) => ({
			bind: (...args: unknown[]) => ({
				run: async () => {
					if (sql.startsWith("INSERT INTO write_log")) rows.push(args);
					else if (sql.startsWith("UPDATE")) updates.push(args);
					return { meta: { changes: 1, last_row_id: rows.length || 1 } };
				},
			}),
		}),
	} as unknown as D1Database;
	return { db, rows, updates };
}

function grant(overrides: Partial<UploadGrant> = {}): UploadGrant {
	return { brokerId: 347158, email: USER.email, expiresAt: Date.now() + 600_000, name: USER.name, remaining: 3, target: { id: 6265636, type: "Property" }, ...overrides };
}

function upload(token: string, files: { name: string; bytes: Uint8Array }[], field = "image[photo]") {
	const form = new FormData();
	for (const f of files) form.append(field, new File([f.bytes], f.name));
	return new Request(`https://propstack-mcp.kromeichpartner.workers.dev/upload/images/${token}`, { body: form, method: "POST" });
}

describe("image_upload_url", () => {
	it("erzeugt eine an Nutzer und Objekt gebundene Einmal-Adresse", async () => {
		const { kv, store } = fakeKv();
		const client = { getUnit: async () => ({ id: 5 }) } as unknown as PropstackClient;
		const out = await imageUploadUrl({ client, db: undefined, kv, now: () => new Date("2026-10-15T12:00:00Z"), user: USER }, { max_images: 4, object_id: 5 });
		const result = out.result as { upload_url: string; curl: string; expires_at: string; max_images: number };
		expect(result.upload_url).toMatch(/^https:\/\/propstack-mcp\.kromeichpartner\.workers\.dev\/upload\/images\/[A-Za-z0-9_-]{43}$/);
		expect(result.curl).toContain('-F "image[photo]=@bild1.jpg"');
		expect(result).toMatchObject({ expires_at: "2026-10-15T12:15:00.000Z", max_images: 4 });
		const stored = JSON.parse([...store.values()][0]) as UploadGrant;
		expect(stored).toMatchObject({ brokerId: 347158, remaining: 4, target: { id: 5, type: "Property" } });
	});

	it("Token sind zufällig und 256 Bit", () => {
		expect(newUploadToken()).not.toBe(newUploadToken());
		expect(newUploadToken()).toHaveLength(43);
	});
});

describe("Upload-Endpunkt", () => {
	const token = "A".repeat(43);

	async function setup(g: UploadGrant = grant()) {
		const { kv, store } = fakeKv();
		store.set(`img-upload:${token}`, JSON.stringify(g));
		const { db, rows, updates } = fakeDb();
		const sent: { type: string; id: number; name: string; size: number }[] = [];
		const createClient = () =>
			({
				uploadImage: async (type: string, id: number, photo: Blob, name: string) => {
					sent.push({ id, name, size: photo.size, type });
					return { id: 900 + sent.length };
				},
			}) as unknown as PropstackClient;
		const env = { AUDIT_DB: db, OAUTH_KV: kv } as unknown as Env;
		return { createClient, env, rows, sent, store, updates };
	}

	it("lädt in Reihenfolge hoch, protokolliert und verringert das Kontingent", async () => {
		const s = await setup();
		const res = await handleImageUpload(upload(token, [{ bytes: JPEG, name: "aussen.jpg" }, { bytes: PNG, name: "halle.png" }]), s.env, { createClient: s.createClient });
		expect(res.status).toBe(200);
		expect(await res.json()).toMatchObject({ images: [{ file: "aussen.jpg", image_id: 901 }, { file: "halle.png", image_id: 902 }], remaining_on_this_url: 1, uploaded: 2 });
		expect(s.sent.map((x) => [x.type, x.id, x.name])).toEqual([["Property", 6265636, "aussen.jpg"], ["Property", 6265636, "halle.png"]]);
		expect(JSON.parse(s.store.get(`img-upload:${token}`)!).remaining).toBe(1);
		expect(s.rows[0][3]).toBe("image_upload");
		expect(s.updates[0][0]).toBe("done");
	});

	it("letztes Kontingent löscht die Adresse; danach 404", async () => {
		const s = await setup(grant({ remaining: 1 }));
		expect((await handleImageUpload(upload(token, [{ bytes: JPEG, name: "a.jpg" }]), s.env, { createClient: s.createClient })).status).toBe(200);
		expect(s.store.has(`img-upload:${token}`)).toBe(false);
		expect((await handleImageUpload(upload(token, [{ bytes: JPEG, name: "b.jpg" }]), s.env, { createClient: s.createClient })).status).toBe(404);
	});

	it("weist abgelaufene Adressen, Nicht-Bilder und zu viele Dateien ab – ohne etwas hochzuladen", async () => {
		const expired = await setup(grant({ expiresAt: Date.now() - 1 }));
		expect((await handleImageUpload(upload(token, [{ bytes: JPEG, name: "a.jpg" }]), expired.env, { createClient: expired.createClient })).status).toBe(404);

		const s = await setup();
		const pdf = new TextEncoder().encode("%PDF-1.7 xxxxx");
		const bad = await handleImageUpload(upload(token, [{ bytes: JPEG, name: "ok.jpg" }, { bytes: pdf, name: "expose.pdf" }]), s.env, { createClient: s.createClient });
		expect(bad.status).toBe(400);
		expect(JSON.stringify(await bad.json())).toMatch(/expose\.pdf: kein JPEG/);
		const many = await handleImageUpload(upload(token, Array.from({ length: 4 }, (_, i) => ({ bytes: JPEG, name: `${i}.jpg` }))), s.env, { createClient: s.createClient });
		expect(many.status).toBe(400);
		expect(s.sent).toEqual([]);
		expect(JSON.parse(s.store.get(`img-upload:${token}`)!).remaining).toBe(3);
	});

	it("nur POST, nur gültige Tokenform", async () => {
		const s = await setup();
		expect((await handleImageUpload(new Request(`https://x/upload/images/${token}`), s.env)).status).toBe(405);
		expect((await handleImageUpload(upload("kurz", [{ bytes: JPEG, name: "a.jpg" }]), s.env)).status).toBe(404);
	});

	it("Propstack-Fehler je Bild wird gemeldet", async () => {
		const s = await setup();
		const createClient = () =>
			({
				uploadImage: async () => {
					throw new Error("Propstack-Anfrage fehlgeschlagen (422): photo ungültig");
				},
			}) as unknown as PropstackClient;
		const res = await handleImageUpload(upload(token, [{ bytes: JPEG, name: "a.jpg" }]), s.env, { createClient });
		expect(res.status).toBe(502);
		expect(JSON.stringify(await res.json())).toMatch(/422/);
		expect(s.updates[0][0]).toBe("failed");
	});

	it("sniffImage erkennt Formate an den Bytes", () => {
		expect(sniffImage(JPEG)).toBe("image/jpeg");
		expect(sniffImage(PNG)).toBe("image/png");
		expect(sniffImage(new TextEncoder().encode("RIFF\0\0\0\0WEBPVP8 "))).toBe("image/webp");
		expect(sniffImage(new TextEncoder().encode("GIF89a......"))).toBeNull();
	});
});
