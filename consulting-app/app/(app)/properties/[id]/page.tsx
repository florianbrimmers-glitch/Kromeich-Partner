import Link from "next/link";
import { notFound } from "next/navigation";
import { revalidatePath } from "next/cache";
import { requireTeamMember } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import {
  formatDate,
  STATUS_LABELS,
  TASK_CATEGORY_ORDER,
  TASK_CATEGORY_LABELS,
  TASK_CATEGORY_BADGE,
} from "@/lib/utils";

export default async function PropertyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  await requireTeamMember();
  const { id } = await params;

  const property = await prisma.property.findUnique({
    where: { id },
    include: {
      client: true,
      lease: true,
      tasks: { orderBy: [{ status: "asc" }, { dueDate: "asc" }, { createdAt: "desc" }] },
      notes: { include: { author: true }, orderBy: { createdAt: "desc" } },
      emailThreads: {
        orderBy: { lastMessageAt: "desc" },
        include: { _count: { select: { messages: true } } },
      },
    },
  });

  if (!property) notFound();

  // Aufgaben nach Kategorie gruppieren — Reihenfolge wie in TASK_CATEGORY_ORDER.
  const tasksByCategory = new Map<string, typeof property.tasks>();
  for (const cat of TASK_CATEGORY_ORDER) tasksByCategory.set(cat, []);
  for (const t of property.tasks) {
    tasksByCategory.get(t.category)?.push(t);
  }

  async function saveLease(formData: FormData) {
    "use server";
    await requireTeamMember();
    const data = {
      landlord: ((formData.get("landlord") as string) || "").trim() || null,
      tenant: ((formData.get("tenant") as string) || "").trim() || null,
      startDate: parseDate(formData.get("startDate")),
      endDate: parseDate(formData.get("endDate")),
      hasOption: formData.get("hasOption") === "on",
      optionDetails: ((formData.get("optionDetails") as string) || "").trim() || null,
      indexClause: ((formData.get("indexClause") as string) || "").trim() || null,
      noticePeriod: ((formData.get("noticePeriod") as string) || "").trim() || null,
      monthlyRent: parseDecimal(formData.get("monthlyRent")),
      analysisStatus: (formData.get("analysisStatus") as string) || "PENDING",
      notesMarkdown:
        ((formData.get("notesMarkdown") as string) || "").trim() || null,
    };
    await prisma.lease.upsert({
      where: { propertyId: id },
      create: { propertyId: id, ...data },
      update: data,
    });
    revalidatePath(`/properties/${id}`);
  }

  async function createTask(formData: FormData) {
    "use server";
    await requireTeamMember();
    const title = (formData.get("title") as string)?.trim();
    if (!title) return;
    await prisma.task.create({
      data: {
        propertyId: id,
        title,
        category: (formData.get("category") as
          | "LEASE_ANALYSIS"
          | "MAINTENANCE"
          | "DEADLINE"
          | "DEFECT"
          | "NKA"
          | "AMENDMENT"
          | "REPORTING"
          | "HANDOVER"
          | "CORRESPONDENCE"
          | "GENERIC") || "GENERIC",
        priority: (formData.get("priority") as
          | "LOW"
          | "MEDIUM"
          | "HIGH"
          | "URGENT") || "MEDIUM",
        dueDate: parseDate(formData.get("dueDate")),
        description: ((formData.get("description") as string) || "").trim() || null,
      },
    });
    revalidatePath(`/properties/${id}`);
  }

  async function toggleTaskDone(taskId: string, currentStatus: string) {
    "use server";
    await requireTeamMember();
    await prisma.task.update({
      where: { id: taskId },
      data: { status: currentStatus === "DONE" ? "TODO" : "DONE" },
    });
    revalidatePath(`/properties/${id}`);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="text-sm text-slate-600 flex items-center gap-1">
          <Link href="/clients" className="hover:text-slate-900">
            Mandanten
          </Link>
          <span>›</span>
          <Link
            href={`/clients/${property.client.id}`}
            className="hover:text-slate-900"
          >
            {property.client.company || property.client.name}
          </Link>
        </div>
        <h1 className="text-2xl font-bold mt-1">{property.name}</h1>
        {(property.address || property.city) && (
          <div className="text-sm text-slate-600 mt-0.5">
            {property.address}
            {property.address && (property.postalCode || property.city) ? ", " : ""}
            {property.postalCode} {property.city}
          </div>
        )}
        {property.description && (
          <p className="text-sm text-slate-700 mt-3 whitespace-pre-wrap">
            {property.description}
          </p>
        )}
      </div>

      {/* Mietvertrag */}
      <section className="card space-y-4">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">Mietvertrag</h2>
          {property.lease && (
            <span className="text-xs text-slate-500">
              Analyse: {leaseStatusLabel(property.lease.analysisStatus)}
            </span>
          )}
        </div>
        <form action={saveLease} className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="label">Vermieter</label>
            <input
              className="input"
              name="landlord"
              defaultValue={property.lease?.landlord || ""}
            />
          </div>
          <div>
            <label className="label">Mieter</label>
            <input
              className="input"
              name="tenant"
              defaultValue={property.lease?.tenant || ""}
            />
          </div>
          <div>
            <label className="label">Mietbeginn</label>
            <input
              className="input"
              name="startDate"
              type="date"
              defaultValue={dateInput(property.lease?.startDate)}
            />
          </div>
          <div>
            <label className="label">Mietende</label>
            <input
              className="input"
              name="endDate"
              type="date"
              defaultValue={dateInput(property.lease?.endDate)}
            />
          </div>
          <div>
            <label className="label">Monatsmiete (EUR)</label>
            <input
              className="input"
              name="monthlyRent"
              type="number"
              step="0.01"
              defaultValue={property.lease?.monthlyRent?.toString() || ""}
            />
          </div>
          <div>
            <label className="label">Analyse-Status</label>
            <select
              className="input"
              name="analysisStatus"
              defaultValue={property.lease?.analysisStatus || "PENDING"}
            >
              <option value="PENDING">Offen</option>
              <option value="IN_PROGRESS">In Arbeit</option>
              <option value="COMPLETED">Abgeschlossen</option>
            </select>
          </div>
          <div className="md:col-span-2 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="hasOption"
              id="hasOption"
              defaultChecked={property.lease?.hasOption || false}
              className="h-4 w-4"
            />
            <label htmlFor="hasOption">Option / Verlängerung vorhanden</label>
          </div>
          <div>
            <label className="label">Optionsdetails</label>
            <input
              className="input"
              name="optionDetails"
              defaultValue={property.lease?.optionDetails || ""}
              placeholder="z. B. +5 Jahre, Ausübung 12 Mon. vor Ende"
            />
          </div>
          <div>
            <label className="label">Indexierung</label>
            <input
              className="input"
              name="indexClause"
              defaultValue={property.lease?.indexClause || ""}
              placeholder="Staffel, VPI, ..."
            />
          </div>
          <div className="md:col-span-2">
            <label className="label">Kündigungsfrist</label>
            <input
              className="input"
              name="noticePeriod"
              defaultValue={property.lease?.noticePeriod || ""}
            />
          </div>
          <div className="md:col-span-2">
            <label className="label">Notizen</label>
            <textarea
              className="input"
              name="notesMarkdown"
              rows={3}
              defaultValue={property.lease?.notesMarkdown || ""}
              placeholder="Auffälligkeiten, Sonderregelungen, …"
            />
          </div>
          <div className="md:col-span-2">
            <button className="btn-primary">Speichern</button>
          </div>
        </form>
      </section>

      {/* Aufgaben — neue Aufgabe + Kategorie-Buckets */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Aufgaben</h2>

        <form
          action={createTask}
          className="card grid grid-cols-1 md:grid-cols-12 gap-3 items-end"
        >
          <div className="md:col-span-5">
            <label className="label">Titel *</label>
            <input className="input" name="title" required />
          </div>
          <div className="md:col-span-3">
            <label className="label">Kategorie</label>
            <select className="input" name="category" defaultValue="GENERIC">
              {TASK_CATEGORY_ORDER.map((c) => (
                <option key={c} value={c}>
                  {TASK_CATEGORY_LABELS[c]}
                </option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="label">Priorität</label>
            <select className="input" name="priority" defaultValue="MEDIUM">
              <option value="LOW">Niedrig</option>
              <option value="MEDIUM">Mittel</option>
              <option value="HIGH">Hoch</option>
              <option value="URGENT">Dringend</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="label">Fällig</label>
            <input className="input" name="dueDate" type="date" />
          </div>
          <div className="md:col-span-12">
            <label className="label">Beschreibung</label>
            <textarea className="input" name="description" rows={2} />
          </div>
          <div className="md:col-span-12">
            <button className="btn-primary">Aufgabe anlegen</button>
          </div>
        </form>

        {TASK_CATEGORY_ORDER.filter((c) => (tasksByCategory.get(c) || []).length > 0).map(
          (cat) => (
            <div key={cat} className="space-y-2">
              <div className="flex items-center gap-2">
                <span
                  className={`badge ${TASK_CATEGORY_BADGE[cat]}`}
                >
                  {TASK_CATEGORY_LABELS[cat]}
                </span>
                <span className="text-xs text-slate-500">
                  {tasksByCategory.get(cat)!.length}
                </span>
              </div>
              <div className="card p-0 divide-y divide-slate-100">
                {tasksByCategory.get(cat)!.map((t) => (
                  <div key={t.id} className="px-4 py-3 flex items-start gap-3">
                    <form
                      action={async () => {
                        "use server";
                        await toggleTaskDone(t.id, t.status);
                      }}
                    >
                      <button
                        type="submit"
                        title={t.status === "DONE" ? "Wieder öffnen" : "Erledigt"}
                        className={`h-5 w-5 rounded-full border-2 flex items-center justify-center text-xs mt-0.5 ${
                          t.status === "DONE"
                            ? "bg-emerald-500 border-emerald-500 text-white"
                            : "border-slate-300 hover:border-emerald-500"
                        }`}
                      >
                        {t.status === "DONE" ? "✓" : ""}
                      </button>
                    </form>
                    <div className="flex-1 min-w-0">
                      <div
                        className={`text-sm font-medium ${
                          t.status === "DONE" ? "line-through text-slate-400" : ""
                        }`}
                      >
                        {t.title}
                      </div>
                      {t.description && (
                        <div className="text-xs text-slate-600 mt-1 whitespace-pre-wrap">
                          {t.description}
                        </div>
                      )}
                      <div className="text-xs text-slate-500 mt-1 flex gap-3">
                        <span>{STATUS_LABELS[t.status]}</span>
                        {t.dueDate && <span>fällig {formatDate(t.dueDate)}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ),
        )}

        {property.tasks.length === 0 && (
          <div className="card text-sm text-slate-600">
            Noch keine Aufgaben — leg oben die erste an.
          </div>
        )}
      </section>

      {/* Inbox-Threads zum Objekt */}
      {property.emailThreads.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Korrespondenz</h2>
          <div className="card p-0 divide-y divide-slate-100">
            {property.emailThreads.map((th) => (
              <Link
                key={th.id}
                href={`/inbox/${th.id}`}
                className="block px-4 py-3 hover:bg-slate-50"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <div
                    className={`text-sm ${
                      th.unread ? "font-semibold" : "font-medium"
                    }`}
                  >
                    {th.subject}
                  </div>
                  <div className="text-xs text-slate-500 whitespace-nowrap">
                    {formatDate(th.lastMessageAt)}
                  </div>
                </div>
                <div className="text-xs text-slate-500 mt-0.5">
                  {th._count.messages} Nachricht{th._count.messages === 1 ? "" : "en"}
                  {th.unread ? " · ungelesen" : ""}
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Notizen */}
      {property.notes.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Notizen</h2>
          {property.notes.map((n) => (
            <div key={n.id} className="card space-y-1">
              <div className="flex items-baseline justify-between">
                <div className="font-medium">{n.title}</div>
                <div className="text-xs text-slate-500">
                  {n.author?.name || n.author?.email} · {formatDate(n.createdAt)}
                </div>
              </div>
              <div className="text-sm text-slate-700 whitespace-pre-wrap">
                {n.content}
              </div>
            </div>
          ))}
        </section>
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

function dateInput(d: Date | null | undefined): string {
  if (!d) return "";
  const date = new Date(d);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function parseDate(v: FormDataEntryValue | null): Date | null {
  if (!v || typeof v !== "string" || v.trim() === "") return null;
  return new Date(v);
}

function parseDecimal(v: FormDataEntryValue | null): number | null {
  if (!v || typeof v !== "string" || v.trim() === "") return null;
  const n = Number(v.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}
