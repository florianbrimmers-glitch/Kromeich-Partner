import Link from "next/link";
import { redirect } from "next/navigation";
import { requireTeamMember } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import { sendNewMail } from "@/lib/email/send";

export default async function ComposePage() {
  await requireTeamMember();

  const [accounts, projects] = await Promise.all([
    prisma.emailAccount.findMany({ orderBy: { createdAt: "asc" } }),
    prisma.project.findMany({
      where: { status: { in: ["ACTIVE", "ON_HOLD"] } },
      include: { client: true },
      orderBy: { updatedAt: "desc" },
    }),
  ]);

  async function send(formData: FormData) {
    "use server";
    await requireTeamMember();
    const accountId = formData.get("accountId") as string;
    const to = (formData.get("to") as string)?.trim();
    const subject = (formData.get("subject") as string)?.trim();
    const body = (formData.get("body") as string)?.trim();
    const projectId = (formData.get("projectId") as string) || null;
    if (!accountId || !to || !subject || !body) return;
    const threadId = await sendNewMail({ accountId, to, subject, body, projectId });
    redirect(`/inbox/${threadId}`);
  }

  if (accounts.length === 0) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Neue E-Mail</h1>
        <div className="card text-sm text-slate-600">
          Kein Postfach verbunden. Lege zuerst unter{" "}
          <Link href="/settings" className="text-brand-600">
            Einstellungen
          </Link>{" "}
          ein E-Mail-Konto an.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 max-w-2xl">
      <div>
        <Link href="/inbox" className="text-sm text-slate-600 hover:text-slate-900">
          ← Inbox
        </Link>
        <h1 className="text-2xl font-bold mt-1">Neue E-Mail</h1>
      </div>

      <form action={send} className="card space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Von</label>
            <select className="input" name="accountId" required>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label} ({a.email})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Projekt (optional)</label>
            <select className="input" name="projectId">
              <option value="">— kein Projekt —</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.client.name} · {p.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className="label">An</label>
          <input className="input" name="to" type="email" required placeholder="empfaenger@firma.de" />
        </div>
        <div>
          <label className="label">Betreff</label>
          <input className="input" name="subject" required />
        </div>
        <div>
          <label className="label">Nachricht</label>
          <textarea className="input font-mono text-sm" name="body" rows={10} required />
        </div>
        <div className="flex justify-end">
          <button className="btn-primary">Senden</button>
        </div>
      </form>
    </div>
  );
}
