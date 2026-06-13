// Demo-Daten zum Ausprobieren: Mandanten, Objekte, Aufgaben (typisiert),
// Mietverträge, Notizen und eine gefüllte Inbox.
// Vorlage: anonymisierte Beispiele basierend auf der Realstruktur des
// Consulting-Bereichs (Mandant -> Objekt -> Themen-Aufgaben).
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
const monthsFromNow = (m, h = 10) => {
  const d = new Date();
  d.setMonth(d.getMonth() + m);
  d.setHours(h, 0, 0, 0);
  return d;
};

async function reset() {
  await prisma.emailAccount.deleteMany({ where: { label: { startsWith: DEMO_TAG } } });
  await prisma.client.deleteMany({ where: { notes: DEMO_TAG } });
  console.log("Demo-Daten gelöscht.");
}

// Vorlage für die Standard-Themen, die jedes Objekt bekommt.
// `metadata` bleibt leer und wird je nach Bedarf später gefüllt.
function defaultTaskSetup(propertyId, { handoverInMonths = null } = {}) {
  return [
    {
      propertyId,
      title: "Mietvertraganalyse",
      category: "LEASE_ANALYSIS",
      status: "TODO",
      priority: "HIGH",
      description:
        "Rechte, Pflichten und Fristen aus dem MV extrahieren. Ergebnis fließt in Fristen- und Wartungskalender.",
    },
    {
      propertyId,
      title: "Wartungskalender aufbauen",
      category: "MAINTENANCE",
      status: "TODO",
      priority: "MEDIUM",
      description:
        "Alle wartungspflichtigen Gewerke erfassen (Brandschutz, Tore, Elektro, Lüftung, …) mit Intervall und letzter/nächster Prüfung.",
    },
    {
      propertyId,
      title: "Fristen & Termine",
      category: "DEADLINE",
      status: "TODO",
      priority: "MEDIUM",
      description:
        "Sammelaufgabe für alle Fristen aus MV: Optionsausübung, Staffel, NK-Einspruch, Reporting.",
    },
    {
      propertyId,
      title: "Mängel & Schäden",
      category: "DEFECT",
      status: "TODO",
      priority: "MEDIUM",
      description: "Laufende Liste von Mängeln, Schäden und offenen Tickets.",
    },
    {
      propertyId,
      title: "NK-Abrechnung prüfen",
      category: "NKA",
      status: "TODO",
      priority: "MEDIUM",
      metadata: { period: `${new Date().getFullYear() - 1}` },
      description: "Jährliche Prüfung der Nebenkostenabrechnung des Vermieters.",
    },
    handoverInMonths !== null
      ? {
          propertyId,
          title: "Übergabe vorbereiten",
          category: "HANDOVER",
          status: "TODO",
          priority: "HIGH",
          dueDate: monthsFromNow(handoverInMonths),
          metadata: { handoverDate: monthsFromNow(handoverInMonths).toISOString() },
          description: "Übergabe-Checkliste, Protokoll, Mängelaufnahme vor Ort.",
        }
      : null,
  ].filter(Boolean);
}

