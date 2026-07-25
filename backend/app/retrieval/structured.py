"""Motor Structured (README §4) — filtrado por número sobre `product_specs`.

El README es explícito: los filtros los emite el modelo como tool call con
`strict: true` contra un schema JSON, NO como text-to-SQL libre. Este módulo es
ese schema y su traducción a SQL parametrizado.

Dos barreras, no una:

1. Lista blanca de campos y coacción de tipo. Cada valor se convierte a float,
   int, bool o miembro de un enum cerrado antes de tocar nada. Un campo que el
   modelo se invente, o un '4 metros' donde va un número, revientan con
   `FilterError`.
2. Parámetros `%s`, nunca interpolación. Ningún valor entra en la cadena SQL.

`build_query` devuelve `(sql, params, notes)`. Las `notes` explican en
castellano qué se filtró: alimentan la justificación del nodo `explain`, para
que un descarte sea legible y no un booleano suelto.
"""

from __future__ import annotations

from typing import Any

# --- Enums cerrados -----------------------------------------------------------

DEVICE_CATEGORIES = (
    "laser_scanner",
    "safety_controller",
    "safety_camera_3d",
    "safety_radar",
)

# Órdenes normativos. "PL d o superior" necesita saber que e > d, y el texto
# suelto no lo sabe.
PL_ORDER = {"PL a": 1, "PL b": 2, "PL c": 3, "PL d": 4, "PL e": 5}
SIL_ORDER = {"SIL 1": 1, "SIL 2": 2, "SIL 3": 3}

IP_RATINGS = ("IP20", "IP54", "IP65", "IP66", "IP67", "IP69K")


class FilterError(ValueError):
    """Filtro fuera del schema. Nunca debe llegar a construir SQL."""


# --- Coacción de tipos --------------------------------------------------------

