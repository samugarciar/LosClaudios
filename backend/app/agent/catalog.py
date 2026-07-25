"""Catálogo de fichas técnicas SICK.

Carga `data/catalog/sick_datasheets.*.json` y convierte sus campos en valores
consultables. Las reglas del §5 de `docs/catalog-handover.md` están implementadas
aquí **como código**, no como documentación:

  §5.1  Un campo ausente no es cero → `None`, y las búsquedas lo devuelven como
        INDETERMINADO, nunca como descartado.
  §5.2  No generalizar entre familias → `parte_sistema` viaja en el registro y
        cada referencia se filtra por sí misma.
  §5.4  Nunca inferir del código de tipo → no hay parser de nomenclatura.
  §5.5  Funciones con condición → los strings de `funciones` se conservan
        íntegros, con su condición.
  §6.2  Revisión antigua → `advertencia` se propaga.
  §6.5  Referencias en dos productos → un registro por referencia.

Diseño clave: distinguir **«no cumple»** de **«la ficha no lo dice»**. Un dato
ausente de seguridad funcional convertido en 0.0 sería un fallo grave, no un
detalle de parseo — las fichas de safeRS3 traen `pfhd` como prosa, no como número.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Valores
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Span:
    """Magnitud que puede ser un punto o un rango, conservando el original.

    `'0,2 a 5'` → Span(0.2, 5). `4` → Span(4, 4).
    `'<=2 (4 m en modo alcance ampliado)'` → Span(0, 2, note='4 m en modo…').
    """

    low: float
    high: float
    raw: str
    note: str | None = None

    @property
    def is_range(self) -> bool:
        return self.low != self.high


@dataclass(frozen=True, slots=True)
class IpRating:
    """Grado IP. Puede haber más de uno en la misma ficha ('IP65 / IP67')."""

    values: tuple[int, ...]
    raw: str

    @property
    def best(self) -> int:
        return max(self.values)

    @property
    def worst(self) -> int:
        return min(self.values)


@dataclass(frozen=True, slots=True)
class Provenance:
    """Trazabilidad de una ficha (§5.3)."""

    reference: str
    revision_date: date
    source_url: str
    language: str
    title: str
    warning: str | None = None

    @property
    def doc_version(self) -> int:
        """Versión entera para `citations.doc_version`.

        El origen trae fecha de revisión, no número de versión, y nuestro esquema
        exige un entero NOT NULL. `2026-05-12` → `20260512`: monótono, auditable
        y legible a ojo, sin inventarse una numeración que nadie ha asignado.
        """
        return int(self.revision_date.strftime("%Y%m%d"))


# ---------------------------------------------------------------------------
# Normalizadores
# ---------------------------------------------------------------------------

_NUM = r"-?\d+(?:[.,]\d+)?"


def _to_float(raw: str) -> float | None:
    """Convierte con coma o punto decimal. Devuelve None si no es numérico."""
    try:
        return float(raw.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    ).lower()


def parse_span(value: Any) -> Span | None:
    """Número, rango `'a a b'`, o cota `'<=n'`. Conserva la condición entre paréntesis."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Span(float(value), float(value), raw=str(value))
    if not isinstance(value, str):
        return None

    raw = value.strip()
    note_match = re.search(r"\(([^)]*)\)", raw)
    note = note_match.group(1).strip() if note_match else None
    body = re.sub(r"\([^)]*\)", "", raw).strip()

    if rng := re.search(rf"({_NUM})\s*(?:a|-|–|hasta)\s*({_NUM})", body):
        low, high = _to_float(rng.group(1)), _to_float(rng.group(2))
        if low is not None and high is not None:
            return Span(min(low, high), max(low, high), raw=raw, note=note)

    if cap := re.search(rf"<=\s*({_NUM})", body):
        high = _to_float(cap.group(1))
        if high is not None:
            return Span(0.0, high, raw=raw, note=note)

    if single := re.search(rf"({_NUM})", body):
        n = _to_float(single.group(1))
        if n is not None:
            return Span(n, n, raw=raw, note=note)

    return None


def parse_ip(value: Any) -> IpRating | None:
    """`'IP65 / IP67 (IEC 60529)'` → IpRating((65, 67))."""
    if not isinstance(value, str):
        return None
    found = tuple(int(m) for m in re.findall(r"IP\s*(\d{2})", value, flags=re.IGNORECASE))
    return IpRating(values=found, raw=value.strip()) if found else None


