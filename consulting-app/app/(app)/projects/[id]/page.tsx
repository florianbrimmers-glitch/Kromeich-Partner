import Link from "next/link";
import { notFound } from "next/navigation";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireTeamMember } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import { formatDate, STATUS_LABELS } from "@/lib/utils";
import { TaskList } from "@/components/tasks/TaskList";
import { NotesList } from "@/components/projects/NotesList";
import { DocumentsList } from "@/components/projects/DocumentsList";

const PROJECT_STATUSES = ["ACTIVE", "ON_HOLD", "COMPLETED", "ARCHIVED"] as const;

export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  await requireTeamMember();
  const { id } = await params;

  const project = await prisma.project.findUnique({
    where: { id },
    include: {
      client: true,
      emailThreads: {
        orderBy: { lastMessageAt: "desc" },
        include: {
          messages: { orderBy: { sentAt: "desc" }, take: 1 },
          _count: { select: { messages: true } },
        },
      },
    },
  });
  if (!project) notFound();

  async function updateProject(formData: FormData) {
    "use server";
    await requireTeamMember();
    const status = formData.get("status") as typeof PROJECT_STATUSES[number];
    const deadline = formData.get("deadline") as string;
    await prisma.project.update({
      where: { id },
      data: {
        status,
        deadline: deadline ? new Date(deadline) : null,
      },
    });
    revalidatePath(`/projects/${id}`);
  }

  async function deleteProject() {
    "use server";
    await requireTeamMember();
    const clientId = project!.clientId;
    await prisma.project.delete({ where: { id } });
    redirect(`/clients/${clientId}`);
  }

  return (
    <div className="space-y-8">
      <div>
        <Link
          href={`/clients/${project.clientId}`}
          className="text-sm text-slate-600 hover:text-slate-900"
        >
          ← {project.client.name}
        </Link>
        <h1 className="text-2xl font-bold mt-1">{project.name}</h1>
        {project.description && (
          <p className="text-sm text-slate-600 mt-1">{project.description}</p>
        )}
      </div>

      <form action={updateProject} className="card flex flex-wrap gap-3 items-end">
        <div>
          <label className="label">Status</label>
          <select className="input" name="status" defaultValue={project.status}>
            {PROJECT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Deadline</label>
          <input
            className="input"
            type="date"
            name="deadline"
            defaultValue={project.deadline?.toISOString().slice(0, 10) ?? ""}
          />
        </div>
        <div className="text-xs text-slate-500 self-center">
          Aktuell: <strong>{STATUS_LABELS[project.status]}</strong> · Deadline {formatDate(project.deadline)}
        </div>
        <div className="ml-auto flex gap-2">
          <button className="btn-secondary">Speichern</button>
        </div>
      </form>

      <section>
        <h2 className="text-lg font-semibold mb-3">Aufgaben</h2>
        <TaskList projectId={id} />
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Notizen</h2>
        <NotesList projectId={id} />
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Dokumente</h2>
        <DocumentsList projectId={id} />
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">
          Kommunikation ({project.emailThreads.length})
        </h2>
        {project.emailThreads.length === 0 ? (
          <div className="card text-sm text-slate-600">
            Noch keine E-Mails zugeordnet. Ordne Threads in der{" "}
            <Link href="/inbox" className="text-brand-600">
              Inbox
            </Link>{" "}
            diesem Projekt zu.
          </div>
        ) : (
          <div className="card p-0 divide-y divide-slate-100">
            {project.emailThreads.map((t) => {
              const latest = t.messages[0];
              return (
                <Link
                  key={t.id}
                  href={`/inbox/${t.id}`}
                  className="block px-4 py-3 hover:bg-slate-50"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium text-sm">
                      {t.subject}
                      {t._count.messages > 1 && (
                        <span className="text-slate-400 ml-1">
                          ({t._count.messages})
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500 whitespace-nowrap">
                      {formatDate(t.lastMessageAt)}
                    </div>
                  </div>
                  <div className="text-xs text-slate-500 truncate mt-0.5">
                    {latest?.direction === "OUT"
                      ? `An: ${latest.toAddr}`
                      : latest?.fromAddr}{" "}
                    — {latest?.textBody.replace(/\s+/g, " ").slice(0, 100)}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <form action={deleteProject} className="card border-rose-200">
          <h3 className="font-medium text-rose-700 mb-1">Gefahrenzone</h3>
          <p className="text-sm text-slate-600 mb-3">
            Projekt komplett löschen (inkl. Aufgaben, Notizen, Dokumenten).
          </p>
          <button className="btn bg-rose-600 hover:bg-rose-700 text-white">
            Projekt löschen
          </button>
        </form>
      </section>
    </div>
  );
}
