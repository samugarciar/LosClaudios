"""Recorrido completo del grafo sin clave de API ni base de datos.

Usa `ScriptedModel` (determinista) y el catálogo real. Verifica el recorrido y las
decisiones del grafo, no la calidad de la redacción — eso necesita el modelo real
y un conjunto de evaluación validado por un ingeniero, que es trabajo aparte.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agent.catalog import Catalog, default_catalog_path
from app.agent.graph import GraphRunner, build_graph
from app.agent.model import ScriptedModel
from app.agent.nodes import verify_guardrails
from app.agent.retrieval import CatalogRetriever
from app.protocol import MessageRequest

# El corpus no está versionado (ver .gitignore). Las pruebas de guardrails no
# dependen de él, así que solo se salta lo que recorre el grafo.
try:
    default_catalog_path()
    _CATALOG_MISSING = False
except FileNotFoundError:
    _CATALOG_MISSING = True


@pytest.fixture
def runner() -> GraphRunner:
    if _CATALOG_MISSING:
        pytest.skip("falta data/catalog/sick_datasheets.<fecha>.json (no versionado)")
    retriever = CatalogRetriever(Catalog.default())
    return GraphRunner(build_graph(ScriptedModel(), retriever))


async def _turn(runner: GraphRunner, session: str, text: str) -> list[Any]:
    request = MessageRequest(kind="message", locale="es", text=text, slot=None)
    return [event async for event in runner.run(session, request)]


def _types(events: list[Any]) -> list[str]:
    return [event.type for event in events]


# ---------------------------------------------------------------------------
# Descubrimiento
# ---------------------------------------------------------------------------


async def test_primer_turno_pregunta_y_ofrece_opciones(runner: GraphRunner) -> None:
    events = _types(await _turn(runner, "s1", "Necesito proteger una prensa"))
    assert "stage" in events
    assert "token" in events
    assert "chips" in events  # el usuario no técnico necesita opciones
    assert events[-1] == "done"


async def test_no_propone_producto_sin_datos_suficientes(runner: GraphRunner) -> None:
    events = _types(await _turn(runner, "s2", "Necesito proteger una prensa"))
    assert "candidates" not in events
    assert "citations" not in events


async def test_una_sola_pregunta_por_turno(runner: GraphRunner) -> None:
    events = await _turn(runner, "s3", "Necesito proteger una prensa")
    chips_events = [e for e in events if e.type == "chips"]
    assert len(chips_events) == 1
    slots = {chip.slot for chip in chips_events[0].chips}
    assert len(slots) == 1


# ---------------------------------------------------------------------------
# Recorrido hasta preselección
# ---------------------------------------------------------------------------


async def test_recorrido_completo_hasta_handoff(runner: GraphRunner) -> None:
    session = "s4"
    # Los textos son los `value` reales de los chips: el mismo camino que la UI.
    await _turn(runner, session, "Quiero proteger una zona alrededor de la máquina.")
    await _turn(runner, session, "Pasa una persona entera.")
    await _turn(runner, session, "Es interior y limpio.")
    final = await _turn(runner, session, "La zona mide unos 4 metros.")

    events = _types(final)
    assert "citations" in events, "sin citas no hay trazabilidad"
    assert "candidates" in events
    assert "handoff_request" in events
    assert events[-1] == "done"

    candidates = next(e for e in final if e.type == "candidates").candidates
    assert 1 <= len(candidates) <= 3, "el shortlist debe ser corto"
    for candidate in candidates:
        assert candidate.cons, "todo candidato expone contras"
        assert candidate.citation_markers, "todo candidato va citado"


async def test_las_citas_llevan_version_de_documento(runner: GraphRunner) -> None:
    session = "s5"
    await _turn(runner, session, "Quiero proteger una zona alrededor de la máquina.")
    await _turn(runner, session, "Pasa una persona entera.")
    await _turn(runner, session, "Es interior y limpio.")
    final = await _turn(runner, session, "La zona mide unos 4 metros.")

    citations = next(e for e in final if e.type == "citations").citations
    assert citations
    for citation in citations:
        assert citation.doc_version >= 20200101
        assert citation.source_url.startswith("http")


async def test_el_handoff_declara_lo_que_falta(runner: GraphRunner) -> None:
    session = "s6"
    await _turn(runner, session, "Quiero proteger una zona alrededor de la máquina.")
    await _turn(runner, session, "Pasa una persona entera.")
    await _turn(runner, session, "Es interior y limpio.")
    final = await _turn(runner, session, "La zona mide unos 4 metros.")

    request = next(e for e in final if e.type == "handoff_request").request
    # Nadie ha dicho el tiempo de parada, así que debe seguir pendiente.
    assert "stopping_time" in request.missing
    assert request.reason == "missing_critical_data"
    assert request.consent_text_version


# ---------------------------------------------------------------------------
# Fuera de alcance
# ---------------------------------------------------------------------------


async def test_deteccion_de_dedos_deriva_a_humano(runner: GraphRunner) -> None:
    """El catálogo no tiene cortinas ópticas: improvisar con un escáner sería grave."""
    session = "s7"
    await _turn(runner, session, "Quiero proteger una zona alrededor de la máquina.")
    final = await _turn(runner, session, "Hay riesgo de que entren dedos.")

    events = _types(final)
    assert "candidates" not in events
    assert "handoff_request" in events
    assert next(e for e in final if e.type == "handoff_request").request.reason == (
        "out_of_scope"
    )


async def test_punto_de_operacion_deriva_a_humano(runner: GraphRunner) -> None:
    final = await _turn(
        runner, "s8", "Quiero evitar que se meta la mano en un punto de la máquina."
    )
    assert "candidates" not in _types(final)
    assert next(e for e in final if e.type == "handoff_request").request.reason == (
        "out_of_scope"
    )


async def test_peticion_explicita_de_persona(runner: GraphRunner) -> None:
    final = await _turn(runner, "s9", "Prefiero hablar con una persona directamente")
    request = next(e for e in final if e.type == "handoff_request").request
    assert request.reason == "user_request"


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Esta configuración cumple PL d según la ficha.",
        "El conjunto satisface SIL 2 en esta aplicación.",
        "La distancia mínima de seguridad es 1,4 m.",
        "La distancia de seguridad son 850 mm.",
    ],
)
def test_el_verificador_detecta_afirmaciones_prohibidas(text: str) -> None:
    assert verify_guardrails(text)


@pytest.mark.parametrize(
    "text",
    [
        "El microScan3 Pro tiene un campo de protección de 4 m según la ficha [1].",
        "La distancia de montaje depende del tiempo de parada de tu máquina.",
        "El nivel de prestaciones requerido lo determina la evaluación de riesgos.",
    ],
)
def test_el_verificador_no_da_falsos_positivos(text: str) -> None:
    assert verify_guardrails(text) == []
