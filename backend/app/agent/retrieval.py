"""Puerto de recuperación y su implementación sobre el catálogo.

El agente pide candidatos a través de `RetrievalPort` y nunca conoce la fuente.
Hoy detrás hay un catálogo estructurado (`catalog.py`); cuando el equipo de
recuperación documental entregue su índice híbrido, implementarán este mismo
puerto y el grafo no cambia.

Las contras de cada candidato **se derivan del dato**, no se redactan: una ficha
sin PFHd numérico, una revisión antigua, un equipo solo de interior o una función
con condición son contras reales. Inventarlas sería exactamente el fallo que este
sistema no puede permitirse.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.agent.catalog import (
    INDOOR,
    OUTDOOR,
    Catalog,
    CatalogQuery,
    CatalogRecord,
)
from app.protocol import Candidate, Citation

logger = logging.getLogger(__name__)

# Umbral de antigüedad para avisar de la revisión de una ficha (§6.7).
STALE_REVISION_YEARS = 3

MAX_CANDIDATES = 3


@dataclass(frozen=True, slots=True)
class RetrievalSpec:
    """Restricciones duras derivadas del perfil de requisitos."""

    families: frozenset[str] | None = None
    min_protective_field_m: float | None = None
    max_resolution_mm: int | None = None
    min_ip: int | None = None
    environment: str | None = None
    min_pl_rank: int | None = None


@dataclass(slots=True)
class RetrievalResult:
    candidates: list[Candidate] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    #: Referencias que podrían valer pero cuya ficha no permite confirmarlo.
    indeterminate: list[tuple[str, str]] = field(default_factory=list)
    #: Cuántas referencias se descartaron por no cumplir (no por falta de dato).
    rejected_count: int = 0


class RetrievalPort(Protocol):
    async def search(self, spec: RetrievalSpec) -> RetrievalResult: ...

    async def describe(self, reference: str) -> RetrievalResult: ...


class CatalogRetriever:
    """Recuperación estructurada sobre las fichas técnicas."""

    def __init__(self, catalog: Catalog, *, today: date | None = None) -> None:
        self._catalog = catalog
        self._today = today or date.today()

    async def search(self, spec: RetrievalSpec) -> RetrievalResult:
        result = self._catalog.search(
            CatalogQuery(
                families=spec.families,
                min_protective_field_m=spec.min_protective_field_m,
                max_resolution_mm=spec.max_resolution_mm,
                min_ip=spec.min_ip,
                environment=spec.environment,
                min_pl_rank=spec.min_pl_rank,
            )
        )
        return self._to_result(result.matched[:MAX_CANDIDATES], result)

    async def describe(self, reference: str) -> RetrievalResult:
        record = self._catalog.get(reference)
        if record is None:
            # §6: si está en `pendientes`, existe pero no tenemos su ficha. Y si
            # no está en ninguno de los dos, no lo conocemos. Son cosas distintas
            # y el agente debe poder decir cuál.
            note = (
                "referencia pendiente de extracción: existe, pero no tenemos su ficha"
                if self._catalog.is_pending(reference)
                else "referencia desconocida en el catálogo"
            )
            return RetrievalResult(indeterminate=[(reference, note)])
        return self._to_result((record,), None)

    # ------------------------------------------------------------------
    def _to_result(
        self,
        records: Sequence[CatalogRecord],
        search_result: object | None,
    ) -> RetrievalResult:
        result = RetrievalResult()

        for index, record in enumerate(records, start=1):
            result.citations.append(self._citation(record, marker=index))
            result.candidates.append(self._candidate(record, rank=index, marker=index))

        if search_result is not None:
            from app.agent.catalog import SearchResult  # noqa: PLC0415 — evita ciclo

            if isinstance(search_result, SearchResult):
                result.indeterminate = [
                    (record.reference, reason)
                    for record, reason in search_result.indeterminate
                ]
                result.rejected_count = search_result.rejected_count

        return result

    def _citation(self, record: CatalogRecord, *, marker: int) -> Citation:
        provenance = record.provenance
        return Citation(
            marker=marker,
            doc_id=provenance.reference,
            doc_version=provenance.doc_version,
            doc_title=provenance.title,
            # La extracción actual NO trae número de página: la ficha se cita
            # completa. Cuando el índice documental aporte granularidad de
            # fragmento, este campo se rellenará.
            page=None,
            section_path=None,
            snippet=self._snippet(record),
            source_url=provenance.source_url,
            score=None,
        )

    @staticmethod
    def _snippet(record: CatalogRecord) -> str:
        parts = [f"Ref. {record.reference} · {record.variant}"]
        if record.performance_level:
            parts.append(record.performance_level)
        if record.protective_field_m:
            parts.append(f"campo de protección {record.protective_field_m.raw} m")
        if record.ip:
            parts.append(record.ip.raw)
        if record.operating_temp_c:
            parts.append(record.operating_temp_c.raw)
        return " · ".join(parts)

    def _candidate(self, record: CatalogRecord, *, rank: int, marker: int) -> Candidate:
        return Candidate(
            part_number=record.reference,
            family=record.family,
            variant=record.variant,
            rank=rank,
            headline=self._headline(record),
            pros=self._pros(record),
            cons=self._cons(record),
            citation_markers=[marker],
            confidence=None,
        )

    @staticmethod
    def _headline(record: CatalogRecord) -> str:
        name = record.version or record.family
        if record.system_part:
            # §5.2: en safeRS3 no decir «safeRS3 es IP67» sin distinguir la parte.
            name = f"{name} — {record.system_part.lower()}"
        return name

    @staticmethod
    def _pros(record: CatalogRecord) -> list[str]:
        pros: list[str] = []
        if record.protective_field_m:
            pros.append(f"Campo de protección de {record.protective_field_m.raw} m")
        if record.resolutions_mm:
            pros.append(
                "Capacidad de detección configurable desde "
                f"{min(record.resolutions_mm)} mm"
            )
        if record.resolution_by_body_part:
            detail = ", ".join(
                f"{part} {value} mm"
                for part, value in sorted(record.resolution_by_body_part.items())
            )
            pros.append(f"Detección diferenciada por parte del cuerpo: {detail}")
        if OUTDOOR in record.environments:
            pros.append("Apto para uso en exterior según ficha")
        if record.monitoring_cases and record.monitoring_cases > 1:
            pros.append(
                f"{record.monitoring_cases} casos de monitorización conmutables"
            )
        # §5.5: las funciones se citan con su condición incrustada, íntegras.
        conditional = [f for f in record.functions if "(" in f]
        for function in conditional[:2]:
            pros.append(f"Función disponible: {function}")
        return pros

    def _cons(self, record: CatalogRecord) -> list[str]:
        cons: list[str] = []

        # §6.3 — PFHd como prosa, no como número.
        if record.pfhd is None and record.pfhd_raw:
            cons.append(
                "La ficha no publica un PFHd numérico: "
                f"«{record.pfhd_raw}». Hay que consultarlo antes de calcular el PL."
            )

        # §6.2 — revisión antigua con advertencia explícita.
        if record.provenance.warning:
            cons.append(f"Aviso sobre la fuente: {record.provenance.warning}")
        elif (
            self._today.year - record.provenance.revision_date.year
            >= STALE_REVISION_YEARS
        ):
            cons.append(
                "La revisión de la ficha es de "
                f"{record.provenance.revision_date.isoformat()}: conviene contrastarla."
            )

        # §5.2 — no generalizar el ámbito entre familias ni partes.
        if record.environments == frozenset({INDOOR}):
            cons.append("Solo para interior según ficha")
        elif not record.environments:
            cons.append("La ficha no declara ámbito de uso (interior / exterior)")

        if record.system_part:
            cons.append(
                f"Es la parte «{record.system_part}» del sistema: los datos "
                "ambientales no son los del conjunto"
            )

        # Constante en este dominio: la distancia de montaje nunca sale de aquí.
        cons.append(
            "La distancia de montaje depende del tiempo de parada de la máquina "
            "y no está en la ficha"
        )
        return cons


def build_default_retriever() -> CatalogRetriever:
    catalog = Catalog.default()
    logger.info(
        "catálogo cargado: %d fichas, familias=%s, %d referencias pendientes",
        len(catalog.records),
        catalog.families(),
        len(catalog.pending_references),
    )
    return CatalogRetriever(catalog)
