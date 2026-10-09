import { describe, expect, it } from "vitest";
import { AuthRejection } from "../src/auth/errors";
import { checkIdTokenClaims, verifyGoogleIdToken } from "../src/auth/google-id-token";
import { CLIENT_ID, NOW, createSigner, validClaims } from "./helpers";

const check = (claims: Record<string, unknown>) => () =>
	checkIdTokenClaims(claims, { clientId: CLIENT_ID, nowSeconds: NOW });

describe("3a – Claims-Prüfung", () => {
	it("lässt verifiziertes kromeichpartner.de-Konto durch", () => {
		expect(check(validClaims())()).toEqual({
			email: "florian.brimmers@kromeichpartner.de",
			name: "Florian Brimmers",
			subject: "1234567890",
		});
	});

	it("lehnt privates Gmail-Konto ab (kein hd)", () => {
		const claims = validClaims({ email: "irgendwer@gmail.com" });
		delete claims.hd;
		expect(check(claims)).toThrow(AuthRejection);
	});

	it("lehnt fremde Workspace-Domain ab", () => {
		expect(check(validClaims({ hd: "andere-firma.de" }))).toThrow(/kromeichpartner\.de/);
	});

	it("lehnt Domain ab, die nur ähnlich aussieht", () => {
		expect(check(validClaims({ hd: "kromeichpartner.de.evil.com" }))).toThrow(AuthRejection);
		expect(check(validClaims({ hd: "evilkromeichpartner.de" }))).toThrow(AuthRejection);
	});

	it("akzeptiert hd unabhängig von Groß-/Kleinschreibung", () => {
		expect(check(validClaims({ hd: "KromeichPartner.de" }))).not.toThrow();
	});

	it.each([false, "true", undefined, 1])("lehnt email_verified=%s ab", (value) => {
		expect(check(validClaims({ email_verified: value }))).toThrow(/nicht verifiziert/);
	});

	it("lehnt fremde Audience ab", () => {
		expect(check(validClaims({ aud: "anderer-client" }))).toThrow(/nicht für diese Anwendung/);
	});

	it("lehnt leere Client-ID ab (Fehlkonfiguration)", () => {
		expect(() => checkIdTokenClaims(validClaims({ aud: "" }), { clientId: "", nowSeconds: NOW })).toThrow(
			AuthRejection,
		);
	});

	it("lehnt fremden Issuer ab", () => {
		expect(check(validClaims({ iss: "https://evil.example" }))).toThrow(/nicht von Google/);
	});

	it("lehnt abgelaufenes Token ab", () => {
		expect(check(validClaims({ exp: NOW - 3600 }))).toThrow(/abgelaufen/);
	});

	it("lehnt Token aus der Zukunft ab", () => {
		expect(check(validClaims({ iat: NOW + 3600 }))).toThrow(/noch nicht gültig/);
	});

	it("lehnt Token ohne E-Mail ab", () => {
		const claims = validClaims();
		delete claims.email;
		expect(check(claims)).toThrow(/keine E-Mail/);
	});

	it("lehnt kaputte Claims ab", () => {
		expect(check({ foo: "bar" })).toThrow(AuthRejection);
	});
});

describe("3a – Signaturprüfung", () => {
	it("akzeptiert korrekt signiertes Token", async () => {
		const { jwksFetch, sign } = await createSigner();
		const identity = await verifyGoogleIdToken(await sign(validClaims()), {
			clientId: CLIENT_ID,
			fetchFn: jwksFetch,
			nowSeconds: NOW,
		});
		expect(identity.email).toBe("florian.brimmers@kromeichpartner.de");
	});

	it("lehnt manipulierte Claims ab (hd nachträglich gesetzt)", async () => {
		const { jwksFetch, sign } = await createSigner();
		const privateClaims = validClaims({ email: "irgendwer@gmail.com" });
		delete privateClaims.hd;
		const [header, , signature] = (await sign(privateClaims)).split(".");
		const forged = btoa(JSON.stringify(validClaims({ email: "irgendwer@gmail.com" })))
			.replace(/\+/g, "-")
			.replace(/\//g, "_")
			.replace(/=+$/, "");
		await expect(
			verifyGoogleIdToken(`${header}.${forged}.${signature}`, {
				clientId: CLIENT_ID,
				fetchFn: jwksFetch,
				nowSeconds: NOW,
			}),
		).rejects.toThrow(/Signatur/);
	});

	it("lehnt Token eines fremden Schlüssels ab", async () => {
		const google = await createSigner("same-kid");
		const attacker = await createSigner("same-kid");
		await expect(
			verifyGoogleIdToken(await attacker.sign(validClaims()), {
				clientId: CLIENT_ID,
				fetchFn: google.jwksFetch,
				nowSeconds: NOW,
			}),
		).rejects.toThrow(/Signatur/);
	});

	it("lehnt alg=none und unbekannte kid ab", async () => {
		const { jwksFetch, sign } = await createSigner();
		const options = { clientId: CLIENT_ID, fetchFn: jwksFetch, nowSeconds: NOW };
		await expect(verifyGoogleIdToken(await sign(validClaims(), { alg: "none" }), options)).rejects.toThrow(
			AuthRejection,
		);
		await expect(verifyGoogleIdToken(await sign(validClaims(), { kid: "unbekannt" }), options)).rejects.toThrow(
			/unbekannt/,
		);
	});

	it("lehnt Nicht-JWTs ab", async () => {
		const { jwksFetch } = await createSigner();
		await expect(
			verifyGoogleIdToken("kein.jwt", { clientId: CLIENT_ID, fetchFn: jwksFetch, nowSeconds: NOW }),
		).rejects.toThrow(AuthRejection);
	});
});
