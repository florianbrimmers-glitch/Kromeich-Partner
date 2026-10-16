import type { Props } from "./auth/session";
import type { PropstackClient } from "./propstack-client";
import { beginWrite, finishWrite } from "./write-log";

// Automatische Prüfaufgabe nach jedem Anlegen über den MCP (Entscheidung Florian, 15.10.2026).
// Propstack-Regeln (Skill/Team-Prozess): is_reminder: true (sonst Notiz),
// fällig am nächsten Werktag 09:00. Testdaten gehen an den Nutzer selbst, nicht an Lena.

export const REVIEWER = { brokerId: 254958, name: "Lena Klinnert" };
export const CRM_BASE = "https://crm.propstack.de/app/portfolio";

function escapeHtml(text: string): string {
	return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Nächster Werktag (Mo–Fr) in deutscher Zeit, 09:00. */
export function nextWorkdayNine(now: Date): string {
	const berlin = (d: Date) => new Intl.DateTimeFormat("en-CA", { day: "2-digit", month: "2-digit", timeZone: "Europe/Berlin", year: "numeric" }).format(d);
	const weekday = (d: Date) => new Intl.DateTimeFormat("en-US", { timeZone: "Europe/Berlin", weekday: "short" }).format(d);
	let day = new Date(now.getTime() + 24 * 3600 * 1000);
	while (["Sat", "Sun"].includes(weekday(day))) day = new Date(day.getTime() + 24 * 3600 * 1000);
	return `${berlin(day)}T09:00:00`;
}

export interface ReviewTaskInput {
	user: Props;
	test: boolean;
	title: string;
	lines: string[];
	projectIds?: number[];
	propertyIds?: number[];
	now?: Date;
}

export interface ReviewTaskResult {
	id?: number;
	assigned_to?: string;
	due?: string;
	error?: string;
}

/** Legt die Prüfaufgabe an. Fehler brechen das Anlegen des Objekts nicht ab, sondern werden gemeldet. */
export async function createReviewTask(
	client: Pick<PropstackClient, "createTask">,
	db: D1Database | undefined,
	input: ReviewTaskInput,
): Promise<ReviewTaskResult> {
	const assignee = input.test ? { brokerId: input.user.brokerId, name: input.user.name } : REVIEWER;
	const due = nextWorkdayNine(input.now ?? new Date());
	// Umlaute bleiben erhalten: der MCP sendet sauberes UTF-8 (die ASCII-Regel im Skill stammt aus dem alten curl-Weg)
	const title = `${input.test ? "[MCP-TEST] " : ""}Prüfung: ${input.title}`.slice(0, 250);
	const body = `<p>${input.lines.map((l) => escapeHtml(l)).join("<br>")}</p>`;
	const task: Record<string, unknown> = {
		body,
		broker_id: assignee.brokerId,
		due_date: due,
		is_reminder: true,
		title,
		...(input.projectIds?.length ? { project_ids: input.projectIds } : {}),
		...(input.propertyIds?.length ? { property_ids: input.propertyIds } : {}),
	};
	let logId: number;
	try {
		logId = await beginWrite(db, {
			action: "create",
			before: null,
			brokerId: input.user.brokerId,
			entity: "task",
			entityId: null,
			overrideReason: null,
			request: task,
			tool: "review_task",
			userEmail: input.user.email,
			warnings: [],
		});
	} catch (error) {
		return { error: `Prüfaufgabe nicht angelegt: ${(error as Error).message}` };
	}
	try {
		const response = (await client.createTask(task)) as Record<string, unknown> | undefined;
		const id = typeof response?.id === "number" ? response.id : undefined;
		await finishWrite(db, logId, { entityId: id ?? null, status: id ? "done" : "done_with_gaps", notApplied: id ? [] : ["task id"] });
		return { assigned_to: assignee.name, due, id };
	} catch (error) {
		await finishWrite(db, logId, { error: (error as Error).message, status: "failed" });
		return { error: `Prüfaufgabe nicht angelegt: ${(error as Error).message}` };
	}
}
