"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "@/lib/useChat";
import { Composer } from "@/components/Composer";
import { MessageBubble } from "@/components/MessageBubble";
import { ChipGroup } from "@/components/ChipGroup";
import { CandidateCard } from "@/components/CandidateCard";
import { CitationDrawer } from "@/components/CitationDrawer";
import { HandoffForm } from "@/components/HandoffForm";
import { STAGES, type Locale, type Message } from "@/lib/protocol";
import type { Dictionary } from "@/lib/i18n";

/**
 * Contenedor del chat: compone el estado de `useChat` con los componentes de
 * dominio. No contiene lógica de asesoramiento — decide únicamente disposición
 * y qué está visible en cada momento.
 */

interface ChatPanelProps {
  locale: Locale;
  dict: Dictionary;
}

export function ChatPanel({ locale, dict }: ChatPanelProps) {
  const chat = useChat(locale);
  const [openMarker, setOpenMarker] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chat.messages, chat.streamingText, chat.candidates, chat.handoffRequest]);

  /** Marcadores con cita real: MessageBubble no debe ofrecer botones huecos. */
  const knownMarkers = useMemo(
    () => new Set(chat.citations.map((citation) => citation.marker)),
    [chat.citations],
  );

  const isStreaming = chat.status === "streaming";
  const isEmpty = chat.messages.length === 0 && !chat.streamingText;

  /** El turno en curso se pinta como un mensaje más, sin id definitivo. */
  const streamingMessage: Message | null = chat.streamingText
    ? {
        id: "streaming",
        role: "assistant",
        content: chat.streamingText,
        citationMarkers: [],
        createdAt: "",
      }
    : null;

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
          <MessageBubble
            key={message.id}
            message={message}
            dict={dict}
            knownMarkers={knownMarkers}
            onOpenCitation={setOpenMarker}
          />
        ))}

        {streamingMessage && (
          <MessageBubble
            message={streamingMessage}
            dict={dict}
            knownMarkers={knownMarkers}
            onOpenCitation={setOpenMarker}
            streaming
          />
        )}

        {isStreaming && !chat.streamingText && (
          <p className="text-sm text-fg-muted">{dict.chat.thinking}</p>
        )}

        {chat.candidates.length > 0 && (
          <div className="space-y-2 pt-1">
            <h2 className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
              {dict.candidates.title}
            </h2>
            {chat.candidates.map((candidate) => (
              <CandidateCard
                key={candidate.partNumber}
                candidate={candidate}
                dict={dict}
                knownMarkers={knownMarkers}
                onOpenCitation={setOpenMarker}
              />
            ))}
          </div>
        )}

        {chat.handoffRequest && (
          <HandoffForm
            request={chat.handoffRequest}
            dict={dict}
            disabled={isStreaming}
            onSubmit={(lead) => void chat.submitLead(lead)}
          />
        )}

        <div ref={bottomRef} />
      </div>

      {chat.error && (
        <div
          role="alert"
          className="flex shrink-0 items-center justify-between gap-3 rounded-lg border border-warn-border bg-warn-surface px-3 py-2 text-sm text-warn-fg"
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

      <ChipGroup
        chips={chat.chips}
        disabled={isStreaming}
        onSelect={(chip) => void chat.sendMessage(chip.value, chip.slot)}
      />

      <Composer
        dict={dict}
        disabled={isStreaming}
        onSend={(text) => void chat.sendMessage(text)}
        onStop={chat.stop}
        isStreaming={isStreaming}
      />

      <CitationDrawer
        citations={chat.citations}
        openMarker={openMarker}
        dict={dict}
        onClose={() => setOpenMarker(null)}
      />
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
                ? "border-accent bg-accent font-medium text-accent-contrast"
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