def parse_temp_range(value: Any) -> Span | None:
    """`'-10 C a +50 C (disipador necesario desde 40 C)'` → Span(-10, 50, note=…)."""
    if not isinstance(value, str):
        return None
    note_match = re.search(r"\(([^)]*)\)", value)
    note = note_match.group(1).strip() if note_match else None
    body = re.sub(r"\([^)]*\)", "", value)
    nums = [_to_float(n) for n in re.findall(rf"({_NUM})\s*C", body)]
    clean = [n for n in nums if n is not None]
    if len(clean) < 2:
        return None
    return Span(min(clean), max(clean), raw=value.strip(), note=note)


def parse_pfhd(value: Any) -> tuple[float | None, str | None]:
    """Devuelve (número, texto original).

    En safeRS3 el valor es prosa: *'Ver instrucciones de uso, apartado
    Parametros de seguridad'*. Convertirlo en 0.0 sería declarar una
    probabilidad de fallo peligroso de cero. Se devuelve None y el texto se
    conserva para poder mostrarlo tal cual (§6.3).
    """
    if value is None:
        return None, None
    raw = str(value).strip()
    if m := re.fullmatch(rf"\s*({_NUM})\s*[eE]\s*({_NUM})\s*", raw):
        mantissa, exponent = _to_float(m.group(1)), _to_float(m.group(2))
        if mantissa is not None and exponent is not None:
            return mantissa * (10**exponent), raw
    return None, raw


# Orden de niveles de prestaciones. safeVisionary2 es el único PL c (§5.2).
_PL_RANK = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}


