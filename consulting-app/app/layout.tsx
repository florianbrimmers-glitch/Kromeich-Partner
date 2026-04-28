import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kromeich Consulting",
  description: "Internes Consulting-Tool",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}
