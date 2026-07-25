"""Capa de recuperación (README §4).

Mismo patrón que `app.db`: un `Retriever` como Protocol con dos
implementaciones. `PostgresRetriever` consulta Supabase; `NullRetriever`
devuelve vacío pero **lo registra en el log**, porque un recuperador que
devuelve cero resultados en silencio se confunde con "no hay producto que
cumpla", que es una respuesta muy distinta y mucho peor.

De los tres motores del §4 aquí vive el **Structured**, que es el que responde
por los números. El Semantic necesita embeddings, que siguen sin decidirse
(README §3), y el Glossary necesita un corpus de notas de aplicación que aún no
existe. Cuando lleguen, se añaden como métodos de este mismo puerto sin tocar a
quien lo llama.

Regla que este módulo hace cumplir: **los números vienen de SQL**. Nada de lo
que sale de aquí lo ha escrito un modelo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.protocol import Citation
from app.retrieval.structured import FilterError, build_query, evaluate

logger = logging.getLogger(__name__)


@dataclass
class SpecMatch:
    """Un candidato con su procedencia y el veredicto por criterio."""

    part_number: str
    family: str
    variant: str | None
    row: dict[str, Any]
    checks: list[dict[str, str]] = field(default_factory=list)

    @property
    def passes(self) -> bool:
        return all(c["resultado"] == "pass" for c in self.checks)

    @property
    def failures(self) -> list[str]:
        return [c["criterio"] for c in self.checks if c["resultado"] == "fail"]

    @property
    def unknowns(self) -> list[str]:
        return [c["criterio"] for c in self.checks if c["resultado"] == "desconocido"]

    def citation(self, marker: int) -> Citation:
        """Cita de esta spec.

        `page` va a None a propósito y no por olvido: el catálogo consolidado
        del que salen estos datos no conserva el número de página, así que la
        cita resuelve al documento y a su versión, no a la página. Inventar un
        número aquí rompería la auditoría que `doc_version` existe para
        garantizar.
        """
        return Citation(
            marker=marker,
            doc_id=self.row["doc_id"],
            doc_version=self.row["doc_version"],
            doc_title=self.row["doc_title"],
            page=None,
            section_path=None,
            snippet=self._snippet(),
            source_url=self.row["source_url"],
        )

    def _snippet(self) -> str:
        """Valores VERBATIM del datasheet, no los normalizados.

        Las columnas tipadas sirven para filtrar; la cita tiene que mostrar lo
        que el documento decía. Si el datasheet pone
        '<=2 (4 m en modo alcance ampliado)', eso es lo que se enseña — el 2.0
        de la columna perdería el matiz.
        """
        raw = self.row.get("raw") or {}
        campos = [
            ("campo_proteccion_m", "campo de protección", "m"),
            ("resolucion_configurable_mm", "resolución", "mm"),
            ("tiempo_respuesta_ms", "tiempo de respuesta", "ms"),
            ("grado_proteccion_ip", "grado de protección", ""),
            ("performance_level", "Performance Level", ""),
        ]
        partes = []
        for key, label, unit in campos:
            v = raw.get(key)
            if v in (None, "", []):
                continue
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            partes.append(f"{label}: {v}{' ' + unit if unit else ''}")
        cabecera = f"{self.variant or self.part_number} ({self.part_number})"
        return f"{cabecera} — " + "; ".join(partes) if partes else cabecera


class Retriever(Protocol):
    async def search_specs(
        self, filters: dict[str, Any], limit: int = 20
    ) -> list[SpecMatch]: ...


class NullRetriever:
    """Sin base de datos. Devuelve vacío, pero lo dice."""

    async def search_specs(
        self, filters: dict[str, Any], limit: int = 20
    ) -> list[SpecMatch]:
        # Se validan igual los filtros: si el agente emite basura, queremos que
        # se vea también sin DATABASE_URL, no solo en producción.
        build_query(filters, limit)
        logger.warning(
            "NullRetriever: recuperación NO ejecutada (sin DATABASE_URL). "
            "Cero candidatos NO significa que no haya producto que cumpla."
        )
        return []


class PostgresRetriever:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def search_specs(
        self, filters: dict[str, Any], limit: int = 20
    ) -> list[SpecMatch]:
        """Candidatos que cumplen TODOS los filtros duros.

        Propaga `FilterError` a propósito: un filtro inválido es un fallo del
        agente que debe verse, no degradarse a una búsqueda sin condiciones que
        devolvería el catálogo entero como si fuera una respuesta.
        """
        sql, params, notes = build_query(filters, limit)
        logger.debug("search_specs: %s", "; ".join(notes) or "sin filtros")

        async with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(sql, params)
            rows = await cur.fetchall()

        return [
            SpecMatch(
                part_number=r["part_number"],
                family=r["family"],
                variant=r["variant"],
                row=r,
                checks=evaluate(r, filters),
            )
            for r in rows
        ]

    async def explain_candidates(
        self, part_numbers: list[str], filters: dict[str, Any]
    ) -> list[SpecMatch]:
        """Evalúa referencias CONCRETAS contra los requisitos, cumplan o no.

        `search_specs` solo devuelve lo que pasa el filtro, así que por sí solo
        no puede explicar por qué se descartó algo. Esto es lo que permite al
        nodo `shortlist` decir "el nanoScan3 no llega: 3 m frente a los 4 m que
        necesitas" en vez de callarse el descarte.
        """
        if not part_numbers:
            return []

        # `filters` NO entra en la consulta: se pasa solo a evaluate() para el
        # veredicto. Si se aplicaran aquí, los candidatos que fallan quedarían
        # fuera y no habría nada que explicar.
        sql, params, _ = build_query({}, limit=100, part_numbers=part_numbers)

        async with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(sql, params)
            rows = await cur.fetchall()

        return [
            SpecMatch(
                part_number=r["part_number"],
                family=r["family"],
                variant=r["variant"],
                row=r,
                checks=evaluate(r, filters),
            )
            for r in rows
        ]


__all__ = [
    "FilterError",
    "NullRetriever",
    "PostgresRetriever",
    "Retriever",
    "SpecMatch",
]
