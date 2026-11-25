import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { Props } from "../auth/session";
import { PropstackError } from "../propstack-client";

// Regeln für Service-Sitzungen (objekte-handler, siehe src/service-access.ts). Kein Mensch sitzt davor – deshalb
// nur ausgewählte Werkzeuge und keine Freigaben, die eine menschliche Bestätigung voraussetzen.

/** Werkzeuge, die eine Service-Sitzung sieht und nutzen darf (Auftrag Florian, 25.11.2026). */
export const SERVICE_TOOLS: ReadonlySet<string> = new Set([
	"whoami",
	"search_objects",
	"get_object",
	"get_project",
	"search_contacts",
	"get_contact",
	"list_reference",
	"list_fields",
	"create_project",
	"create_object",
	"set_project_owner",
	"add_images",
	"create_task",
]);

/**
 * Parameter, die eine menschliche Bestätigung sind: Begründung für eine Dublette und die Bestätigung eines
 * öffentlichen Preises. Im Service-Zugang abgewiesen.
 */
const HUMAN_ONLY_PARAMS = ["allow_duplicate_reason", "public_price_confirmed"];

/** Objekte aus dem Service-Zugang entstehen immer in Vorbereitung – inaktiv, bis ein Mensch sie prüft. */
export const SERVICE_OBJECT_STATUS = 163673;

/** In Service-Sitzungen nur die freigegebenen Werkzeuge anmelden; sonst der Server unverändert. */
export function serviceServer(server: McpServer, props: Props | undefined): McpServer {
	if (!props?.service) return server;
	return new Proxy(server, {
		get(target, key, receiver) {
			if (key !== "registerTool") return Reflect.get(target, key, receiver);
			return (name: string, ...rest: unknown[]) =>
				SERVICE_TOOLS.has(name) ? (target.registerTool as (...args: unknown[]) => unknown).call(target, name, ...rest) : undefined;
		},
	});
}

/** Vor jedem Werkzeug-Aufruf: Steht es im Service-Zugang zur Verfügung, und fehlen die menschlichen Bestätigungen? */
export function assertServiceAllowed(props: Props, tool: string, params: unknown): void {
	if (!props.service) return;
	if (!SERVICE_TOOLS.has(tool)) {
		throw new PropstackError(`„${tool}“ steht im Service-Zugang (${props.service}) nicht zur Verfügung.`, 403);
	}
	const given = params && typeof params === "object" ? HUMAN_ONLY_PARAMS.filter((key) => (params as Record<string, unknown>)[key] !== undefined) : [];
	if (given.length) {
		throw new PropstackError(
			`${given.join(" und ")} ist im Service-Zugang (${props.service}) nicht erlaubt – das muss ein Mensch entscheiden. Ohne diesen Parameter erneut aufrufen; offene Punkte gehören in die Prüfaufgabe.`,
			400,
		);
	}
}

/**
 * create_object aus einer Service-Sitzung: immer Status 163673 (Vorbereitung) und nie aktiv – ein anderer Status
 * wird ersetzt, active: true nicht übernommen; beides steht im Ergebnis. Aktiv würde das Objekt sonst trotz
 * Vorbereitung in Automatisierungen (Exposéversand, Webseite) schicken.
 */
export function serviceObjectInput<T extends { status_id?: number; active?: boolean }>(user: Props, input: T): { input: T; notes: string[] } {
	if (!user.service) return { input, notes: [] };
	const notes: string[] = [];
	if (input.status_id !== SERVICE_OBJECT_STATUS) {
		notes.push(`Status ${input.status_id ?? "(keiner)"} durch ${SERVICE_OBJECT_STATUS} Vorbereitung ersetzt – Objekte aus dem Service-Zugang entstehen immer in Vorbereitung, bis ein Mensch sie prüft.`);
	}
	if (input.active === true) notes.push("active: true nicht übernommen – Objekte aus dem Service-Zugang bleiben inaktiv, bis ein Mensch sie prüft.");
	return { input: { ...input, active: input.active === true ? undefined : input.active, status_id: SERVICE_OBJECT_STATUS }, notes };
}
