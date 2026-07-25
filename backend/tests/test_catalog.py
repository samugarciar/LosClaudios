"""Los límites conocidos del catálogo, convertidos en aserciones.

`docs/catalog-handover.md` §5 y §6 enumeran reglas y trampas del dato. En prosa
no protegen de nada: si mañana cambia la extracción o alguien "simplifica" un
parser, sólo un test lo detecta. Cada prueba de aquí cita el apartado que defiende.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.agent.catalog import (
    INDOOR,
    OUTDOOR,
    Catalog,
    CatalogQuery,
    default_catalog_path,
    parse_pfhd,
)
from app.agent.retrieval import CatalogRetriever, RetrievalSpec

# El corpus NO está versionado: es documentación de SICK con revisión de términos
# pendiente (ver .gitignore y docs/catalog-handover.md). Sin él estos tests se
# saltan con motivo visible, en lugar de fallar por una causa que no es un bug.
try:
    default_catalog_path()
    _CATALOG_MISSING = False
except FileNotFoundError:
    _CATALOG_MISSING = True

pytestmark = pytest.mark.skipif(
    _CATALOG_MISSING,
    reason="falta data/catalog/sick_datasheets.<fecha>.json (no versionado)",
)

# Referencias con comportamiento singular, verificadas contra el JSON real.
SAFE_VISIONARY = "1116398"  # cámara 3D, único PL c, IP dual, resolución por miembro
RADAR_SENSOR = "6080599"  # safeRS3 sensor: IP67, PFHd como prosa
RADAR_SENSOR_9M = "6082806"
RADAR_CONTROL = "6080600"  # safeRS3 unidad de control: IP20
OLD_REVISION = "1100334"  # revisión de 2020 con advertencia
DUAL_PRODUCT = "1126792"  # aparece en dos productos


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.default()


@pytest.fixture
def retriever(catalog: Catalog) -> CatalogRetriever:
    return CatalogRetriever(catalog, today=date(2026, 7, 25))


# ---------------------------------------------------------------------------
# §2 — `pendientes` no son fichas
# ---------------------------------------------------------------------------


def test_solo_registros_son_fichas(catalog: Catalog) -> None:
    assert len(catalog.records) == 15
    assert len(catalog.pending_references) == 5


@pytest.mark.parametrize(
    "reference", ["1094455", "1110035", "1110033", "1094465", "1092538"]
)
def test_una_pendiente_no_se_puede_consultar(catalog: Catalog, reference: str) -> None:
    """Tratarlas como fichas produciría respuestas incompletas dadas por completas."""
    assert catalog.get(reference) is None
    assert catalog.is_pending(reference) is True


async def test_describe_distingue_pendiente_de_desconocida(
    retriever: CatalogRetriever,
) -> None:
    pendiente = await retriever.describe("1094455")
    assert pendiente.candidates == []
    assert "pendiente" in pendiente.indeterminate[0][1]

    desconocida = await retriever.describe("0000000")
    assert "desconocida" in desconocida.indeterminate[0][1]


def test_no_se_confunde_1110035_con_1110034(catalog: Catalog) -> None:
    """§6.1: 1110034 es un artículo distinto y no sustituye a 1110035."""
    assert catalog.is_pending("1110035") is True
    assert catalog.get("1110034") is None
    assert catalog.is_pending("1110034") is False


# ---------------------------------------------------------------------------
# §5.1 / §6.3 — un campo ausente no es cero
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reference", [RADAR_SENSOR, RADAR_SENSOR_9M, RADAR_CONTROL])
def test_pfhd_de_saferS3_es_none_y_no_cero(catalog: Catalog, reference: str) -> None:
    """Un PFHd de 0.0 declararía probabilidad de fallo peligroso nula."""
    record = catalog.get(reference)
    assert record is not None
    assert record.pfhd is None
    assert record.pfhd_raw is not None
    assert "instrucciones de uso" in record.pfhd_raw.lower()


def test_pfhd_numerico_se_parsea_con_coma_decimal() -> None:
    value, raw = parse_pfhd("8,0e-8")
    assert value == pytest.approx(8.0e-8)
    assert raw == "8,0e-8"


def test_pfhd_en_prosa_no_devuelve_numero() -> None:
    value, raw = parse_pfhd("Ver instrucciones de uso, apartado Parametros de seguridad")
    assert value is None
    assert raw is not None


def test_filtro_sin_dato_es_indeterminado_no_descartado(catalog: Catalog) -> None:
    """Los controladores no tienen campo de protección: no es que no cumplan."""
    result = catalog.search(CatalogQuery(min_protective_field_m=3.0))
    indeterminadas = {record.reference for record, _ in result.indeterminate}
    assert "1085349" in indeterminadas  # Flexi Compact, un controlador
    razones = {reason for _, reason in result.indeterminate}
    assert any("campo de protección" in reason for reason in razones)


# ---------------------------------------------------------------------------
# §5.2 — no generalizar entre familias ni partes del sistema
# ---------------------------------------------------------------------------


def test_saferS3_no_tiene_un_unico_grado_ip(catalog: Catalog) -> None:
    """Responder «safeRS3 es IP67» llevaría a montar un IP20 a la intemperie."""
    sensor = catalog.get(RADAR_SENSOR)
    control = catalog.get(RADAR_CONTROL)
    assert sensor is not None and control is not None

    assert sensor.system_part == "Sensor"
    assert control.system_part == "Unidad de control"
    assert sensor.ip is not None and control.ip is not None
    assert sensor.ip.best == 67
    assert control.ip.best == 20


def test_safevisionary2_es_el_unico_pl_c(catalog: Catalog) -> None:
    pl_c = [r.reference for r in catalog.records if r.performance_level == "PL c"]
    assert pl_c == [SAFE_VISIONARY]


def test_grado_ip_doble_se_conserva(catalog: Catalog) -> None:
    record = catalog.get(SAFE_VISIONARY)
    assert record is not None
    assert record.ip is not None
    assert record.ip.values == (65, 67)
    assert record.ip.worst == 65


def test_el_exterior_lo_cubre_el_radar_no_el_escaner(catalog: Catalog) -> None:
    """outdoorScan3 quedó excluido (§6.6), pero safeRS3 declara Indoor / Outdoor."""
    exteriores = {r.reference for r in catalog.records if OUTDOOR in r.environments}
    assert RADAR_SENSOR in exteriores
    interior = catalog.get(SAFE_VISIONARY)
    assert interior is not None
    assert interior.environments == frozenset({INDOOR})


# ---------------------------------------------------------------------------
# Normalización de valores reales
# ---------------------------------------------------------------------------


def test_campo_de_proteccion_como_rango(catalog: Catalog) -> None:
    record = catalog.get(RADAR_SENSOR)
    assert record is not None
    span = record.protective_field_m
    assert span is not None
    assert (span.low, span.high) == (0.2, 5.0)
    assert span.is_range is True


def test_campo_de_proteccion_como_cota_con_condicion(catalog: Catalog) -> None:
    record = catalog.get(SAFE_VISIONARY)
    assert record is not None
    span = record.protective_field_m
    assert span is not None
    assert span.high == 2.0
    assert span.note is not None
    assert "alcance ampliado" in span.note


def test_temperatura_conserva_su_condicion(catalog: Catalog) -> None:
    record = catalog.get(SAFE_VISIONARY)
    assert record is not None
    temp = record.operating_temp_c
    assert temp is not None
    assert (temp.low, temp.high) == (-10.0, 50.0)
    assert temp.note is not None
    assert "disipador" in temp.note


def test_resolucion_por_parte_del_cuerpo(catalog: Catalog) -> None:
    """Encaja directamente con el slot `body_part` del perfil de requisitos."""
    record = catalog.get(SAFE_VISIONARY)
    assert record is not None
    assert record.resolution_by_body_part == {
        "mano": 20,
        "brazo": 40,
        "pierna": 50,
        "cuerpo": 200,
    }


# ---------------------------------------------------------------------------
# §6.2 / §6.5 — advertencias y deduplicación
# ---------------------------------------------------------------------------


def test_revision_antigua_expone_su_advertencia(catalog: Catalog) -> None:
    record = catalog.get(OLD_REVISION)
    assert record is not None
    assert record.provenance.revision_date.year == 2020
    assert record.provenance.warning is not None


async def test_la_advertencia_llega_a_las_contras(retriever: CatalogRetriever) -> None:
    result = await retriever.describe(OLD_REVISION)
    assert any("aviso sobre la fuente" in c.lower() for c in result.candidates[0].cons)


def test_referencia_en_dos_productos_es_un_solo_registro(catalog: Catalog) -> None:
    record = catalog.get(DUAL_PRODUCT)
    assert record is not None
    assert len(record.products) == 2
    # Contar por producto duplicaría; contar registros no.
    assert sum(1 for r in catalog.records if r.reference == DUAL_PRODUCT) == 1
    assert sum(catalog.families().values()) == len(catalog.records)


# ---------------------------------------------------------------------------
# Trazabilidad
# ---------------------------------------------------------------------------


def test_doc_version_se_deriva_de_la_fecha_de_revision(catalog: Catalog) -> None:
    record = catalog.get("1091037")
    assert record is not None
    assert record.provenance.revision_date == date(2026, 5, 12)
    assert record.provenance.doc_version == 20260512


async def test_toda_cita_lleva_version_y_url(retriever: CatalogRetriever) -> None:
    result = await retriever.search(RetrievalSpec())
    assert result.citations
    for citation in result.citations:
        assert citation.doc_version > 0
        assert citation.source_url.startswith("http")
        # La extracción actual no trae página: se cita la ficha completa.
        assert citation.page is None


async def test_todo_candidato_expone_contras(retriever: CatalogRetriever) -> None:
    """Un shortlist sin contras sería un catálogo, no un asesoramiento."""
    from app.agent.retrieval import RetrievalSpec

    result = await retriever.search(RetrievalSpec())
    assert result.candidates
    for candidate in result.candidates:
        assert candidate.cons, f"{candidate.part_number} sin contras"
        assert any("distancia de montaje" in c for c in candidate.cons)
