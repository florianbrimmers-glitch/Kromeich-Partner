import Link from "next/link";
import { revalidatePath } from "next/cache";
import { requireTeamMember } from "@/lib/access";
import { prisma } from "@/lib/prisma";

export default async function ClientsPage() {
  await requireTeamMember();

  const clients = await prisma.client.findMany({
    orderBy: { name: "asc" },
    include: { _count: { select: { projects: true } } },
  });

  async function createClient(formData: FormData) {
    "use server";
    await requireTeamMember();
    const name = (formData.get("name") as string)?.trim();
    if (!name) return;
    await prisma.client.create({
      data: {
        name,
        company: (formData.get("company") as string)?.trim() || null,
        email: (formData.get("email") as string)?.trim() || null,
        phone: (formData.get("phone") as string)?.trim() || null,
      },
    });
    revalidatePath("/clients");
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Mandanten</h1>

      <form action={createClient} className="card grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
        <div>
          <label className="label">Name *</label>
          <input className="input" name="name" required />
        </div>
        <div>
          <label className="label">Firma</label>
          <input className="input" name="company" />
        </div>
        <div>
          <label className="label">E-Mail</label>
          <input className="input" name="email" type="email" />
        </div>
        <div className="flex gap-2">
          <input className="input" name="phone" placeholder="Telefon" />
          <button className="btn-primary whitespace-nowrap">Anlegen</button>
        </div>
      </form>

      {clients.length === 0 ? (
        <div className="card text-sm text-slate-600">Noch keine Mandanten.</div>
      ) : (
        <div className="card p-0 divide-y divide-slate-100">
          {clients.map((c) => (
            <Link
              key={c.id}
              href={`/clients/${c.id}`}
              className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
            >
              <div>
                <div className="font-medium">{c.name}</div>
                {c.company && <div className="text-xs text-slate-500">{c.company}</div>}
              </div>
              <div className="text-xs text-slate-500">
                {c._count.projects} Projekt{c._count.projects === 1 ? "" : "e"}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
