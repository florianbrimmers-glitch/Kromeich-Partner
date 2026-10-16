import { z } from "zod";
import { PropstackClient, PropstackError } from "../propstack-client";
import { type DedupeResult, sameAddress } from "../propstack/dedupe";
import { scalar } from "../propstack/mappers";
import { CRM_BASE, createReviewTask } from "../review-task";
import { beginWrite, finishWrite } from "../write-log";
import { coordsOf, ensureCoordinates } from "../propstack/geo";
import { linkOwnerTo, type OwnerResult } from "../propstack/owner";
import { loadAll, type ToolOutput } from "./read-tools";
import { TEST_TAG, type WriteDeps } from "./write-tools";

// Phase 3b (Entscheidung Florian, 15.10.2026): Projekte anlegen, Eigentümer verknüpfen,
// Bilder per URL hochladen. Regeln aus Notion-Feld-Mapping und Team-Prozess:
// - Wrapper project; note ist nicht schreibbar (Projekte haben kein internes Notizfeld → Prüfaufgabe).
// - Eigentümer separat per PUT relationships_attributes mit related_client_id (nicht client_id),
//   Kontakt muss aus dem eigenen Shop stammen. Der Projekt-GET zeigt frische Verknüpfungen nicht →
//   Prüfung über die Relationship-Liste.
// - Bilder: image[photo] als Multipart oder remote_photo_url; hier nur öffentliche URLs.
// - Keine Lösch-Funktionen.

type Raw = Record<string, unknown>;

const optionalText = (max: number) => z.string().trim().min(1).max(max).optional();
const id = z.number().int().positive();
const MIN_OVERRIDE_REASON = 15;
const EXPOSE_VISIBLE = "EXPOSÉ-SICHTBAR: keine Konditionen, Eigentümer, Kundennamen oder offenen Punkte";

function today(now: Date): string {
	return now.toISOString().slice(0, 10);
}

function createdId(response: unknown): number {
	const raw = (response ?? {}) as Raw;
	const value = raw.id ?? (raw.data as Raw | undefined)?.id;
	if (typeof value !== "number") {
		throw new PropstackError("Propstack hat keine ID zurückgegeben – Status unklar, bitte in Propstack prüfen.", 0);
	}
	return value;
}

function asObject(value: unknown): Raw {
	return value && typeof value === "object" && !Array.isArray(value) ? (value as Raw) : {};
}

function readValue(actual: Raw, key: string): unknown {
	if (key === "broker_id" && "broker" in actual) {
		const broker = actual.broker as Raw | null | undefined;
		return broker && typeof broker === "object" ? (broker.id ?? null) : null;
	}
	return key in actual ? scalar(actual[key]) : undefined;
}

function matches(requested: unknown, actual: unknown): boolean {
	if (typeof requested === "number") return actual !== null && actual !== "" && Number(actual) === requested;
	if (typeof requested === "boolean") return actual === requested || String(actual) === String(requested);
	const squash = (v: unknown) => String(v ?? "").replace(/\s+/g, " ").trim();
	return squash(actual) === squash(requested);
}

/** Vergleich nach dem Write: fehlende Keys = nicht prüfbar, abweichende = nicht übernommen. */
function compareProject(fields: Raw, actual: Raw): { missing: string[]; unverified: string[] } {
	const missing: string[] = [];
	const unverified: string[] = [];
	for (const [key, value] of Object.entries(fields)) {
		const got = readValue(actual, key);
		if (got === undefined) unverified.push(key);
		else if (!matches(value, got)) missing.push(key);
	}
	return { missing, unverified };
}

// ---------- Projekt anlegen ----------

