import { revalidatePath } from "next/cache";
import { randomUUID } from "node:crypto";
import { writeFile, mkdir, unlink } from "node:fs/promises";
import { join } from "node:path";
import { prisma } from "@/lib/prisma";
import { requireTeamMember } from "@/lib/access";
import { formatBytes, formatDateTime } from "@/lib/utils";

const STORAGE_DIR = join(process.cwd(), "storage", "uploads");

export async function DocumentsList({ projectId }: { projectId: string }) {
  const docs = await prisma.document.findMany({
    where: { projectId },
    include: { uploadedBy: true },
    orderBy: { createdAt: "desc" },
  });

  async function uploadDocument(formData: FormData) {
    "use server";
    const user = await requireTeamMember();
    const file = formData.get("file") as File | null;
    if (!file || file.size === 0) return;

    await mkdir(STORAGE_DIR, { recursive: true });
    const storageKey = `${projectId}/${randomUUID()}-${file.name}`;
    const fullPath = join(STORAGE_DIR, storageKey);
    await mkdir(join(STORAGE_DIR, projectId), { recursive: true });
    const buffer = Buffer.from(await file.arrayBuffer());
    await writeFile(fullPath, buffer);

    await prisma.document.create({
      data: {
        projectId,
        uploadedById: user.id,
        filename: file.name,
        storageKey,
        mimeType: file.type || "application/octet-stream",
        sizeBytes: file.size,
        visibility: (formData.get("visibility") as "INTERNAL" | "SHARED_WITH_CLIENT") || "INTERNAL",
      },
    });
    revalidatePath(`/projects/${projectId}`);
  }

  async function deleteDocument(formData: FormData) {
    "use server";
    await requireTeamMember();
    const id = formData.get("id") as string;
    const doc = await prisma.document.findUnique({ where: { id } });
    if (!doc) return;
    try {
      await unlink(join(STORAGE_DIR, doc.storageKey));
    } catch {
      // Datei evtl. schon weg — nicht blockieren
    }
    await prisma.document.delete({ where: { id } });
    revalidatePath(`/projects/${projectId}`);
  }

  return (
    <div className="space-y-4">
      <form action={uploadDocument} className="card flex flex-col md:flex-row gap-3 md:items-end">
        <div className="flex-1">
          <label className="label">Datei hochladen</label>
          <input className="input" type="file" name="file" required />
        </div>
        <div>
          <label className="label">Sichtbarkeit</label>
          <select className="input" name="visibility" defaultValue="INTERNAL">
            <option value="INTERNAL">Intern</option>
            <option value="SHARED_WITH_CLIENT">Mit Mandant teilen (ab Phase 3)</option>
          </select>
        </div>
        <button className="btn-primary">Hochladen</button>
      </form>

      {docs.length === 0 ? (
        <div className="card text-sm text-slate-600">Noch keine Dokumente.</div>
      ) : (
        <div className="card p-0 divide-y divide-slate-100">
          {docs.map((d) => (
            <div key={d.id} className="px-4 py-3 flex items-center justify-between gap-3">
              <a
                href={`/api/documents/${d.id}`}
                className="flex-1 hover:text-brand-600"
              >
                <div className="font-medium">{d.filename}</div>
                <div className="text-xs text-slate-500 mt-0.5">
                  {formatBytes(d.sizeBytes)} · {d.uploadedBy.name ?? d.uploadedBy.email} · {formatDateTime(d.createdAt)}
                  {d.visibility === "SHARED_WITH_CLIENT" && (
                    <span className="ml-2 badge bg-amber-100 text-amber-800">Mandant</span>
                  )}
                </div>
              </a>
              <form action={deleteDocument}>
                <input type="hidden" name="id" value={d.id} />
                <button className="btn-ghost text-rose-600 text-xs">Löschen</button>
              </form>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
