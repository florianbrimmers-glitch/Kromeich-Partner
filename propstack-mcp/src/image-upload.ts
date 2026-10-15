import { z } from "zod";
import { writeAuditEntry } from "./audit";
import { IMAGE_UPLOAD_MAX_BYTES, IMAGE_UPLOAD_MAX_FILES, IMAGE_UPLOAD_TTL_SECONDS, PUBLIC_BASE_URL } from "./config";
import { PropstackClient, PropstackError } from "./propstack-client";
import { beginWrite, finishWrite } from "./write-log";
import type { ToolOutput } from "./tools/read-tools";
import type { WriteDeps } from "./tools/write-tools";

// Bild-Upload per Einmal-Adresse (Entscheidung Florian, 15.10.2026).
// Ein MCP-Tool bekommt nur Text – Bilddateien passen da nicht durch. Deshalb:
// 1. Tool image_upload_url erzeugt eine Upload-Adresse: 15 min gültig, an Nutzer + genau ein Objekt/Projekt
//    gebunden, mit Höchstzahl an Bildern. Das Token ist 256 Bit zufällig und liegt nur in KV.
// 2. Die Sitzung (Claude Code / Cowork) lädt die Dateien per curl hoch: -F "image[photo]=@bild.jpg".
// 3. Der Worker reicht sie per Multipart (image[photo]) an Propstack weiter, mit Write-Log und Audit.
// Kein Propstack-API-Key verlässt den Server.

const KV_PREFIX = "img-upload:";
const FILE_FIELDS = ["image[photo]", "photo", "file", "image", "images[]"];

type Target = { type: "Property" | "Project"; id: number };

export interface UploadGrant {
	target: Target;
	email: string;
	brokerId: number;
	name: string;
	remaining: number;
	expiresAt: number;
}

