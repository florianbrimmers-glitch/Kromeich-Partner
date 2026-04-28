import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

export async function requireUser() {
  const session = await auth();
  if (!session?.user) redirect("/login");
  return session.user;
}

export async function requireTeamMember() {
  const user = await requireUser();
  if (user.role === "CLIENT") redirect("/login");
  return user;
}

export async function canAccessProject(userId: string, projectId: string): Promise<boolean> {
  const user = await prisma.user.findUnique({ where: { id: userId } });
  if (!user) return false;
  if (user.role === "TEAM_ADMIN") return true;

  const membership = await prisma.projectMember.findUnique({
    where: { projectId_userId: { projectId, userId } },
  });
  if (membership) return true;

  // Team-Mitglieder ohne explizite Zuweisung dürfen lesen
  return user.role === "TEAM_MEMBER";
}
