import { revalidatePath } from "next/cache";
import { prisma } from "@/lib/prisma";
import { requireTeamMember } from "@/lib/access";
import { formatDate, PRIORITY_LABELS } from "@/lib/utils";
import { StatusSelect } from "@/components/tasks/StatusSelect";

const PRIORITIES = ["LOW", "MEDIUM", "HIGH", "URGENT"] as const;
const STATUSES = ["TODO", "IN_PROGRESS", "REVIEW", "DONE"] as const;

export async function TaskList({ projectId }: { projectId: string }) {
  const [tasks, members] = await Promise.all([
    prisma.task.findMany({
      where: { projectId },
      include: { assignee: true },
      orderBy: [{ status: "asc" }, { dueDate: "asc" }, { createdAt: "desc" }],
    }),
    prisma.user.findMany({
      where: { role: { in: ["TEAM_ADMIN", "TEAM_MEMBER"] } },
      orderBy: { email: "asc" },
    }),
  ]);

  async function createTask(formData: FormData) {
    "use server";
    await requireTeamMember();
    const title = (formData.get("title") as string)?.trim();
    if (!title) return;
    const dueDate = formData.get("dueDate") as string;
    const assigneeId = formData.get("assigneeId") as string;
    await prisma.task.create({
      data: {
        projectId,
        title,
        priority: (formData.get("priority") as typeof PRIORITIES[number]) || "MEDIUM",
        assigneeId: assigneeId || null,
        dueDate: dueDate ? new Date(dueDate) : null,
      },
    });
    revalidatePath(`/projects/${projectId}`);
  }

  async function updateStatus(formData: FormData) {
    "use server";
    await requireTeamMember();
    const id = formData.get("id") as string;
    const status = formData.get("status") as typeof STATUSES[number];
    await prisma.task.update({ where: { id }, data: { status } });
    revalidatePath(`/projects/${projectId}`);
  }

  async function deleteTask(formData: FormData) {
    "use server";
    await requireTeamMember();
    const id = formData.get("id") as string;
    await prisma.task.delete({ where: { id } });
    revalidatePath(`/projects/${projectId}`);
  }

  return (
    <div className="space-y-4">
      <form action={createTask} className="card grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
        <div className="md:col-span-5">
          <label className="label">Aufgabe</label>
          <input className="input" name="title" required placeholder="Was ist zu tun?" />
        </div>
        <div className="md:col-span-3">
          <label className="label">Zuweisen</label>
          <select className="input" name="assigneeId">
            <option value="">Niemand</option>
            {members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name ?? m.email}
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-2">
          <label className="label">Priorität</label>
          <select className="input" name="priority" defaultValue="MEDIUM">
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {PRIORITY_LABELS[p]}
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-2">
          <label className="label">Deadline</label>
          <input className="input" name="dueDate" type="date" />
        </div>
        <div className="md:col-span-12">
          <button className="btn-primary">Aufgabe hinzufügen</button>
        </div>
      </form>

      {tasks.length === 0 ? (
        <div className="card text-sm text-slate-600">Noch keine Aufgaben.</div>
      ) : (
        <div className="card p-0 divide-y divide-slate-100">
          {tasks.map((task) => (
            <div key={task.id} className="px-4 py-3 flex items-center gap-3">
              <StatusSelect taskId={task.id} current={task.status} action={updateStatus} />
              <div className="flex-1">
                <div className={task.status === "DONE" ? "line-through text-slate-500" : "font-medium"}>
                  {task.title}
                </div>
                <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-2 flex-wrap">
                  <span>{task.assignee?.name ?? task.assignee?.email ?? "—"}</span>
                  <span>·</span>
                  <span>{formatDate(task.dueDate)}</span>
                  <span>·</span>
                  <span>{PRIORITY_LABELS[task.priority]}</span>
                </div>
              </div>
              <form action={deleteTask}>
                <input type="hidden" name="id" value={task.id} />
                <button className="btn-ghost text-rose-600 text-xs" aria-label="Löschen">
                  Löschen
                </button>
              </form>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
