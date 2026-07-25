"""Acceso al modelo, detrás de un puerto.

`AnthropicModel` llama a Claude de verdad. `ScriptedModel` es determinista y no
necesita clave: existe para que el grafo se pueda probar en CI sin gastar tokens
ni depender de la red, no para producción — y lo dice en el log.

Decisiones de coste que importan:

- El prompt del sistema es invariante por sesión y lleva el breakpoint de caché.
  Interpolar ahí la fecha o el perfil rompería el prefijo en cada petición.
- El contexto que cambia (perfil, fichas recuperadas) viaja en un mensaje aparte,
  después del prefijo cacheado.
- La extracción del perfil corre a esfuerzo bajo: es clasificación, no
  razonamiento. El esfuerzo alto se reserva para la explicación.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol

from anthropic import AsyncAnthropic

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import RequirementProfile, Turn

logger = logging.getLogger(__name__)

# Margen amplio: con pensamiento adaptativo activo, el razonamiento comparte
# presupuesto con el texto de respuesta. Un max_tokens justo trunca a mitad.
_MAX_TOKENS_ANSWER = 12_000
_MAX_TOKENS_EXTRACT = 8_000


class ModelPort(Protocol):
    def stream(
        self,
        *,
        instruction: str,
        turns: Sequence[Turn],
        context: str | None = None,
    ) -> AsyncIterator[str]: ...

    async def extract_profile(
        self, turns: Sequence[Turn], current: RequirementProfile
    ) -> RequirementProfile: ...


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------


class AnthropicModel:
    def __init__(self, api_key: str, *, model: str, effort: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._effort = effort

    @property
    def _system(self) -> list[dict[str, Any]]:
        # El breakpoint va en el último bloque estable: cachea el prompt entero.
        return [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    async def stream(
        self,
        *,
        instruction: str,
        turns: Sequence[Turn],
        context: str | None = None,
    ) -> AsyncIterator[str]:
        messages: list[dict[str, Any]] = [dict(turn) for turn in turns]
        # La instrucción del nodo y el contexto recuperado van al final, después
        # del prefijo cacheado y del historial.
        tail = instruction if context is None else f"{instruction}\n\n{context}"
        messages.append({"role": "user", "content": tail})

        async with self._client.messages.stream(
            model=self._model,
            max_tokens=_MAX_TOKENS_ANSWER,
            system=self._system,
            thinking={"type": "adaptive"},
            output_config={"effort": self._effort},
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

            final = await stream.get_final_message()
            usage = final.usage
            # `cache_write` y `cache_read` son la señal de que el prefijo cacheado
            # funciona: si ambos quedan a 0 turno tras turno, algo lo invalida.
            logger.info(
                "modelo: in=%s out=%s cache_write=%s cache_read=%s",
                usage.input_tokens,
                usage.output_tokens,
                getattr(usage, "cache_creation_input_tokens", None),
                getattr(usage, "cache_read_input_tokens", None),
            )

    async def extract_profile(
        self, turns: Sequence[Turn], current: RequirementProfile
    ) -> RequirementProfile:
        transcript = "\n".join(f"{t['role']}: {t['content']}" for t in turns)
        prompt = (
            "Extrae el perfil de requisitos a partir de TODA la conversación.\n\n"
            "Reglas:\n"
            "- Deja en null lo que el cliente no haya dicho. No adivines.\n"
            "- Si el cliente se corrige, vale la última versión.\n"
            "- `protected_distance_m` solo si ha dado una medida.\n\n"
            f"Perfil actual (puede estar incompleto):\n{current.model_dump_json()}\n\n"
            f"Conversación:\n{transcript}"
        )

        response = await self._client.messages.parse(
            model=self._model,
            max_tokens=_MAX_TOKENS_EXTRACT,
            system=self._system,
            messages=[{"role": "user", "content": prompt}],
            output_format=RequirementProfile,
        )
        parsed = response.parsed_output
        if parsed is None:
            logger.warning("extracción de perfil sin resultado; se conserva el actual")
            return current
        return parsed


# ---------------------------------------------------------------------------
# Sustituto determinista
# ---------------------------------------------------------------------------

# Extractor por palabras clave. Cubre exactamente los valores que emiten los
# chips, que es lo que necesita el smoke test. No pretende entender lenguaje
# libre: para eso está el modelo real.
_KEYWORDS: dict[str, list[tuple[str, Any]]] = {
    "application_type": [
        ("zona alrededor", "area"),
        ("paso", "access"),
        ("meta la mano en un punto", "point_of_operation"),
    ],
    "body_part": [
        ("persona entera", "body"),
        ("brazo", "arm"),
        ("una mano", "hand"),
        ("dedos", "finger"),
    ],
    "environment": [
        ("interior y limpio", "indoor_clean"),
        ("polvo", "indoor_dusty"),
        ("intemperie", "outdoor"),
        ("exterior", "outdoor"),
    ],
    "material_passthrough": [
        ("pasa material", True),
        ("solo pasan personas", False),
    ],
    "access_frequency": [
        ("casi nunca", "rare"),
        ("de vez en cuando", "occasional"),
        ("constantemente", "frequent"),
    ],
    "mounting": [
        ("ras de suelo", "horizontal"),
        ("en vertical", "vertical"),
    ],
    "existing_control": [
        ("plc de seguridad", "safety_plc"),
        ("relé de seguridad", "relay"),
        ("no tenemos nada", "none"),
    ],
    "stopping_time_known": [
        ("conocemos el tiempo de parada", True),
        ("no sabemos el tiempo de parada", False),
    ],
    "region": [
        ("unión europea", "eu"),
        ("estados unidos", "us"),
        ("otro país", "other"),
    ],
}


class ScriptedModel:
    """Determinista, sin red. Para tests y para arrancar sin clave."""

    def __init__(self) -> None:
        logger.warning(
            "ScriptedModel activo: las respuestas son plantillas, no razonamiento. "
            "No apto para producción."
        )

    async def stream(
        self,
        *,
        instruction: str,
        turns: Sequence[Turn],
        context: str | None = None,
    ) -> AsyncIterator[str]:
        text = (
            "[modelo simulado] "
            + instruction.strip().split("\n")[0]
            + (" Contexto recuperado disponible." if context else "")
        )
        for chunk in text.split(" "):
            yield chunk + " "

    async def extract_profile(
        self, turns: Sequence[Turn], current: RequirementProfile
    ) -> RequirementProfile:
        transcript = " ".join(t["content"] for t in turns if t["role"] == "user").lower()
        data = current.model_dump()

        for field_name, options in _KEYWORDS.items():
            if data.get(field_name) is not None:
                continue
            for needle, value in options:
                if needle in transcript:
                    data[field_name] = value
                    break

        if data.get("protected_distance_m") is None and (
            match := re.search(r"(\d+(?:[.,]\d+)?)\s*metros?", transcript)
        ):
            data["protected_distance_m"] = float(match.group(1).replace(",", "."))

        return RequirementProfile.model_validate(data)


def build_model(api_key: str | None, *, model: str, effort: str) -> ModelPort:
    if api_key:
        return AnthropicModel(api_key, model=model, effort=effort)
    return ScriptedModel()