export const createProjectInput = {
	name: z.string().trim().min(1).max(250).describe("Projektname, Format: Logistikhalle in (XX) Ort – Straße (XX = erste zwei PLZ-Ziffern)"),
	title: optionalText(250).describe("Marketingname, z. B. des Eigentümers. Standard: wie name"),
	marketing_type: z.enum(["RENT", "BUY"]).describe("RENT = Vermietung, BUY = Verkauf"),
	street: z.string().trim().min(1).max(200),
	house_number: optionalText(20),
	zip_code: z.string().trim().regex(/^\d{4,5}$/),
	city: z.string().trim().min(1).max(100),
	hide_address: z.boolean().optional().describe("Adresse im Exposé ausblenden"),
	courtage: optionalText(200).describe("Provisionstext fürs Exposé, z. B. „Provisionsfrei“"),
	courtage_note: optionalText(2000).describe("Provisionshinweis, z. B. „Die Anmietung erfolgt provisionsfrei für den Mieter.“"),
	description_note: optionalText(10000).describe(`Objektbeschreibung. ${EXPOSE_VISIBLE}`),
	location_note: optionalText(10000).describe(`Lagebeschreibung. ${EXPOSE_VISIBLE}`),
	furnishing_note: optionalText(10000).describe(`Ausstattung. ${EXPOSE_VISIBLE}`),
	owner_contact_id: id.optional().describe("Eigentümer-Kontakt (eigener Shop). Wird nach dem Anlegen separat verknüpft – an den Einheiten ebenfalls angeben"),
	lat: z.number().min(-90).max(90).optional().describe("Breitengrad, falls bekannt. Sonst übernimmt das Tool Propstacks Geokodierung oder ermittelt die Koordinaten aus der Adresse (OpenStreetMap)"),
	lng: z.number().min(-180).max(180).optional().describe("Längengrad, falls bekannt"),
	review_notes: z
		.array(z.string().trim().min(1).max(500))
		.max(20)
		.optional()
		.describe(
			"Offene Punkte, abgeleitete/unsichere Werte – landen in der Prüfaufgabe (Projekte haben kein internes Notizfeld). Dieselben Punkte beim Anlegen der Einheit(en) zusätzlich per bemerkung_append vermerken, sonst sieht sie niemand an der Einheit",
		),
	test: z.boolean().optional().describe(`Testdatensatz: Name beginnt mit ${TEST_TAG}, Prüfaufgabe geht an dich statt an Lena. Für alle Tests Pflicht.`),
	allow_duplicate_reason: optionalText(500).describe("Nur wenn ein Projekt an derselben Adresse existiert und es nachweislich ein anderes ist: Begründung"),
};

async function projectDuplicates(client: PropstackClient, input: { street: string; house_number?: string; zip_code: string }): Promise<DedupeResult> {
	const loaded = await loadAll((q) => client.searchProjects(q), { q: input.zip_code }, 100, 5);
	if (!loaded.complete) throw new PropstackError(`Zu viele Projekte in PLZ ${input.zip_code} für die Dublettenprüfung.`, 400);
	const duplicates = loaded.rows
		.filter((row) => sameAddress({ ...input, marketing_type: "" }, row))
		.map((row) => ({ id: row.id as number, name: String(scalar(row.name) ?? scalar(row.title) ?? "Projekt"), reason: "gleiche Adresse" }));
	return { duplicates, warnings: [] };
}

