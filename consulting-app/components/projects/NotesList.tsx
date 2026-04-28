import ReactMarkdown from "react-markdown";
import { revalidatePath } from "next/cache";
import { prisma } from "@/lib/prisma";
import { requireTeamMember } from "@/lib/access";
import { formatDateTime } from "@/lib/utils";

export async function NotesList({ projectId }: { projectId: string }) {
  const notes = await prisma.note.findMany({
    where: { projectId },
    include: { author: true },
    orderBy: { createdAt: "desc" },
  });

  async function createNote(formData: FormData) {
    "use server";
    const user = await requireTeamMember();
    const title = (formData.get("title") as string)?.trim();
    const content = (formData.get("content") as string)?.trim();
    if (!title || !content) return;
    await prisma.note.create({
      data: {
        projectId,
        authorId: user.id,
        title,
        content,
        visibility: (formData.get("visibility") as "INTERNAL" | "SHARED_WITH_CLIENT") || "INTERNAL",
      },
    });
    revalidatePath(`/projects/${projectId}`);
  }

  async function deleteNote(formData: FormData) {
    "use server";
    await requireTeamMember();
    const id = formData.get("id") as string;
    await prisma.note.delete({ where: { id } });
    revalidatePath(`/projects/${projectId}`);
  }

  return (
    <div className="space-y-4">
      <form action={createNote} className="card space-y-3">
        <div>
          <label className="label">Titel</label>
          <input className="input" name="title" required />
        </div>
        <div>
          <label className="label">Inhalt (Markdown)</label>
          <textarea className="input font-mono text-sm" name="content" rows={5} required />
        </div>
        <div className="flex items-center justify-between">
          <select name="visibility" className="input max-w-xs" defaultValue="INTERNAL">
            <option value="INTERNAL">Intern</option>
            <option value="SHARED_WITH_CLIENT">Mit Mandant teilen (ab Phase 3)</option>
          </select>
          <button className="btn-primary">Notiz speichern</button>
        </div>
      </form>

      {notes.length === 0 ? (
        <div className="card text-sm text-slate-600">Noch keine Notizen.</div>
      ) : (
        <div className="space-y-3">
          {notes.map((n) => (
            <div key={n.id} className="card">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <div className="font-medium">{n.title}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {n.author.name ?? n.author.email} · {formatDateTime(n.createdAt)}
                    {n.visibility === "SHARED_WITH_CLIENT" && (
                      <span className="ml-2 badge bg-amber-100 text-amber-800">Mandant</span>
                    )}
                  </div>
                </div>
                <form action={deleteNote}>
                  <input type="hidden" name="id" value={n.id} />
                  <button className="btn-ghost text-rose-600 text-xs">Löschen</button>
                </form>
              </div>
              <div className="prose prose-sm max-w-none">
                <ReactMarkdown>{n.content}</ReactMarkdown>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
