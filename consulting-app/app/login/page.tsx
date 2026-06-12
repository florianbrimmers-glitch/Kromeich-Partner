import { signIn } from "@/lib/auth";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ "check-mail"?: string; error?: string }>;
}) {
  const params = await searchParams;
  const checkMail = params["check-mail"];
  const error = params.error;

  const mailpitUrl =
    process.env.CODESPACE_NAME && process.env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN
      ? `https://${process.env.CODESPACE_NAME}-8025.${process.env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}`
      : "http://localhost:8025";

  async function handleSignIn(formData: FormData) {
    "use server";
    const email = formData.get("email") as string;
    await signIn("nodemailer", { email, redirectTo: "/dashboard" });
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm card">
        <h1 className="text-2xl font-bold text-slate-900 mb-1">Kromeich Consulting</h1>
        <p className="text-sm text-slate-600 mb-6">
          Login per Magic Link
        </p>

        {checkMail ? (
          <div className="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-800">
            Wir haben dir eine E-Mail mit dem Login-Link geschickt. Lokal findest
            du sie in Mailpit:{" "}
            <a className="underline font-medium" href={mailpitUrl} target="_blank" rel="noreferrer">
              {mailpitUrl.replace(/^https?:\/\//, "")}
            </a>
          </div>
        ) : (
          <form action={handleSignIn} className="space-y-4">
            <div>
              <label className="label" htmlFor="email">
                E-Mail
              </label>
              <input
                className="input"
                id="email"
                name="email"
                type="email"
                required
                autoComplete="email"
                placeholder="du@example.com"
              />
            </div>
            {error && (
              <div className="rounded-md bg-rose-50 border border-rose-200 p-3 text-sm text-rose-800">
                Login fehlgeschlagen. Bitte E-Mail prüfen.
              </div>
            )}
            <button type="submit" className="btn-primary w-full">
              Magic Link senden
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
