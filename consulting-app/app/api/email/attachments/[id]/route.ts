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
  if (!session?.user || session.user.role === "CLIENT") {
    return new Response("Unauthorized", { status: 401 });
  }
  const { id } = await params;
  const att = await prisma.emailAttachment.findUnique({ where: { id } });
  if (!att) return new Response("Not found", { status: 404 });

  try {
    const buffer = await readFile(join(STORAGE_DIR, att.storageKey));
    return new Response(buffer, {
      headers: {
        "Content-Type": att.mimeType,
        "Content-Disposition": `inline; filename="${encodeURIComponent(att.filename)}"`,
      },
    });
  } catch {
    return new Response("File missing on disk", { status: 410 });
  }
}
