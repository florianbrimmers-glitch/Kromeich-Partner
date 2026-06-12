import Link from "next/link";
import { requireUser } from "@/lib/access";
import { signOut } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireUser();

  const unreadCount = await prisma.emailThread.count({
    where: { status: "OPEN", unread: true },
  });

  async function handleSignOut() {
    "use server";
    await signOut({ redirectTo: "/login" });
  }

  return (
    <div className="min-h-screen flex">
      <aside className="w-60 bg-slate-900 text-slate-100 flex flex-col">
        <div className="px-5 py-5 border-b border-slate-800">
          <div className="font-semibold">Kromeich Consulting</div>
          <div className="text-xs text-slate-400 mt-0.5">{user.email}</div>
        </div>
        <nav className="flex-1 p-3 space-y-1 text-sm">
          <NavLink href="/dashboard" label="Dashboard" />
          <Link
            href="/inbox"
            className="flex items-center justify-between px-3 py-1.5 rounded hover:bg-slate-800 transition-colors"
          >
            <span>Inbox</span>
            {unreadCount > 0 && (
              <span className="badge bg-brand-500 text-white">{unreadCount}</span>
            )}
          </Link>
          <NavLink href="/clients" label="Mandanten" />
          <NavLink href="/projects" label="Projekte" />
          <NavLink href="/tasks" label="Meine Aufgaben" />
          <NavLink href="/settings" label="Einstellungen" />
        </nav>
        <form action={handleSignOut} className="p-3 border-t border-slate-800">
          <button className="w-full text-left px-3 py-1.5 rounded text-sm text-slate-300 hover:bg-slate-800">
            Abmelden
          </button>
        </form>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-8 py-8">{children}</div>
      </main>
    </div>
  );
}

function NavLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="block px-3 py-1.5 rounded hover:bg-slate-800 transition-colors"
    >
      {label}
    </Link>
  );
}
