import Link from "next/link";
import { requireTeamMember } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import { formatDate, STATUS_LABELS } from "@/lib/utils";

export default async function ProjectsListPage() {
  await requireTeamMember();

  const projects = await prisma.project.findMany({
    orderBy: { updatedAt: "desc" },
    include: {
      client: true,
      _count: { select: { tasks: true } },
    },
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Projekte</h1>
      {projects.length === 0 ? (
        <div className="card text-sm text-slate-600">
          Noch keine Projekte.{" "}
          <Link href="/clients" className="text-brand-600">
            Lege zuerst einen Mandanten an.
          </Link>
        </div>
      ) : (
        <div className="card p-0 divide-y divide-slate-100">
          {projects.map((p) => (
            <Link
              key={p.id}
              href={`/projects/${p.id}`}
              className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
            >
              <div>
                <div className="text-xs text-slate-500">{p.client.name}</div>
                <div className="font-medium">{p.name}</div>
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <span>{p._count.tasks} Aufgaben</span>
                <span>Deadline {formatDate(p.deadline)}</span>
                <span className="badge bg-slate-100 text-slate-700">
                  {STATUS_LABELS[p.status]}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
