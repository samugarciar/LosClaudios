"""Aplicación FastAPI.

Expone `POST /chat` (SSE) y `GET /health`. El frontend habla solo con este
endpoint, a través de su propio route handler; nunca con Supabase ni con el
proveedor del modelo (README §10).

Responsabilidades de este módulo, y ninguna más: sesión, límites, persistencia
del turno y transporte. El razonamiento vive detrás de `AgentRunner`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import TypeAdapter, ValidationError

from app.agent.graph import build_runner
from app.config import Settings, get_settings
from app.db import (
    NullStore,
    PostgresStore,
    Store,
    open_checkpointer_pool,
    open_pool,
)
from app.protocol import ChatRequest, ErrorEvent, LeadRequest, MessageRequest
from app.ratelimit import SlidingWindowLimiter, check_session_budget
from app.runner import AgentRunner
from app.session import (
    client_key,
    compute_anon_hash,
    new_session_id,
    read_session_id,
    set_session_cookie,
)
from app.sse import SSE_HEADERS, encode_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("app")

_chat_request_adapter: TypeAdapter[ChatRequest] = TypeAdapter(ChatRequest)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.log_degradations()

    pool = None
    checkpointer_pool = None
    checkpointer = None
    store: Store

    if settings.persistence_enabled:
        assert settings.database_url is not None
        pool = await open_pool(settings.database_url)
        store = PostgresStore(pool)
        logger.info("persistencia activa contra Postgres")

        # El checkpointer crea sus propias tablas la primera vez (ver
        # supabase/README.md). Si falla, se degrada a memoria con aviso en lugar
        # de impedir el arranque: perder reanudación es malo, no arrancar es peor.
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            checkpointer_pool = await open_checkpointer_pool(settings.database_url)
            saver = AsyncPostgresSaver(checkpointer_pool)  # type: ignore[arg-type]
            await saver.setup()
            checkpointer = saver
            logger.info("checkpointer de LangGraph sobre Postgres")
        except Exception:
            logger.exception(
                "no se pudo inicializar el checkpointer Postgres; se usa memoria"
            )
            if checkpointer_pool is not None:
                await checkpointer_pool.close()
                checkpointer_pool = None
    else:
        store = NullStore()

    app.state.settings = settings
    app.state.store = store
    app.state.runner = await build_runner(settings, checkpointer)
    app.state.limiter = SlidingWindowLimiter(max_events=settings.rate_limit_per_minute)

    try:
        yield
    finally:
        if checkpointer_pool is not None:
            await checkpointer_pool.close()
        if pool is not None:
            await pool.close()


app = FastAPI(title="SICK Safety Advisor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().allowed_origin],
    allow_credentials=True,  # imprescindible: la sesión va en cookie
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["content-type"],
)


@app.get("/health")
async def health() -> dict[str, Any]:
    settings: Settings = app.state.settings
    return {
        "status": "ok",
        "persistence": settings.persistence_enabled,
        "model": settings.model_enabled,
        "runner": type(app.state.runner).__name__,
    }


@app.post("/chat")
async def chat(request: Request) -> Response:
    settings: Settings = app.state.settings
    store: Store = app.state.store
    runner: AgentRunner = app.state.runner
    limiter: SlidingWindowLimiter = app.state.limiter

    # --- Validación del cuerpo contra el contrato ---------------------------
    try:
        payload = _chat_request_adapter.validate_python(await request.json())
    except (ValidationError, ValueError):
        return JSONResponse(
            {"code": "invalid_request", "message": "El cuerpo no cumple el contrato."},
            status_code=400,
        )

    # --- Ráfaga por cliente -------------------------------------------------
    verdict = limiter.check(client_key(request, settings))
    if not verdict.allowed:
        headers = (
            {"retry-after": str(verdict.retry_after_seconds)}
            if verdict.retry_after_seconds
            else {}
        )
        return JSONResponse(
            {"code": verdict.reason, "message": "Demasiadas peticiones."},
            status_code=429,
            headers=headers,
        )

    # --- Sesión -------------------------------------------------------------
    # El cliente no elige su id: o trae una cookie válida, o se emite una nueva.
    session_id = read_session_id(request, settings) or new_session_id()
    anon_hash = compute_anon_hash(request, settings)
    session_row = await store.ensure_session(session_id, anon_hash, payload.locale)

    # --- Topes acumulados de la sesión -------------------------------------
    budget = check_session_budget(
        turn_count=session_row.turn_count,
        tokens_used=session_row.tokens_used,
        max_turns=settings.max_turns_per_session,
        max_tokens=settings.max_tokens_per_session,
    )
    if not budget.allowed:
        return JSONResponse(
            {
                "code": budget.reason,
                "message": (
                    "Esta conversación ha alcanzado su límite. "
                    "Solicita contacto con un ingeniero."
                ),
            },
            status_code=429,
        )

    if isinstance(payload, MessageRequest):
        await store.add_message(session_id, "user", payload.text)

    stream = _stream_turn(
        runner=runner,
        store=store,
        settings=settings,
        session_id=session_id,
        payload=payload,
        http_request=request,
    )

    response = StreamingResponse(stream, media_type="text/event-stream", headers=SSE_HEADERS)
    # Se re-emite en cada respuesta para renovar la caducidad.
    set_session_cookie(response, session_id, settings)
    return response


async def _stream_turn(
    *,
    runner: AgentRunner,
    store: Store,
    settings: Settings,
    session_id: str,
    payload: ChatRequest,
    http_request: Request,
) -> AsyncIterator[str]:
    """Consume el runner, emite SSE y persiste el resultado del turno."""
    assistant_text: list[str] = []
    citations: list[Any] = []
    candidates: list[Any] = []
    handoff: Any = None

    try:
        async for event in runner.run(session_id, payload):
            # Si el usuario cierra la pestaña, no se sigue gastando modelo.
            if await http_request.is_disconnected():
                logger.info("cliente desconectado; se aborta el turno")
                return

            match event.type:
                case "token":
                    assistant_text.append(event.text)
                case "citations":
                    citations = event.citations
                case "candidates":
                    candidates = event.candidates
                case "handoff_request":
                    handoff = event.request
                case "stage":
                    await store.set_stage(session_id, event.stage)

            yield encode_event(event)

    except Exception:
        logger.exception("fallo durante el turno")
        yield encode_event(
            ErrorEvent(
                code="internal_error",
                message="Se ha producido un error procesando tu mensaje.",
                retryable=True,
            )
        )
        return

    # --- Persistencia del turno --------------------------------------------
    try:
        content = "".join(assistant_text)
        message_id = (
            await store.add_message(
                session_id,
                "assistant",
                content,
                model=settings.model if settings.model_enabled else None,
                effort=settings.effort,
            )
            if content
            else None
        )
        if citations:
            await store.add_citations(message_id, citations)
        if candidates:
            await store.add_recommendations(session_id, candidates, {})
        if isinstance(payload, LeadRequest):
            await store.add_lead(
                session_id,
                payload.lead,
                handoff.model_dump(by_alias=True) if handoff is not None else {},
            )
        # Sin telemetría real de tokens todavía: el lote F la aporta.
        await store.bump_usage(session_id, 0)
    except Exception:
        # El turno ya se entregó al usuario. Un fallo de persistencia se
        # registra pero no se convierte en un error visible a posteriori.
        logger.exception("fallo al persistir el turno %s", session_id)
