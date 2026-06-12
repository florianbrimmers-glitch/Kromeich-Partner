// In GitHub Codespaces läuft die App hinter einem Reverse-Proxy. Next.js 15
// blockiert Server Actions, wenn der Origin nicht in der Allowlist steht,
// sonst schlägt jedes Form-Submit mit
// "An unexpected response was received from the server" fehl.
const allowedOrigins = ["localhost:3000"];
if (
  process.env.CODESPACE_NAME &&
  process.env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN
) {
  allowedOrigins.push(
    `${process.env.CODESPACE_NAME}-3000.${process.env.GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}`,
  );
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverActions: {
      bodySizeLimit: "25mb",
      allowedOrigins,
    },
  },
};

module.exports = nextConfig;