async function seed() {
  const existing = await prisma.client.findFirst({ where: { notes: DEMO_TAG } });
  if (existing) {
    console.log("Demo-Daten existieren bereits. Mit --reset neu anlegen.");
    return;
  }

  // ============================================================
  // Mandant 1: IMC PRO LOGISTICS — drei Objekte in NRW
  // ============================================================
  const imc = await prisma.client.create({
    data: {
      name: "Yuti Vahidi",
      company: "IMC PRO LOGISTICS GmbH",
      email: "yuti.vahidi@imc-prologistics.example",
      phone: "+49 2161 555 0100",
      notes: DEMO_TAG,
    },
  });

  const dieselstr = await prisma.property.create({
    data: {
      clientId: imc.id,
      name: "Dieselstraße 72-90",
      address: "Dieselstraße 72-90",
      city: "Mönchengladbach",
      postalCode: "41238",
      description:
        "Logistikobjekt mit mehreren Hallen (1-4 + FF). Eigentümerseite: Arrow/Palmira, Verwaltung Evers/FMI.",
    },
  });
  await prisma.lease.create({
    data: {
      propertyId: dieselstr.id,
      landlord: "Arrow / Palmira",
      tenant: "IMC PRO LOGISTICS GmbH",
      startDate: daysAgo(180),
      hasOption: true,
      optionDetails: "Optionsausübung 12 Monate vor Vertragsende",
      indexClause: "Staffel ab 01.06., jährlich",
      monthlyRent: 27870.5,
      analysisStatus: "IN_PROGRESS",
    },
  });
  await prisma.task.createMany({
    data: [
      ...defaultTaskSetup(dieselstr.id).map((t, i) =>
        i === 0 ? { ...t, status: "IN_PROGRESS" } : t,
      ),
      {
        propertyId: dieselstr.id,
        title: "Anmeldung Strom",
        category: "GENERIC",
        status: "IN_PROGRESS",
        priority: "HIGH",
        description:
          "Hauptzähler bei Übergabe nicht eindeutig zuordenbar. §5.1e MV: Mieter schließt Versorgungsvertrag selbst ab. Westbridge & LÖWE angefragt.",
      },
      {
        propertyId: dieselstr.id,
        title: "Brandschutzbeauftragter",
        category: "GENERIC",
        status: "IN_PROGRESS",
        priority: "MEDIUM",
        description:
          "Angebotsvergleich Feuerschutz Plus / Safety Performance / Hamacher liegt vor — Entscheidung bei IMC.",
      },
      {
        propertyId: dieselstr.id,
        title: "Mietanpassung 05/26 — Korrektur",
        category: "AMENDMENT",
        status: "DONE",
        priority: "HIGH",
        description:
          "Rechnerisch falscher Tag im Vermieter-Schreiben. 17 vs. 16 Tage; Differenz 95,87 EUR zugunsten Mieter. Mit Juni verrechnet.",
        metadata: { version: "2026-05" },
      },
      {
        propertyId: dieselstr.id,
        title: "Außenwerbung installieren",
        category: "GENERIC",
        status: "TODO",
        priority: "LOW",
        description:
          "IMC-Logo an Fassade. Mecit-Angebot 1.800 € (Zusage IMC). Installation nach Unterzeichnung Nachtrag.",
      },
      {
        propertyId: dieselstr.id,
        title: "Wassertest auf Bakterien",
        category: "DEADLINE",
        status: "TODO",
        priority: "MEDIUM",
        dueDate: monthsFromNow(1),
        metadata: { source: "Vormieter-Unterlagen (April 2026 geplant)" },
        description: "Bei Höfels nachfragen ob nur Protokoll fehlt oder Prüfung gar nicht erfolgt ist.",
      },
    ],
  });

  const hamburgring = await prisma.property.create({
    data: {
      clientId: imc.id,
      name: "Hamburgring 30",
      address: "Hamburgring 30",
      city: "Mönchengladbach",
      postalCode: "41179",
      description:
        "Lager+Bürofläche. Eigentümer: HIH. Mietverhältnis seit 10/2021. Optionsausübung Ende 2025 erfolgt (5 Jahre + 2 Monate mietfrei + Nachhaltigkeitsklauseln).",
    },
  });
  await prisma.lease.create({
    data: {
      propertyId: hamburgring.id,
      landlord: "HIH Real Estate",
      tenant: "IMC PRO LOGISTICS GmbH",
      signedAt: new Date("2021-10-27"),
      startDate: new Date("2021-12-15"),
      hasOption: true,
      optionDetails: "Option +5 Jahre + 2 Monate mietfrei ausgeübt",
      indexClause: "Indexierung an VPI",
      analysisStatus: "COMPLETED",
    },
  });
  await prisma.task.createMany({
    data: [
      ...defaultTaskSetup(hamburgring.id).map((t) =>
        t.category === "LEASE_ANALYSIS"
          ? { ...t, status: "DONE", description: "Analyse 06/2026 finalisiert (alte + neue Vertragsversion)." }
          : t,
      ),
      {
        propertyId: hamburgring.id,
        title: "Ausschreibung FM-Dienstleister",
        category: "GENERIC",
        status: "IN_PROGRESS",
        priority: "MEDIUM",
        description: "FM künftig durch IMC statt HIH — neu ausgeschrieben.",
      },
      {
        propertyId: hamburgring.id,
        title: "Flucht- und Rettungspläne",
        category: "DEFECT",
        status: "TODO",
        priority: "HIGH",
        description: "Fehlen noch — bei Vermieter anfordern.",
        metadata: { location: "Hallen 1-4", severity: "high" },
      },
      {
        propertyId: hamburgring.id,
        title: "Fassadenreinigung",
        category: "GENERIC",
        status: "TODO",
        priority: "LOW",
      },
      {
        propertyId: hamburgring.id,
        title: "Strom & Gas Tarif optimieren",
        category: "GENERIC",
        status: "DONE",
        priority: "MEDIUM",
        description: "Über Westbridge Advisory (kostenfreier Energieeinkauf-Check).",
      },
    ],
  });

  const bergkamen = await prisma.property.create({
    data: {
      clientId: imc.id,
      name: "Industriestraße 16/16a",
      address: "Industriestraße 16/16a",
      city: "Bergkamen",
      postalCode: "59192",
      description:
        "Logistikobjekt mit Untermieter JF Global. Hausnummer geändert von 10 auf 16/16a. Verwaltung Apleona. Brandschutzbegehung erfolgt 15.04.",
    },
  });
  await prisma.lease.create({
    data: {
      propertyId: bergkamen.id,
      landlord: "Apleona / Eigentümer",
      tenant: "IMC PRO LOGISTICS GmbH",
      hasOption: false,
      analysisStatus: "PENDING",
    },
  });
  await prisma.task.createMany({
    data: [
      ...defaultTaskSetup(bergkamen.id),
      {
        propertyId: bergkamen.id,
        title: "Vertragsübernahme JF Global",
        category: "AMENDMENT",
        status: "IN_PROGRESS",
        priority: "HIGH",
        description: "JF soll Vertrag von IMC übernehmen — Freimeldung läuft.",
      },
      {
        propertyId: bergkamen.id,
        title: "Brandschutzbegehung 15.04 — Bericht",
        category: "DEADLINE",
        status: "IN_PROGRESS",
        priority: "MEDIUM",
        metadata: { source: "Begehung Apleona" },
        description: "Begehung hat stattgefunden, Bericht steht noch aus.",
      },
      {
        propertyId: bergkamen.id,
        title: "Videoüberwachung — Demontage prüfen",
        category: "DEFECT",
        status: "TODO",
        priority: "LOW",
        description:
          "Vom Vormieter hinterlassen, nur Festplatte installiert. Falls Raum nicht als Überwachungsraum nutzbar, Monitor demontieren.",
      },
      {
        propertyId: bergkamen.id,
        title: "Seitenwände Durchgang Hallen — Entscheidung",
        category: "DEFECT",
        status: "TODO",
        priority: "MEDIUM",
        description: "Sollen ersatzlos entfernt werden — Kältebrücke!",
      },
      {
        propertyId: bergkamen.id,
        title: "NKA 2024",
        category: "NKA",
        status: "IN_PROGRESS",
        priority: "MEDIUM",
        metadata: { period: "2024" },
        description: "Abrechnung prüfen — How-To-Vorlage + Hamburgring-Ordner als Referenz.",
      },
    ],
  });

  // ============================================================
  // Mandant 2: Patac — zwei Objekte
  // ============================================================
  const patac = await prisma.client.create({
    data: {
      name: "Frau Drepper",
      company: "Patac GmbH",
      email: "drepper@patac.example",
      notes: DEMO_TAG,
    },
  });

  const harkort = await prisma.property.create({
    data: {
      clientId: patac.id,
      name: "Harkortstraße 2-6",
      address: "Harkortstraße 2-6",
      city: "Ratingen",
      postalCode: "40878",
      description:
        "Auslaufendes Mietverhältnis. Schlussrechnung eingegangen — Gesamtaufstellung versenden, dann abgeschlossen. Vermieter: Mileway.",
    },
  });
  await prisma.lease.create({
    data: {
      propertyId: harkort.id,
      landlord: "Mileway",
      tenant: "Patac GmbH",
      endDate: daysAgo(-30),
      analysisStatus: "COMPLETED",
    },
  });
  await prisma.task.createMany({
    data: [
      {
        propertyId: harkort.id,
        title: "Durchbruch — BSK-konform verschließen",
        category: "DEFECT",
        status: "IN_PROGRESS",
        priority: "HIGH",
        description:
          "Patac hat zwischen Einheiten einen Durchbruch erstellt, nicht BSK-konform. Bei Mietende verschließen. Angebote 4 Seasons vorhanden — Wand evtl. als F90 anerkennbar.",
        metadata: { location: "Halle, zwischen Einheiten", severity: "high" },
      },
      {
        propertyId: harkort.id,
        title: "Rückgabe Kaution",
        category: "AMENDMENT",
        status: "IN_PROGRESS",
        priority: "MEDIUM",
        description:
          "Wu (Mileway) will Mietrückstand März aufrechnen. Aufrechnung 13.05 raus, am 26.05 erinnert.",
      },
      {
        propertyId: harkort.id,
        title: "Schlussrechnung — Gesamtaufstellung",
        category: "CORRESPONDENCE",
        status: "TODO",
        priority: "HIGH",
        dueDate: daysAgo(-7),
        description: "Schlussrechnung eingegangen, Gesamtaufstellung an Mandant und fertig.",
      },
    ],
  });

  const hamborner = await prisma.property.create({
    data: {
      clientId: patac.id,
      name: "Hamborner Straße 32",
      address: "Hamborner Straße 32",
      city: "Duisburg",
      postalCode: "47166",
      description:
        "Frisch übernommenes Mietverhältnis. Vermieter Garbe (PM Andre Kreutz), FM DBK Gebäudemanagement (OL Damian Dreimol).",
    },
  });
  await prisma.lease.create({
    data: {
      propertyId: hamborner.id,
      landlord: "Garbe",
      tenant: "Patac GmbH",
      startDate: daysAgo(60),
      analysisStatus: "IN_PROGRESS",
    },
  });
  await prisma.task.createMany({
    data: [
      ...defaultTaskSetup(hamborner.id).map((t) =>
        t.category === "LEASE_ANALYSIS" ? { ...t, status: "IN_PROGRESS" } : t,
      ),
      {
        propertyId: hamborner.id,
        title: "Reporting-Pflichten",
        category: "REPORTING",
        status: "TODO",
        priority: "MEDIUM",
        description: "Übersicht aller Melde-/Nachweispflichten aus dem MV erstellen.",
        metadata: { recipient: "Garbe / Vermieter", cadence: "quarterly" },
      },
      {
        propertyId: hamborner.id,
        title: "Internet anschließen",
        category: "GENERIC",
        status: "DONE",
        priority: "MEDIUM",
        description:
          "Glasfaser über Duisburg CityCom (K.Y. Müller, +49 203 604 1958, kundenservice@duisburgcity.com).",
      },
      {
        propertyId: hamborner.id,
        title: "Versicherung abschließen",
        category: "GENERIC",
        status: "DONE",
        priority: "HIGH",
      },
      {
        propertyId: hamborner.id,
        title: "Zusätzliche Staplerladesteckdosen",
        category: "DEFECT",
        status: "DONE",
        priority: "MEDIUM",
        description: "Patrick Garvert (02872/8076-16, p.garvert@garvert.de).",
      },
    ],
  });

  // ============================================================
  // Mandant 3: JF Global — ein Objekt
  // ============================================================
  const jfGlobal = await prisma.client.create({
    data: {
      name: "Herr Yang",
      company: "JF Global GmbH",
      email: "yang@jfglobal.example",
      notes: DEMO_TAG,
    },
  });

  const gelsenkirchen = await prisma.property.create({
    data: {
      clientId: jfGlobal.id,
      name: "Europastraße 5",
      address: "Europastraße 5",
      city: "Gelsenkirchen",
      postalCode: "45891",
      description:
        "Untermietverhältnis. Hauptmieter (Tech & Home Mate, Landport) hat Vertrag kopiert — fehlerhaft. Festlaufzeit bis 30.11.2028, Option +2 J.",
    },
  });
  await prisma.lease.create({
    data: {
      propertyId: gelsenkirchen.id,
      landlord: "Tech & Home Mate / Landport",
      tenant: "JF Global GmbH",
      endDate: new Date("2028-11-30"),
      hasOption: true,
      optionDetails: "Option +2 Jahre",
      analysisStatus: "IN_PROGRESS",
      notesMarkdown:
        "Eigentlich Untermietvertrag — Hauptmieter hat Vertrag kopiert, fehlerhaft. Scan auf Pflichten/Fristen.",
    },
  });
  await prisma.task.createMany({
    data: [
      ...defaultTaskSetup(gelsenkirchen.id).map((t) =>
        t.category === "LEASE_ANALYSIS" ? { ...t, status: "IN_PROGRESS" } : t,
      ),
      {
        propertyId: gelsenkirchen.id,
        title: "Mängel aus Übergabe",
        category: "DEFECT",
        status: "IN_PROGRESS",
        priority: "HIGH",
        description:
          "Moos entfernen; 2 Tore defekt; Urinale ohne Funktion; Bügel Mezzanine fehlt; Strom nicht anmeldbar; Büro teils nicht begehbar.",
      },
      {
        propertyId: gelsenkirchen.id,
        title: "Stromanmeldung",
        category: "GENERIC",
        status: "TODO",
        priority: "HIGH",
        description:
          "Durch Landport (Fr. Cai) oder JF Global? Zähler damals nicht ermittelbar — Klärung nötig.",
      },
      {
        propertyId: gelsenkirchen.id,
        title: "Genehmigung der Untervermietung",
        category: "DEADLINE",
        status: "TODO",
        priority: "MEDIUM",
        dueDate: daysAgo(-5),
        metadata: { source: "MV Hauptmietverhältnis" },
        description: "Landport muss diese vertraglich bis 01.06 einholen.",
      },
      {
        propertyId: gelsenkirchen.id,
        title: "Störfallcontainer aufstellen",
        category: "GENERIC",
        status: "TODO",
        priority: "LOW",
      },
    ],
  });

  // ============================================================
  // Mandant 4: Landport / Tech & Home Mate — ein Objekt
  // ============================================================
  const landport = await prisma.client.create({
    data: {
      name: "Herr Cai",
      company: "Tech & Home Mate GmbH (Landport)",
      email: "cai@techhomemate.example",
      notes: DEMO_TAG,
    },
  });

  const viersen = await prisma.property.create({
    data: {
      clientId: landport.id,
      name: "Ernst-Moritz-Arndt-Straße 10",
      address: "Ernst-Moritz-Arndt-Straße 10",
      city: "Viersen",
      postalCode: "41747",
      description:
        "Übergabe geplant für 30.06. Vertragsanalyse raus, Leistungsvertrag bei Mandant. Auch Objekt Emmerich angedacht.",
    },
  });
  await prisma.lease.create({
    data: {
      propertyId: viersen.id,
      landlord: "Eigentümer Viersen",
      tenant: "Tech & Home Mate GmbH",
      startDate: monthsFromNow(0),
      analysisStatus: "IN_PROGRESS",
    },
  });
  await prisma.task.createMany({
    data: defaultTaskSetup(viersen.id, { handoverInMonths: 0 }),
  });

  // ============================================================
  // E-Mail-Konto + Inbox-Threads
  // ============================================================
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

  // Thread 1: IMC Dieselstr. — Mietanpassung Klärung
  const t1 = await prisma.emailThread.create({
    data: {
      accountId: account.id,
      propertyId: dieselstr.id,
      subject: "Mietanpassung 05/26 — Differenz",
      normalizedSubject: "mietanpassung 05/26 — differenz",
      unread: true,
      lastMessageAt: daysAgo(0, 9, 22),
    },
  });
  await prisma.emailMessage.createMany({
    data: [
      {
        threadId: t1.id,
        accountId: account.id,
        direction: "OUT",
        messageId: "<demo-imc-1a@kromeich>",
        fromAddr: "info@kromeichpartner.example",
        toAddr: "Yuti Vahidi <yuti.vahidi@imc-prologistics.example>",
        subject: "Mietanpassung 05/26 — Differenz",
        textBody:
          "Hallo Yuti,\n\nwir haben das Schreiben des Vermieters zur Mietanpassung 05/26 geprüft. Rechnerisch wurden 17 Tage angesetzt (15.-31.05.), korrekt wären aber 16 Tage (16.-31.05.).\n\nDifferenz zugunsten von IMC: 95,87 EUR.\n\nDa IMC bereits gezahlt hat, schlagen wir vor, das mit der Juni-Miete zu verrechnen. Bitte um kurze Rückbestätigung.\n\nBeste Grüße\nDenise Kromeich",
        sentAt: daysAgo(3, 14, 12),
      },
      {
        threadId: t1.id,
        accountId: account.id,
        direction: "IN",
        messageId: "<demo-imc-1b@imc>",
        inReplyTo: "<demo-imc-1a@kromeich>",
        fromAddr: "Yuti Vahidi <yuti.vahidi@imc-prologistics.example>",
        toAddr: "info@kromeichpartner.example",
        subject: "Re: Mietanpassung 05/26 — Differenz",
        textBody:
          "Hallo Denise,\n\ndanke für die Prüfung. Verrechnung mit Juni ist okay. Bitte gib auch nochmal kurz Bescheid wenn der Nachtrag durch ist — Evers wollte ab 01.06. mit der neuen Staffel rechnen.\n\nViele Grüße\nYuti",
        sentAt: daysAgo(0, 9, 22),
      },
    ],
  });

  // Thread 2: Patac — Bürgschaft / Aufrechnung Mietrückstand
  const t2 = await prisma.emailThread.create({
    data: {
      accountId: account.id,
      propertyId: harkort.id,
      subject: "Aufrechnung Mietrückstand März — Stand?",
      normalizedSubject: "aufrechnung mietrückstand märz — stand?",
      unread: true,
      lastMessageAt: daysAgo(1, 11, 4),
    },
  });
  await prisma.emailMessage.create({
    data: {
      threadId: t2.id,
      accountId: account.id,
      direction: "IN",
      messageId: "<demo-patac-1a@mileway>",
      fromAddr: "Frau Wu <wu@mileway.example>",
      toAddr: "info@kromeichpartner.example",
      subject: "Aufrechnung Mietrückstand März — Stand?",
      textBody:
        "Sehr geehrte Damen und Herren,\n\nzum Thema Aufrechnung des Mietrückstands März bitte ich um eine kurze Rückmeldung — am 13.05. hatten wir Ihnen unseren Vorschlag zugesandt, am 26.05. nochmal nachgefasst.\n\nKönnen wir das diese Woche zum Abschluss bringen?\n\nMit freundlichen Grüßen\nWu, Mileway",
      sentAt: daysAgo(1, 11, 4),
    },
  });

  // Thread 3: JF Global — Strom-Klärung
  const t3 = await prisma.emailThread.create({
    data: {
      accountId: account.id,
      propertyId: gelsenkirchen.id,
      subject: "Stromzähler Europastraße — Zuordnung unklar",
      normalizedSubject: "stromzähler europastraße — zuordnung unklar",
      unread: false,
      lastMessageAt: daysAgo(2, 16, 30),
    },
  });
  await prisma.emailMessage.create({
    data: {
      threadId: t3.id,
      accountId: account.id,
      direction: "IN",
      messageId: "<demo-jf-1a@yang>",
      fromAddr: "Mr. Yang <yang@jfglobal.example>",
      toAddr: "info@kromeichpartner.example",
      subject: "Stromzähler Europastraße — Zuordnung unklar",
      textBody:
        "Hi team,\n\nat the handover the meter assignment was not clear. JF Global as subtenant apparently cannot register electricity directly. Could you check with Landport (Frau Cai) whether they will do the registration?\n\nThanks,\nYang",
      sentAt: daysAgo(2, 16, 30),
    },
  });

  // Thread 4: Notar-Bestätigung (unzugeordnet, klassisches Triage-Beispiel)
  const t4 = await prisma.emailThread.create({
    data: {
      accountId: account.id,
      subject: "Beurkundungstermin 24.06. bestätigt",
      normalizedSubject: "beurkundungstermin 24.06. bestätigt",
      unread: true,
      lastMessageAt: daysAgo(0, 8, 12),
    },
  });
  await prisma.emailMessage.create({
    data: {
      threadId: t4.id,
      accountId: account.id,
      direction: "IN",
      messageId: "<demo-notar-1a@koehler>",
      fromAddr: "Notariat Köhler <termine@notar-koehler.example>",
      toAddr: "info@kromeichpartner.example",
      subject: "Beurkundungstermin 24.06. bestätigt",
      textBody:
        "Sehr geehrte Damen und Herren,\n\nhiermit bestätigen wir den Termin am 24.06.2026 um 14:00 Uhr in unseren Geschäftsräumen.\n\nBitte bringen Sie die im Vorfeld übersandten Unterlagen im Original mit.\n\nMit freundlichen Grüßen\nNotariat Köhler",
      sentAt: daysAgo(0, 8, 12),
    },
  });

  // Notiz auf Objekt-Ebene (Begehungsprotokoll) — falls Team-User existiert
  const author = await prisma.user.findFirst({
    where: { role: { in: ["TEAM_ADMIN", "TEAM_MEMBER"] } },
  });
  if (author) {
    await prisma.propertyNote.create({
      data: {
        propertyId: dieselstr.id,
        authorId: author.id,
        title: "Begehung Dieselstraße 22.05.",
        content:
          "## Vor Ort: FMI, Palmira, IMC\n\n- Konstruktiv aber ergebnislos\n- Höfels verweist auf vorliegende Angebote → mangelnde Beauftragung\n- Zuständigkeit technisch FMI & Palmira, rechtlich Arrow/Evers\n- IMC-Verstoß: versperrte Fluchtwege dokumentiert\n\n## TODO\n\n- Wagner (RA) zum Stand briefen\n- Frist 24.03 ist abgelaufen — nachfassen",
      },
    });
  }

  const propertyCount = await prisma.property.count();
  const taskCount = await prisma.task.count();
  const threadCount = await prisma.emailThread.count();
  console.log("Demo-Daten angelegt:");
  console.log(`  4 Mandanten, ${propertyCount} Objekte, ${taskCount} Aufgaben`);
  console.log(`  ${threadCount} Inbox-Threads (3 mit Objektbezug, 1 unzugeordnet)`);
  console.log("");
  console.log("Hinweis: Antworten aus der Inbox gehen an Mailpit (Port 8025).");
  console.log("Der IMAP-Sync schlägt bewusst fehl — echtes Postfach unter Einstellungen verbinden.");
}

const wantReset = process.argv.includes("--reset");
try {
  if (wantReset) await reset();
  await seed();
} finally {
  await prisma.$disconnect();
}
