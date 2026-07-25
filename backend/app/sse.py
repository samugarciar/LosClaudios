"""Serialización SSE.

Un único sitio donde se convierte un evento en bytes, para que `by_alias=True`
no dependa de que cada llamante se acuerde. Olvidarlo emitiría `doc_version` en
lugar de `docVersion` y el frontend descartaría el evento en silencio.
"""

from __future__ import annotations

from pydantic import BaseModel

# Un comentario SSE (línea que empieza por ':') mantiene la conexión viva
# atravesando proxies sin que el cliente vea ningún evento.
HEARTBEAT = ": ping\n\n"

SSE_HEADERS: dict[str, str] = {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-cache, no-transform",
    "connection": "keep-alive",
    # Sin esto, algunos proxies bufferizan la respuesta y rompen el streaming.
    "x-accel-buffering": "no",
}


def encode_event(event: BaseModel) -> str:
    """Serializa un evento del contrato como frame SSE."""
    return f"data: {event.model_dump_json(by_alias=True, exclude_none=False)}\n\n"