export async function createProject(deps: WriteDeps, input: z.infer<z.ZodObject<typeof createProjectInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	const now = deps.now?.() ?? new Date();

	const dedupe = await projectDuplicates(client, input);
	if (dedupe.duplicates.length && !input.allow_duplicate_reason) {
		return {
			count: 0,
			result: {
				created: false,
				blocked: "Dublette",
				duplicates: dedupe.duplicates,
				hint: "Nichts angelegt. Vorhandenes Projekt verwenden (Einheiten mit project_id anlegen) – oder, falls es nachweislich ein anderes ist, mit allow_duplicate_reason erneut aufrufen.",
			},
		};
	}
	const overrideReason = dedupe.duplicates.length ? input.allow_duplicate_reason!.trim() : null;
	if (overrideReason !== null && overrideReason.length < MIN_OVERRIDE_REASON) {
		throw new PropstackError(`allow_duplicate_reason braucht eine echte Begründung (mind. ${MIN_OVERRIDE_REASON} Zeichen).`, 400);
	}

	let owner: { id: number; name: string } | undefined;
	if (input.owner_contact_id) {
		const contact = asObject(await client.getContact(input.owner_contact_id));
		owner = { id: input.owner_contact_id, name: String(scalar(contact.name) ?? input.owner_contact_id) };
	}

	const name = input.test ? `${TEST_TAG} ${input.name}` : input.name;
	const fields: Raw = {
		broker_id: user.brokerId,
		city: input.city,
		country: "DEU",
		name,
		street: input.street,
		title: input.title ?? name,
		zip_code: input.zip_code,
		...(input.marketing_type === "RENT" ? { for_rent: true } : { for_sale: true }),
	};
	for (const key of ["house_number", "hide_address", "courtage", "courtage_note", "description_note", "location_note", "furnishing_note"] as const) {
		if (input[key] !== undefined) fields[key] = input[key];
	}

	const logId = await beginWrite(deps.db, {
		action: "create",
		before: null,
		brokerId: user.brokerId,
		entity: "project",
		entityId: null,
		overrideReason,
		request: { ...fields, owner_contact_id: input.owner_contact_id },
		tool: "create_project",
		userEmail: user.email,
		warnings: dedupe.warnings,
	});
	let projectId: number;
	try {
		projectId = createdId(await client.createProject(fields));
	} catch (error) {
		await finishWrite(deps.db, logId, { error: (error as Error).message, status: "failed" });
		throw error;
	}

	// Zurücklesen; was im Sammel-Request verloren ging, einzeln nachsetzen (Feld-Mapping: Multi-Feld-Writes verlieren still)
	let actual = asObject(await client.getProject(projectId));
	let { missing, unverified } = compareProject(fields, actual);
	const writeErrors: string[] = [];
	if (missing.length) {
		for (const key of missing) {
			try {
				await client.updateProject(projectId, { [key]: fields[key] });
			} catch (error) {
				writeErrors.push(`${key}: ${(error as Error).message}`);
			}
		}
		actual = asObject(await client.getProject(projectId));
		({ missing, unverified } = compareProject(fields, actual));
	}

	const coordinates = await ensureCoordinates({
		address: input,
		current: coordsOf(actual),
		provided: { lat: input.lat, lng: input.lng },
		fetchFn: deps.fetchFn,
		put: (body) => client.updateProject(projectId, body),
		read: async () => coordsOf(asObject(await client.getProject(projectId))),
	});
	// Lücke nur, wenn geschrieben wurde und nicht haftet; „nichts gefunden“ steht in der Prüfaufgabe
	if (!coordinates.verified && coordinates.source !== "keine") missing.push("lat/lng");
	const ownerResult = owner ? await linkOwner(client, projectId, owner.id) : undefined;
	if (ownerResult?.error) writeErrors.push(`Eigentümer: ${ownerResult.error}`);
	const ownerGap = ownerResult && ownerResult.linked !== true && !ownerResult.error ? [`owner ${ownerResult.linked === false ? "nicht gefunden" : "nicht prüfbar"}`] : [];
	await finishWrite(deps.db, logId, {
		entityId: projectId,
		error: writeErrors.length ? writeErrors.join(" | ") : undefined,
		notApplied: [...missing, ...ownerGap, ...unverified.map((f) => `${f} (nicht prüfbar)`)],
		status: missing.length || writeErrors.length || ownerGap.length ? "done_with_gaps" : "done",
	});

	const review = await createReviewTask(client, deps.db, {
		lines: [
			`Projekt ${projectId}: ${name}`,
			`${CRM_BASE}/projects/${projectId}`,
			`Angelegt über Claude (Propstack MCP) von ${user.name} am ${today(now)}.`,
			owner ? `Eigentümer: ${owner.name} (${owner.id})${ownerResult?.linked === true ? "" : " – Verknüpfung prüfen"}` : "Eigentümer: nicht verknüpft",
			coordinates.verified
				? `Koordinaten: ${coordinates.lat}, ${coordinates.lng} (${coordinates.source}${coordinates.precision ? `, Genauigkeit ${coordinates.precision}` : ""})`
				: "Koordinaten: fehlen – bitte nachtragen",
			...(overrideReason ? [`Dublette bewusst angelegt: ${overrideReason}`] : []),
			...(missing.length ? [`Nicht übernommen: ${missing.join(", ")}`] : []),
			...(writeErrors.length ? [`Fehler: ${writeErrors.join("; ")}`] : []),
			...(input.review_notes ?? []).map((n) => `Offen: ${n}`),
			"Prüfen: Adresse/Koordinaten, Texte (keine Konditionen/Eigentümer), Provision, Einheiten, Bilder.",
		],
		now,
		projectIds: [projectId],
		test: input.test === true,
		title: `${name} - Projekt ${projectId}`,
		user,
	});

	return {
		count: 1,
		result: {
			created: true,
			id: projectId,
			name,
			link: `${CRM_BASE}/projects/${projectId}`,
			broker: user.name,
			test: input.test || undefined,
			owner: owner ? { ...owner, linked: ownerResult?.linked } : undefined,
			coordinates,
			override_reason: overrideReason ?? undefined,
			not_applied: missing.length ? missing : undefined,
			not_verifiable: unverified.length ? unverified : undefined,
			write_errors: writeErrors.length ? writeErrors : undefined,
			review_task: review,
			next: "Einheiten mit create_object und project_id anlegen; Bilder mit add_images.",
		},
	};
}

