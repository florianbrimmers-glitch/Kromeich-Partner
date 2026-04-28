import Link from "next/link";
import { notFound } from "next/navigation";
import { revalidatePath } from "next/cache";
import { requireTeamMember } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import { formatDate, STATUS_LABELS } from "@/lib/utils";

export default async function ClientDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  await requireTeamMember();
  const { id } = await params;

  const client = await prisma.client.findUnique({
    where: { id },
    include: {
      projects: {
        include: { _count: { select: { tasks: true } } },
        orderBy: { updatedAt: "desc" },
      },
    },
  });

  if (!client) notFound();

  async function createProject(formData: FormData) {
    "use server";
    await requireTeamMember();
    const name = (formData.get("name") as string)?.trim();
    if (!name) return;
    const deadline = formData.get("deadline") as string;
    await prisma.project.create({
      data: {
        clientId: id,
        name,
        description: (formData.get("description") as string)?.trim() || null,
        deadline: deadline ? new Date(deadline) : null,
      },
    });
    revalidatePath(`/clients/${id}`);
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href="/clients" className="text-sm text-slate-600 hover:text-slate-900">
          ← Mandanten
        </Link>
        <h1 className="text-2xl font-bold mt-1">{client.name}</h1>
        {client.company && (
          <div className="text-sm text-slate-600">{client.company}</div>
        )}
        <div className="text-xs text-slate-500 mt-1">
          {client.email && <span className="mr-3">{client.email}</span>}
          {client.phone && <span>{client.phone}</span>}
        </div>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Projekte</h2>
        <form action={createProject} className="card grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
          <div className="md:col-span-2">
            <label className="label">Projektname *</label>
            <input className="input" name="name" required />
          </div>
          <div>
            <label className="label">Deadline</label>
            <input className="input" name="deadline" type="date" />
          </div>
          <div className="md:col-span-3">
            <label className="label">Beschreibung</label>
            <textarea className="input" name="description" rows={2} />
          </div>
          <div className="md:col-span-3">
            <button className="btn-primary">Projekt anlegen</button>
          </div>
        </form>

        {client.projects.length === 0 ? (
          <div className="card text-sm text-slate-600">Noch keine Projekte.</div>
        ) : (
          <div className="card p-0 divide-y divide-slate-100">
            {client.projects.map((p) => (
              <Link
                key={p.id}
                href={`/projects/${p.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
              >
                <div>
                  <div className="font-medium">{p.name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {p._count.tasks} Aufgaben · Deadline {formatDate(p.deadline)}
                  </div>
                </div>
                <span className="badge bg-slate-100 text-slate-700">
                  {STATUS_LABELS[p.status]}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
