import Link from "next/link";
import { requireTeamMember } from "@/lib/access";
import { prisma } from "@/lib/prisma";

export default async function PropertiesPage() {
  await requireTeamMember();

  const properties = await prisma.property.findMany({
    where: { archivedAt: null },
    orderBy: [{ client: { name: "asc" } }, { name: "asc" }],
    include: {
      client: { select: { id: true, name: true, company: true } },
      lease: { select: { analysisStatus: true } },
      _count: { select: { tasks: true, emailThreads: true } },
    },
  });

  // Gruppieren nach Mandant, damit die Liste schnell scanbar ist.
  const byClient = new Map<
    string,
    { name: string; company: string | null; items: typeof properties }
  >();
  for (const p of properties) {
    const k = p.client.id;
    if (!byClient.has(k)) {
      byClient.set(k, { name: p.client.name, company: p.client.company, items: [] });
    }
    byClient.get(k)!.items.push(p);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold">Objekte</h1>
        <div className="text-sm text-slate-500">
          {properties.length} Objekt{properties.length === 1 ? "" : "e"}
          {" · "}
          {byClient.size} Mandant{byClient.size === 1 ? "" : "en"}
        </div>
      </div>

      {properties.length === 0 ? (
        <div className="card text-sm text-slate-600">
          Noch keine Objekte. Lege eines über einen Mandanten an.
        </div>
      ) : (
        <div className="space-y-5">
          {Array.from(byClient.entries()).map(([clientId, group]) => (
            <section key={clientId} className="space-y-2">
              <Link
                href={`/clients/${clientId}`}
                className="text-sm font-medium text-slate-600 hover:text-slate-900"
              >
                {group.company || group.name}
              </Link>
              <div className="card p-0 divide-y divide-slate-100">
                {group.items.map((p) => (
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
                    <div className="text-right text-xs text-slate-500 space-y-0.5">
                      <div>
                        {p._count.tasks} Aufgaben
                        {p._count.emailThreads > 0
                          ? ` · ${p._count.emailThreads} Mails`
                          : ""}
                      </div>
                      {p.lease && (
                        <div>MV: {leaseStatusLabel(p.lease.analysisStatus)}</div>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
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
