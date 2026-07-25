"""Recuperación sobre el catálogo local, sin base de datos.

Tercera implementación del puerto `Retriever` (junto a `PostgresRetriever` y
`NullRetriever`). Lee las fichas del JSON de `data/catalog/` en lugar de
`product_specs`, y **reutiliza el mismo motor de filtros**: `build_query()` para
validar y `evaluate()` para el veredicto por criterio.

Por qué existe: `PostgresRetriever` necesita `DATABASE_URL` y el seed aplicado.
Mientras eso llega, esto da recomendaciones reales con procedencia real. Y en
tests permite recorrer el agente entero sin levantar infraestructura.

Por qué no duplica lógica: la fila que produce `CatalogRecord.to_spec_row()`
lleva los nombres de columna de `product_specs`, así que `evaluate()` opera
sobre ella exactamente igual que sobre una fila de SQL. Si el filtro cambia,
cambia para los dos caminos a la vez.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.catalog import Catalog
from app.retrieval.engine import SpecMatch
from app.retrieval.structured import build_query, evaluate

logger = logging.getLogger(__name__)


class CatalogRetriever:
    """`Retriever` sobre las fichas en memoria."""

    def __init__(self, catalog: Catalog) -> None:
        self._rows: list[dict[str, Any]] = [
            record.to_spec_row() for record in catalog.records
        ]
        logger.info(
            "CatalogRetriever: %d fichas en memoria (sin base de datos)",
            len(self._rows),
        )

    async def search_specs(
        self, filters: dict[str, Any], limit: int = 20
    ) -> list[SpecMatch]:
        # Se valida con su propio validador aunque no vaya a ejecutarse SQL: un
        # filtro inventado debe fallar igual aquí que en producción, o el error
        # solo aparecería al desplegar.
        build_query(filters, limit)

        matches = [self._match(row, filters) for row in self._rows]
        passing = [match for match in matches if match.passes]
        passing.sort(key=_order_key)
        return passing[:limit]

    async def explain_candidates(
        self, part_numbers: list[str], filters: dict[str, Any]
    ) -> list[SpecMatch]:
        """Evalúa referencias concretas, cumplan o no. Para explicar descartes."""
        if not part_numbers:
            return []
        wanted = set(part_numbers)
        return [
            self._match(row, filters)
            for row in self._rows
            if row["part_number"] in wanted
        ]

    @staticmethod
    def _match(row: dict[str, Any], filters: dict[str, Any]) -> SpecMatch:
        return SpecMatch(
            part_number=row["part_number"],
            family=row["family"],
            variant=row["variant"],
            row=row,
            checks=evaluate(row, filters),
        )


def _order_key(match: SpecMatch) -> tuple[bool, float, str]:
    """Mismo orden que su SQL: `protective_field_max_m desc nulls last, part_number`."""
    reach = match.row.get("protective_field_max_m")
    return (reach is None, -float(reach or 0), match.part_number)