def parse_pl_rank(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    if m := re.search(r"PL\s*([a-e])", value, flags=re.IGNORECASE):
        return _PL_RANK.get(m.group(1).lower())
    return None


def parse_degrees(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    m = re.search(rf"({_NUM})\s*grados", value)
    return _to_float(m.group(1)) if m else None


def parse_resolutions(value: Any) -> tuple[int, ...]:
    """Lista de resoluciones configurables, o el dict por parte del cuerpo."""
    if isinstance(value, list):
        return tuple(int(v) for v in value if isinstance(v, (int, float)))
    if isinstance(value, dict):
        return tuple(sorted(int(v) for v in value.values() if isinstance(v, (int, float))))
    if isinstance(value, (int, float)):
        return (int(value),)
    return ()


# ---------------------------------------------------------------------------
# Convenciones de valor del equipo de RAG
# ---------------------------------------------------------------------------
# Estas cuatro funciones replican las de `ingest/normalize.py`. No se importan
# porque `ingest/` vive fuera del paquete del backend. `test_catalog.py` verifica
# que no divergimos de sus enums: si lo hacen, el filtro fallaría en silencio.

_DEVICE_CATEGORY_BY_FAMILY: dict[str, str] = {
    "escaner laser de seguridad": "laser_scanner",
    "controladores de seguridad": "safety_controller",
    "camara 3d de seguridad": "safety_camera_3d",
    "sensores de radar seguros": "safety_radar",
}


def device_category_of(family: str) -> str | None:
    return _DEVICE_CATEGORY_BY_FAMILY.get(_strip_accents(family).strip())


def parse_sil_short(value: Any) -> str | None:
    """`'SIL 2 (IEC 61508)'` → `'SIL 2'`."""
    if not isinstance(value, str):
        return None
    m = re.search(r"SIL\s*(\d)", value, flags=re.IGNORECASE)
    return f"SIL {m.group(1)}" if m else None


def parse_ip_short(rating: IpRating | None) -> str | None:
    """`IpRating((65, 67))` → `'IP65'`.

    El **menor** de los dos, igual que su ingesta. Es el criterio conservador:
    prometer IP67 cuando la ficha admite una variante IP65 podría acabar en un
    equipo montado donde no debe.
    """
    return f"IP{rating.worst}" if rating else None


def parse_label_int(value: Any, prefix: str) -> int | None:
    """`'Categoria 3'` → 3 · `'Tipo 2 (IEC 61496-3)'` → 2."""
    if not isinstance(value, str):
        return None
    m = re.search(rf"{prefix}\s*(\d)", value, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

# Ámbito de uso declarado en la ficha (`aplicacion`).
INDOOR = "indoor"
OUTDOOR = "outdoor"


@dataclass(frozen=True, slots=True)
class CatalogRecord:
    reference: str
    variant: str
    family: str
    version: str | None
    products: tuple[str, ...]
    # §5.2: en safeRS3 el sensor es IP67 y la unidad de control IP20.
    system_part: str | None

    # Seguridad funcional
    performance_level: str | None
    pl_rank: int | None
    sil: str | None
    iso13849_category: str | None
    iec61496_type: str | None
    pfhd: float | None
    pfhd_raw: str | None

    # Detección
    protective_field_m: Span | None
    warning_field_m: Span | None
    resolutions_mm: tuple[int, ...]
    resolution_by_body_part: dict[str, int] | None
    response_time_ms: Span | None
    scan_angle_deg: float | None
    field_sets: int | None
    monitoring_cases: int | None

    # Entorno
    ip: IpRating | None
    operating_temp_c: Span | None
    environments: frozenset[str]

    functions: tuple[str, ...]
    provenance: Provenance
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def display_name(self) -> str:
        return f"{self.version or self.family} · {self.variant}"

    def supports(self, environment: str) -> bool | None:
        """None = la ficha no lo dice. No es lo mismo que «no»."""
        if not self.environments:
            return None
        return environment in self.environments

    def to_spec_row(self) -> dict[str, Any]:
        """Fila con los nombres de columna de `product_specs` (rango 0100+).

        Es la pieza que une los dos mundos: emitiendo las claves que espera el
        motor Structured del equipo de RAG, su `evaluate()` y su `SpecMatch`
        operan sobre el catálogo en memoria **sin ninguna modificación**. La
        misma fila sale de SQL en producción y de este JSON en desarrollo.
        """
        protective = self.protective_field_m
        warning = self.warning_field_m
        response = self.response_time_ms
        temp = self.operating_temp_c
        measuring = parse_span(self.raw.get("alcance_medida_m"))

        return {
            "part_number": self.reference,
            "family": self.family,
            "variant": self.variant,
            "device_category": device_category_of(self.family),
            "protective_field_min_m": protective.low if protective else None,
            "protective_field_max_m": protective.high if protective else None,
            "warning_field_min_m": warning.low if warning else None,
            "warning_field_max_m": warning.high if warning else None,
            "measuring_range_max_m": measuring.high if measuring else None,
            "response_time_min_ms": response.low if response else None,
            "response_time_max_ms": response.high if response else None,
            "resolution_mm": list(self.resolutions_mm),
            "scan_angle_deg": self.scan_angle_deg,
            "n_fields_max": self.field_sets,
            "n_monitoring_cases_max": self.monitoring_cases,
            "pl": self.performance_level,
            "sil": parse_sil_short(self.sil),
            "iso13849_category": parse_label_int(self.iso13849_category, "categoria"),
            "iec61496_type": parse_label_int(self.iec61496_type, "tipo"),
            "pfhd": self.pfhd,
            "ip_rating": parse_ip_short(self.ip),
            # `outdoor` sale a None si la ficha no declara ámbito: su filtro usa
            # `is not true`, de modo que un None nunca se lee como «vale fuera».
            "outdoor": (OUTDOOR in self.environments) if self.environments else None,
            "temp_min_c": temp.low if temp else None,
            "temp_max_c": temp.high if temp else None,
            "raw": self.raw,
            # Procedencia, con los alias que su SELECT da a las columnas de
            # `documents`, para que `SpecMatch.citation()` funcione igual.
            "doc_id": self.provenance.reference,
            "doc_version": self.provenance.doc_version,
            "doc_title": self.provenance.title,
            "source_url": self.provenance.source_url,
            "revision_date": self.provenance.revision_date,
        }


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        span = parse_span(value)
        return int(span.high) if span else None
    return None


def _build_record(raw: dict[str, Any]) -> CatalogRecord:
    pfhd, pfhd_raw = parse_pfhd(raw.get("pfhd"))

    application = raw.get("aplicacion") or ""
    environments: set[str] = set()
    if "indoor" in application.lower():
        environments.add(INDOOR)
    if "outdoor" in application.lower():
        environments.add(OUTDOOR)

    body_parts = raw.get("resolucion_objeto_mm")
    by_body_part = (
        {str(k): int(v) for k, v in body_parts.items() if isinstance(v, (int, float))}
        if isinstance(body_parts, dict)
        else None
    )

    revision = date.fromisoformat(str(raw["fecha_revision"]))
    reference = str(raw["referencia"])

    return CatalogRecord(
        reference=reference,
        variant=str(raw.get("variante", "")),
        family=str(raw.get("familia", "")),
        version=raw.get("version"),
        products=tuple(raw.get("productos") or ()),
        system_part=raw.get("parte_sistema"),
        performance_level=raw.get("performance_level"),
        pl_rank=parse_pl_rank(raw.get("performance_level")),
        sil=raw.get("sil"),
        iso13849_category=raw.get("categoria_iso13849"),
        iec61496_type=raw.get("tipo_iec61496"),
        pfhd=pfhd,
        pfhd_raw=pfhd_raw,
        protective_field_m=parse_span(raw.get("campo_proteccion_m")),
        warning_field_m=parse_span(raw.get("campo_aviso_m")),
        resolutions_mm=parse_resolutions(
            raw.get("resolucion_configurable_mm") or raw.get("resolucion_objeto_mm")
        ),
        resolution_by_body_part=by_body_part,
        response_time_ms=parse_span(raw.get("tiempo_respuesta_ms")),
        scan_angle_deg=parse_degrees(raw.get("angulo_escaneo")),
        field_sets=_int_or_none(raw.get("num_campos")),
        monitoring_cases=_int_or_none(raw.get("num_casos_monitorizacion")),
        ip=parse_ip(raw.get("grado_proteccion_ip")),
        operating_temp_c=parse_temp_range(raw.get("temp_servicio")),
        environments=frozenset(environments),
        functions=tuple(raw.get("funciones") or ()),
        provenance=Provenance(
            reference=reference,
            revision_date=revision,
            source_url=str(raw.get("url_fuente", "")),
            language=str(raw.get("idioma_fuente", "")),
            title=f"Ficha técnica {raw.get('variante', reference)}",
            warning=raw.get("advertencia"),
        ),
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------
# El filtrado NO vive aquí. Lo hace el motor Structured del equipo de RAG
# (`app.retrieval.structured`), que aplica los mismos criterios sobre SQL y
# sobre memoria. Duplicar la lógica de filtro era garantizar que un día
# divergieran y nadie se enterase.


class Catalog:
    """Sólo `registros` es fuente de verdad. `pendientes` no son fichas (§2)."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._meta: dict[str, Any] = payload.get("meta", {})
        raw_records: list[dict[str, Any]] = payload.get("registros", [])

        # §6.5: una referencia puede aparecer en dos productos, pero hay un
        # único registro por referencia. Se indexa por referencia para que
        # contar por producto no la cuente dos veces.
        self._records: dict[str, CatalogRecord] = {}
        for raw in raw_records:
            record = _build_record(raw)
            self._records[record.reference] = record

        self._pending: dict[str, str] = {}
        for product, entries in (payload.get("pendientes") or {}).items():
            for entry in entries:
                self._pending[str(entry["referencia"])] = (
                    f"{entry.get('variante', '?')} ({product})"
                )

    # --- carga -------------------------------------------------------------
    @classmethod
    def from_path(cls, path: Path) -> Catalog:
        with path.open(encoding="utf-8") as fh:
            return cls(json.load(fh))

    @classmethod
    def default(cls) -> Catalog:
        return cls.from_path(default_catalog_path())

    # --- acceso ------------------------------------------------------------
    @property
    def meta(self) -> dict[str, Any]:
        return dict(self._meta)

    @property
    def records(self) -> tuple[CatalogRecord, ...]:
        return tuple(self._records.values())

    @property
    def pending_references(self) -> dict[str, str]:
        return dict(self._pending)

    def get(self, reference: str) -> CatalogRecord | None:
        """§5.4: si no está en `registros`, no conocemos sus datos. Punto."""
        return self._records.get(str(reference))

    def is_pending(self, reference: str) -> bool:
        return str(reference) in self._pending

    def reference_status(self, reference: str) -> str:
        """`known` · `pending` · `unknown`. Son tres cosas distintas (§6.1).

        «Pendiente de extraer» significa que la referencia existe y no tenemos su
        ficha; «desconocida» significa que no sabemos ni que exista. Colapsarlas
        haría que el agente respondiera lo mismo a dos preguntas muy distintas.
        """
        key = str(reference)
        if key in self._records:
            return "known"
        if key in self._pending:
            return "pending"
        return "unknown"

    def families(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self._records.values():
            counts[record.family] = counts.get(record.family, 0) + 1
        return counts


def default_catalog_path() -> Path:
    """El JSON más reciente de `data/catalog/`, por nombre.

    El nombre lleva la fecha de extracción a propósito (§6.7: es una foto de un
    momento), así que ordenar por nombre da la extracción más nueva.
    """
    root = Path(__file__).resolve().parents[3]
    candidates = sorted((root / "data" / "catalog").glob("sick_datasheets.*.json"))
    if not candidates:
        raise FileNotFoundError(
            "No hay catálogo en data/catalog/. Se esperaba sick_datasheets.<fecha>.json"
        )
    return candidates[-1]
