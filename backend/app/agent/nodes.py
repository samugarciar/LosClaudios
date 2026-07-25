"""Nodos del grafo.

Cada nodo emite eventos del contrato a través del writer de LangGraph y devuelve
sus actualizaciones de estado. Ningún nodo escribe en base de datos: eso es de
`main.py`, que ve pasar los eventos.

`explain` es el único nodo que además **verifica**: comprueba su propia salida
contra los guardrails antes de darla por buena. Un prompt no es una garantía.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langgraph.config import get_stream_writer

from app.agent.model import ModelPort
from app.agent.prompts import (
    ASK_INSTRUCTION,
    EXPLAIN_INSTRUCTION,
    OUT_OF_SCOPE_INSTRUCTION,
    SLOT_DESCRIPTIONS,
    SLOT_PRIORITY,
    chips_for,
)
from app.agent.shortlist import MAX_CANDIDATES, build_candidates, describe_rejections
from app.agent.state import AdvisorState, profile_of
from app.protocol import (
    CandidatesEvent,
    ChipsEvent,
    CitationsEvent,
    HandoffRequest,
    HandoffRequestEvent,
    StageEvent,
    TokenEvent,
)
from app.retrieval.engine import Retriever, SpecMatch
from app.retrieval.structured import FilterError, evaluate

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 4000

#: Señales de que el usuario quiere hablar con una persona.
_HUMAN_REQUEST = re.compile(
    r"\b(hablar con (una persona|alguien|un ingeniero)|contact(o|ar)|"
    r"llam(ar|adme|ame)|talk to (a )?(human|person|engineer))\b",
    re.IGNORECASE,
)

#: Intentos de reescribir las reglas del sistema desde el turno del usuario.
_INJECTION = re.compile(
    r"(ignora|olvida|disregard|ignore)\s+(las\s+|tus\s+|the\s+|your\s+)?"
    r"(instrucciones|reglas|instructions|rules|system prompt)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Verificación de guardrails
# ---------------------------------------------------------------------------

#: Afirmar que algo cumple PL/SIL. Lo decide la evaluación de riesgos.
_CLAIMS_COMPLIANCE = re.compile(
    r"\b(cumple|conforme a|satisface|complies with|meets)\b[^.]{0,40}"
    r"\b(PL\s*[a-e]|SIL\s*\d)\b",
    re.IGNORECASE,
)

#: Dar la distancia mínima de seguridad como cifra.
_CLAIMS_SAFETY_DISTANCE = re.compile(
    r"\bdistancia\s+(m[íi]nima|de\s+seguridad)\b[^.]{0,30}?\b\d+(?:[.,]\d+)?\s*(m|mm|cm)\b",
    re.IGNORECASE,
)


def verify_guardrails(text: str) -> list[str]:
    """Devuelve las violaciones encontradas en la salida del modelo."""
    violations: list[str] = []
    if _CLAIMS_COMPLIANCE.search(text):
        violations.append("afirma cumplimiento de PL/SIL")
    if _CLAIMS_SAFETY_DISTANCE.search(text):
        violations.append("da una distancia de seguridad numérica")
    return violations


# ---------------------------------------------------------------------------
# Nodos
# ---------------------------------------------------------------------------


def make_nodes(model: ModelPort, retriever: Retriever) -> dict[str, Any]:
    """Construye los nodos con sus dependencias inyectadas."""

    async def guard_input(state: AdvisorState) -> dict[str, Any]:
        turns = state.get("turns") or []
        last = turns[-1]["content"] if turns else ""

        if len(last) > MAX_INPUT_CHARS:
            return {"blocked": "mensaje demasiado largo"}
        if _INJECTION.search(last):
            # No se corta la conversación: se ignora el intento y se sigue. El
            # prompt del sistema no es negociable desde el turno del usuario.
            logger.warning("posible intento de inyección de prompt; se ignora")
        return {}

    async def router(state: AdvisorState) -> dict[str, Any]:
        turns = state.get("turns") or []
        last = turns[-1]["content"] if turns else ""
        if _HUMAN_REQUEST.search(last):
            return {"handoff_reason": "user_request"}
        return {}

    async def extract_profile(state: AdvisorState) -> dict[str, Any]:
        writer = get_stream_writer()
        writer(StageEvent(stage="discovery"))

        current = profile_of(state)
        updated = await model.extract_profile(state.get("turns") or [], current)
        return {
            "profile": updated.model_dump(),
            "out_of_scope": updated.out_of_scope_reason(),
        }

    async def ask_next_question(state: AdvisorState) -> dict[str, Any]:
        writer = get_stream_writer()
        profile = profile_of(state)
        locale = state.get("locale", "es")

        missing = profile.missing()
        slot = next((s for s in SLOT_PRIORITY if s in missing), None)
        if slot is None:
            return {}

        collected: list[str] = []
        async for chunk in model.stream(
            instruction=ASK_INSTRUCTION.format(slot_description=SLOT_DESCRIPTIONS[slot]),
            turns=state.get("turns") or [],
        ):
            collected.append(chunk)
            writer(TokenEvent(text=chunk))

        writer(ChipsEvent(chips=chips_for(slot, locale)))
        # El turno del asistente vuelve al estado: sin esto el modelo no vería
        # sus propias preguntas anteriores y repetiría alguna.
        return {
            "stage": "discovery",
            "turns": [{"role": "assistant", "content": "".join(collected)}],
        }

    async def retrieve(state: AdvisorState) -> dict[str, Any]:
        writer = get_stream_writer()
        writer(StageEvent(stage="shortlist"))

        profile = profile_of(state)
        filters = profile.to_filters()

        try:
            matches = await retriever.search_specs(filters, limit=20)
        except FilterError:
            # Un filtro inválido es un fallo nuestro, no del cliente. Se
            # registra y se sigue sin candidatos en vez de devolver el catálogo
            # entero como si fuera una respuesta.
            logger.exception("filtros inválidos para el motor Structured: %s", filters)
            matches = []

        rejected: list[str] = []
        if len(matches) < MAX_CANDIDATES:
            # Solo cuando hay hueco en el shortlist se paga una segunda consulta
            # para poder explicar qué quedó fuera y por qué.
            rejected = await _explain_rejections(retriever, filters, matches)

        candidates, citations = build_candidates(matches)
        if citations:
            writer(CitationsEvent(citations=citations))

        return {
            "candidates": [c.model_dump(by_alias=True) for c in candidates],
            "citations": [c.model_dump(by_alias=True) for c in citations],
            "rejected": rejected,
        }

    async def shortlist(state: AdvisorState) -> dict[str, Any]:
        writer = get_stream_writer()
        from app.protocol import Candidate  # noqa: PLC0415 — evita import circular

        raw = state.get("candidates") or []
        candidates = [Candidate.model_validate(item) for item in raw]
        if candidates:
            writer(CandidatesEvent(candidates=candidates))
        return {"stage": "compare"}

    async def explain(state: AdvisorState) -> dict[str, Any]:
        writer = get_stream_writer()
        raw = state.get("candidates") or []
        citations = state.get("citations") or []

        if not raw:
            async for chunk in model.stream(
                instruction=(
                    "No hay ninguna referencia del catálogo que encaje con los "
                    "requisitos. Dilo en dos frases y ofrece contacto con un "
                    "ingeniero. No propongas nada que no esté en el catálogo."
                ),
                turns=state.get("turns") or [],
            ):
                writer(TokenEvent(text=chunk))
            return {"handoff_reason": "out_of_scope"}

        context = _render_context(raw, citations, state.get("rejected") or [])
        collected: list[str] = []
        async for chunk in model.stream(
            instruction=EXPLAIN_INSTRUCTION,
            turns=state.get("turns") or [],
            context=context,
        ):
            collected.append(chunk)
            writer(TokenEvent(text=chunk))

        answer = "".join(collected)
        if violations := verify_guardrails(answer):
            # La salida ya se ha emitido: no se puede retirar. Se corrige de forma
            # visible y se registra, porque es un fallo del prompt, no del usuario.
            logger.error("guardrail incumplido: %s", ", ".join(violations))
            correction = (
                "\n\nCorrección importante: lo anterior no debe leerse como una "
                "declaración de cumplimiento ni como una distancia de montaje "
                "definitiva. Ambas cosas las determina la evaluación de riesgos y "
                "el tiempo de parada de tu máquina, con un ingeniero."
            )
            for chunk in correction.split(" "):
                writer(TokenEvent(text=chunk + " "))

        profile = profile_of(state)
        reason = (
            "profile_complete"
            if profile.stopping_time_known
            else "missing_critical_data"
        )
        return {
            "handoff_reason": reason,
            "turns": [{"role": "assistant", "content": answer}],
        }

    async def escalate_human(state: AdvisorState) -> dict[str, Any]:
        writer = get_stream_writer()
        reason = state.get("out_of_scope")
        if reason:
            async for chunk in model.stream(
                instruction=OUT_OF_SCOPE_INSTRUCTION.format(reason=reason),
                turns=state.get("turns") or [],
            ):
                writer(TokenEvent(text=chunk))
            return {"handoff_reason": "out_of_scope"}
        return {"handoff_reason": state.get("handoff_reason") or "user_request"}

    async def handoff(state: AdvisorState) -> dict[str, Any]:
        writer = get_stream_writer()
        writer(StageEvent(stage="handoff"))

        profile = profile_of(state)
        reason = state.get("handoff_reason") or "profile_complete"

        writer(
            HandoffRequestEvent(
                request=HandoffRequest(
                    reason=reason,  # type: ignore[arg-type]
                    missing=profile.missing(),
                    summary_for_user=_summarize(state),
                    consent_text_version=_consent_version(),
                )
            )
        )
        return {"stage": "handoff"}

    return {
        "guard_input": guard_input,
        "router": router,
        "extract_profile": extract_profile,
        "ask_next_question": ask_next_question,
        "retrieve": retrieve,
        "shortlist": shortlist,
        "explain": explain,
        "escalate_human": escalate_human,
        "handoff": handoff,
    }


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _consent_version() -> str:
    import os  # noqa: PLC0415

    return os.environ.get("CONSENT_TEXT_VERSION", "2026-07-25.v1")


async def _explain_rejections(
    retriever: Retriever, filters: dict[str, Any], matched: list[SpecMatch]
) -> list[str]:
    """Por qué quedaron fuera las referencias que no pasaron el filtro.

    Se pide el catálogo sin filtros y se evalúa cada fila con el mismo
    `evaluate()` que usa el motor. Así el agente puede decir «el nanoScan3 no
    llega: 3 m frente a los 4 que necesitas» en lugar de callarse el descarte,
    que es lo que hace que un shortlist parezca arbitrario.
    """
    try:
        universe = await retriever.search_specs({}, limit=50)
    except FilterError:  # pragma: no cover — {} siempre es válido
        return []

    chosen = {match.part_number for match in matched}
    others = [
        SpecMatch(
            part_number=match.part_number,
            family=match.family,
            variant=match.variant,
            row=match.row,
            checks=evaluate(match.row, filters),
        )
        for match in universe
        if match.part_number not in chosen
    ]
    return describe_rejections(others)


def _render_context(
    candidates: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    rejected: list[str],
) -> str:
    """Contexto recuperado, en texto, para el turno de explicación.

    Va después del prefijo cacheado. Incluye explícitamente lo que NO se sabe:
    si el modelo no ve el hueco, lo rellena.
    """
    lines = ["FICHAS RECUPERADAS (única fuente permitida para cifras):"]
    by_marker = {c["marker"]: c for c in citations}

    for candidate in candidates:
        markers = candidate.get("citationMarkers") or []
        marker = markers[0] if markers else None
        citation = by_marker.get(marker, {})
        lines.append(
            f"\n[{marker}] {candidate['family']} {candidate.get('variant') or ''} "
            f"· ref. {candidate['partNumber']}"
        )
        lines.append(f"    resumen: {citation.get('snippet', '')}")
        lines.append(f"    revisión del documento: {citation.get('docVersion')}")
        for pro in candidate.get("pros", []):
            lines.append(f"    encaja: {pro}")
        for con in candidate.get("cons", []):
            lines.append(f"    vigilar: {con}")

    if rejected:
        lines.append("\nREFERENCIAS DESCARTADAS Y POR QUÉ (puedes mencionarlo):")
        lines.extend(f"    {line}" for line in rejected[:5])

    return "\n".join(lines)


def _summarize(state: AdvisorState) -> str:
    profile = profile_of(state)
    filled = profile.filled()
    parts: list[str] = []
    if profile.application_type:
        parts.append(f"aplicación: {profile.application_type}")
    if profile.environment:
        parts.append(f"entorno: {profile.environment}")
    if profile.protected_distance_m:
        parts.append(f"zona de ~{profile.protected_distance_m} m")
    if profile.body_part:
        parts.append(f"detección de: {profile.body_part}")
    candidates = state.get("candidates") or []
    if candidates:
        refs = ", ".join(c["partNumber"] for c in candidates)
        parts.append(f"preselección: {refs}")
    parts.append(f"{len(filled)} de 10 datos del perfil recogidos")
    return " · ".join(parts)
