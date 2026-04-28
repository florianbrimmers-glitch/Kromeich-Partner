import Link from "next/link";
import { requireUser } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import { formatDate, STATUS_LABELS, PRIORITY_LABELS } from "@/lib/utils";

export default async function MyTasksPage() {
  const user = await requireUser();

  const tasks = await prisma.task.findMany({
    where: { assigneeId: user.id },
    include: { project: { include: { client: true } } },
    orderBy: [{ status: "asc" }, { dueDate: "asc" }],
  });

  const grouped = {
    TODO: tasks.filter((t) => t.status === "TODO"),
    IN_PROGRESS: tasks.filter((t) => t.status === "IN_PROGRESS"),
    REVIEW: tasks.filter((t) => t.status === "REVIEW"),
    DONE: tasks.filter((t) => t.status === "DONE"),
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Meine Aufgaben</h1>

      {tasks.length === 0 ? (
        <div className="card text-sm text-slate-600">
          Dir sind keine Aufgaben zugewiesen.
        </div>
      ) : (
        <div className="space-y-6">
          {(["TODO", "IN_PROGRESS", "REVIEW", "DONE"] as const).map((status) => {
            const items = grouped[status];
            if (items.length === 0) return null;
            return (
              <section key={status}>
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">
                  {STATUS_LABELS[status]} ({items.length})
                </h2>
                <div className="card p-0 divide-y divide-slate-100">
                  {items.map((t) => (
                    <Link
                      key={t.id}
                      href={`/projects/${t.projectId}`}
                      className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
                    >
                      <div>
                        <div className={status === "DONE" ? "line-through text-slate-500" : "font-medium"}>
                          {t.title}
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5">
                          {t.project.client.name} · {t.project.name}
                        </div>
                      </div>
                      <div className="text-xs text-slate-500 flex items-center gap-3">
                        <span>{PRIORITY_LABELS[t.priority]}</span>
                        <span>{formatDate(t.dueDate)}</span>
                      </div>
                    </Link>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
