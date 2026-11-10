import { z } from "zod";
import type { Props } from "../auth/session";
import { PropstackError, type PropstackClient } from "../propstack-client";
import { compact, scalar } from "../propstack/mappers";
import { escapeHtml, nextWorkdayNine } from "../review-task";
import { beginWrite, finishWrite } from "../write-log";
import { flag, id } from "./params";
import type { ToolOutput } from "./read-tools";

// Aufgabe an einen Propstack-Nutzer – z. B. eine Entscheidungsvorlage (Ansage Florian, 10.11.2026).
// Nur Anlegen: Ändern und Löschen bietet der Connector nicht. Deshalb wird alles VOR dem Schreiben geprüft
// (Empfänger, Fälligkeit, verknüpfte Datensätze) und danach gegengelesen.

type Raw = Record<string, unknown>;

export interface TaskDeps {
	client: Pick<PropstackClient, "listBrokers" | "getUnit" | "getProject" | "getContact" | "createTask" | "getTask">;
	db: D1Database | undefined;
	user: Props;
	now?: () => Date;
}

export const createTaskInput = {
	title: z.string().trim().min(5).max(200).describe("Titel: was zu tun oder zu entscheiden ist, z. B. „Entscheidung: alte Datensätze archivieren?“"),
	body: z
		.string()
		.trim()
		.min(1)
		.max(8000)
		.describe(
			"Text der Aufgabe, ohne HTML. Absätze durch eine Leerzeile trennen, Aufzählungen je Zeile mit „- “. Entscheidungsvorlage: worum es geht, die Möglichkeiten, eine Empfehlung",
		),
	assignee_id: id.optional().describe("Propstack-Nutzer-ID, an wen die Aufgabe geht (list_reference kind=users). Ohne Angabe: an dich selbst"),
	due_date: z
		.string()
		.regex(/^\d{4}-\d{2}-\d{2}$/)
		.optional()
		.describe("Fällig am, JJJJ-MM-TT (9:00 Uhr deutscher Zeit). Ohne Angabe: nächster Werktag"),
	object_ids: z.array(id).min(1).max(10).optional().describe("Objekte, um die es geht – werden an der Aufgabe verknüpft und müssen existieren"),
	project_ids: z.array(id).min(1).max(10).optional().describe("Projekte, um die es geht"),
	contact_ids: z.array(id).min(1).max(5).optional().describe("Kontakte, um die es geht"),
	test: flag.optional().describe("Testaufgabe: Titel beginnt mit [MCP-TEST], geht an dich selbst (assignee_id wird ignoriert)"),
};

const berlinDate = (d: Date) => new Intl.DateTimeFormat("en-CA", { day: "2-digit", month: "2-digit", timeZone: "Europe/Berlin", year: "numeric" }).format(d);

/** „2026-11-11T09:00:00“ (deutsche Zeit) mit Zeitzonen-Versatz versehen, damit Propstack nichts raten muss. */
export function withBerlinOffset(local: string): string {
	const zone = new Intl.DateTimeFormat("en-US", { timeZone: "Europe/Berlin", timeZoneName: "longOffset" })
		.formatToParts(new Date(`${local}Z`))
		.find((part) => part.type === "timeZoneName")?.value;
	const match = /GMT([+-]\d{2}):?(\d{2})/.exec(zone ?? "");
	return match ? `${local}${match[1]}:${match[2]}` : local;
}

/** Klartext → schlichtes HTML: je Absatz ein <p>, Zeilenumbrüche als <br>. Mehr als das ist in Propstack nicht erprobt. */
export function taskBodyHtml(text: string): string {
	return text
		.replace(/\r\n?/g, "\n")
		.split(/\n[ \t]*\n/)
		.map((block) => block.split("\n").map((line) => line.trim()).filter(Boolean))
		.filter((lines) => lines.length > 0)
		.map((lines) => `<p>${lines.map(escapeHtml).join("<br>")}</p>`)
		.join("");
}

