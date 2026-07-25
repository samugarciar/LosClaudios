"use client";

import { useState } from "react";
import type { Dictionary } from "@/lib/i18n";

/**
 * Banner permanente de alcance (README §1 y §12).
 *
 * Esto NO es decoración legal ni un aviso de cookies: es el límite del
 * producto. El agente preselecciona; no determina el PL requerido ni la
 * distancia mínima de seguridad. El titular queda siempre visible y solo el
 * detalle es plegable — no debe existir un estado de la UI en el que el
 * usuario no vea que esto es una orientación.
 */

export function SafetyDisclaimer({ dict }: { dict: Dictionary }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <aside
      role="note"
      className="shrink-0 rounded-lg border border-warn-border bg-warn-surface px-3 py-2 text-warn-fg"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium">{dict.disclaimer.title}</p>
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          aria-controls="disclaimer-detail"
          className="shrink-0 rounded-md border border-warn-border px-2 py-0.5 text-xs font-medium hover:bg-warn-border/20"
        >
          {expanded ? dict.citations.close : dict.disclaimer.more}
        </button>
      </div>

      {expanded && (
        <p id="disclaimer-detail" className="mt-2 text-xs leading-relaxed">
          {dict.disclaimer.body}
        </p>
      )}
    </aside>
  );
}
