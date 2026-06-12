import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { syncAllAccounts } from "@/lib/email/sync";

// Manuell (eingeloggtes Team) oder per Cron mit Bearer-Token (CRON_SECRET):
//   curl -X POST -H "Authorization: Bearer $CRON_SECRET" https://…/api/email/sync
export async function POST(req: NextRequest) {
  const cronSecret = process.env.CRON_SECRET;
  const authHeader = req.headers.get("authorization");
  const viaCron = cronSecret && authHeader === `Bearer ${cronSecret}`;

  if (!viaCron) {
    const session = await auth();
    if (!session?.user || session.user.role === "CLIENT") {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  const results = await syncAllAccounts();
  return NextResponse.json({ results });
}
