// Zeitrechnung für das Dashboard – genau so, wie der bisherige Python-Export sie macht
// (weekly_report/dashboard_export.py): Berliner Wanduhrzeit, ISO-Kalenderwochen und die
// Schreibweise von datetime.isoformat(). Das Dashboard-HTML bleibt unverändert, deshalb
// müssen Wochenschlüssel und Zeitstempel bis aufs Zeichen passen.

const BERLIN = "Europe/Berlin";

const wanduhrFormat = new Intl.DateTimeFormat("en-CA", {
	day: "2-digit",
	hour: "2-digit",
	hourCycle: "h23",
	minute: "2-digit",
	month: "2-digit",
	second: "2-digit",
	timeZone: BERLIN,
	year: "numeric",
});

export interface Wanduhr {
	jahr: number;
	monat: number;
	tag: number;
	stunde: number;
	minute: number;
	sekunde: number;
}

/** Ein Zeitpunkt in Berliner Zeit: Millisekunden seit 1970 und die Schreibweise von Pythons isoformat(). */
export interface BerlinZeit {
	ms: number;
	iso: string;
}

const zwei = (zahl: number) => String(zahl).padStart(2, "0");

/** Berliner Wanduhrzeit eines Zeitpunkts. */
export function berlinWanduhr(ms: number): Wanduhr {
	const teile: Record<string, number> = {};
	for (const teil of wanduhrFormat.formatToParts(new Date(ms))) {
		if (teil.type !== "literal") teile[teil.type] = Number(teil.value);
	}
	return { jahr: teile.year, minute: teile.minute, monat: teile.month, sekunde: teile.second, stunde: teile.hour, tag: teile.day };
}

/** UTC-Versatz Berlins zu diesem Zeitpunkt in Minuten (+60 im Winter, +120 im Sommer). */
export function berlinVersatzMinuten(ms: number): number {
	const w = berlinWanduhr(ms);
	const alsUtc = Date.UTC(w.jahr, w.monat - 1, w.tag, w.stunde, w.minute, w.sekunde);
	return Math.round((alsUtc - Math.floor(ms / 1000) * 1000) / 60_000);
}

function versatzText(minuten: number): string {
	const betrag = Math.abs(minuten);
	return `${minuten < 0 ? "-" : "+"}${zwei(Math.floor(betrag / 60))}:${zwei(betrag % 60)}`;
}

/** Wie datetime.isoformat(): Sekundenbruchteile nur, wenn sie nicht null sind – dann sechsstellig. */
function isoText(w: Wanduhr, millisekunden: number, versatzMinuten: number): string {
	const bruch = millisekunden ? `.${String(millisekunden).padStart(3, "0")}000` : "";
	return `${w.jahr}-${zwei(w.monat)}-${zwei(w.tag)}T${zwei(w.stunde)}:${zwei(w.minute)}:${zwei(w.sekunde)}${bruch}${versatzText(versatzMinuten)}`;
}

/** Zeitpunkt als Berliner Zeit (entspricht datetime.now(ZoneInfo("Europe/Berlin")) bzw. astimezone). */
export function berlinZeit(ms: number): BerlinZeit {
	return { iso: isoText(berlinWanduhr(ms), ((ms % 1000) + 1000) % 1000, berlinVersatzMinuten(ms)), ms };
}

/**
 * Berliner Wanduhrzeit → Zeitpunkt, wie Python sie auflöst (fold=0): Gibt es die Uhrzeit zweimal
 * (Ende der Sommerzeit), gilt das erste Mal; gibt es sie gar nicht (Beginn der Sommerzeit), gilt der
 * Versatz von vorher.
 */
function wanduhrZuMs(w: Wanduhr, millisekunden: number): { ms: number; versatz: number } {
	const alsUtc = Date.UTC(w.jahr, w.monat - 1, w.tag, w.stunde, w.minute, w.sekunde, millisekunden);
	const davor = berlinVersatzMinuten(alsUtc - 3 * 3_600_000);
	const danach = berlinVersatzMinuten(alsUtc + 3 * 3_600_000);
	// größerer Versatz zuerst = früherer Zeitpunkt
	for (const versatz of [...new Set([davor, danach])].sort((a, b) => b - a)) {
		const ms = alsUtc - versatz * 60_000;
		if (berlinVersatzMinuten(ms) === versatz) return { ms, versatz };
	}
	return { ms: alsUtc - davor * 60_000, versatz: davor };
}

