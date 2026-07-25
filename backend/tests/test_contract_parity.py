"""Paridad del contrato entre TypeScript y Python.

`lib/protocol.ts` y `backend/app/protocol.py` describen el mismo cable. El riesgo
no es que uno falle: es que **ambos validen y signifiquen cosas distintas** — un
campo renombrado en un lado se traduce en eventos silenciosamente descartados en
el otro, sin error en ninguna parte.

Este test lee el TypeScript como texto y lo compara con los modelos Pydantic. Es
un guardia, no un parser: si algún día el fichero TS cambia de forma y el test
deja de encontrar los bloques, falla ruidosamente en vez de pasar en vacío.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.protocol import (
    SERVER_EVENT_TYPES,
    Candidate,
    Chip,
    Citation,
    HandoffRequest,
    Lead,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_TS = REPO_ROOT / "lib" / "protocol.ts"


@pytest.fixture(scope="module")
def ts_source() -> str:
    assert PROTOCOL_TS.is_file(), f"no se encuentra {PROTOCOL_TS}"
    source = PROTOCOL_TS.read_text(encoding="utf-8")
    # Los comentarios contienen dos puntos y ejemplos de campos: fuera.
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"//[^\n]*", "", source)
    return source


def _schema_fields(ts_source: str, schema_name: str) -> set[str]:
    """Nombres de campo de `export const <schema_name> = z.object({...})`."""
    match = re.search(
        rf"export const {schema_name} = z\.object\(\{{(.*?)\n\}}\);",
        ts_source,
        flags=re.DOTALL,
    )
    assert match, f"no se encontró {schema_name} en protocol.ts"
    body = match.group(1)
    return set(re.findall(r"^\s{2}(\w+):", body, flags=re.MULTILINE))


def _python_aliases(model: type) -> set[str]:
    schema = model.model_json_schema(by_alias=True)  # type: ignore[attr-defined]
    return set(schema.get("properties", {}))


# ---------------------------------------------------------------------------
# Tipos de evento
# ---------------------------------------------------------------------------


def test_los_ocho_eventos_coinciden(ts_source: str) -> None:
    block = re.search(
        r"export const ServerEventSchema = z\.discriminatedUnion\((.*?)\n\]\);",
        ts_source,
        flags=re.DOTALL,
    )
    assert block, "no se encontró ServerEventSchema en protocol.ts"

    ts_types = set(re.findall(r'z\.literal\("([a-z_]+)"\)', block.group(1)))
    assert ts_types == set(SERVER_EVENT_TYPES), (
        f"eventos solo en TS: {ts_types - set(SERVER_EVENT_TYPES)} · "
        f"solo en Python: {set(SERVER_EVENT_TYPES) - ts_types}"
    )
    assert len(ts_types) == 8


def test_las_dos_peticiones_coinciden(ts_source: str) -> None:
    block = re.search(
        r"export const ChatRequestSchema = z\.discriminatedUnion\((.*?)\n\]\);",
        ts_source,
        flags=re.DOTALL,
    )
    assert block, "no se encontró ChatRequestSchema en protocol.ts"
    assert set(re.findall(r'z\.literal\("(\w+)"\)', block.group(1))) == {
        "message",
        "lead",
    }


# ---------------------------------------------------------------------------
# Campos de los tipos de dominio
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("schema_name", "model"),
    [
        ("CitationSchema", Citation),
        ("ChipSchema", Chip),
        ("CandidateSchema", Candidate),
        ("HandoffRequestSchema", HandoffRequest),
        ("LeadSchema", Lead),
    ],
)
def test_campos_identicos(ts_source: str, schema_name: str, model: type) -> None:
    ts_fields = _schema_fields(ts_source, schema_name)
    py_fields = _python_aliases(model)
    assert ts_fields == py_fields, (
        f"{schema_name}: solo en TS {ts_fields - py_fields} · "
        f"solo en Python {py_fields - ts_fields}"
    )


# ---------------------------------------------------------------------------
# Invariantes que no deben relajarse en ninguno de los dos lados
# ---------------------------------------------------------------------------


def test_doc_version_es_obligatorio_en_ambos(ts_source: str) -> None:
    """El ancla de auditoría. Hacerlo opcional rompería la trazabilidad (§7)."""
    citation_block = re.search(
        r"export const CitationSchema = z\.object\(\{(.*?)\n\}\);",
        ts_source,
        flags=re.DOTALL,
    )
    assert citation_block
    doc_version_line = re.search(r"docVersion:.*", citation_block.group(1))
    assert doc_version_line
    assert ".optional()" not in doc_version_line.group(0)
    assert ".nullable()" not in doc_version_line.group(0)

    assert Citation.model_fields["doc_version"].is_required()


def test_consentimiento_es_literal_true_en_ambos(ts_source: str) -> None:
    """Sin consentimiento no existe lead válido, a nivel de tipo (§9)."""
    lead_block = re.search(
        r"export const LeadSchema = z\.object\(\{(.*?)\n\}\);",
        ts_source,
        flags=re.DOTALL,
    )
    assert lead_block
    assert "consentAccepted: z.literal(true)" in lead_block.group(1)

    schema = Lead.model_json_schema(by_alias=True)
    assert schema["properties"]["consentAccepted"]["const"] is True


def test_el_limite_de_mensaje_es_el_mismo(ts_source: str) -> None:
    from app.protocol import MAX_USER_MESSAGE_CHARS

    match = re.search(r"MAX_USER_MESSAGE_CHARS = (\d+)", ts_source)
    assert match, "no se encontró MAX_USER_MESSAGE_CHARS en protocol.ts"
    assert int(match.group(1)) == MAX_USER_MESSAGE_CHARS


def test_los_slots_del_perfil_coinciden(ts_source: str) -> None:
    from app.protocol import PROFILE_SLOTS

    block = re.search(r"export const PROFILE_SLOTS = \[(.*?)\] as const;", ts_source, re.DOTALL)
    assert block, "no se encontró PROFILE_SLOTS en protocol.ts"
    ts_slots = tuple(re.findall(r'"(\w+)"', block.group(1)))
    assert ts_slots == PROFILE_SLOTS
