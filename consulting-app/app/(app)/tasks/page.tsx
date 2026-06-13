import Link from "next/link";
import { requireUser } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import {
  formatDate,
  STATUS_LABELS,
  PRIORITY_LABELS,
  TASK_CATEGORY_LABELS,
  TASK_CATEGORY_BADGE,
} from "@/lib/utils";

export default async function MyTasksPage() {
  const user = await requireUser();

  const tasks = await prisma.task.findMany({
    where: { assigneeId: user.id },
    include: {
      project: { include: { client: true } },
      property: { include: { client: true } },
      client: true,
    },
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
                      href={taskHref(t)}
                      className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
                    >
                      <div className="min-w-0">
                        <div
                          className={
                            status === "DONE"
                              ? "line-through text-slate-500"
                              : "font-medium"
                          }
                        >
                          {t.title}
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5 truncate">
                          {taskContext(t)}
                        </div>
                      </div>
                      <div className="text-xs text-slate-500 flex items-center gap-3 whitespace-nowrap">
                        <span
                          className={`badge ${TASK_CATEGORY_BADGE[t.category]}`}
                        >
                          {TASK_CATEGORY_LABELS[t.category]}
                        </span>
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

type TaskWithContext = {
  propertyId: string | null;
  projectId: string | null;
  clientId: string | null;
  property: { client: { name: string; company: string | null }; name: string } | null;
  project: { client: { name: string; company: string | null }; name: string } | null;
  client: { name: string; company: string | null } | null;
};

function taskHref(t: TaskWithContext): string {
  if (t.propertyId) return `/properties/${t.propertyId}`;
  if (t.projectId) return `/projects/${t.projectId}`;
  if (t.clientId) return `/clients/${t.clientId}`;
  return "/tasks";
}

function taskContext(t: TaskWithContext): string {
  if (t.property) {
    return `${t.property.client.company || t.property.client.name} · ${t.property.name}`;
  }
  if (t.project) {
    return `${t.project.client.company || t.project.client.name} · ${t.project.name}`;
  }
  if (t.client) {
    return t.client.company || t.client.name;
  }
  return "—";
}