/**
 * Zeitpunkt minus ganze Tage in Berliner Wanduhrzeit – wie `until - timedelta(days=tage)` auf einem
 * datetime mit ZoneInfo: gleiche Uhrzeit, anderer Kalendertag, Versatz des Zieltags. Über einen
 * Zeitumstellungstag hinweg sind das nicht genau tage × 24 Stunden.
 */
export function minusTage(zeit: BerlinZeit, tage: number): BerlinZeit {
	const w = berlinWanduhr(zeit.ms);
	const ziel = new Date(Date.UTC(w.jahr, w.monat - 1, w.tag - tage));
	const wanduhr: Wanduhr = { ...w, jahr: ziel.getUTCFullYear(), monat: ziel.getUTCMonth() + 1, tag: ziel.getUTCDate() };
	const millisekunden = ((zeit.ms % 1000) + 1000) % 1000;
	const { ms, versatz } = wanduhrZuMs(wanduhr, millisekunden);
	return { iso: isoText(wanduhr, millisekunden, versatz), ms };
}

/** Berliner Kalendertag eines Zeitpunkts, verschoben um ganze Tage, als JJJJ-MM-TT (für created_at_from/to). */
export function berlinTag(zeit: BerlinZeit, verschiebungTage = 0): string {
	const w = berlinWanduhr(zeit.ms);
	const ziel = new Date(Date.UTC(w.jahr, w.monat - 1, w.tag + verschiebungTage));
	return `${ziel.getUTCFullYear()}-${zwei(ziel.getUTCMonth() + 1)}-${zwei(ziel.getUTCDate())}`;
}

/** Propstack-Zeitstempel ("2026-08-19T11:29:56.983+02:00") als Millisekunden; NaN, wenn nicht lesbar. */
export function zeitMs(iso: string): number {
	return Date.parse(iso);
}

const ISO_MUSTER = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?(Z|[+-]\d{2}(?::?\d{2})?)?$/;

/**
 * Schreibweise von `datetime.fromisoformat(text).isoformat()`: Propstack liefert drei Nachkommastellen
 * (".983"), Python schreibt sechs (".983000") und lässt sie weg, wenn sie null sind. So steht
 * `erste_einheit` im bisherigen Export. Nicht lesbare Texte bleiben unverändert.
 */
export function pythonIsoformat(iso: string): string {
	const treffer = ISO_MUSTER.exec(iso.trim());
	if (!treffer) return iso;
	const [, tag, stunde, minute, sekunde = "00", bruchRoh = "", zoneRoh = ""] = treffer;
	const bruch = bruchRoh.slice(0, 6).padEnd(6, "0");
	let zone = zoneRoh;
	if (zone === "Z") zone = "+00:00";
	else if (/^[+-]\d{4}$/.test(zone)) zone = `${zone.slice(0, 3)}:${zone.slice(3)}`;
	else if (/^[+-]\d{2}$/.test(zone)) zone = `${zone}:00`;
	return `${tag}T${stunde}:${minute}:${sekunde}${/[1-9]/.test(bruch) ? `.${bruch}` : ""}${zone}`;
}

/**
 * ISO-Kalenderwoche in Berliner Zeit als Dokument-ID, z. B. "2026-KW39".
 * Muss mit keyVon() im Dashboard übereinstimmen, sonst landet eine Einheit vom Sonntagabend in einer
 * anderen Woche als die, unter der das Dashboard sie zählt.
 */
export function wochenSchluessel(ms: number): string {
	const w = berlinWanduhr(ms);
	const tag = new Date(Date.UTC(w.jahr, w.monat - 1, w.tag));
	const wochentag = tag.getUTCDay() || 7; // Montag = 1 … Sonntag = 7
	tag.setUTCDate(tag.getUTCDate() + 4 - wochentag); // Donnerstag derselben ISO-Woche bestimmt das Jahr
	const jahr = tag.getUTCFullYear();
	const woche = Math.ceil(((tag.getTime() - Date.UTC(jahr, 0, 1)) / 86_400_000 + 1) / 7);
	return `${jahr}-KW${zwei(woche)}`;
}
