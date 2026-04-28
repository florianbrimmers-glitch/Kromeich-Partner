import Link from "next/link";
import { requireUser } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import { formatDate, STATUS_LABELS } from "@/lib/utils";

export default async function DashboardPage() {
  const user = await requireUser();

  const [myTasks, recentProjects, taskCount] = await Promise.all([
    prisma.task.findMany({
      where: {
        assigneeId: user.id,
        status: { in: ["TODO", "IN_PROGRESS", "REVIEW"] },
      },
      include: { project: { include: { client: true } } },
      orderBy: [{ dueDate: "asc" }, { priority: "desc" }],
      take: 10,
    }),
    prisma.project.findMany({
      where: { status: { in: ["ACTIVE", "ON_HOLD"] } },
      include: { client: true, _count: { select: { tasks: true } } },
      orderBy: { updatedAt: "desc" },
      take: 5,
    }),
    prisma.task.count({
      where: {
        assigneeId: user.id,
        status: { in: ["TODO", "IN_PROGRESS"] },
      },
    }),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Hallo {user.name ?? user.email}</h1>
        <p className="text-slate-600 mt-1">
          {taskCount === 0
            ? "Keine offenen Aufgaben — gut gemacht."
            : `Du hast ${taskCount} offene Aufgabe${taskCount === 1 ? "" : "n"}.`}
        </p>
      </div>

      <section>
        <h2 className="text-lg font-semibold mb-3">Meine Aufgaben</h2>
        {myTasks.length === 0 ? (
          <div className="card text-sm text-slate-600">
            Keine offenen Aufgaben.
          </div>
        ) : (
          <div className="card divide-y divide-slate-100 p-0">
            {myTasks.map((task) => (
              <Link
                key={task.id}
                href={`/projects/${task.projectId}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
              >
                <div>
                  <div className="font-medium">{task.title}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {task.project.client.name} · {task.project.name}
                  </div>
                </div>
                <div className="flex items-center gap-3 text-xs">
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
        <h2 className="text-lg font-semibold mb-3">Aktive Projekte</h2>
        {recentProjects.length === 0 ? (
          <div className="card text-sm text-slate-600">
            Noch keine Projekte. Lege unter <Link className="text-brand-600" href="/clients">Mandanten</Link> einen Mandanten und ein Projekt an.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {recentProjects.map((project) => (
              <Link
                key={project.id}
                href={`/projects/${project.id}`}
                className="card hover:shadow-md transition-shadow"
              >
                <div className="text-xs text-slate-500">{project.client.name}</div>
                <div className="font-medium mt-1">{project.name}</div>
                <div className="flex items-center justify-between mt-3 text-xs text-slate-500">
                  <span>{project._count.tasks} Aufgaben</span>
                  <span className="badge bg-slate-100 text-slate-700">
                    {STATUS_LABELS[project.status]}
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
