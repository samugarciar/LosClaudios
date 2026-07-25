import { headers } from "next/headers";
import { getDictionary, resolveLocale } from "@/lib/i18n";
import { ChatPanel } from "@/components/ChatPanel";

/**
 * Página única del MVP. Server component: resuelve el idioma y pasa el
 * diccionario ya materializado al panel de chat, que es el que necesita ser
 * cliente por el streaming.
 *
 * Pendiente del lote C: SafetyDisclaimer (banner permanente) y CitationDrawer.
 */

export default async function Page() {
  const locale = resolveLocale((await headers()).get("accept-language"));
  const dict = getDictionary(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col px-4 py-6 sm:px-6">
      <header className="mb-4 shrink-0">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
          {dict.app.title}
        </h1>
        <p className="mt-1 text-sm text-fg-muted">{dict.app.subtitle}</p>
      </header>

      <ChatPanel locale={locale} dict={dict} />
    </main>
  );
}
