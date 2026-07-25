"""Adaptador `SpecMatch` → `Candidate` del contrato.

Los pros y las contras **se derivan del veredicto por criterio**, no se
redactan. Cada `check` en `pass` es una razón de encaje comprobada contra el
dato; cada `fail` es un motivo real de descarte; cada `desconocido` es una
laguna de la ficha que el cliente merece ver.

A eso se suman los avisos que no dependen de la consulta: PFHd no publicado,
revisión antigua, equipo solo de interior, parte de un sistema mayor, y el
recordatorio de que la distancia de montaje nunca sale de aquí.

Funciona igual con `PostgresRetriever` y con `CatalogRetriever` porque ambos
entregan la misma fila, incluido `raw` con la ficha original.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.protocol import Candidate, Citation
from app.retrieval.engine import SpecMatch

#: A partir de esta antigüedad se avisa de la revisión de la ficha (§6.7).
STALE_REVISION_YEARS = 3

MAX_CANDIDATES = 3


def build_candidates(
    matches: list[SpecMatch], *, today: date | None = None
) -> tuple[list[Candidate], list[Citation]]:
    """Convierte coincidencias en candidatos citados, en orden de relevancia."""
    reference_day = today or date.today()
    candidates: list[Candidate] = []
    citations: list[Citation] = []

    for index, match in enumerate(matches[:MAX_CANDIDATES], start=1):
        citations.append(match.citation(index))
        candidates.append(
            Candidate(
                part_number=match.part_number,
                family=match.family,
                variant=match.variant,
                rank=index,
                headline=_headline(match),
                pros=_pros(match),
                cons=_cons(match, reference_day),
                citation_markers=[index],
                confidence=None,
            )
        )

    return candidates, citations


def describe_rejections(matches: list[SpecMatch]) -> list[str]:
    """Frases de descarte para las referencias que NO pasaron el filtro.

    Sin esto el agente calla los descartes, y un shortlist que no explica qué
    quedó fuera parece arbitrario. Con `explain_candidates` se puede decir «el
    nanoScan3 no llega» en lugar de omitirlo.
    """
    lines: list[str] = []
    for match in matches:
        if match.passes:
            continue
        motivos = match.failures + [f"{c} (no consta)" for c in match.unknowns]
        if motivos:
            lines.append(
                f"{match.variant or match.part_number} ({match.part_number}): "
                + "; ".join(motivos)
            )
    return lines


# ---------------------------------------------------------------------------


def _raw(match: SpecMatch) -> dict[str, Any]:
    return match.row.get("raw") or {}


def _headline(match: SpecMatch) -> str:
    raw = _raw(match)
    name = raw.get("version") or match.family
    part = raw.get("parte_sistema")
    if part:
        # §5.2: en safeRS3 el sensor y la unidad de control no comparten datos
        # ambientales. Nombrarlos igual induce justo al error peligroso.
        name = f"{name} — {str(part).lower()}"
    return name


def _pros(match: SpecMatch) -> list[str]:
    pros = [
        check["criterio"].capitalize()
        for check in match.checks
        if check["resultado"] == "pass"
    ]

    raw = _raw(match)
    if resolutions := match.row.get("resolution_mm"):
        pros.append(f"Capacidad de detección configurable desde {min(resolutions)} mm")
    if isinstance(raw.get("resolucion_objeto_mm"), dict):
        detalle = ", ".join(
            f"{parte} {valor} mm"
            for parte, valor in sorted(raw["resolucion_objeto_mm"].items())
        )
        pros.append(f"Detección diferenciada por parte del cuerpo: {detalle}")
    if (casos := match.row.get("n_monitoring_cases_max")) and casos > 1:
        pros.append(f"{casos} casos de monitorización conmutables")

    # §5.5: las funciones con condición se citan enteras, con su condición.
    for funcion in [f for f in raw.get("funciones") or [] if "(" in str(f)][:2]:
        pros.append(f"Función disponible: {funcion}")

    return pros


def _cons(match: SpecMatch, today: date) -> list[str]:
    cons: list[str] = []
    raw = _raw(match)

    for check in match.checks:
        if check["resultado"] == "fail":
            cons.append(f"No cumple: {check['criterio']}")
        elif check["resultado"] == "desconocido":
            # «No consta» no es «no cumple»: colapsarlos mentiría en la
            # dirección peligrosa.
            cons.append(f"La ficha no permite confirmar: {check['criterio']}")

    # §6.3 — PFHd como prosa en safeRS3.
    if match.row.get("pfhd") is None and raw.get("pfhd"):
        cons.append(
            f"La ficha no publica un PFHd numérico: «{raw['pfhd']}». "
            "Hay que consultarlo antes de calcular el PL."
        )

    # §6.2 — revisión antigua.
    if aviso := raw.get("advertencia"):
        cons.append(f"Aviso sobre la fuente: {aviso}")
    elif (
        (revision := match.row.get("revision_date"))
        and isinstance(revision, date)
        and today.year - revision.year >= STALE_REVISION_YEARS
    ):
        cons.append(
            f"La revisión de la ficha es de {revision.isoformat()}: "
            "conviene contrastarla."
        )

    aplicacion = str(raw.get("aplicacion") or "")
    if aplicacion and "outdoor" not in aplicacion.lower():
        cons.append("Solo para interior según ficha")
    elif not aplicacion:
        cons.append("La ficha no declara ámbito de uso (interior / exterior)")

    if parte := raw.get("parte_sistema"):
        cons.append(
            f"Es la parte «{parte}» del sistema: los datos ambientales no son "
            "los del conjunto"
        )

    # Invariante del dominio: esto no sale nunca de una ficha.
    cons.append(
        "La distancia de montaje depende del tiempo de parada de la máquina y "
        "no está en la ficha"
    )
    return cons
