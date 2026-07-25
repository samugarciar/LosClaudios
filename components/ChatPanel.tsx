"use client";

import { useEffect, useRef } from "react";
import { useChat } from "@/lib/useChat";
import { Composer } from "@/components/Composer";
import { STAGES, type Locale } from "@/lib/protocol";
import type { Dictionary } from "@/lib/i18n";

/**
 * Contenedor del chat.
 *
 * NOTA DE ETAPA — el lote B renderiza los mensajes con marcado inline y no
 * muestra chips, candidatos ni handoff (existen en el estado, se ven en la
 * tira de diagnóstico de desarrollo). El lote C sustituye ese marcado por
 * MessageBubble / ChipGroup / CandidateCard / HandoffForm, lo que implica
 * MODIFICAR este fichero. Está anticipado, no es un cambio sorpresa.
 */

interface ChatPanelProps {
  locale: Locale;
  dict: Dictionary;
}

export function ChatPanel({ locale, dict }: ChatPanelProps) {
  const chat = useChat(locale);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chat.messages, chat.streamingText]);

  const isStreaming = chat.status === "streaming";
  const isEmpty = chat.messages.length === 0 && !chat.streamingText;

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-3">
      <StageIndicator current={chat.stage} dict={dict} />

      <div
        className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-lg border border-border-subtle bg-surface-raised p-4"
        aria-live="polite"
        aria-atomic="false"
      >
        {isEmpty && (
          <p className="text-sm text-fg-muted">{dict.composer.placeholder}</p>
        )}

        {chat.messages.map((message) => (
          <article
            key={message.id}
            className={
              message.role === "user"
                ? "ml-auto max-w-[85%] rounded-lg bg-accent px-3 py-2 text-sm text-accent-contrast"
                : "max-w-[92%] rounded-lg bg-surface-sunken px-3 py-2 text-sm whitespace-pre-wrap"
            }
          >
            <span className="sr-only">
              {message.role === "user" ? dict.chat.you : dict.chat.advisor}:{" "}
            </span>
            {message.content}
          </article>
        ))}

        {chat.streamingText && (
          <article className="max-w-[92%] rounded-lg bg-surface-sunken px-3 py-2 text-sm whitespace-pre-wrap">
            <span className="sr-only">{dict.chat.advisor}: </span>
            {chat.streamingText}
            <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-fg-muted align-middle" />
          </article>
        )}

        {isStreaming && !chat.streamingText && (
          <p className="text-sm text-fg-muted">{dict.chat.thinking}</p>
        )}

        <div ref={bottomRef} />
      </div>

      {chat.error && (
        <div
          role="alert"
          className="flex items-center justify-between gap-3 rounded-lg border border-warn-border bg-warn-surface px-3 py-2 text-sm text-warn-fg"
        >
          <span>{dict.chat.errorGeneric}</span>
          {chat.error.retryable && (
            <button
              type="button"
              onClick={() => void chat.retry()}
              className="shrink-0 rounded-md border border-warn-border px-2 py-1 font-medium hover:bg-warn-border/20"
            >
              {dict.chat.retry}
            </button>
          )}
        </div>
      )}

      <Composer
        dict={dict}
        disabled={isStreaming}
        onSend={(text) => void chat.sendMessage(text)}
        onStop={chat.stop}
        isStreaming={isStreaming}
      />

      {process.env.NODE_ENV !== "production" && (
        <p className="shrink-0 font-mono text-[11px] text-fg-muted">
          {/* Tira de diagnóstico: confirma que el contrato SSE llega completo
              antes de que existan los componentes del lote C. */}
          dev · stage={chat.stage} · chips={chat.chips.length} · citations=
          {chat.citations.length} · candidates={chat.candidates.length} · handoff=
          {chat.handoffRequest ? chat.handoffRequest.reason : "—"}
        </p>
      )}
    </section>
  );
}

function StageIndicator({
  current,
  dict,
}: {
  current: (typeof STAGES)[number];
  dict: Dictionary;
}) {
  const currentIndex = STAGES.indexOf(current);

  return (
    <ol className="flex shrink-0 flex-wrap gap-1.5 text-xs" aria-label="Progreso">
      {STAGES.map((stage, index) => {
        const isActive = stage === current;
        const isPast = index < currentIndex;
        return (
          <li
            key={stage}
            aria-current={isActive ? "step" : undefined}
            className={[
              "rounded-full border px-2.5 py-1",
              isActive
                ? "border-accent bg-accent text-accent-contrast font-medium"
                : isPast
                  ? "border-border-subtle text-fg-muted"
                  : "border-border-subtle text-fg-muted/60",
            ].join(" ")}
          >
            {dict.stages[stage]}
          </li>
        );
      })}
    </ol>
  );
}
