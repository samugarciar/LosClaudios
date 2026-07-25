import { headers } from "next/headers";
import { getDictionary, resolveLocale } from "@/lib/i18n";
import { ChatPanel } from "@/components/ChatPanel";
import { SafetyDisclaimer } from "@/components/SafetyDisclaimer";

/**
 * Página única del MVP. Server component: resuelve el idioma y pasa el
 * diccionario ya materializado al panel de chat, que es el que necesita ser
 * cliente por el streaming.
 *
 * El CitationDrawer vive dentro de ChatPanel y no aquí: depende del estado de
 * citas, que es estado de cliente.
 */

export default async function Page() {
  const locale = resolveLocale((await headers()).get("accept-language"));
  const dict = getDictionary(locale);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col px-4 py-6 sm:px-6">
      <header className="mb-3 shrink-0">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
          {dict.app.title}
        </h1>
        <p className="mt-1 text-sm text-fg-muted">{dict.app.subtitle}</p>
      </header>

      {/* Permanente por diseño: el límite de alcance no es plegable (README §1). */}
      <div className="mb-3">
        <SafetyDisclaimer dict={dict} />
      </div>

      <ChatPanel locale={locale} dict={dict} />
    </main>
  );
}
