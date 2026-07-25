"""Persistencia.

Un `Store` como Protocol con dos implementaciones: `PostgresStore` contra
Supabase y `NullStore` cuando no hay `DATABASE_URL`. `NullStore` **registra en
el log** cada operación que descarta: una persistencia que falla en silencio es
peor que no tener persistencia.

Las tablas son las de `supabase/schema/`. Este módulo no crea esquema: si una
tabla no existe, la operación falla y se ve. Crear tablas desde el código de la
aplicación en una base compartida con otro equipo es una forma segura de
provocar un conflicto.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.protocol import Candidate, Citation, Lead, Stage

logger = logging.getLogger(__name__)


@dataclass
class SessionRow:
    id: str
    turn_count: int
    tokens_used: int
    stage: Stage


class Store(Protocol):
    async def ensure_session(
        self, session_id: str, anon_hash: str, locale: str
    ) -> SessionRow: ...

    async def set_stage(self, session_id: str, stage: Stage) -> None: ...

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        model: str | None = None,
        effort: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_read_input_tokens: int | None = None,
        latency_ms: int | None = None,
    ) -> int | None: ...

    async def add_citations(
        self, message_id: int | None, citations: list[Citation]
    ) -> None: ...

    async def add_recommendations(
        self, session_id: str, candidates: list[Candidate], profile_snapshot: dict[str, Any]
    ) -> None: ...

    async def add_lead(
        self, session_id: str, lead: Lead, handoff_summary: dict[str, Any]
    ) -> None: ...

    async def bump_usage(self, session_id: str, tokens: int) -> None: ...


# ---------------------------------------------------------------------------
# Sin persistencia
# ---------------------------------------------------------------------------


class NullStore:
    """Descarta todo, pero lo dice."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRow] = {}

    async def ensure_session(
        self, session_id: str, anon_hash: str, locale: str
    ) -> SessionRow:
        row = self._sessions.get(session_id)
        if row is None:
            row = SessionRow(id=session_id, turn_count=0, tokens_used=0, stage="discovery")
            self._sessions[session_id] = row
        return row

    async def set_stage(self, session_id: str, stage: Stage) -> None:
        if row := self._sessions.get(session_id):
            row.stage = stage

    async def add_message(self, session_id: str, role: str, content: str, **_: Any) -> int | None:
        logger.debug("NullStore: mensaje %s descartado (sin persistencia)", role)
        return None

    async def add_citations(self, message_id: int | None, citations: list[Citation]) -> None:
        if citations:
            logger.debug("NullStore: %d citas descartadas", len(citations))

    async def add_recommendations(
        self, session_id: str, candidates: list[Candidate], profile_snapshot: dict[str, Any]
    ) -> None:
        if candidates:
            logger.warning(
                "NullStore: %d recomendaciones NO persistidas (sin DATABASE_URL)",
                len(candidates),
            )

    async def add_lead(
        self, session_id: str, lead: Lead, handoff_summary: dict[str, Any]
    ) -> None:
        # Un lead perdido es negocio perdido: nivel ERROR, no DEBUG.
        logger.error(
            "NullStore: LEAD NO PERSISTIDO (sin DATABASE_URL). sesión=%s", session_id
        )

    async def bump_usage(self, session_id: str, tokens: int) -> None:
        if row := self._sessions.get(session_id):
            row.turn_count += 1
            row.tokens_used += tokens


# ---------------------------------------------------------------------------
# Postgres / Supabase
# ---------------------------------------------------------------------------


class PostgresStore:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def ensure_session(
        self, session_id: str, anon_hash: str, locale: str
    ) -> SessionRow:
        async with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                """
                insert into sessions (id, anon_hash, locale)
                values (%s, %s, %s)
                on conflict (id) do update
                    set last_seen = now()
                returning id::text, turn_count, tokens_used, stage
                """,
                (session_id, anon_hash, locale),
            )
            row = await cur.fetchone()

        if row is None:  # pragma: no cover — RETURNING siempre devuelve fila
            raise RuntimeError("ensure_session no devolvió fila")
        return SessionRow(
            id=row["id"],
            turn_count=row["turn_count"],
            tokens_used=row["tokens_used"],
            stage=row["stage"],
        )

    async def set_stage(self, session_id: str, stage: Stage) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "update sessions set stage = %s, last_seen = now() where id = %s",
                (stage, session_id),
            )

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        model: str | None = None,
        effort: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_read_input_tokens: int | None = None,
        latency_ms: int | None = None,
    ) -> int | None:
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                    insert into messages (
                        session_id, role, content, model, effort,
                        input_tokens, output_tokens, cache_read_input_tokens, latency_ms
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    returning id
                    """,
                (
                    session_id,
                    role,
                    content,
                    model,
                    effort,
                    input_tokens,
                    output_tokens,
                    cache_read_input_tokens,
                    latency_ms,
                ),
            )
            row = await cur.fetchone()
        return int(row[0]) if row else None

    async def add_citations(
        self, message_id: int | None, citations: list[Citation]
    ) -> None:
        if message_id is None or not citations:
            return
        rows = [
            (
                message_id,
                c.marker,
                c.doc_id,
                c.doc_version,
                c.doc_title,
                c.page,
                c.section_path,
                c.snippet,
                c.source_url,
                c.score,
            )
            for c in citations
        ]
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.executemany(
                """
                    insert into citations (
                        message_id, marker, doc_id, doc_version, doc_title,
                        page, section_path, snippet, source_url, score
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (message_id, marker) do nothing
                    """,
                rows,
            )

    async def add_recommendations(
        self, session_id: str, candidates: list[Candidate], profile_snapshot: dict[str, Any]
    ) -> None:
        if not candidates:
            return
        snapshot = json.dumps(profile_snapshot)
        rows = [
            (
                session_id,
                c.part_number,
                c.family,
                c.variant,
                c.rank,
                c.headline,
                c.pros,
                c.cons,
                c.citation_markers,
                c.confidence,
                snapshot,
            )
            for c in candidates
        ]
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.executemany(
                """
                    insert into recommendations (
                        session_id, part_number, family, variant, rank, headline,
                        pros, cons, citation_markers, confidence, profile_snapshot
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                rows,
            )

    async def add_lead(
        self, session_id: str, lead: Lead, handoff_summary: dict[str, Any]
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                insert into leads (
                    session_id, name, email, company, country,
                    consent_text_version, handoff_summary
                )
                values (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    session_id,
                    lead.name,
                    lead.email,
                    lead.company,
                    lead.country,
                    lead.consent_text_version,
                    json.dumps(handoff_summary),
                ),
            )

    async def bump_usage(self, session_id: str, tokens: int) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                update sessions
                   set turn_count  = turn_count + 1,
                       tokens_used = tokens_used + %s,
                       last_seen   = now()
                 where id = %s
                """,
                (tokens, session_id),
            )


async def open_pool(database_url: str) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(database_url, min_size=1, max_size=8, open=False)
    await pool.open(wait=True, timeout=15)
    return pool


async def open_checkpointer_pool(database_url: str) -> AsyncConnectionPool:
    """Pool separado para el checkpointer de LangGraph.

    Va aparte del nuestro a propósito: el checkpointer exige `dict_row`, y
    nuestro `add_message` lee la fila por posición (`row[0]`). Compartir pool
    haría que uno de los dos fallara de forma difícil de rastrear.
    """
    pool = AsyncConnectionPool(
        database_url,
        min_size=1,
        max_size=4,
        open=False,
        kwargs={"row_factory": dict_row, "autocommit": True},
    )
    await pool.open(wait=True, timeout=15)
    return pool
