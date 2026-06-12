import { revalidatePath } from "next/cache";
import { requireTeamMember } from "@/lib/access";
import { prisma } from "@/lib/prisma";
import { formatDateTime } from "@/lib/utils";

export default async function SettingsPage() {
  const user = await requireTeamMember();

  const [accounts, team] = await Promise.all([
    prisma.emailAccount.findMany({ orderBy: { createdAt: "asc" } }),
    prisma.user.findMany({
      where: { role: { in: ["TEAM_ADMIN", "TEAM_MEMBER"] } },
      orderBy: { createdAt: "asc" },
    }),
  ]);

  async function addAccount(formData: FormData) {
    "use server";
    const u = await requireTeamMember();
    if (u.role !== "TEAM_ADMIN") return;
    const email = (formData.get("email") as string)?.trim();
    const password = formData.get("password") as string;
    if (!email || !password) return;
    await prisma.emailAccount.create({
      data: {
        label: (formData.get("label") as string)?.trim() || email,
        email,
        username: (formData.get("username") as string)?.trim() || email,
        password,
        imapHost: (formData.get("imapHost") as string)?.trim(),
        imapPort: Number(formData.get("imapPort")) || 993,
        imapSecure: true,
        smtpHost: (formData.get("smtpHost") as string)?.trim(),
        smtpPort: Number(formData.get("smtpPort")) || 587,
        smtpSecure: Number(formData.get("smtpPort")) === 465,
      },
    });
    revalidatePath("/settings");
  }

  async function deleteAccount(formData: FormData) {
    "use server";
    const u = await requireTeamMember();
    if (u.role !== "TEAM_ADMIN") return;
    const id = formData.get("id") as string;
    await prisma.emailAccount.delete({ where: { id } });
    revalidatePath("/settings");
  }

  const isAdmin = user.role === "TEAM_ADMIN";

  return (
    <div className="space-y-8 max-w-3xl">
      <h1 className="text-2xl font-bold">Einstellungen</h1>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">📧 E-Mail-Konten (Team-Inbox)</h2>
        <p className="text-sm text-slate-600">
          Verbundene Postfächer werden in die zentrale Inbox synchronisiert.
          Für Gmail/Google Workspace: <code>imap.gmail.com</code> /{" "}
          <code>smtp.gmail.com</code> mit einem{" "}
          <a
            href="https://support.google.com/accounts/answer/185833"
            target="_blank"
            rel="noreferrer"
            className="text-brand-600"
          >
            App-Passwort
          </a>
          .
        </p>

        {accounts.length > 0 && (
          <div className="card p-0 divide-y divide-slate-100">
            {accounts.map((a) => (
              <div key={a.id} className="px-4 py-3 flex items-center justify-between">
                <div>
                  <div className="font-medium text-sm">
                    {a.label} <span className="text-slate-500">({a.email})</span>
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    IMAP {a.imapHost}:{a.imapPort} · SMTP {a.smtpHost}:{a.smtpPort}
                    {a.lastSyncAt && <> · letzter Sync: {formatDateTime(a.lastSyncAt)}</>}
                  </div>
                  {a.lastSyncError && (
                    <div className="text-xs text-rose-600 mt-0.5">
                      Fehler: {a.lastSyncError}
                    </div>
                  )}
                </div>
                {isAdmin && (
                  <form action={deleteAccount}>
                    <input type="hidden" name="id" value={a.id} />
                    <button className="btn-ghost text-rose-600 text-xs">Entfernen</button>
                  </form>
                )}
              </div>
            ))}
          </div>
        )}

        {isAdmin ? (
          <form action={addAccount} className="card grid grid-cols-2 gap-3">
            <div>
              <label className="label">Anzeigename</label>
              <input className="input" name="label" placeholder="z.B. Team-Inbox" />
            </div>
            <div>
              <label className="label">E-Mail-Adresse *</label>
              <input className="input" name="email" type="email" required placeholder="info@kromeichpartner.de" />
            </div>
            <div>
              <label className="label">Benutzername (falls abweichend)</label>
              <input className="input" name="username" />
            </div>
            <div>
              <label className="label">Passwort / App-Passwort *</label>
              <input className="input" name="password" type="password" required />
            </div>
            <div>
              <label className="label">IMAP-Host *</label>
              <input className="input" name="imapHost" required placeholder="imap.gmail.com" />
            </div>
            <div>
              <label className="label">IMAP-Port</label>
              <input className="input" name="imapPort" type="number" defaultValue={993} />
            </div>
            <div>
              <label className="label">SMTP-Host *</label>
              <input className="input" name="smtpHost" required placeholder="smtp.gmail.com" />
            </div>
            <div>
              <label className="label">SMTP-Port</label>
              <input className="input" name="smtpPort" type="number" defaultValue={587} />
            </div>
            <div className="col-span-2">
              <button className="btn-primary">Konto verbinden</button>
            </div>
          </form>
        ) : (
          <div className="card text-sm text-slate-600">
            Nur Admins können E-Mail-Konten verwalten.
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">👥 Team</h2>
        <div className="card p-0 divide-y divide-slate-100">
          {team.map((m) => (
            <div key={m.id} className="px-4 py-3 flex items-center justify-between text-sm">
              <div>
                <div className="font-medium">{m.name ?? m.email}</div>
                <div className="text-xs text-slate-500">{m.email}</div>
              </div>
              <span
                className={
                  m.role === "TEAM_ADMIN"
                    ? "badge bg-rose-100 text-rose-700"
                    : "badge bg-slate-100 text-slate-600"
                }
              >
                {m.role === "TEAM_ADMIN" ? "Admin" : "Team"}
              </span>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500">
          Neue Team-Mitglieder werden beim ersten Magic-Link-Login automatisch
          angelegt. Admin-Rechte über <code>TEAM_ADMIN_EMAILS</code> in der{" "}
          <code>.env</code>.
        </p>
      </section>
    </div>
  );
}
