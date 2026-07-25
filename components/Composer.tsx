"use client";

import { useState, type KeyboardEvent } from "react";
import { MAX_USER_MESSAGE_CHARS } from "@/lib/protocol";
import type { Dictionary } from "@/lib/i18n";

interface ComposerProps {
  dict: Dictionary;
  disabled: boolean;
  isStreaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function Composer({
  dict,
  disabled,
  isStreaming,
  onSend,
  onStop,
}: ComposerProps) {
  const [value, setValue] = useState("");

  const trimmed = value.trim();
  const tooLong = value.length > MAX_USER_MESSAGE_CHARS;
  const canSend = trimmed.length > 0 && !tooLong && !disabled;

  function submit(): void {
    if (!canSend) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    // Enter envía, Mayús+Enter salta línea. En móvil el teclado suele mandar
    // Enter con isComposing durante la predicción: no interrumpirlo.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="shrink-0 space-y-1.5">
      <div className="flex items-end gap-2 rounded-lg border border-border-subtle bg-surface-raised p-2 focus-within:border-accent">
        <label htmlFor="composer" className="sr-only">
          {dict.composer.placeholder}
        </label>
        <textarea
          id="composer"
          rows={2}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={dict.composer.placeholder}
          aria-describedby="composer-hint"
          aria-invalid={tooLong || undefined}
          className="max-h-40 min-h-[2.5rem] flex-1 resize-y bg-transparent px-1 text-sm outline-none placeholder:text-fg-muted"
        />

        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            className="shrink-0 rounded-md border border-border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-sunken"
          >
            {dict.composer.stop}
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!canSend}
            className="shrink-0 rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-contrast enabled:hover:bg-accent-hover disabled:opacity-40"
          >
            {dict.composer.send}
          </button>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 px-1">
        <p id="composer-hint" className="text-[11px] text-fg-muted">
          {dict.composer.hint}
        </p>
        {/* El contador aparece solo cuando importa. */}
        {value.length > MAX_USER_MESSAGE_CHARS * 0.8 && (
          <p
            className={[
              "text-[11px] tabular-nums",
              tooLong ? "text-warn-fg" : "text-fg-muted",
            ].join(" ")}
          >
            {value.length} / {MAX_USER_MESSAGE_CHARS}
          </p>
        )}
      </div>
    </div>
  );
}