def _num(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FilterError(f"{name}: se esperaba un número, llegó {value!r}")
    return float(value)


def _int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FilterError(f"{name}: se esperaba un entero, llegó {value!r}")
    return value


def _enum(name: str, value: Any, allowed) -> str:
    if value not in allowed:
        raise FilterError(f"{name}: {value!r} no está en {tuple(allowed)}")
    return value


def _bool(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise FilterError(f"{name}: se esperaba booleano, llegó {value!r}")
    return value


# --- Traductores: un filtro -> (SQL con %s, params, explicación) --------------

def _f_device_category(v):
    v = _enum("device_category", v, DEVICE_CATEGORIES)
    return "ps.device_category = %s", [v], f"categoría de dispositivo = {v}"


def _f_protective_field_min_m(v):
    v = _num("protective_field_min_m", v)
    return (
        "ps.protective_field_max_m >= %s",
        [v],
        f"alcance de campo protector ≥ {v} m",
    )


def _f_warning_field_min_m(v):
    v = _num("warning_field_min_m", v)
    return "ps.warning_field_max_m >= %s", [v], f"campo de aviso ≥ {v} m"


def _f_resolution_max_mm(v):
    v = _num("resolution_max_mm", v)
    # resolution_mm es int[]: basta con que UNA resolución configurable cumpla.
    return (
        "exists (select 1 from unnest(ps.resolution_mm) r where r <= %s)",
        [v],
        f"alguna resolución configurable ≤ {v} mm",
    )


def _f_response_time_max_ms(v):
    v = _num("response_time_max_ms", v)
    return "ps.response_time_max_ms <= %s", [v], f"tiempo de respuesta ≤ {v} ms"


def _f_pl_min(v):
    v = _enum("pl_min", v, PL_ORDER)
    ok = [k for k, r in PL_ORDER.items() if r >= PL_ORDER[v]]
    return "ps.pl = any(%s)", [ok], f"Performance Level ≥ {v}"


def _f_sil_min(v):
    v = _enum("sil_min", v, SIL_ORDER)
    ok = [k for k, r in SIL_ORDER.items() if r >= SIL_ORDER[v]]
    return "ps.sil = any(%s)", [ok], f"SIL ≥ {v}"


def _f_iso13849_category_min(v):
    v = _int("iso13849_category_min", v)
    return "ps.iso13849_category >= %s", [v], f"categoría ISO 13849 ≥ {v}"


def _f_outdoor(v):
    v = _bool("outdoor", v)
    if v:
        return "ps.outdoor is true", [], "apto para exterior"
    # `is not true` y no `= false`: un NULL significa "no consta", y para equipo
    # de seguridad "no consta" no es "sirve para exterior".
    return "ps.outdoor is not true", [], "uso en interior"


def _f_ip_rating_in(v):
    if not isinstance(v, (list, tuple)) or not v:
        raise FilterError("ip_rating_in: se esperaba una lista no vacía")
    vals = [_enum("ip_rating_in", x, IP_RATINGS) for x in v]
    return "ps.ip_rating = any(%s)", [vals], f"grado de protección en {', '.join(vals)}"


def _f_temp_operating_covers_c(v):
    """El rango de servicio del producto debe cubrir la temperatura dada."""
    v = _num("temp_operating_covers_c", v)
    return (
        "ps.temp_min_c <= %s and ps.temp_max_c >= %s",
        [v, v],
        f"rango de servicio cubre {v} °C",
    )


FILTERS = {
    "device_category": _f_device_category,
    "protective_field_min_m": _f_protective_field_min_m,
    "warning_field_min_m": _f_warning_field_min_m,
    "resolution_max_mm": _f_resolution_max_mm,
    "response_time_max_ms": _f_response_time_max_ms,
    "pl_min": _f_pl_min,
    "sil_min": _f_sil_min,
    "iso13849_category_min": _f_iso13849_category_min,
    "outdoor": _f_outdoor,
    "ip_rating_in": _f_ip_rating_in,
    "temp_operating_covers_c": _f_temp_operating_covers_c,
}

# Se une con `documents` porque una spec sin documento de origen no puede
# citarse, y una recomendación sin cita es un bug (README §7).
_SELECT = """
select ps.part_number, ps.family, ps.variant, ps.device_category,
       ps.protective_field_min_m, ps.protective_field_max_m,
       ps.warning_field_max_m, ps.measuring_range_max_m,
       ps.resolution_mm, ps.scan_angle_deg,
       ps.response_time_min_ms, ps.response_time_max_ms,
       ps.pl, ps.sil, ps.iso13849_category, ps.iec61496_type, ps.pfhd,
       ps.ip_rating, ps.outdoor, ps.temp_min_c, ps.temp_max_c,
       ps.raw,
       d.id::text   as doc_id,
       d.version    as doc_version,
       d.title      as doc_title,
       d.source_url as source_url,
       d.revision_date
  from product_specs ps
  join documents d on d.id = ps.source_doc_id
"""


def build_query(
    filters: dict[str, Any],
    limit: int = 20,
    *,
    part_numbers: list[str] | None = None,
) -> tuple[str, list[Any], list[str]]:
    """Filtros validados -> (SQL parametrizado, params, explicaciones).

    `part_numbers` acota a referencias concretas SIN aplicarlas como filtro
    duro. Es lo que permite evaluar candidatos que NO cumplen, para poder
    explicar por qué se descartan: `filters` decide el veredicto, esta lista
    decide a quién se le pregunta.

    Lanza `FilterError` ante un campo desconocido o un valor del tipo
    equivocado. Es deliberado: un filtro inventado debe fallar ruidosamente, no
    degradarse a una búsqueda sin condiciones que devolvería el catálogo entero
    como si fuera una respuesta.
    """
    if not isinstance(filters, dict):
        raise FilterError("filters debe ser un dict")

    unknown = set(filters) - set(FILTERS)
    if unknown:
        raise FilterError(f"campos no permitidos: {sorted(unknown)}")

    limit = _int("limit", limit)
    if not 1 <= limit <= 100:
        raise FilterError("limit fuera de rango (1-100)")

    predicates: list[str] = []
    params: list[Any] = []
    notes: list[str] = []

    if part_numbers is not None:
        if not isinstance(part_numbers, list) or not all(
            isinstance(p, str) for p in part_numbers
        ):
            raise FilterError("part_numbers: se esperaba una lista de strings")
        predicates.append("ps.part_number = any(%s)")
        params.append(part_numbers)

    for key in sorted(filters):
        value = filters[key]
        if value is None:
            continue
        sql, ps, note = FILTERS[key](value)
        predicates.append(sql)
        params.extend(ps)
        notes.append(note)

    where = " and ".join(predicates) if predicates else "true"
    sql = (
        f"{_SELECT} where {where}\n"
        " order by ps.protective_field_max_m desc nulls last, ps.part_number\n"
        " limit %s"
    )
    params.append(limit)
    return sql, params, notes


# --- Explicación del descarte -------------------------------------------------

def evaluate(row: dict[str, Any], filters: dict[str, Any]) -> list[dict[str, str]]:
    """Pass/fail por criterio para UN candidato.

    El motor Structured filtra, pero `shortlist` necesita enseñar tradeoffs — y
    para eso hace falta el fallo, no solo el acierto.

    Tres estados, no dos. `desconocido` es distinto de `fail`: significa que el
    dato no consta en el datasheet. En equipo de seguridad "no consta" no es
    "no cumple", y colapsarlos mentiría en la dirección peligrosa.
    """
    checks = []
    for key in sorted(filters):
        value = filters[key]
        if value is None or key not in FILTERS:
            continue
        _, _, note = FILTERS[key](value)
        checks.append(
            {"campo": key, "criterio": note, "resultado": _verdict(row, key, value)}
        )
    return checks


def _cmp(value, ok: bool) -> str:
    return "desconocido" if value is None else ("pass" if ok else "fail")


def _verdict(row: dict[str, Any], key: str, value: Any) -> str:
    get = row.get
    if key == "protective_field_min_m":
        v = get("protective_field_max_m")
        return _cmp(v, v is not None and float(v) >= value)
    if key == "warning_field_min_m":
        v = get("warning_field_max_m")
        return _cmp(v, v is not None and float(v) >= value)
    if key == "response_time_max_ms":
        v = get("response_time_max_ms")
        return _cmp(v, v is not None and float(v) <= value)
    if key == "resolution_max_mm":
        rs = get("resolution_mm")
        return _cmp(rs or None, bool(rs) and any(float(r) <= value for r in rs))
    if key == "pl_min":
        v = get("pl")
        return _cmp(v, bool(v) and PL_ORDER.get(v, 0) >= PL_ORDER[value])
    if key == "sil_min":
        v = get("sil")
        return _cmp(v, bool(v) and SIL_ORDER.get(v, 0) >= SIL_ORDER[value])
    if key == "iso13849_category_min":
        v = get("iso13849_category")
        return _cmp(v, v is not None and int(v) >= value)
    if key == "device_category":
        return "pass" if get("device_category") == value else "fail"
    if key == "ip_rating_in":
        v = get("ip_rating")
        return _cmp(v, v in value)
    if key == "outdoor":
        v = get("outdoor")
        return _cmp(v, bool(v) == value)
    if key == "temp_operating_covers_c":
        lo, hi = get("temp_min_c"), get("temp_max_c")
        if lo is None or hi is None:
            return "desconocido"
        return "pass" if float(lo) <= value <= float(hi) else "fail"
    return "desconocido"
