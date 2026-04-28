import { NextRequest } from "next/server";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { auth } from "@/lib/auth";
import { prisma } from "@/lib/prisma";

const STORAGE_DIR = join(process.cwd(), "storage", "uploads");

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await auth();
  if (!session?.user) {
    return new Response("Unauthorized", { status: 401 });
  }
  const { id } = await params;
  const doc = await prisma.document.findUnique({ where: { id } });
  if (!doc) return new Response("Not found", { status: 404 });

  // Mandanten dürfen nur SHARED_WITH_CLIENT sehen
  if (session.user.role === "CLIENT" && doc.visibility !== "SHARED_WITH_CLIENT") {
    return new Response("Forbidden", { status: 403 });
  }

  try {
    const buffer = await readFile(join(STORAGE_DIR, doc.storageKey));
    return new Response(buffer, {
      headers: {
        "Content-Type": doc.mimeType,
        "Content-Disposition": `inline; filename="${encodeURIComponent(doc.filename)}"`,
      },
    });
  } catch {
    return new Response("File missing on disk", { status: 410 });
  }
}