function base64url(bytes: Uint8Array): string {
	let text = "";
	for (const b of bytes) text += String.fromCharCode(b);
	return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function newUploadToken(): string {
	return base64url(crypto.getRandomValues(new Uint8Array(32)));
}

/** JPEG, PNG oder WebP anhand der ersten Bytes – dem mitgeschickten Content-Type wird nicht vertraut. */
export function sniffImage(bytes: Uint8Array): "image/jpeg" | "image/png" | "image/webp" | null {
	if (bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "image/jpeg";
	if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) return "image/png";
	const ascii = (from: number, to: number) => String.fromCharCode(...bytes.slice(from, to));
	if (ascii(0, 4) === "RIFF" && ascii(8, 12) === "WEBP") return "image/webp";
	return null;
}

// ---------- Tool ----------

export const imageUploadUrlInput = {
	object_id: z.number().int().positive().optional().describe("Objekt (Einheit), an das die Bilder kommen"),
	project_id: z.number().int().positive().optional().describe("Projekt, an das die Bilder kommen (statt object_id)"),
	max_images: z.number().int().min(1).max(IMAGE_UPLOAD_MAX_FILES).optional().describe(`Höchstzahl Bilder für diese Adresse (Standard 10, max. ${IMAGE_UPLOAD_MAX_FILES})`),
};

export async function imageUploadUrl(
	deps: WriteDeps & { kv: KVNamespace | undefined },
	input: z.infer<z.ZodObject<typeof imageUploadUrlInput>>,
): Promise<ToolOutput> {
	const { client, user, kv } = deps;
	if (!kv) throw new PropstackError("Upload-Speicher nicht verfügbar.", 0);
	if ((input.object_id === undefined) === (input.project_id === undefined)) {
		throw new PropstackError("Genau eins von object_id oder project_id angeben.", 400);
	}
	const target: Target = input.object_id !== undefined ? { id: input.object_id, type: "Property" } : { id: input.project_id!, type: "Project" };
	// Ziel muss existieren (404 statt verwaister Upload-Adresse)
	if (target.type === "Property") await client.getUnit(target.id);
	else await client.getProject(target.id);

	const now = deps.now?.() ?? new Date();
	const token = newUploadToken();
	const grant: UploadGrant = {
		brokerId: user.brokerId,
		email: user.email,
		expiresAt: now.getTime() + IMAGE_UPLOAD_TTL_SECONDS * 1000,
		name: user.name,
		remaining: input.max_images ?? 10,
		target,
	};
	await kv.put(`${KV_PREFIX}${token}`, JSON.stringify(grant), { expirationTtl: IMAGE_UPLOAD_TTL_SECONDS });
	const url = `${PUBLIC_BASE_URL}/upload/images/${token}`;
	return {
		count: 1,
		result: {
			upload_url: url,
			target: { id: target.id, type: target.type === "Property" ? "object" : "project" },
			expires_at: new Date(grant.expiresAt).toISOString(),
			max_images: grant.remaining,
			max_mb_per_image: IMAGE_UPLOAD_MAX_BYTES / 1024 / 1024,
			formats: "JPEG, PNG, WebP",
			curl: `curl -sS -F "image[photo]=@bild1.jpg" -F "image[photo]=@bild2.jpg" "${url}"`,
			note: "Dateien in der gewünschten Reihenfolge anhängen – das erste Bild eines Objekts wird Titelbild (bestes Außenfoto zuerst). Die Adresse nicht weitergeben; sie verfällt nach 15 Minuten bzw. wenn die Höchstzahl erreicht ist. Firmenschriftzüge vorher entfernen, Bildrechte klären.",
		},
	};
}

// ---------- HTTP-Endpunkt ----------

function json(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json; charset=utf-8" }, status });
}

export interface UploadOptions {
	createClient?: () => Pick<PropstackClient, "uploadImage">;
	now?: () => number;
}

export async function handleImageUpload(request: Request, env: Env, options: UploadOptions = {}): Promise<Response> {
	if (request.method !== "POST") return json(405, { error: "Nur POST (multipart/form-data) erlaubt." });
	const token = new URL(request.url).pathname.split("/").pop() ?? "";
	if (!/^[A-Za-z0-9_-]{43}$/.test(token)) return json(404, { error: "Upload-Adresse ungültig oder abgelaufen." });
	const key = `${KV_PREFIX}${token}`;
	const grant = await env.OAUTH_KV.get<UploadGrant>(key, "json");
	const now = options.now?.() ?? Date.now();
	if (!grant || grant.expiresAt < now) return json(404, { error: "Upload-Adresse ungültig oder abgelaufen. Neue Adresse mit image_upload_url holen." });
	if (!(request.headers.get("content-type") ?? "").startsWith("multipart/form-data")) {
		return json(400, { error: 'Bitte als multipart/form-data senden: curl -F "image[photo]=@bild.jpg" <Adresse>' });
	}

	let form: FormData;
	try {
		form = await request.formData();
	} catch {
		return json(400, { error: "Formular nicht lesbar." });
	}
	const files: File[] = [];
	for (const field of FILE_FIELDS) {
		for (const value of form.getAll(field)) if (typeof value !== "string") files.push(value as File);
	}
	if (!files.length) return json(400, { error: 'Keine Datei gefunden. Feldname: image[photo], z. B. -F "image[photo]=@bild.jpg".' });
	if (files.length > grant.remaining) {
		return json(400, { error: `Zu viele Bilder: ${files.length}, mit dieser Adresse noch erlaubt: ${grant.remaining}. Nichts hochgeladen.` });
	}

	// Alles vorab prüfen – lieber nichts hochladen als die Hälfte
	const checked: { file: File; type: string }[] = [];
	const problems: string[] = [];
	for (const file of files) {
		if (file.size > IMAGE_UPLOAD_MAX_BYTES) {
			problems.push(`${file.name}: größer als ${IMAGE_UPLOAD_MAX_BYTES / 1024 / 1024} MB`);
			continue;
		}
		const type = sniffImage(new Uint8Array(await file.slice(0, 12).arrayBuffer()));
		if (!type) problems.push(`${file.name}: kein JPEG, PNG oder WebP`);
		else checked.push({ file, type });
	}
	if (problems.length) return json(400, { error: "Nichts hochgeladen.", problems });

	// Kontingent sofort reservieren (Doppelverwendung der Adresse begrenzen)
	const remaining = grant.remaining - files.length;
	const ttl = Math.max(60, Math.ceil((grant.expiresAt - now) / 1000));
	if (remaining > 0) await env.OAUTH_KV.put(key, JSON.stringify({ ...grant, remaining }), { expirationTtl: ttl });
	else await env.OAUTH_KV.delete(key);

	let logId: number;
	try {
		logId = await beginWrite(env.AUDIT_DB, {
			action: "create",
			before: null,
			brokerId: grant.brokerId,
			entity: "image",
			entityId: grant.target.id,
			overrideReason: null,
			request: { files: checked.map(({ file, type }) => ({ bytes: file.size, name: file.name, type })), imageable_id: grant.target.id, imageable_type: grant.target.type },
			tool: "image_upload",
			userEmail: grant.email,
			warnings: [],
		});
	} catch (error) {
		return json(503, { error: (error as Error).message });
	}

	const client = options.createClient?.() ?? new PropstackClient({ apiKey: env.PROPSTACK_API_KEY });
	const started = now;
	const uploaded: { file: string; image_id: number | null }[] = [];
	const errors: string[] = [];
	for (const { file, type } of checked) {
		try {
			const response = (await client.uploadImage(grant.target.type, grant.target.id, new Blob([await file.arrayBuffer()], { type }), file.name)) as
				| Record<string, unknown>
				| undefined;
			const id = typeof response?.id === "number" ? response.id : null;
			uploaded.push({ file: file.name, image_id: id });
			if (id === null) errors.push(`${file.name}: keine Bild-ID zurückbekommen – bitte in der UI prüfen`);
		} catch (error) {
			errors.push(`${file.name}: ${(error as Error).message}`);
		}
	}
	const ok = uploaded.filter((u) => u.image_id !== null).length;
	await finishWrite(env.AUDIT_DB, logId, {
		error: errors.length ? errors.join(" | ") : undefined,
		status: errors.length ? (ok ? "done_with_gaps" : "failed") : "done",
	});
	await writeAuditEntry(env.AUDIT_DB, {
		brokerId: grant.brokerId,
		durationMs: (options.now?.() ?? Date.now()) - started,
		error: errors.length ? errors.join(" | ").slice(0, 500) : null,
		ok: errors.length === 0,
		params: { files: checked.length, target: grant.target },
		resultCount: ok,
		tool: "image_upload",
		ts: new Date(started).toISOString(),
		userEmail: grant.email,
	});

	return json(ok ? 200 : 502, {
		target: { id: grant.target.id, type: grant.target.type === "Property" ? "object" : "project" },
		uploaded: ok,
		images: uploaded,
		errors: errors.length ? errors : undefined,
		remaining_on_this_url: Math.max(0, remaining),
	});
}
