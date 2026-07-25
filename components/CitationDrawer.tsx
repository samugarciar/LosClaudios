"use client";

import { useEffect, useRef } from "react";
import type { Dictionary } from "@/lib/i18n";
import type { Citation } from "@/lib/protocol";

/**
 * Panel de fuentes (README §7).
 *
 * Muestra la versión del documento junto a la página. Ese dato parece menor y
 * es el que hace auditable una recomendación: las hojas de datos de seguridad
 * se revisan, y una cita sin versión no permite reconstruir qué se le dijo al
 * cliente en su momento.
 */

interface CitationDrawerProps {
  citations: Citation[];
  /** Marcador a destacar al abrir. `null` = cerrado. */
  openMarker: number | null;
  dict: Dictionary;
  onClose: () => void;
}

export function CitationDrawer({
  citations,
  openMarker,
  dict,
  onClose,
}: CitationDrawerProps) {
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const isOpen = openMarker !== null;

  useEffect(() => {
    if (!isOpen) return;

    closeRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={dict.citations.title}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border-subtle bg-surface-raised shadow-xl"
      >
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border-subtle px-4 py-3">
          <h2 className="text-sm font-semibold">{dict.citations.title}</h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-md border border-border-subtle px-2 py-1 text-xs font-medium hover:bg-surface-sunken"
          >
            {dict.citations.close}
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          {citations.length === 0 && (
            <p className="text-sm text-fg-muted">{dict.citations.empty}</p>
          )}

          {citations.map((citation) => (
            <section
              key={`${citation.docId}-${citation.marker}`}
              aria-current={citation.marker === openMarker ? "true" : undefined}
              className={[
                "rounded-lg border p-3",
                citation.marker === openMarker
                  ? "border-accent bg-surface-sunken"
                  : "border-border-subtle",
              ].join(" ")}
            >
              <div className="flex items-baseline gap-2">
                <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-[3px] border border-accent px-1 text-[11px] font-medium text-accent tabular-nums">
                  {citation.marker}
                </span>
                <h3 className="text-sm font-medium">{citation.docTitle}</h3>
              </div>

              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-xs text-fg-muted">
                {citation.page !== null && (
                  <>
                    <dt>{dict.citations.page}</dt>
                    <dd className="tabular-nums">{citation.page}</dd>
                  </>
                )}
                <dt>{dict.citations.version}</dt>
                <dd className="tabular-nums">v{citation.docVersion}</dd>
                {citation.sectionPath !== null && (
                  <>
                    <dt>{dict.citations.section}</dt>
                    <dd>{citation.sectionPath}</dd>
                  </>
                )}
              </dl>

              <blockquote className="mt-2 border-l-2 border-border-subtle pl-2 text-xs leading-relaxed text-fg-muted">
                {citation.snippet}
              </blockquote>

              <a
                href={citation.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-block text-xs font-medium text-accent underline hover:no-underline"
              >
                {dict.citations.open}
              </a>
            </section>
          ))}
        </div>
      </div>
    </>
  );
}
