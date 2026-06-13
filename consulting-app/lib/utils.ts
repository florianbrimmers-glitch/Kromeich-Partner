export function formatDate(date: Date | string | null | undefined): string {
  if (!date) return "—";
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function formatDateTime(date: Date | string | null | undefined): string {
  if (!date) return "—";
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function classNames(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export const STATUS_LABELS: Record<string, string> = {
  TODO: "Offen",
  IN_PROGRESS: "In Arbeit",
  REVIEW: "Review",
  DONE: "Erledigt",
  ACTIVE: "Aktiv",
  ON_HOLD: "Pausiert",
  COMPLETED: "Abgeschlossen",
  ARCHIVED: "Archiviert",
};

export const PRIORITY_LABELS: Record<string, string> = {
  LOW: "Niedrig",
  MEDIUM: "Mittel",
  HIGH: "Hoch",
  URGENT: "Dringend",
};

// Reihenfolge bestimmt die Sortierung der Sektionen auf der Objektseite.
export const TASK_CATEGORY_ORDER = [
  "LEASE_ANALYSIS",
  "DEADLINE",
  "MAINTENANCE",
  "DEFECT",
  "NKA",
  "AMENDMENT",
  "REPORTING",
  "HANDOVER",
  "CORRESPONDENCE",
  "GENERIC",
] as const;

export const TASK_CATEGORY_LABELS: Record<string, string> = {
  LEASE_ANALYSIS: "Mietvertraganalyse",
  MAINTENANCE: "Wartung",
  DEADLINE: "Fristen & Termine",
  DEFECT: "Mängel & Schäden",
  NKA: "Nebenkostenabrechnung",
  AMENDMENT: "Nachträge",
  REPORTING: "Reporting",
  HANDOVER: "Übergabe",
  CORRESPONDENCE: "Schriftwechsel",
  GENERIC: "Allgemein",
};

export const TASK_CATEGORY_SHORT: Record<string, string> = {
  LEASE_ANALYSIS: "MV",
  MAINTENANCE: "Wartung",
  DEADLINE: "Frist",
  DEFECT: "Mangel",
  NKA: "NKA",
  AMENDMENT: "Nachtrag",
  REPORTING: "Reporting",
  HANDOVER: "Übergabe",
  CORRESPONDENCE: "Mail",
  GENERIC: "Allgemein",
};

// Tailwind-Klassen für den farbigen Kategorie-Chip auf Aufgaben.
export const TASK_CATEGORY_BADGE: Record<string, string> = {
  LEASE_ANALYSIS: "bg-violet-100 text-violet-800",
  MAINTENANCE: "bg-amber-100 text-amber-800",
  DEADLINE: "bg-rose-100 text-rose-800",
  DEFECT: "bg-orange-100 text-orange-800",
  NKA: "bg-emerald-100 text-emerald-800",
  AMENDMENT: "bg-sky-100 text-sky-800",
  REPORTING: "bg-indigo-100 text-indigo-800",
  HANDOVER: "bg-teal-100 text-teal-800",
  CORRESPONDENCE: "bg-slate-100 text-slate-700",
  GENERIC: "bg-slate-100 text-slate-700",
};
