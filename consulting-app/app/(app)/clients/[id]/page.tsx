import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { requireTeamMember } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import { createPropertyWithDefaults } from "@/lib/properties";

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
      properties: {
        where: { archivedAt: null },
        orderBy: { name: "asc" },
        include: {
          lease: { select: { analysisStatus: true } },
          _count: { select: { tasks: true } },
        },
      },
    },
  });

  if (!client) notFound();

  async function createProperty(formData: FormData) {
    "use server";
    await requireTeamMember();
    const name = (formData.get("name") as string)?.trim();
    if (!name) return;
    const property = await createPropertyWithDefaults({
      clientId: id,
      name,
      address: (formData.get("address") as string)?.trim() || null,
      city: (formData.get("city") as string)?.trim() || null,
      postalCode: (formData.get("postalCode") as string)?.trim() || null,
      applyTemplate: formData.get("applyTemplate") === "on",
    });
    redirect(`/properties/${property.id}`);
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
        <h2 className="text-lg font-semibold">Objekte</h2>

        <form
          action={createProperty}
          className="card grid grid-cols-1 md:grid-cols-3 gap-3 items-end"
        >
          <div className="md:col-span-2">
            <label className="label">Objektname *</label>
            <input
              className="input"
              name="name"
              required
              placeholder="z. B. Dieselstraße 72-90"
            />
          </div>
          <div>
            <label className="label">Stadt</label>
            <input className="input" name="city" placeholder="Mönchengladbach" />
          </div>
          <div className="md:col-span-2">
            <label className="label">Adresse</label>
            <input className="input" name="address" placeholder="Dieselstraße 72-90" />
          </div>
          <div>
            <label className="label">PLZ</label>
            <input className="input" name="postalCode" placeholder="41238" />
          </div>
          <div className="md:col-span-3 flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              name="applyTemplate"
              id="applyTemplate"
              defaultChecked
              className="h-4 w-4"
            />
            <label htmlFor="applyTemplate">
              Standard-Themen anlegen (Mietvertraganalyse, Wartung, Fristen, Mängel, NKA, Übergabe)
            </label>
          </div>
          <div className="md:col-span-3">
            <button className="btn-primary">Objekt anlegen</button>
          </div>
        </form>

        {client.properties.length === 0 ? (
          <div className="card text-sm text-slate-600">Noch keine Objekte.</div>
        ) : (
          <div className="card p-0 divide-y divide-slate-100">
            {client.properties.map((p) => (
              <Link
                key={p.id}
                href={`/properties/${p.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
              >
                <div>
                  <div className="font-medium">{p.name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {p.address ? `${p.address}, ` : ""}
                    {p.postalCode} {p.city}
                  </div>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <div>
                    {p._count.tasks} Aufgabe{p._count.tasks === 1 ? "" : "n"}
                  </div>
                  {p.lease && (
                    <div className="mt-0.5">MV: {leaseStatusLabel(p.lease.analysisStatus)}</div>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function leaseStatusLabel(s: string) {
  switch (s) {
    case "PENDING":
      return "offen";
    case "IN_PROGRESS":
      return "läuft";
    case "COMPLETED":
      return "fertig";
    default:
      return s;
  }
}
