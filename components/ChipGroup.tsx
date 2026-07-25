"use client";

import type { Chip } from "@/lib/protocol";

/**
 * Opciones sugeridas (README §8).
 *
 * Son el mecanismo que permite a un usuario no técnico avanzar sin tener que
 * redactar una respuesta. Al pulsar, se envía `chip.value` como mensaje —
 * `chip.label` es solo lo que se muestra, porque lo que necesita el agente y
 * lo que le cabe a un botón rara vez coinciden.
 */

interface ChipGroupProps {
  chips: Chip[];
  disabled: boolean;
  onSelect: (chip: Chip) => void;
}

export function ChipGroup({ chips, disabled, onSelect }: ChipGroupProps) {
  if (chips.length === 0) return null;

  return (
    <div className="flex shrink-0 flex-wrap gap-2">
      {chips.map((chip) => (
        <button
          key={chip.id}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(chip)}
          title={chip.value}
          className="rounded-full border border-accent px-3 py-1.5 text-xs font-medium text-accent enabled:hover:bg-accent enabled:hover:text-accent-contrast disabled:opacity-40"
        >
          {chip.label}
        </button>
      ))}
    </div>
  );
}
