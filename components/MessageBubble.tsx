"use client";

import type { ReactNode } from "react";
import { CitationBadge } from "@/components/CitationBadge";
import type { Dictionary } from "@/lib/i18n";
import type { Message } from "@/lib/protocol";

/**
 * Burbuja de mensaje.
 *
 * El texto del agente se renderiza con un tokenizador propio y deliberadamente
 * mínimo: negrita `**así**` y marcadores de cita `[1]`. No se usa un parser de
 * markdown completo ni `dangerouslySetInnerHTML` — el contenido viene de un
 * modelo, así que tratarlo como HTML sería una vía de inyección directa.
 */

const INLINE_PATTERN = /(\*\*[^*\n]+\*\*|\[\d{1,2}\])/g;

interface MessageBubbleProps {
  message: Message;
  dict: Dictionary;
  /** Marcadores con cita real disponible. */
  knownMarkers: ReadonlySet<number>;
  onOpenCitation: (marker: number) => void;
  /** Añade el cursor de escritura al final (turno en curso). */
  streaming?: boolean;
}

export function MessageBubble({
  message,
  dict,
  knownMarkers,
  onOpenCitation,
  streaming = false,
}: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <article
      className={
        isUser
          ? "ml-auto max-w-[85%] rounded-lg bg-accent px-3 py-2 text-sm text-accent-contrast"
          : "max-w-[92%] rounded-lg bg-surface-sunken px-3 py-2 text-sm leading-relaxed"
      }
    >
      <span className="sr-only">{isUser ? dict.chat.you : dict.chat.advisor}: </span>

      {isUser ? (
        <span className="whitespace-pre-wrap">{message.content}</span>
      ) : (
        <span className="whitespace-pre-wrap">
          {renderInline(message.content, dict, knownMarkers, onOpenCitation)}
          {streaming && (
            <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-fg-muted align-middle" />
          )}
        </span>
      )}
    </article>
  );
}

function renderInline(
  text: string,
  dict: Dictionary,
  knownMarkers: ReadonlySet<number>,
  onOpenCitation: (marker: number) => void,
): ReactNode[] {
  const parts = text.split(INLINE_PATTERN);

  return parts.map((part, index) => {
    if (!part) return null;

    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={index} className="font-semibold">
          {part.slice(2, -2)}
        </strong>
      );
    }

    const citation = /^\[(\d{1,2})\]$/.exec(part);
    if (citation?.[1]) {
      const marker = Number.parseInt(citation[1], 10);
      // Marcador sin cita recuperada: se deja como texto plano en lugar de
      // ofrecer un botón que no lleva a ninguna fuente.
      if (!knownMarkers.has(marker)) return part;
      return (
        <CitationBadge
          key={index}
          marker={marker}
          dict={dict}
          onOpen={onOpenCitation}
        />
      );
    }

    return part;
  });
}
