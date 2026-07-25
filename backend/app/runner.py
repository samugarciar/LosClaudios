"""Puerto del agente.

`main.py` no debe saber que por debajo hay LangGraph: recibe un iterador
asíncrono de eventos del contrato y los escribe en el stream. Ese desacoplamiento
es lo que permite arrancar y verificar el backend antes de que el grafo exista, y
lo que permitirá sustituirlo sin tocar el endpoint.

`EchoRunner` es el sustituto provisional del lote E. El lote F añade
`GraphRunner` con el grafo real; `main.py` no cambia.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Protocol

from app.protocol import (
    ChatRequest,
    DoneEvent,
    LeadRequest,
    MessageRequest,
    ServerEvent,
    StageEvent,
    TokenEvent,
)


class AgentRunner(Protocol):
    """Recibe un turno y emite eventos del contrato."""

    def run(
        self, session_id: str, request: ChatRequest
    ) -> AsyncIterator[ServerEvent]: ...


class EchoRunner:
    """Sustituto provisional: valida el transporte, no el producto.

    No consulta modelo ni recuperación. Existe para poder verificar sesión,
    límites, persistencia y streaming de forma aislada, sin arrastrar el grafo.
    """

    async def run(
        self, session_id: str, request: ChatRequest
    ) -> AsyncIterator[ServerEvent]:
        yield StageEvent(stage="discovery")

        if isinstance(request, LeadRequest):
            text = (
                "Lead recibido. Este es el runner provisional del lote E: "
                "todavía no hay agente detrás."
            )
        elif isinstance(request, MessageRequest):
            text = (
                "Runner provisional del lote E. Recibido: "
                f"«{request.text[:120]}». El grafo llega en el lote F."
            )
        else:  # pragma: no cover — la unión está cerrada
            text = "Petición no reconocida."

        for chunk in text.split(" "):
            yield TokenEvent(text=chunk + " ")

        yield DoneEvent(message_id=str(uuid.uuid4()))
