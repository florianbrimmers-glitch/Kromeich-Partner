import Link from "next/link";
import { revalidatePath } from "next/cache";
import { requireTeamMember } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import { syncAllAccounts } from "@/lib/email/sync";
import { formatDateTime, classNames } from "@/lib/utils";

type Filter = "open" | "unread" | "mine" | "archived";

const FILTER_LABELS: Record<Filter, string> = {
  open: "Alle",
  unread: "Ungelesen",
  mine: "Mir zugewiesen",
  archived: "Archiv",
};

export default async function InboxPage({
  searchParams,
}: {
  searchParams: Promise<{ filter?: string; q?: string }>;
}) {
  const user = await requireTeamMember();
  const params = await searchParams;
  const filter = (Object.keys(FILTER_LABELS).includes(params.filter ?? "")
    ? params.filter
    : "open") as Filter;
  const query = params.q?.trim() ?? "";

  const accounts = await prisma.emailAccount.findMany({
    orderBy: { createdAt: "asc" },
  });

  const threads = await prisma.emailThread.findMany({
    where: {
      status: filter === "archived" ? "ARCHIVED" : "OPEN",
      ...(filter === "unread" ? { unread: true } : {}),
      ...(filter === "mine" ? { assigneeId: user.id } : {}),
      ...(query
        ? {
            OR: [
              { subject: { contains: query, mode: "insensitive" } },
              { messages: { some: { fromAddr: { contains: query, mode: "insensitive" } } } },
              { messages: { some: { textBody: { contains: query, mode: "insensitive" } } } },
            ],
          }
        : {}),
    },
    include: {
      project: { include: { client: true } },
      assignee: true,
      messages: {
        orderBy: { sentAt: "desc" },
        take: 1,
      },
      _count: { select: { messages: true } },
    },
    orderBy: { lastMessageAt: "desc" },
    take: 100,
  });

  const attachmentCounts = await prisma.emailAttachment.groupBy({
    by: ["messageId"],
    where: { message: { threadId: { in: threads.map((t) => t.id) } } },
    _count: true,
  });
  const threadHasAttachments = new Set<string>();
  if (attachmentCounts.length > 0) {
    const messages = await prisma.emailMessage.findMany({
      where: { id: { in: attachmentCounts.map((a) => a.messageId) } },
      select: { threadId: true },
    });
    for (const m of messages) threadHasAttachments.add(m.threadId);
  }

  async function runSync() {
    "use server";
    await requireTeamMember();
    await syncAllAccounts();
    revalidatePath("/inbox");
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Inbox</h1>
          <p className="text-sm text-slate-600 mt-1">
            {accounts.length === 0
              ? "Noch kein Postfach verbunden."
              : accounts.map((a) => a.email).join(" · ")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <form action={runSync}>
            <button className="btn-secondary" disabled={accounts.length === 0}>
              ↻ Synchronisieren
            </button>
          </form>
          <Link href="/inbox/compose" className="btn-primary">
            + Neue E-Mail
          </Link>
        </div>
      </div>

      {accounts.some((a) => a.lastSyncError) && (
        <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
          {accounts
            .filter((a) => a.lastSyncError)
            .map((a) => (
              <div key={a.id}>
                Sync-Fehler bei <strong>{a.email}</strong>: {a.lastSyncError}
              </div>
            ))}
        </div>
      )}

      <div className="flex items-center gap-2">
        <div className="flex gap-1">
          {(Object.entries(FILTER_LABELS) as [Filter, string][]).map(([key, label]) => (
            <Link
              key={key}
              href={`/inbox?filter=${key}${query ? `&q=${encodeURIComponent(query)}` : ""}`}
              className={classNames(
                "px-3 py-1.5 rounded-md text-sm",
                filter === key
                  ? "bg-brand-600 text-white"
                  : "text-slate-600 hover:bg-slate-100"
              )}
            >
              {label}
            </Link>
          ))}
        </div>
        <form className="flex-1 max-w-xs ml-auto" method="GET" action="/inbox">
          <input type="hidden" name="filter" value={filter} />
          <input
            className="input"
            name="q"
            placeholder="Suchen…"
            defaultValue={query}
          />
        </form>
      </div>

      {accounts.length === 0 ? (
        <div className="card text-sm text-slate-600">
          Verbinde unter{" "}
          <Link href="/settings" className="text-brand-600">
            Einstellungen
          </Link>{" "}
          ein Postfach (IMAP), um Mails zu empfangen — oder führe das
          Demo-Seed-Skript aus (<code>node scripts/seed-demo.mjs</code>), um die
          Inbox mit Beispieldaten zu sehen.
        </div>
      ) : threads.length === 0 ? (
        <div className="card text-sm text-slate-600">Keine Threads in dieser Ansicht.</div>
      ) : (
        <div className="card p-0 divide-y divide-slate-100">
          {threads.map((t) => {
            const latest = t.messages[0];
            const snippet = latest?.textBody.replace(/\s+/g, " ").slice(0, 120) ?? "";
            return (
              <Link
                key={t.id}
                href={`/inbox/${t.id}`}
                className={classNames(
                  "block px-4 py-3 hover:bg-slate-50",
                  t.unread && "bg-brand-50/50"
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <div
                    className={classNames(
                      "text-sm truncate",
                      t.unread ? "font-semibold" : "text-slate-700"
                    )}
                  >
                    {latest?.direction === "OUT" ? `An: ${latest.toAddr}` : latest?.fromAddr}
                  </div>
                  <div className="text-xs text-slate-500 whitespace-nowrap">
                    {formatDateTime(t.lastMessageAt)}
                  </div>
                </div>
                <div className={classNames("text-sm mt-0.5", t.unread ? "font-medium" : "")}>
                  {t.subject}
                  {t._count.messages > 1 && (
                    <span className="text-slate-400 ml-1">({t._count.messages})</span>
                  )}
                </div>
                <div className="text-xs text-slate-500 truncate mt-0.5">{snippet}</div>
                <div className="flex items-center gap-1.5 mt-1.5">
                  {t.project && (
                    <span className="badge bg-emerald-100 text-emerald-700">
                      {t.project.client.name} · {t.project.name}
                    </span>
                  )}
                  {t.assignee && (
                    <span className="badge bg-rose-100 text-rose-700">
                      {t.assignee.name ?? t.assignee.email}
                    </span>
                  )}
                  {threadHasAttachments.has(t.id) && (
                    <span className="badge bg-slate-100 text-slate-600">📎</span>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
