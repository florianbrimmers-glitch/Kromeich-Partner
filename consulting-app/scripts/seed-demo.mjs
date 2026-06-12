// Demo-Daten zum Ausprobieren: Mandanten, Projekte, Aufgaben, Notizen
// und eine gefüllte Inbox — ohne dass ein echtes Postfach nötig ist.
//
//   node scripts/seed-demo.mjs          # Daten anlegen (idempotent)
//   node scripts/seed-demo.mjs --reset  # Demo-Daten vorher löschen
//
// Voraussetzung: Postgres läuft (docker compose up -d) und `npm run db:push`.

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const DEMO_TAG = "[DEMO]";

const daysAgo = (n, h = 10, min = 0) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  d.setHours(h, min, 0, 0);
  return d;
};

async function reset() {
  await prisma.emailAccount.deleteMany({ where: { label: { startsWith: DEMO_TAG } } });
  await prisma.client.deleteMany({ where: { notes: DEMO_TAG } });
  console.log("Demo-Daten gelöscht.");
}

async function seed() {
  const existing = await prisma.emailAccount.findFirst({
    where: { label: { startsWith: DEMO_TAG } },
  });
  if (existing) {
    console.log("Demo-Daten existieren bereits. Mit --reset neu anlegen.");
    return;
  }

  // --- Mandanten + Projekte ---
  const mueller = await prisma.client.create({
    data: {
      name: "Dr. Andreas Müller",
      company: "Müller Immobilien GmbH",
      email: "mueller@mueller-immo.example",
      phone: "+49 69 111111",
      notes: DEMO_TAG,
    },
  });
  const schneider = await prisma.client.create({
    data: {
      name: "Christian Schneider",
      company: "Schneider Holding AG",
      email: "c.schneider@schneider-h.example",
      notes: DEMO_TAG,
    },
  });
  const weber = await prisma.client.create({
    data: {
      name: "Familie Weber",
      company: "Weber & Söhne KG",
      email: "kontakt@weber-soehne.example",
      notes: DEMO_TAG,
    },
  });

  const westend = await prisma.project.create({
    data: {
      clientId: mueller.id,
      name: "Bewertung Bürogebäude Westend",
      description: "Verkehrswertgutachten für das Bürogebäude Westendstraße 12.",
      deadline: daysAgo(-18),
    },
  });
  const strategie = await prisma.project.create({
    data: {
      clientId: schneider.id,
      name: "Strategieprojekt 2026",
      description: "Marktanalyse und strategische Neuausrichtung.",
      deadline: daysAgo(-45),
    },
  });
  await prisma.project.create({
    data: {
      clientId: weber.id,
      name: "Nachfolgeberatung",
      status: "ON_HOLD",
    },
  });

  // --- Aufgaben ---
  await prisma.task.createMany({
    data: [
      { projectId: westend.id, title: "Bewertungsgutachten finalisieren", status: "IN_PROGRESS", priority: "URGENT", dueDate: daysAgo(0) },
      { projectId: westend.id, title: "Marktdaten Westend Q2 einarbeiten", status: "REVIEW", priority: "HIGH", dueDate: daysAgo(-4) },
      { projectId: westend.id, title: "Termin Besichtigung abstimmen", status: "TODO", priority: "MEDIUM", dueDate: daysAgo(-8) },
      { projectId: westend.id, title: "Vergleichsmieten recherchieren", status: "DONE", priority: "MEDIUM" },
      { projectId: strategie.id, title: "Marktanalyse Q2 vorbereiten", status: "IN_PROGRESS", priority: "HIGH", dueDate: daysAgo(-2) },
      { projectId: strategie.id, title: "Workshop-Termin mit Vorstand", status: "TODO", priority: "MEDIUM" },
    ],
  });

  // --- Notiz (braucht einen Autor: erster Team-User, sonst überspringen) ---
  const author = await prisma.user.findFirst({
    where: { role: { in: ["TEAM_ADMIN", "TEAM_MEMBER"] } },
  });
  if (author) {
    await prisma.note.create({
      data: {
        projectId: westend.id,
        authorId: author.id,
        title: "Kickoff-Protokoll 02.06.",
        content:
          "## Besprochen\n\n- Bewertungsstichtag **01.06.2026**\n- Liquidationswert separat ausweisen\n- Gutachten bis Ende Juni\n\n## Offene Punkte\n\n- Mietverträge OG 3 fehlen noch",
      },
    });
  }

  // --- E-Mail-Konto (Demo) + Inbox-Threads ---
  const account = await prisma.emailAccount.create({
    data: {
      label: `${DEMO_TAG} Team-Inbox`,
      email: "info@kromeichpartner.example",
      username: "info@kromeichpartner.example",
      password: "demo",
      imapHost: "demo.invalid",
      smtpHost: "localhost", // Mailpit: Antworten landen unter localhost:8025
      smtpPort: 1025,
      smtpSecure: false,
      lastSyncAt: new Date(),
    },
  });

  // Thread 1: Gutachten Westend (zugeordnet, mehrere Nachrichten)
  const t1 = await prisma.emailThread.create({
    data: {
      accountId: account.id,
      projectId: westend.id,
      subject: "Gutachten Westend",
      normalizedSubject: "gutachten westend",
      unread: true,
      lastMessageAt: daysAgo(0, 10, 14),
    },
  });
  await prisma.emailMessage.createMany({
    data: [
      {
        threadId: t1.id,
        accountId: account.id,
        direction: "OUT",
        messageId: "<demo-1a@kromeich>",
        fromAddr: "info@kromeichpartner.example",
        toAddr: "Dr. Müller <mueller@mueller-immo.example>",
        subject: "Gutachten Westend",
        textBody:
          "Sehr geehrter Herr Dr. Müller,\n\nanbei wie besprochen der aktuelle Entwurf des Verkehrswertgutachtens. Über Ihre Rückmeldung bis Ende der Woche würden wir uns freuen.\n\nMit besten Grüßen\nFlorian Brimmers",
        sentAt: daysAgo(3, 16, 42),
      },
      {
        threadId: t1.id,
        accountId: account.id,
        direction: "IN",
        messageId: "<demo-1b@mueller>",
        inReplyTo: "<demo-1a@kromeich>",
        fromAddr: "Dr. Müller <mueller@mueller-immo.example>",
        toAddr: "info@kromeichpartner.example",
        subject: "Re: Gutachten Westend",
        textBody:
          "Hallo Herr Brimmers,\n\nvielen Dank für die Übersendung. Ich schaue mir das heute Abend an.\n\nEine kurze Rückfrage zu Seite 12: Sie schreiben dort von einem Liquidationswert von 2,3 Mio. €. Beziehen Sie sich auf das Bewertungsdatum 01.06. oder bereits auf den prognostizierten Wert zum 31.12.2026?\n\nBeste Grüße\nDr. Müller",
        sentAt: daysAgo(0, 10, 14),
      },
    ],
  });

  // Thread 2: Notar-Bestätigung (nicht zugeordnet, ungelesen)
  const t2 = await prisma.emailThread.create({
    data: {
      accountId: account.id,
      subject: "Beurkundungstermin 24.06. bestätigt",
      normalizedSubject: "beurkundungstermin 24.06. bestätigt",
      unread: true,
      lastMessageAt: daysAgo(0, 9, 48),
    },
  });
  await prisma.emailMessage.create({
    data: {
      threadId: t2.id,
      accountId: account.id,
      direction: "IN",
      messageId: "<demo-2a@notar>",
      fromAddr: "Notariat Köhler <termine@notar-koehler.example>",
      toAddr: "info@kromeichpartner.example",
      subject: "Beurkundungstermin 24.06. bestätigt",
      textBody:
        "Sehr geehrte Damen und Herren,\n\nhiermit bestätigen wir den Termin zur Beurkundung am 24.06.2026 um 14:00 Uhr in unseren Geschäftsräumen.\n\nBitte bringen Sie die im Vorfeld übersandten Unterlagen im Original mit.\n\nMit freundlichen Grüßen\nNotariat Köhler",
      sentAt: daysAgo(0, 9, 48),
    },
  });

  // Thread 3: Schneider Korrekturen (gelesen, zugeordnet)
  const t3 = await prisma.emailThread.create({
    data: {
      accountId: account.id,
      projectId: strategie.id,
      subject: "Marktanalyse Q2 — Korrekturen",
      normalizedSubject: "marktanalyse q2 — korrekturen",
      unread: false,
      lastMessageAt: daysAgo(2, 11, 5),
    },
  });
  await prisma.emailMessage.create({
    data: {
      threadId: t3.id,
      accountId: account.id,
      direction: "IN",
      messageId: "<demo-3a@schneider>",
      fromAddr: "Christian Schneider <c.schneider@schneider-h.example>",
      toAddr: "info@kromeichpartner.example",
      subject: "Marktanalyse Q2 — Korrekturen",
      textBody:
        "Hallo zusammen,\n\nim Anhang die kommentierte Fassung mit kleinen Korrekturen. Insgesamt sind wir sehr zufrieden mit der Richtung.\n\nKönnen wir Donnerstag um 14 Uhr kurz telefonieren?\n\nViele Grüße\nChristian Schneider",
      sentAt: daysAgo(2, 11, 5),
    },
  });

  console.log("Demo-Daten angelegt:");
  console.log("  3 Mandanten, 3 Projekte, 6 Aufgaben" + (author ? ", 1 Notiz" : " (Notiz übersprungen: noch kein Team-User — erst einloggen)"));
  console.log("  1 Demo-E-Mail-Konto, 3 Inbox-Threads (2 ungelesen)");
  console.log("");
  console.log("Hinweis: Antworten aus der Inbox gehen an Mailpit (localhost:8025).");
  console.log("Der IMAP-Sync des Demo-Kontos schlägt bewusst fehl (demo.invalid) —");
  console.log("echtes Postfach unter Einstellungen verbinden.");
}

const wantReset = process.argv.includes("--reset");
try {
  if (wantReset) await reset();
  await seed();
} finally {
  await prisma.$disconnect();
}
