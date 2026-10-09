/**
 * Login wird bewusst abgelehnt (Domain falsch, kein Propstack-Nutzer …).
 * Die Nachricht ist für den Nutzer bestimmt und enthält keine Interna.
 */
export class AuthRejection extends Error {
	constructor(message: string) {
		super(message);
		this.name = "AuthRejection";
	}
}
