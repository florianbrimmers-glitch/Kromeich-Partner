import { ImapFlow } from "imapflow";
import { simpleParser, type ParsedMail } from "mailparser";
import { randomUUID } from "node:crypto";
import { writeFile, mkdir } from "node:fs/promises";
import { join, dirname } from "node:path";
import type { EmailAccount } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import { normalizeSubject, findThreadFor, guessPropertyFor } from "@/lib/email/threading";

const STORAGE_DIR = join(process.cwd(), "storage", "uploads");

// Beim allerersten Sync eines Kontos nicht das ganze Archiv ziehen
const INITIAL_SYNC_LIMIT = 50;

export type SyncResult = {
  accountId: string;
  email: string;
  imported: number;
  error?: string;
};

export async function syncAllAccounts(): Promise<SyncResult[]> {
  const accounts = await prisma.emailAccount.findMany();
  const results: SyncResult[] = [];
  for (const account of accounts) {
    results.push(await syncAccount(account));
  }
  return results;
}

export async function syncAccount(account: EmailAccount): Promise<SyncResult> {
  const result: SyncResult = { accountId: account.id, email: account.email, imported: 0 };

  const client = new ImapFlow({
    host: account.imapHost,
    port: account.imapPort,
    secure: account.imapSecure,
    auth: { user: account.username, pass: account.password },
    logger: false,
    connectionTimeout: 15_000,
  });

  try {
    await client.connect();
    const lock = await client.getMailboxLock("INBOX");
    try {
      const mailbox = client.mailbox;
      if (!mailbox || typeof mailbox === "boolean") {
        throw new Error("INBOX konnte nicht geöffnet werden");
      }

      const uidValidity = String(mailbox.uidValidity ?? "");
      const sameGeneration = account.uidValidity === uidValidity && account.lastUid != null;
      let maxUid = sameGeneration ? account.lastUid! : 0;

      // Bei bekanntem Stand nur neue UIDs holen, sonst die letzten N Mails
      let range: string;
      let useUid: boolean;
      if (sameGeneration) {
        range = `${account.lastUid! + 1}:*`;
        useUid = true;
      } else {
        const start = Math.max(1, mailbox.exists - INITIAL_SYNC_LIMIT + 1);
        range = mailbox.exists > 0 ? `${start}:*` : "";
        useUid = false;
      }

      if (range) {
        for await (const msg of client.fetch(range, { uid: true, source: true }, { uid: useUid })) {
          if (!msg.source) continue;
          if (sameGeneration && msg.uid <= account.lastUid!) continue;
          const parsed = await simpleParser(msg.source);
          const stored = await storeIncomingMail(account, parsed);
          if (stored) result.imported++;
          if (msg.uid > maxUid) maxUid = msg.uid;
        }
      }

      await prisma.emailAccount.update({
        where: { id: account.id },
        data: {
          uidValidity,
          lastUid: maxUid || account.lastUid,
          lastSyncAt: new Date(),
          lastSyncError: null,
        },
      });
    } finally {
      lock.release();
    }
    await client.logout();
  } catch (err) {
    result.error = err instanceof Error ? err.message : String(err);
    await prisma.emailAccount.update({
      where: { id: account.id },
      data: { lastSyncAt: new Date(), lastSyncError: result.error },
    });
    try {
      await client.logout();
    } catch {
      // Verbindung war ohnehin schon tot
    }
  }

  return result;
}

/** Speichert eine geparste Mail samt Anhängen; gibt false zurück bei Duplikat. */
async function storeIncomingMail(account: EmailAccount, parsed: ParsedMail): Promise<boolean> {
  const messageId = parsed.messageId ?? null;
  if (messageId) {
    const existing = await prisma.emailMessage.findUnique({ where: { messageId } });
    if (existing) return false;
  }

  const subject = parsed.subject ?? "(kein Betreff)";
  const normalized = normalizeSubject(subject);
  const fromAddr = parsed.from?.text ?? "unbekannt";
  const toValue = parsed.to;
  const toAddr = (Array.isArray(toValue) ? toValue.map((t) => t.text).join(", ") : toValue?.text) ?? account.email;
  const ccValue = parsed.cc;
  const ccAddr = (Array.isArray(ccValue) ? ccValue.map((c) => c.text).join(", ") : ccValue?.text) ?? null;
  const sentAt = parsed.date ?? new Date();
  const references = Array.isArray(parsed.references)
    ? parsed.references
    : parsed.references
      ? [parsed.references]
      : [];

  let threadId = await findThreadFor(account.id, parsed.inReplyTo ?? null, references, normalized);

  if (!threadId) {
    const propertyId = await guessPropertyFor(fromAddr);
    const thread = await prisma.emailThread.create({
      data: {
        accountId: account.id,
        propertyId,
        subject,
        normalizedSubject: normalized,
        lastMessageAt: sentAt,
      },
    });
    threadId = thread.id;
  } else {
    await prisma.emailThread.update({
      where: { id: threadId },
      data: { unread: true, status: "OPEN", lastMessageAt: sentAt },
    });
  }

  const message = await prisma.emailMessage.create({
    data: {
      threadId,
      accountId: account.id,
      direction: "IN",
      messageId,
      inReplyTo: parsed.inReplyTo ?? null,
      fromAddr,
      toAddr,
      ccAddr,
      subject,
      textBody: parsed.text ?? "",
      htmlBody: typeof parsed.html === "string" ? parsed.html : null,
      sentAt,
    },
  });

  for (const att of parsed.attachments ?? []) {
    const filename = att.filename ?? "anhang.bin";
    const storageKey = `email/${account.id}/${randomUUID()}-${filename}`;
    const fullPath = join(STORAGE_DIR, storageKey);
    await mkdir(dirname(fullPath), { recursive: true });
    await writeFile(fullPath, att.content);
    await prisma.emailAttachment.create({
      data: {
        messageId: message.id,
        filename,
        storageKey,
        mimeType: att.contentType ?? "application/octet-stream",
        sizeBytes: att.size ?? att.content.length,
      },
    });
  }

  return true;
}
