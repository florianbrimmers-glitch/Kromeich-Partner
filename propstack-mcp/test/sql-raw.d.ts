// Vitest/Vite: Dateiinhalt als Text einbinden (für die Migration im SQL-Test).
declare module "*.sql?raw" {
	const sql: string;
	export default sql;
}
