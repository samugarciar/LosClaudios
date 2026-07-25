"""Grafo del agente y su runner.

El grafo lleva el estado y el checkpointer; el runner lo consume y traduce a
eventos del contrato. `main.py` solo ve `AgentRunner`, así que sustituir el grafo
—o el modelo, o la recuperación— no toca el endpoint.

Los nodos emiten eventos con el writer de LangGraph y el runner los reenvía tal
cual (`stream_mode="custom"`). Así el streaming al navegador no depende de la
forma interna del estado.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agent.model import ModelPort, build_model
from app.agent.nodes import make_nodes
from app.agent.state import AdvisorState, profile_of
from app.config import Settings
from app.protocol import (
    ChatRequest,
    DoneEvent,
    LeadRequest,
    MessageRequest,
    ServerEvent,
    StageEvent,
    TokenEvent,
)
from app.retrieval.engine import NullRetriever, PostgresRetriever, Retriever

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Aristas condicionales
# ---------------------------------------------------------------------------


def _after_guard(state: AdvisorState) -> str:
    return "escalate_human" if state.get("blocked") else "router"


def _after_router(state: AdvisorState) -> str:
    return "escalate_human" if state.get("handoff_reason") else "extract_profile"


def _after_extract(state: AdvisorState) -> str:
    if state.get("out_of_scope"):
        return "escalate_human"
    if profile_of(state).ready_for_shortlist():
        return "retrieve"
    return "ask_next_question"


def build_graph(
    model: ModelPort,
    retriever: Retriever,
    checkpointer: Any | None = None,
) -> Any:
    nodes = make_nodes(model, retriever)
    graph: StateGraph = StateGraph(AdvisorState)

    for name, fn in nodes.items():
        graph.add_node(name, fn)

    graph.set_entry_point("guard_input")
    graph.add_conditional_edges(
        "guard_input", _after_guard, {"router": "router", "escalate_human": "escalate_human"}
    )
    graph.add_conditional_edges(
        "router",
        _after_router,
        {"extract_profile": "extract_profile", "escalate_human": "escalate_human"},
    )
    graph.add_conditional_edges(
        "extract_profile",
        _after_extract,
        {
            "retrieve": "retrieve",
            "ask_next_question": "ask_next_question",
            "escalate_human": "escalate_human",
        },
    )

    # Pedir un dato termina el turno: la conversación espera al usuario.
    graph.add_edge("ask_next_question", END)

    graph.add_edge("retrieve", "shortlist")
    graph.add_edge("shortlist", "explain")
    graph.add_edge("explain", "handoff")
    graph.add_edge("escalate_human", "handoff")
    graph.add_edge("handoff", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class GraphRunner:
    """Adapta el grafo al puerto que consume `main.py`."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    async def run(
        self, session_id: str, request: ChatRequest
    ) -> AsyncIterator[ServerEvent]:
        if isinstance(request, LeadRequest):
            async for event in self._acknowledge_lead(request):
                yield event
            return

        assert isinstance(request, MessageRequest)
        config = {"configurable": {"thread_id": session_id}}
        state: dict[str, Any] = {
            "session_id": session_id,
            "locale": request.locale,
            "turns": [{"role": "user", "content": request.text}],
        }

        emitted = False
        async for payload in self._graph.astream(
            state, config=config, stream_mode="custom"
        ):
            # El writer emite modelos del contrato; se reenvían sin reinterpretar.
            if isinstance(payload, tuple):  # (namespace, dato) en subgrafos
                payload = payload[-1]
            yield payload  # type: ignore[misc]
            emitted = True

        if not emitted:
            # Un turno sin salida sería una pantalla en blanco. Preferible decirlo.
            logger.error("el grafo no emitió ningún evento en la sesión %s", session_id)
            yield TokenEvent(text="No he podido procesar tu mensaje. Inténtalo de nuevo.")

        yield DoneEvent(message_id=str(uuid.uuid4()))

    async def _acknowledge_lead(
        self, request: LeadRequest
    ) -> AsyncIterator[ServerEvent]:
        yield StageEvent(stage="handoff")
        text = (
            "Recibido. Le paso tus datos y el resumen de esta conversación al equipo "
            "de SICK; te contactarán con todo el contexto ya leído."
            if request.locale == "es"
            else "Got it. I'm passing your details and this conversation's summary to "
            "the SICK team; they'll reach out with the full context already read."
        )
        for chunk in text.split(" "):
            yield TokenEvent(text=chunk + " ")
        yield DoneEvent(message_id=str(uuid.uuid4()))


def build_retriever(pool: Any | None) -> Retriever:
    """Elige recuperador en tres escalones, y deja constancia de cuál.

    1. Postgres, si hay base de datos: es el camino de producción y el único
       que ve el catálogo completo tras la ingesta.
    2. Catálogo local, si está el JSON: da recomendaciones reales sin
       infraestructura. Es lo que permite demostrar el MVP hoy.
    3. Nada: responde vacío, pero lo grita. Cero candidatos NO es «no hay
       producto que cumpla».
    """
    if pool is not None:
        logger.info("recuperación: PostgresRetriever (product_specs)")
        return PostgresRetriever(pool)

    try:
        from app.agent.catalog import Catalog
        from app.retrieval.catalog import CatalogRetriever

        retriever = CatalogRetriever(Catalog.default())
        logger.warning(
            "recuperación: CatalogRetriever sobre el JSON local. Solo ve las "
            "fichas extraídas, no el catálogo completo."
        )
        return retriever
    except FileNotFoundError:
        logger.error(
            "SIN CATÁLOGO y sin base de datos: el agente no podrá proponer "
            "producto. Ver docs/catalog-handover.md."
        )
        return NullRetriever()


async def build_runner(
    settings: Settings,
    checkpointer: Any | None = None,
    pool: Any | None = None,
) -> GraphRunner:
    """Construye el runner con las dependencias que haya disponibles."""
    model = build_model(
        settings.anthropic_api_key, model=settings.model, effort=settings.effort
    )
    retriever = build_retriever(pool)

    if checkpointer is None:
        logger.warning(
            "checkpointer en memoria: la conversación no sobrevive a un reinicio"
        )

    return GraphRunner(build_graph(model, retriever, checkpointer))