/** HTML wieder auf den reinen Text bringen – zum Vergleich mit dem, was Propstack gespeichert hat. */
function plainText(html: string): string {
	return html
		.replace(/<br\s*\/?>|<\/p>|<\/div>|<\/li>/gi, "\n")
		.replace(/<[^>]+>/g, "")
		.replace(/&nbsp;/g, " ")
		.replace(/&lt;/g, "<")
		.replace(/&gt;/g, ">")
		.replace(/&quot;/g, '"')
		.replace(/&#0?39;|&apos;/g, "'")
		.replace(/&amp;/g, "&")
		.replace(/\s+/g, " ")
		.trim();
}

const unique = (ids: number[] | undefined) => [...new Set(ids ?? [])];
const rows = (raw: unknown): Raw[] => (Array.isArray(raw) ? raw : []).filter((row): row is Raw => !!row && typeof row === "object");

function label(raw: Raw, keys: string[]): string | undefined {
	for (const key of keys) {
		const value = scalar(raw[key]);
		if (typeof value === "string" && value.trim()) return value.trim();
	}
	return undefined;
}

/** IDs der verknüpften Datensätze aus der Aufgabe lesen – als ID-Liste oder als Liste von Datensätzen. */
function linkedIds(task: Raw, idKeys: string[], listKeys: string[]): number[] | undefined {
	for (const key of idKeys) {
		const value = task[key];
		if (Array.isArray(value)) return value.filter((v): v is number => typeof v === "number");
	}
	for (const key of listKeys) {
		const value = task[key];
		if (Array.isArray(value)) return rows(value).map((row) => row.id).filter((v): v is number => typeof v === "number");
	}
	return undefined;
}

/** Gleicher Zeitpunkt? Ohne Zeitzone in der Antwort wird die Uhrzeit wörtlich verglichen. */
function sameMoment(sent: string, got: unknown): boolean | undefined {
	if (typeof got !== "string" || !got) return undefined;
	if (!/(Z|[+-]\d{2}:?\d{2})$/.test(got)) return got.slice(0, 16) === sent.slice(0, 16);
	return Date.parse(got) === Date.parse(sent);
}

export interface TaskCheck {
	not_applied: string[];
	not_verifiable: string[];
}

/** Vergleicht die gespeicherte Aufgabe mit dem, was gesendet wurde. */
export function checkTask(stored: Raw, sent: Raw): TaskCheck {
	const not_applied: string[] = [];
	const not_verifiable: string[] = [];

	const title = scalar(stored.title);
	if (typeof title !== "string") not_verifiable.push("Titel");
	else if (title.trim() !== sent.title) not_applied.push("Titel");

	const broker = typeof stored.broker_id === "number" ? stored.broker_id : (stored.broker as Raw | undefined)?.id;
	if (typeof broker !== "number") not_verifiable.push("Empfänger");
	else if (broker !== sent.broker_id) not_applied.push("Empfänger");

	const due = sameMoment(String(sent.due_date), scalar(stored.due_date));
	if (due === undefined) not_verifiable.push("Fälligkeit");
	else if (!due) not_applied.push(`Fälligkeit (gespeichert: ${String(scalar(stored.due_date)).slice(0, 25)})`);

	if (stored.is_reminder === false) not_applied.push("Art „Aufgabe“ (als Notiz gespeichert)");

	const body = scalar(stored.body);
	if (typeof body !== "string") not_verifiable.push("Text");
	else if (plainText(body) !== plainText(String(sent.body))) not_applied.push("Text (von Propstack verändert gespeichert)");

	const links: [string, string, string[], string[]][] = [
		["property_ids", "Objekt", ["property_ids", "unit_ids"], ["units", "properties"]],
		["project_ids", "Projekt", ["project_ids"], ["projects"]],
		["client_ids", "Kontakt", ["client_ids"], ["clients"]],
	];
	for (const [key, name, idKeys, listKeys] of links) {
		const wanted = (sent[key] as number[] | undefined) ?? [];
		if (!wanted.length) continue;
		const got = linkedIds(stored, idKeys, listKeys);
		if (!got) not_verifiable.push(`Verknüpfung ${name}e`);
		else for (const wantedId of wanted) if (!got.includes(wantedId)) not_applied.push(`${name} ${wantedId} nicht verknüpft`);
	}
	return { not_applied, not_verifiable };
}

export async function createTask(deps: TaskDeps, input: z.infer<z.ZodObject<typeof createTaskInput>>): Promise<ToolOutput> {
	const { client, db, user } = deps;
	const now = deps.now?.() ?? new Date();

	if (/<\/?[a-z][^>]*>/i.test(input.body)) {
		throw new PropstackError("Der Text enthält HTML. Bitte als reinen Text schicken: Absätze durch Leerzeile, Aufzählungen mit „- “.", 0);
	}

	// Empfänger: muss ein Propstack-Nutzer mit Zugang sein, sonst sieht niemand die Aufgabe
	const assigneeId = input.test ? user.brokerId : (input.assignee_id ?? user.brokerId);
	const assignee = rows(await client.listBrokers()).find((broker) => broker.id === assigneeId);
	if (!assignee) {
		throw new PropstackError(`Den Nutzer ${assigneeId} gibt es in Propstack nicht. Nutzer und IDs: list_reference kind=users.`, 0);
	}
	const assigneeName = label(assignee, ["name"]) ?? `Nutzer ${assigneeId}`;
	if (assignee.connected === false) {
		throw new PropstackError(`${assigneeName} hat keinen aktiven Propstack-Zugang – die Aufgabe würde niemand sehen. Bitte einen anderen Nutzer wählen.`, 0);
	}

	// Fälligkeit
	let due = nextWorkdayNine(now);
	if (input.due_date) {
		const parsed = new Date(`${input.due_date}T00:00:00Z`);
		if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== input.due_date) {
			throw new PropstackError(`„${input.due_date}“ ist kein gültiges Datum (JJJJ-MM-TT).`, 0);
		}
		if (input.due_date < berlinDate(now)) {
			throw new PropstackError(`Die Fälligkeit ${input.due_date} liegt in der Vergangenheit.`, 0);
		}
		due = `${input.due_date}T09:00:00`;
	}

	// Verknüpfte Datensätze: müssen existieren – eine falsch verknüpfte Aufgabe lässt sich hier nicht mehr korrigieren
	const objectIds = unique(input.object_ids);
	const projectIds = unique(input.project_ids);
	const contactIds = unique(input.contact_ids);
	const missing: string[] = [];
	const lookup = async (kind: string, recordId: number, read: () => Promise<unknown>, keys: string[]) => {
		try {
			const raw = (await read()) as Raw | undefined;
			return { id: recordId, name: (raw && label(raw, keys)) ?? `${kind} ${recordId}` };
		} catch (error) {
			if (error instanceof PropstackError && error.status === 404) {
				missing.push(`${kind} ${recordId}`);
				return undefined;
			}
			throw error;
		}
	};
	const objects = [];
	for (const objectId of objectIds) objects.push(await lookup("Objekt", objectId, () => client.getUnit(objectId), ["name", "title"]));
	const projects = [];
	for (const projectId of projectIds) projects.push(await lookup("Projekt", projectId, () => client.getProject(projectId), ["name", "title"]));
	const contacts = [];
	for (const contactId of contactIds) contacts.push(await lookup("Kontakt", contactId, () => client.getContact(contactId), ["name", "company"]));
	if (missing.length) {
		throw new PropstackError(`Nicht gefunden: ${missing.join(", ")}. Es wurde keine Aufgabe angelegt.`, 0);
	}

	const title = `${input.test ? "[MCP-TEST] " : ""}${input.title}`;
	const task: Raw = {
		body: taskBodyHtml(input.body),
		broker_id: assigneeId,
		due_date: withBerlinOffset(due),
		is_reminder: true,
		title,
		...(objectIds.length ? { property_ids: objectIds } : {}),
		...(projectIds.length ? { project_ids: projectIds } : {}),
		...(contactIds.length ? { client_ids: contactIds } : {}),
	};

	// Write-Log ist fail-closed: ohne Eintrag wird nichts geschrieben
	const logId = await beginWrite(db, {
		action: "create",
		before: null,
		brokerId: user.brokerId,
		entity: "task",
		entityId: null,
		overrideReason: null,
		request: task,
		tool: "create_task",
		userEmail: user.email,
		warnings: [],
	});
	let taskId: number | undefined;
	try {
		const response = (await client.createTask(task)) as Raw | undefined;
		taskId = typeof response?.id === "number" ? response.id : undefined;
	} catch (error) {
		await finishWrite(db, logId, { error: (error as Error).message, status: "failed" });
		throw error;
	}

	// Gegenlesen
	let check: TaskCheck = { not_applied: [], not_verifiable: [] };
	let readbackFields: string[] | undefined;
	if (taskId === undefined) {
		check.not_verifiable.push("Propstack hat keine Aufgaben-ID zurückgegeben – bitte in Propstack nachsehen, ob die Aufgabe da ist");
	} else {
		try {
			const stored = (await client.getTask(taskId)) as Raw;
			check = checkTask(stored && typeof stored === "object" ? stored : {}, task);
			// nur Feldnamen, keine Werte – damit sich ein geändertes Antwortformat erkennen lässt
			if (check.not_verifiable.length) readbackFields = Object.keys(stored ?? {}).sort().slice(0, 60);
		} catch (error) {
			check.not_verifiable.push(`Gegenlesen nicht möglich (${error instanceof PropstackError ? error.message : "Fehler"})`);
		}
	}
	await finishWrite(db, logId, {
		entityId: taskId ?? null,
		notApplied: check.not_applied,
		status: taskId !== undefined && !check.not_applied.length ? "done" : "done_with_gaps",
	});

	return {
		count: 1,
		result: compact({
			created: true,
			id: taskId,
			title,
			assigned_to: assigneeName,
			due: `${due.slice(0, 10)} 09:00`,
			linked: compact({
				objects: objects.filter(Boolean),
				projects: projects.filter(Boolean),
				contacts: contacts.filter(Boolean),
			}),
			not_applied: check.not_applied,
			not_verifiable: check.not_verifiable,
			readback_fields: readbackFields,
			hint: "Aufgaben kann der Connector weder ändern noch löschen – Korrekturen direkt in Propstack.",
		}),
	};
}
