import type { Metadata } from "next";
import { headers } from "next/headers";
import { getDictionary, resolveLocale } from "@/lib/i18n";
import "./globals.css";

/**
 * No se usan fuentes web: la tipografía sale del stack del sistema
 * (`--font-sans` en globals.css). Evita una descarga en el build y una
 * dependencia externa mientras no haya guía de marca.
 */

export async function generateMetadata(): Promise<Metadata> {
  const locale = resolveLocale((await headers()).get("accept-language"));
  const dict = getDictionary(locale);
  return {
    title: dict.app.title,
    description: dict.app.subtitle,
    robots: { index: false, follow: false }, // MVP: fuera de índices de búsqueda
  };
}

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = resolveLocale((await headers()).get("accept-language"));

  return (
    <html lang={locale}>
      <body className="min-h-dvh bg-surface text-fg">{children}</body>
    </html>
  );
}
