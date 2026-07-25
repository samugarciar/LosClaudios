"use client";

import { CitationBadge } from "@/components/CitationBadge";
import type { Dictionary } from "@/lib/i18n";
import type { Candidate } from "@/lib/protocol";

/**
 * Tarjeta de candidato de la preselección (README §8).
 *
 * Las contras se renderizan con el mismo peso visual que los pros, a propósito.
 * Un shortlist que solo muestra ventajas es un catálogo, no un asesoramiento —
 * y en producto de seguridad lo que hay que vigilar suele ser más decisivo que
 * lo que encaja.
 *
 * Esta tarjeta no muestra ni deriva niveles PL/SIL: ese lenguaje pertenece a la
 * evaluación de riesgos del integrador, no a una preselección comercial.
 */

interface CandidateCardProps {
  candidate: Candidate;
  dict: Dictionary;
  knownMarkers: ReadonlySet<number>;
  onOpenCitation: (marker: number) => void;
}

export function CandidateCard({
  candidate,
  dict,
  knownMarkers,
  onOpenCitation,
}: CandidateCardProps) {
  const markers = candidate.citationMarkers.filter((m) => knownMarkers.has(m));

  return (
    <article className="rounded-lg border border-border-subtle bg-surface-raised p-3">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wide text-fg-muted">
            {dict.candidates.rank} {candidate.rank}
          </p>
          <h3 className="truncate text-sm font-semibold">
            {candidate.family}
            {candidate.variant ? ` ${candidate.variant}` : ""}
          </h3>
          <p className="font-mono text-[11px] text-fg-muted">
            {candidate.partNumber}
          </p>
        </div>

        {candidate.confidence !== null && (
          <div className="shrink-0 text-right">
            <p className="text-[11px] text-fg-muted">
              {dict.candidates.confidence}
            </p>
            <p className="text-sm font-medium tabular-nums">
              {Math.round(candidate.confidence * 100)}%
            </p>
          </div>
        )}
      </header>

      <p className="mt-2 text-sm leading-relaxed">{candidate.headline}</p>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <TradeoffList title={dict.candidates.why} items={candidate.pros} tone="pro" />
        <TradeoffList title={dict.candidates.whyNot} items={candidate.cons} tone="con" />
      </div>

      {markers.length > 0 && (
        <footer className="mt-3 flex items-center gap-1 border-t border-border-subtle pt-2">
          <span className="text-[11px] text-fg-muted">{dict.citations.title}:</span>
          {markers.map((marker) => (
            <CitationBadge
              key={marker}
              marker={marker}
              dict={dict}
              onOpen={onOpenCitation}
            />
          ))}
        </footer>
      )}
    </article>
  );
}

function TradeoffList({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "pro" | "con";
}) {
  if (items.length === 0) return null;

  return (
    <div>
      <h4 className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
        {title}
      </h4>
      <ul className="mt-1 space-y-1">
        {items.map((item, index) => (
          <li key={index} className="flex gap-1.5 text-xs leading-relaxed">
            <span
              aria-hidden="true"
              className={tone === "pro" ? "text-accent" : "text-warn-fg"}
            >
              {tone === "pro" ? "+" : "!"}
            </span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
