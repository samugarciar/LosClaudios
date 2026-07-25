"use client";

import type { Dictionary } from "@/lib/i18n";

/**
 * Marcador de cita clicable que aparece inline en el texto del agente.
 *
 * Solo se renderiza si el marcador existe de verdad entre las citas recibidas
 * (lo comprueba MessageBubble). Un [3] que no abre nada es peor que no tener
 * marcador: sugiere una fuente que no existe.
 */

interface CitationBadgeProps {
  marker: number;
  dict: Dictionary;
  onOpen: (marker: number) => void;
}

export function CitationBadge({ marker, dict, onOpen }: CitationBadgeProps) {
  return (
    <button
      type="button"
      onClick={() => onOpen(marker)}
      aria-label={`${dict.citations.badgeAria} ${marker}`}
      className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-[3px] border border-accent px-1 align-super text-[10px] font-medium leading-none text-accent tabular-nums hover:bg-accent hover:text-accent-contrast"
    >
      {marker}
    </button>
  );
}