// ---------- Eigentümer verknüpfen ----------

/** Kompatibel zu früher: Eigentümer an einem Projekt. */
export function linkOwner(client: PropstackClient, projectId: number, contactId: number): Promise<OwnerResult> {
	return linkOwnerTo(client, { id: projectId, type: "project" }, contactId);
}

export const setProjectOwnerInput = {
	project_id: id.optional().describe("Propstack-Projekt-ID"),
	object_id: id.optional().describe("Propstack-Objekt-ID (Einheit) – statt project_id"),
	contact_id: id.describe("Eigentümer-Kontakt-ID (eigener Shop)"),
};

export async function setProjectOwner(deps: WriteDeps, input: z.infer<z.ZodObject<typeof setProjectOwnerInput>>): Promise<ToolOutput> {
	const { client, user } = deps;
	if ((input.project_id === undefined) === (input.object_id === undefined)) {
		throw new PropstackError("Genau eins von project_id oder object_id angeben.", 400);
	}
	const target = input.project_id !== undefined ? { id: input.project_id, type: "project" as const } : { id: input.object_id!, type: "object" as const };
	const record = asObject(target.type === "project" ? await client.getProject(target.id) : await client.getUnit(target.id));
	const contact = asObject(await client.getContact(input.contact_id));
	const logId = await beginWrite(deps.db, {
		action: "update",
		before: null,
		brokerId: user.brokerId,
		entity: target.type,
		entityId: target.id,
		overrideReason: null,
		request: { owner_contact_id: input.contact_id },
		tool: "set_project_owner",
		userEmail: user.email,
		warnings: [],
	});
	const result = await linkOwnerTo(client, target, input.contact_id);
	await finishWrite(deps.db, logId, {
		error: result.error,
		notApplied: result.linked === true ? [] : [`owner ${result.linked === false ? "nicht gefunden" : "nicht prüfbar"}`],
		status: result.error ? "failed" : result.linked === true ? "done" : "done_with_gaps",
	});
	if (result.error) throw new PropstackError(result.error, 400);
	return {
		count: 1,
		result: {
			[target.type]: { id: target.id, name: scalar(record.name) ?? scalar(record.title) },
			owner: { id: input.contact_id, name: scalar(contact.name) },
			linked: result.linked,
			already_linked: result.already || undefined,
			note: result.linked === true ? undefined : (result.note ?? "Verknüpfung nicht bestätigt – bitte in der UI prüfen."),
		},
	};
}

// ---------- Bilder ----------

