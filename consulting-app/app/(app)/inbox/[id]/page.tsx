import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { requireTeamMember } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import { sendReply } from "@/lib/email/send";
import { formatDateTime, formatBytes, classNames } from "@/lib/utils";

export default async function ThreadPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  await requireTeamMember();
  const { id } = await params;

  const thread = await prisma.emailThread.findUnique({
    where: { id },
    include: {
      account: true,
      project: { include: { client: true } },
      property: { include: { client: true } },
      assignee: true,
      messages: {
        orderBy: { sentAt: "asc" },
        include: { attachments: true },
      },
    },
  });
  if (!thread) notFound();

  // Beim Öffnen als gelesen markieren
  if (thread.unread) {
    await prisma.emailThread.update({ where: { id }, data: { unread: false } });
  }

  const [properties, teamMembers] = await Promise.all([
    prisma.property.findMany({
      where: { archivedAt: null },
      include: { client: true },
      orderBy: [{ client: { name: "asc" } }, { name: "asc" }],
    }),
    prisma.user.findMany({
      where: { role: { in: ["TEAM_ADMIN", "TEAM_MEMBER"] } },
      orderBy: { email: "asc" },
    }),
  ]);

  async function reply(formData: FormData) {
    "use server";
    await requireTeamMember();
    const body = (formData.get("body") as string)?.trim();
    if (!body) return;
    await sendReply(id, body);
    revalidatePath(`/inbox/${id}`);
  }

  async function assignProperty(formData: FormData) {
    "use server";
    await requireTeamMember();
    const propertyId = (formData.get("propertyId") as string) || null;
    await prisma.emailThread.update({
      where: { id },
      // beim Wechsel auf ein Objekt entfernen wir die alte Projektzuordnung,
      // damit nicht beide gleichzeitig gesetzt sind und in der UI doppelt erscheinen.
      data: { propertyId, projectId: propertyId ? null : undefined },
    });
    revalidatePath(`/inbox/${id}`);
  }

  async function assignUser(formData: FormData) {
    "use server";
    await requireTeamMember();
    const assigneeId = (formData.get("assigneeId") as string) || null;
    await prisma.emailThread.update({ where: { id }, data: { assigneeId } });
    revalidatePath(`/inbox/${id}`);
  }

  async function toggleArchive() {
    "use server";
    await requireTeamMember();
    const current = await prisma.emailThread.findUniqueOrThrow({
      where: { id },
      select: { status: true },
    });
    await prisma.emailThread.update({
      where: { id },
      data: { status: current.status === "ARCHIVED" ? "OPEN" : "ARCHIVED" },
    });
    redirect("/inbox");
  }

  async function createTaskFromThread() {
    "use server";
    const user = await requireTeamMember();
    const current = await prisma.emailThread.findUniqueOrThrow({
      where: { id },
      include: { messages: { orderBy: { sentAt: "desc" }, take: 1 } },
    });
    if (!current.propertyId && !current.projectId) return;
    const latest = current.messages[0];
    await prisma.task.create({
      data: {
        propertyId: current.propertyId,
        projectId: current.projectId,
        title: current.subject,
        category: "CORRESPONDENCE",
        description: `Aus E-Mail von ${latest?.fromAddr ?? "?"} (${latest ? latest.sentAt.toLocaleDateString("de-DE") : ""}):\n\n${latest?.textBody.slice(0, 500) ?? ""}`,
        assigneeId: current.assigneeId ?? user.id,
      },
    });
    if (current.propertyId) {
      redirect(`/properties/${current.propertyId}`);
    } else {
      redirect(`/projects/${current.projectId}`);
    }
  }

  const attachmentCount = thread.messages.reduce(
    (sum, m) => sum + m.attachments.length,
    0,
  );

  const contextLink = thread.property
    ? {
        href: `/properties/${thread.property.id}`,
        label: `${thread.property.client.company || thread.property.client.name} · ${thread.property.name}`,
      }
    : thread.project
      ? {
          href: `/projects/${thread.project.id}`,
          label: `${thread.project.client.name} · ${thread.project.name}`,
        }
      : null;

  return (
    <div className="space-y-5">
      <div>
        <Link href="/inbox" className="text-sm text-slate-600 hover:text-slate-900">
          ← Inbox
        </Link>
        <h1 className="text-2xl font-bold mt-1">{thread.subject}</h1>
        <div className="text-xs text-slate-500 mt-1">
          über {thread.account.email} · {thread.messages.length} Nachricht
          {thread.messages.length === 1 ? "" : "en"}
        </div>
      </div>

      <div className="card flex flex-wrap items-end gap-4">
        <form action={assignProperty} className="flex items-end gap-2">
          <div>
            <label className="label">Objekt</label>
            <select
              className="input min-w-[260px]"
              name="propertyId"
              defaultValue={thread.propertyId ?? ""}
            >
              <option value="">— kein Objekt —</option>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {(p.client.company || p.client.name) + " · " + p.name}
                </option>
              ))}
            </select>
          </div>
          <button className="btn-secondary">Zuordnen</button>
        </form>

        <form action={assignUser} className="flex items-end gap-2">
          <div>
            <label className="label">Kümmert sich</label>
            <select
              className="input min-w-[180px]"
              name="assigneeId"
              defaultValue={thread.assigneeId ?? ""}
            >
              <option value="">— niemand —</option>
              {teamMembers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name ?? m.email}
                </option>
              ))}
            </select>
          </div>
          <button className="btn-secondary">Zuweisen</button>
        </form>

        <div className="ml-auto flex items-end gap-2">
          <form action={createTaskFromThread}>
            <button
              className="btn-secondary"
              disabled={!thread.propertyId && !thread.projectId}
              title={
                thread.propertyId || thread.projectId
                  ? ""
                  : "Erst einem Objekt zuordnen"
              }
            >
              + Aufgabe daraus
            </button>
          </form>
          {attachmentCount > 0 && (
            <span className="badge bg-slate-100 text-slate-600">
              📎 {attachmentCount} Anhänge
            </span>
          )}
          <form action={toggleArchive}>
            <button className="btn-ghost">
              {thread.status === "ARCHIVED" ? "Wiederherstellen" : "Archivieren"}
            </button>
          </form>
        </div>
      </div>

      {contextLink && (
        <div className="text-sm">
          Zugeordnet zu:{" "}
          <Link href={contextLink.href} className="text-brand-600 font-medium">
            {contextLink.label}
          </Link>
        </div>
      )}

      <div className="space-y-3">
        {thread.messages.map((m) => (
          <div
            key={m.id}
            className={classNames(
              "card",
              m.direction === "OUT" && "border-brand-100 bg-brand-50/40",
            )}
          >
            <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
              <div>
                {m.direction === "OUT" ? (
                  <span>
                    <strong className="text-brand-700">Ihr</strong> → {m.toAddr}
                  </span>
                ) : (
                  <span>
                    <strong className="text-slate-700">{m.fromAddr}</strong> →{" "}
                    {m.toAddr}
                  </span>
                )}
              </div>
              <div>{formatDateTime(m.sentAt)}</div>
            </div>
            <div className="text-sm whitespace-pre-wrap">{m.textBody}</div>
            {m.attachments.length > 0 && (
              <div className="mt-3 pt-3 border-t border-slate-100 flex flex-wrap gap-2">
                {m.attachments.map((att) => (
                  <a
                    key={att.id}
                    href={`/api/email/attachments/${att.id}`}
                    className="badge bg-slate-100 text-slate-700 hover:bg-slate-200"
                  >
                    📎 {att.filename} ({formatBytes(att.sizeBytes)})
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <form action={reply} className="card space-y-3">
        <div>
          <label className="label">Antworten als {thread.account.email}</label>
          <textarea
            className="input font-mono text-sm"
            name="body"
            rows={6}
            required
            placeholder="Deine Antwort…"
          />
        </div>
        <div className="flex justify-end">
          <button className="btn-primary">↩ Antwort senden</button>
        </div>
      </form>
    </div>
  );
}
