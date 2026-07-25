"""Contrato frontend ↔ agente, lado servidor.

ESPEJO EXACTO de `lib/protocol.ts`. Los dos ficheros describen el mismo cable en
dos lenguajes, y ahí vive el riesgo más caro del sistema: dos contratos que
validan correctamente y significan cosas distintas. `tests/test_contract_parity.py`
compara ambos y falla si divergen.

El cable es camelCase (viene de TypeScript). Aquí se escribe snake_case y se
serializa con alias automático — de ahí `alias_generator=to_camel`. Emitir
siempre con `by_alias=True`; hay un helper en `sse.py` que lo garantiza.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# ---------------------------------------------------------------------------
# Vocabulario cerrado
# ---------------------------------------------------------------------------

Locale = Literal["es", "en"]
Stage = Literal["discovery", "shortlist", "compare", "handoff"]

Slot = Literal[
    "application_type",
    "body_part",
    "area_geometry",
    "mounting",
    "environment",
    "access_frequency",
    "material_passthrough",
    "existing_control",
    "region",
    "stopping_time",
]
PROFILE_SLOTS: tuple[Slot, ...] = (
    "application_type",
    "body_part",
    "area_geometry",
    "mounting",
    "environment",
    "access_frequency",
    "material_passthrough",
    "existing_control",
    "region",
    "stopping_time",
)

HandoffReason = Literal[
    "profile_complete",
    "missing_critical_data",
    "user_request",
    "out_of_scope",
]

MAX_USER_MESSAGE_CHARS = 4000


class _Wire(BaseModel):
    """Base de todo lo que viaja por el cable."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


# ---------------------------------------------------------------------------
# Tipos de dominio
# ---------------------------------------------------------------------------


class Citation(_Wire):
    marker: int = Field(gt=0)
    doc_id: str = Field(min_length=1)
    # Ancla de auditoría (README §7). NO opcional: sin la versión del documento
    # una recomendación pasada no es reconstruible.
    doc_version: int = Field(ge=0)
    doc_title: str = Field(min_length=1)
    page: int | None = Field(default=None, gt=0)
    section_path: str | None = None
    snippet: str
    source_url: str = Field(min_length=1)
    score: float | None = None


class Chip(_Wire):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    slot: Slot | None = None


class Candidate(_Wire):
    part_number: str = Field(min_length=1)
    family: str = Field(min_length=1)
    variant: str | None = None
    rank: int = Field(gt=0)
    headline: str = Field(min_length=1)
    pros: list[str] = Field(default_factory=list)
    # Regla de diseño (README §8): un shortlist honesto expone contras. El
    # esquema es permisivo, pero un candidato sin contras es un defecto del
    # agente y `explain` lo trata como tal.
    cons: list[str] = Field(default_factory=list)
    citation_markers: list[int] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class HandoffRequest(_Wire):
    reason: HandoffReason
    missing: list[Slot] = Field(default_factory=list)
    summary_for_user: str = ""
    consent_text_version: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Eventos servidor → cliente (los 8 del contrato)
# ---------------------------------------------------------------------------


class TokenEvent(_Wire):
    type: Literal["token"] = "token"
    text: str


class StageEvent(_Wire):
    type: Literal["stage"] = "stage"
    stage: Stage


class ChipsEvent(_Wire):
    type: Literal["chips"] = "chips"
    chips: list[Chip] = Field(default_factory=list)


class CitationsEvent(_Wire):
    type: Literal["citations"] = "citations"
    citations: list[Citation] = Field(default_factory=list)


class CandidatesEvent(_Wire):
    type: Literal["candidates"] = "candidates"
    candidates: list[Candidate] = Field(default_factory=list)


class HandoffRequestEvent(_Wire):
    type: Literal["handoff_request"] = "handoff_request"
    request: HandoffRequest


class DoneEvent(_Wire):
    type: Literal["done"] = "done"
    message_id: str = Field(min_length=1)


class ErrorEvent(_Wire):
    type: Literal["error"] = "error"
    code: str = Field(min_length=1)
    message: str
    retryable: bool


ServerEvent = Annotated[
    TokenEvent
    | StageEvent
    | ChipsEvent
    | CitationsEvent
    | CandidatesEvent
    | HandoffRequestEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]

SERVER_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "token",
        "stage",
        "chips",
        "citations",
        "candidates",
        "handoff_request",
        "done",
        "error",
    }
)


# ---------------------------------------------------------------------------
# Peticiones cliente → servidor
# ---------------------------------------------------------------------------


class Lead(_Wire):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    company: str | None = Field(default=None, max_length=160)
    country: str | None = Field(default=None, max_length=80)
    # `True` literal: sin consentimiento explícito no existe lead válido a
    # nivel de tipo, no solo de validación de formulario (README §9).
    consent_accepted: Literal[True]
    consent_text_version: str = Field(min_length=1)


class MessageRequest(_Wire):
    kind: Literal["message"] = "message"
    locale: Locale
    text: str = Field(min_length=1, max_length=MAX_USER_MESSAGE_CHARS)
    slot: Slot | None = None


class LeadRequest(_Wire):
    kind: Literal["lead"] = "lead"
    locale: Locale
    lead: Lead


ChatRequest = Annotated[MessageRequest | LeadRequest, Field(discriminator="kind")]