export const addImagesInput = {
	object_id: id.optional().describe("Objekt (Einheit), an das die Bilder kommen"),
	project_id: id.optional().describe("Projekt, an das die Bilder kommen (statt object_id)"),
	urls: z
		.array(z.string().trim().url().regex(/^https:\/\//, "nur https-URLs"))
		.min(1)
		.max(10)
		.describe("Öffentliche Bild-URLs (https). Reihenfolge = Reihenfolge in Propstack; das erste Bild eines Objekts wird Titelbild – bestes Außenfoto zuerst"),
};

const USER_AGENT = "KromeichPropstackMCP/1.0 (+https://kromeichpartner.de)";

/** Vorab prüfen, ob die URL ein erreichbares Bild ist – Propstack legt sonst ggf. leere Bildobjekte an, die nur in der UI löschbar sind. */
export async function checkImageUrl(url: string, fetchFn: typeof fetch = fetch): Promise<string | null> {
	try {
		// Ohne User-Agent blocken manche Hoster (z. B. Wikimedia) mit 403
		let response = await fetchFn(url, { headers: { "User-Agent": USER_AGENT }, method: "HEAD", redirect: "follow", signal: AbortSignal.timeout(8000) });
		if (response.status === 405 || response.status === 403) {
			response = await fetchFn(url, {
				headers: { Range: "bytes=0-0", "User-Agent": USER_AGENT },
				method: "GET",
				redirect: "follow",
				signal: AbortSignal.timeout(8000),
			});
		}
		if (!response.ok && response.status !== 206) return `nicht erreichbar (HTTP ${response.status})`;
		const type = response.headers.get("content-type") ?? "";
		if (!type.startsWith("image/")) return `kein Bild (Content-Type ${type || "unbekannt"})`;
		return null;
	} catch (error) {
		return `nicht erreichbar (${(error as Error).message})`;
	}
}

export async function addImages(
	deps: WriteDeps & { fetchFn?: typeof fetch },
	input: z.infer<z.ZodObject<typeof addImagesInput>>,
): Promise<ToolOutput> {
	const { client, user } = deps;
	if ((input.object_id === undefined) === (input.project_id === undefined)) {
		throw new PropstackError("Genau eins von object_id oder project_id angeben.", 400);
	}
	const target = input.object_id !== undefined ? { id: input.object_id, type: "Property" } : { id: input.project_id!, type: "Project" };

	// Ziel muss existieren (404 statt verwaister Bilder)
	if (target.type === "Property") await client.getUnit(target.id);
	else await client.getProject(target.id);

	const rejected: { url: string; reason: string }[] = [];
	const valid: string[] = [];
	for (const url of input.urls) {
		const problem = await checkImageUrl(url, deps.fetchFn);
		if (problem) rejected.push({ reason: problem, url });
		else valid.push(url);
	}
	if (!valid.length) {
		return { count: 0, result: { uploaded: 0, rejected, note: "Kein Bild hochgeladen – keine der URLs ist ein erreichbares Bild." } };
	}

	const logId = await beginWrite(deps.db, {
		action: "create",
		before: null,
		brokerId: user.brokerId,
		entity: "image",
		entityId: target.id,
		overrideReason: null,
		request: { imageable_id: target.id, imageable_type: target.type, urls: valid },
		tool: "add_images",
		userEmail: user.email,
		warnings: rejected.map((r) => `${r.url}: ${r.reason}`),
	});
	const uploaded: number[] = [];
	const errors: string[] = [];
	for (const url of valid) {
		try {
			const response = asObject(await client.createImage({ imageable_id: target.id, imageable_type: target.type, remote_photo_url: url }));
			if (typeof response.id === "number") uploaded.push(response.id);
			else errors.push(`${url}: keine Bild-ID zurückbekommen – bitte in der UI prüfen`);
		} catch (error) {
			errors.push(`${url}: ${(error as Error).message}`);
		}
	}
	await finishWrite(deps.db, logId, {
		error: errors.length ? errors.join(" | ") : undefined,
		status: errors.length ? (uploaded.length ? "done_with_gaps" : "failed") : "done",
	});

	return {
		count: uploaded.length,
		result: {
			target: { id: target.id, type: target.type === "Property" ? "object" : "project" },
			uploaded: uploaded.length,
			image_ids: uploaded.length ? uploaded : undefined,
			rejected: rejected.length ? rejected : undefined,
			errors: errors.length ? errors : undefined,
			note: "Bildrechte liegen beim Eigentümer/Entwickler – Portalfreigabe separat klären. Firmenschriftzüge vorher entfernen.",
		},
	};
}
