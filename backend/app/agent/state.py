"""Estado del agente y perfil de requisitos.

El perfil es **tipado**, no texto libre: es lo que permite traducir «hay mucho
polvo y entra un carretillero» en restricciones consultables sobre el catálogo.

Dos decisiones que condicionan el resto:

1. `to_retrieval_spec()` incluye una heurística de capacidad de detección por
   parte del cuerpo. **No es una tabla normativa** — sirve para acotar el
   catálogo en una preselección. La capacidad definitiva sale de la evaluación
   de riesgos y de ISO 13855.
2. `out_of_scope_reason()` detecta lo que el catálogo NO cubre. Protección de
   punto de operación y detección de dedos necesitan cortinas ópticas, y en este
   catálogo no hay ninguna. Reconocerlo y derivar es correcto; improvisar con un
   escáner láser sería peligroso.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.protocol import PROFILE_SLOTS, Locale, Slot, Stage

ApplicationType = Literal["area", "access", "point_of_operation"]
BodyPart = Literal["body", "arm", "hand", "finger"]
Mounting = Literal["horizontal", "vertical", "unknown"]
Environment = Literal["indoor_clean", "indoor_dusty", "outdoor"]
AccessFrequency = Literal["rare", "occasional", "frequent"]
ExistingControl = Literal["none", "relay", "safety_plc"]
Region = Literal["eu", "us", "other"]


# Heurística de preselección, NO una tabla normativa. La referencia más
# conservadora disponible en el propio catálogo es la tabla por miembro de
# safeVisionary2: mano 20 / brazo 40 / pierna 50 / cuerpo 200 mm.
_MAX_RESOLUTION_MM: dict[str, int] = {"hand": 20, "arm": 40, "body": 200}


class RequirementProfile(BaseModel):
    """Perfil de requisitos. Todo opcional: se rellena conversando."""

    model_config = ConfigDict(extra="ignore")

    application_type: ApplicationType | None = Field(
        default=None,
        description="area = proteger una zona; access = un paso; "
        "point_of_operation = un punto concreto de la máquina",
    )
    body_part: BodyPart | None = Field(
        default=None, description="Qué debe detectarse: cuerpo, brazo, mano o dedo"
    )
    protected_distance_m: float | None = Field(
        default=None,
        description="Alcance necesario en metros, si el usuario lo ha indicado",
    )
    mounting: Mounting | None = None
    environment: Environment | None = None
    access_frequency: AccessFrequency | None = None
    material_passthrough: bool | None = Field(
        default=None, description="Si pasa material por la zona durante el ciclo"
    )
    existing_control: ExistingControl | None = None
    region: Region | None = None
    stopping_time_known: bool | None = Field(
        default=None, description="Si el usuario conoce el tiempo de parada"
    )
    notes: str | None = Field(
        default=None, description="Detalles relevantes que no encajan en otro campo"
    )

    # --- cobertura ---------------------------------------------------------
    _SLOT_FIELDS: dict[Slot, str] = {
        "application_type": "application_type",
        "body_part": "body_part",
        "area_geometry": "protected_distance_m",
        "mounting": "mounting",
        "environment": "environment",
        "access_frequency": "access_frequency",
        "material_passthrough": "material_passthrough",
        "existing_control": "existing_control",
        "region": "region",
        "stopping_time": "stopping_time_known",
    }

    def missing(self) -> list[Slot]:
        return [
            slot
            for slot in PROFILE_SLOTS
            if getattr(self, self._SLOT_FIELDS[slot], None) is None
        ]

    def filled(self) -> list[Slot]:
        return [slot for slot in PROFILE_SLOTS if slot not in self.missing()]

    def coverage(self) -> float:
        return len(self.filled()) / len(PROFILE_SLOTS)

    # --- decisiones --------------------------------------------------------
    def out_of_scope_reason(self) -> str | None:
        """Qué NO cubre este catálogo. Derivar es la respuesta correcta."""
        if self.application_type == "point_of_operation":
            return (
                "la protección de un punto de operación se resuelve normalmente con "
                "cortinas ópticas de seguridad, y no hay ninguna en el catálogo "
                "disponible"
            )
        if self.body_part == "finger":
            return (
                "la detección de dedos exige una capacidad de detección que ningún "
                "producto del catálogo disponible ofrece"
            )
        return None

    def ready_for_shortlist(self) -> bool:
        """Los cuatro campos que de verdad acotan el catálogo."""
        return all(
            value is not None
            for value in (
                self.application_type,
                self.body_part,
                self.environment,
                self.protected_distance_m,
            )
        )

    def to_filters(self) -> dict[str, Any]:
        """Filtros para el motor Structured (`app.retrieval.structured`).

        Las claves y los valores son los suyos: `ip_rating_in` con grados de
        `IP_RATINGS`, `outdoor` booleano, `resolution_max_mm` numérico. Emitir
        una clave que no exista lanza `FilterError` a propósito — un filtro
        inventado debe romper, no degradarse a una búsqueda sin condiciones que
        devolvería el catálogo entero como si fuera respuesta.

        Solo se emite lo que el cliente ha dicho: un filtro de más descarta
        producto por un requisito que nadie ha pedido.
        """
        filters: dict[str, Any] = {}

        if self.protected_distance_m is not None:
            filters["protective_field_min_m"] = self.protected_distance_m

        if self.body_part and (mm := _MAX_RESOLUTION_MM.get(self.body_part)):
            filters["resolution_max_mm"] = mm

        if self.environment == "outdoor":
            filters["outdoor"] = True
            # A la intemperie no basta con que la ficha declare uso exterior:
            # el grado de protección tiene que acompañar.
            filters["ip_rating_in"] = ["IP65", "IP66", "IP67", "IP69K"]
        elif self.environment == "indoor_dusty":
            filters["ip_rating_in"] = ["IP65", "IP66", "IP67", "IP69K"]
        elif self.environment == "indoor_clean":
            # Sin filtro de IP: en interior limpio un IP20 de armario es válido.
            pass

        return filters


class Turn(TypedDict):
    role: Literal["user", "assistant"]
    content: str


def _extend(left: list[Any], right: list[Any]) -> list[Any]:
    return [*left, *right]


class AdvisorState(TypedDict, total=False):
    """Estado del grafo. Todo serializable: pasa por el checkpointer."""

    session_id: str
    locale: Locale
    turns: Annotated[list[Turn], _extend]
    profile: dict[str, Any]
    stage: Stage
    candidates: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    #: Frases de descarte de las referencias que no pasaron el filtro.
    rejected: list[str]
    handoff_reason: str | None
    out_of_scope: str | None
    blocked: str | None


def profile_of(state: AdvisorState) -> RequirementProfile:
    return RequirementProfile.model_validate(state.get("profile") or {})
