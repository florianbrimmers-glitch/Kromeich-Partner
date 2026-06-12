import nodemailer from "nodemailer";
import { prisma } from "@/lib/prisma";
import { normalizeSubject } from "@/lib/email/threading";

function transportFor(account: {
  smtpHost: string;
  smtpPort: number;
  smtpSecure: boolean;
  username: string;
  password: string;
}) {
  return nodemailer.createTransport({
    host: account.smtpHost,
    port: account.smtpPort,
    secure: account.smtpSecure,
    auth: account.password
      ? { user: account.username, pass: account.password }
      : undefined,
  });
}

/** Antwortet in einem bestehenden Thread (korrektes RFC-Threading via In-Reply-To/References). */
export async function sendReply(threadId: string, body: string): Promise<void> {
  const thread = await prisma.emailThread.findUniqueOrThrow({
    where: { id: threadId },
    include: {
      account: true,
      messages: { orderBy: { sentAt: "desc" } },
    },
  });

  const lastIncoming = thread.messages.find((m) => m.direction === "IN");
  const lastMessage = thread.messages[0];
  const to = lastIncoming?.fromAddr ?? lastMessage?.toAddr;
  if (!to) throw new Error("Kein Empfänger im Thread gefunden");

  const subject = /^(re|aw):/i.test(thread.subject)
    ? thread.subject
    : `Re: ${thread.subject}`;

  const references = thread.messages
    .map((m) => m.messageId)
    .filter(Boolean)
    .reverse() as string[];

  const transport = transportFor(thread.account);
  const info = await transport.sendMail({
    from: thread.account.email,
    to,
    subject,
    text: body,
    inReplyTo: lastIncoming?.messageId ?? undefined,
    references: references.length > 0 ? references : undefined,
  });

  await prisma.emailMessage.create({
    data: {
      threadId: thread.id,
      accountId: thread.accountId,
      direction: "OUT",
      messageId: info.messageId ?? null,
      inReplyTo: lastIncoming?.messageId ?? null,
      fromAddr: thread.account.email,
      toAddr: to,
      subject,
      textBody: body,
      sentAt: new Date(),
    },
  });

  await prisma.emailThread.update({
    where: { id: thread.id },
    data: { lastMessageAt: new Date(), status: "OPEN" },
  });
}

/** Startet eine neue Konversation aus dem Tool heraus. */
export async function sendNewMail(params: {
  accountId: string;
  to: string;
  subject: string;
  body: string;
  projectId?: string | null;
}): Promise<string> {
  const account = await prisma.emailAccount.findUniqueOrThrow({
    where: { id: params.accountId },
  });

  const transport = transportFor(account);
  const info = await transport.sendMail({
    from: account.email,
    to: params.to,
    subject: params.subject,
    text: params.body,
  });

  const now = new Date();
  const thread = await prisma.emailThread.create({
    data: {
      accountId: account.id,
      projectId: params.projectId ?? null,
      subject: params.subject,
      normalizedSubject: normalizeSubject(params.subject),
      unread: false,
      lastMessageAt: now,
      messages: {
        create: {
          accountId: account.id,
          direction: "OUT",
          messageId: info.messageId ?? null,
          fromAddr: account.email,
          toAddr: params.to,
          subject: params.subject,
          textBody: params.body,
          sentAt: now,
        },
      },
    },
  });

  return thread.id;
}
