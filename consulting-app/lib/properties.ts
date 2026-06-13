import { prisma } from "@/lib/prisma";

// Standardthemen, die beim Anlegen eines neuen Objekts automatisch entstehen,
// wenn der User die Vorlage übernimmt. Spiegeln den typischen Setup-Flow:
// MV-Analyse zuerst (liefert Fristen + Wartungspflichten),
// dann die parallelen Sammelaufgaben.
const DEFAULT_TASKS = [
  {
    title: "Mietvertraganalyse",
    category: "LEASE_ANALYSIS" as const,
    priority: "HIGH" as const,
    description:
      "Rechte, Pflichten und Fristen aus dem MV extrahieren. Ergebnis fließt in Fristen- und Wartungskalender.",
  },
  {
    title: "Wartungskalender aufbauen",
    category: "MAINTENANCE" as const,
    priority: "MEDIUM" as const,
    description:
      "Alle wartungspflichtigen Gewerke erfassen (Brandschutz, Tore, Elektro, Lüftung, …) mit Intervall und letzter/nächster Prüfung.",
  },
  {
    title: "Fristen & Termine",
    category: "DEADLINE" as const,
    priority: "MEDIUM" as const,
    description:
      "Sammelaufgabe für alle Fristen aus MV: Optionsausübung, Staffel, NK-Einspruch, Reporting.",
  },
  {
    title: "Mängel & Schäden",
    category: "DEFECT" as const,
    priority: "MEDIUM" as const,
    description: "Laufende Liste von Mängeln, Schäden und offenen Tickets.",
  },
  {
    title: "NK-Abrechnung prüfen",
    category: "NKA" as const,
    priority: "MEDIUM" as const,
    description: "Jährliche Prüfung der Nebenkostenabrechnung des Vermieters.",
  },
  {
    title: "Übergabe vorbereiten",
    category: "HANDOVER" as const,
    priority: "HIGH" as const,
    description: "Übergabe-Checkliste, Protokoll, Mängelaufnahme vor Ort.",
  },
];

export async function createPropertyWithDefaults(input: {
  clientId: string;
  name: string;
  address?: string | null;
  city?: string | null;
  postalCode?: string | null;
  description?: string | null;
  applyTemplate?: boolean;
}) {
  const property = await prisma.property.create({
    data: {
      clientId: input.clientId,
      name: input.name,
      address: input.address ?? null,
      city: input.city ?? null,
      postalCode: input.postalCode ?? null,
      description: input.description ?? null,
    },
  });

  if (input.applyTemplate) {
    await prisma.task.createMany({
      data: DEFAULT_TASKS.map((t) => ({
        ...t,
        propertyId: property.id,
        status: "TODO" as const,
      })),
    });
    // Leeren Mietvertrag-Stub anlegen, damit das Detail-Panel sofort
    // bearbeitbar ist (statt "noch nichts da").
    await prisma.lease.create({
      data: { propertyId: property.id, analysisStatus: "PENDING" },
    });
  }

  return property;
}
