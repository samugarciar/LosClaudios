"""Capa de recuperación: los tres motores del README §4.

Hoy solo vive el **Structured** (filtrado por número sobre `product_specs`).
El Semantic espera a que se decida el proveedor de embeddings y el Glossary a
que exista un corpus de notas de aplicación — los dos entran por este mismo
puerto, sin tocar a quien lo consume.

    from app.retrieval import PostgresRetriever, FilterError
"""

from app.retrieval.engine import (
    FilterError,
    NullRetriever,
    PostgresRetriever,
    Retriever,
    SpecMatch,
)
from app.retrieval.structured import build_query, evaluate

__all__ = [
    "FilterError",
    "NullRetriever",
    "PostgresRetriever",
    "Retriever",
    "SpecMatch",
    "build_query",
    "evaluate",
]
