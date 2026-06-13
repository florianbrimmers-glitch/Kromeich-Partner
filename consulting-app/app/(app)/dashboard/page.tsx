import Link from "next/link";
import { requireUser } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import {
  formatDate,
  STATUS_LABELS,
  TASK_CATEGORY_LABELS,
  TASK_CATEGORY_BADGE,
} from "@/lib/utils";

export default async function DashboardPage() {
  const user = await requireUser();

  const [myTasks, recentProperties, taskCount, openMailCount] = await Promise.all([
    prisma.task.findMany({
      where: {
        assigneeId: user.id,
        status: { in: ["TODO", "IN_PROGRESS", "REVIEW"] },
      },
      include: {
        project: { include: { client: true } },
        property: { include: { client: true } },
        client: true,
      },
      orderBy: [{ dueDate: "asc" }, { priority: "desc" }],
      take: 10,
    }),
    prisma.property.findMany({
      where: { archivedAt: null },
      include: {
        client: true,
        _count: { select: { tasks: true } },
      },
      orderBy: { updatedAt: "desc" },
      take: 6,
    }),
    prisma.task.count({
      where: {
        assigneeId: user.id,
        status: { in: ["TODO", "IN_PROGRESS"] },
      },
    }),
    prisma.emailThread.count({ where: { status: "OPEN", unread: true } }),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Hallo {user.name ?? user.email}</h1>
        <p className="text-slate-600 mt-1">
          {taskCount === 0
            ? "Keine offenen Aufgaben — gut gemacht."
            : `Du hast ${taskCount} offene Aufgabe${taskCount === 1 ? "" : "n"}.`}
          {openMailCount > 0 && (
            <>
              {" "}
              · <Link href="/inbox" className="text-brand-600">
                {openMailCount} ungelesene Mail{openMailCount === 1 ? "" : "s"}
              </Link>
            </>
          )}
        </p>
      </div>

      <section>
        <h2 className="text-lg font-semibold mb-3">Meine Aufgaben</h2>
        {myTasks.length === 0 ? (
          <div className="card text-sm text-slate-600">Keine offenen Aufgaben.</div>
        ) : (
          <div className="card divide-y divide-slate-100 p-0">
            {myTasks.map((task) => (
              <Link
                key={task.id}
                href={taskHref(task)}
                className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
              >
                <div className="min-w-0">
                  <div className="font-medium">{task.title}</div>
                  <div className="text-xs text-slate-500 mt-0.5 truncate">
                    {taskContext(task)}
                  </div>
                </div>
                <div className="flex items-center gap-3 text-xs whitespace-nowrap">
                  <span
                    className={`badge ${TASK_CATEGORY_BADGE[task.category]}`}
                  >
                    {TASK_CATEGORY_LABELS[task.category]}
                  </span>
                  <span className="text-slate-500">
                    {task.dueDate ? formatDate(task.dueDate) : "kein Datum"}
                  </span>
                  <span className="badge bg-slate-100 text-slate-700">
                    {STATUS_LABELS[task.status]}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Aktive Objekte</h2>
        {recentProperties.length === 0 ? (
          <div className="card text-sm text-slate-600">
            Noch keine Objekte. Lege unter{" "}
            <Link className="text-brand-600" href="/clients">
              Mandanten
            </Link>{" "}
            einen Mandanten und ein Objekt an.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {recentProperties.map((property) => (
              <Link
                key={property.id}
                href={`/properties/${property.id}`}
                className="card hover:shadow-md transition-shadow"
              >
                <div className="text-xs text-slate-500">
                  {property.client.company || property.client.name}
                </div>
                <div className="font-medium mt-1">{property.name}</div>
                <div className="text-xs text-slate-500 mt-0.5">
                  {property.city}
                </div>
                <div className="flex items-center justify-between mt-3 text-xs text-slate-500">
                  <span>
                    {property._count.tasks} Aufgabe
                    {property._count.tasks === 1 ? "" : "n"}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

type TaskCtx = {
  propertyId: string | null;
  projectId: string | null;
  clientId: string | null;
  property: { client: { name: string; company: string | null }; name: string } | null;
  project: { client: { name: string; company: string | null }; name: string } | null;
  client: { name: string; company: string | null } | null;
};

function taskHref(t: TaskCtx): string {
  if (t.propertyId) return `/properties/${t.propertyId}`;
  if (t.projectId) return `/projects/${t.projectId}`;
  if (t.clientId) return `/clients/${t.clientId}`;
  return "/tasks";
}

function taskContext(t: TaskCtx): string {
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
