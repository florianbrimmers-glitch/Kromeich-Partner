import { prisma } from "@/lib/prisma";

/** Entfernt Re:/Fwd:/AW:/WG:-Präfixe für die Thread-Zuordnung über den Betreff. */
export function normalizeSubject(subject: string): string {
  let s = subject.trim();
  const prefix = /^(re|fwd?|aw|wg|antw)\s*(\[\d+\])?\s*:\s*/i;
  while (prefix.test(s)) {
    s = s.replace(prefix, "").trim();
  }
  return s.toLowerCase();
}

/** Extrahiert die reine Adresse aus "Name <mail@host.de>". */
export function extractAddress(raw: string): string {
  const match = raw.match(/<([^>]+)>/);
  return (match ? match[1] : raw).trim().toLowerCase();
}

/**
 * Findet den passenden Thread für eine eingehende Mail:
 * 1. über In-Reply-To/References (zuverlässig)
 * 2. Fallback: gleicher normalisierter Betreff im selben Konto
 */
export async function findThreadFor(
  accountId: string,
  inReplyTo: string | null,
  references: string[],
  normalizedSubject: string
): Promise<string | null> {
  const refIds = [inReplyTo, ...references].filter(Boolean) as string[];
  if (refIds.length > 0) {
    const referenced = await prisma.emailMessage.findFirst({
      where: { accountId, messageId: { in: refIds } },
      select: { threadId: true },
    });
    if (referenced) return referenced.threadId;
  }

  if (normalizedSubject) {
    const bySubject = await prisma.emailThread.findFirst({
      where: { accountId, normalizedSubject },
      orderBy: { lastMessageAt: "desc" },
      select: { id: true },
    });
    if (bySubject) return bySubject.id;
  }

  return null;
}

/**
 * Komfort-Feature: Mail von bekannter Mandanten-Adresse → automatisch dem
 * Objekt dieses Mandanten zuordnen, das zuletzt aktualisiert wurde.
 * Wenn der Mandant mehrere Objekte hat, ist das nur ein Vorschlag — der User
 * kann im Thread-Detail auf das richtige Objekt umstellen.
 */
export async function guessPropertyFor(fromAddr: string): Promise<string | null> {
  const address = extractAddress(fromAddr);
  if (!address) return null;

  const client = await prisma.client.findFirst({
    where: { email: { equals: address, mode: "insensitive" } },
    select: {
      properties: {
        where: { archivedAt: null },
        orderBy: { updatedAt: "desc" },
        take: 1,
        select: { id: true },
      },
    },
  });

  return client?.properties[0]?.id ?? null;
}
