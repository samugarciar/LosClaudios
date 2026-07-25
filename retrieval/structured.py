"""
Motor Structured (README §4) — filtrado por número sobre product_specs.

El README es explícito: los filtros los emite el modelo como tool call con
`strict: true` contra un schema JSON, NO como text-to-SQL libre. Este módulo es
ese schema y su traducción a SQL.

Por qué no hay inyección posible: ningún texto libre llega nunca al SQL. Cada
filtro se valida contra una lista blanca de campos, y su valor se coacciona a
float, int, bool o a un miembro de un enum cerrado antes de construir la
consulta. Si algo no pasa por ahí, revienta con FilterError.

    >>> sql, notes = build_query({"protective_field_min_m": 4, "resolution_max_mm": 50})
    >>> # -> where protective_field_max_m >= 4.0 and exists (... r <= 50)

`notes` explica en castellano qué se filtró: alimenta la justificación del nodo
`explain` para que un fallo sea legible y no un booleano suelto.
"""

from __future__ import annotations

# --- Enums cerrados -----------------------------------------------------------

DEVICE_CATEGORIES = ("laser_scanner", "safety_controller", "safety_camera_3d", "safety_radar")

# Órdenes normativos. Un "PL d o superior" necesita saber que e > d; el texto
# suelto no lo sabe.
PL_ORDER = {"PL a": 1, "PL b": 2, "PL c": 3, "PL d": 4, "PL e": 5}
SIL_ORDER = {"SIL 1": 1, "SIL 2": 2, "SIL 3": 3}

# IP: el primer dígito es sólidos, el segundo líquidos. Se comparan por separado
# porque IP67 no es "mejor que" IP65 en todo — es mejor en agua, igual en polvo.
IP_RATINGS = ("IP20", "IP54", "IP65", "IP66", "IP67", "IP69K")


class FilterError(ValueError):
    """Filtro fuera del schema. Nunca debe llegar a construir SQL."""


def _num(name: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FilterError(f"{name}: se esperaba un número, llegó {value!r}")
    return float(value)


def _int(name: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FilterError(f"{name}: se esperaba un entero, llegó {value!r}")
    return value


def _enum(name: str, value, allowed) -> str:
    if value not in allowed:
        raise FilterError(f"{name}: {value!r} no está en {tuple(allowed)}")
    return value


def _bool(name: str, value) -> bool:
    if not isinstance(value, bool):
        raise FilterError(f"{name}: se esperaba booleano, llegó {value!r}")
    return value


# --- Traductores: un filtro -> (predicado SQL, explicación) -------------------
# Cada uno devuelve SQL ya seguro: los valores han pasado por coacción a tipo.

def _f_device_category(v):
    v = _enum("device_category", v, DEVICE_CATEGORIES)
    return f"device_category = '{v}'", f"categoría de dispositivo = {v}"


def _f_protective_field_min_m(v):
    v = _num("protective_field_min_m", v)
    return (
        f"protective_field_max_m >= {v}",
        f"alcance de campo protector ≥ {v} m",
    )


def _f_warning_field_min_m(v):
    v = _num("warning_field_min_m", v)
    return f"warning_field_max_m >= {v}", f"campo de aviso ≥ {v} m"


def _f_resolution_max_mm(v):
    v = _num("resolution_max_mm", v)
    # resolution_mm es int[]: basta con que UNA resolución configurable cumpla.
    return (
        f"exists (select 1 from unnest(resolution_mm) r where r <= {v})",
        f"alguna resolución configurable ≤ {v} mm",
    )


def _f_response_time_max_ms(v):
    v = _num("response_time_max_ms", v)
    return (
        f"response_time_max_ms <= {v}",
        f"tiempo de respuesta ≤ {v} ms",
    )


def _f_pl_min(v):
    v = _enum("pl_min", v, PL_ORDER)
    ok = [k for k, r in PL_ORDER.items() if r >= PL_ORDER[v]]
    lst = ", ".join(f"'{k}'" for k in ok)
    return f"pl in ({lst})", f"Performance Level ≥ {v}"


def _f_sil_min(v):
    v = _enum("sil_min", v, SIL_ORDER)
    ok = [k for k, r in SIL_ORDER.items() if r >= SIL_ORDER[v]]
    lst = ", ".join(f"'{k}'" for k in ok)
    return f"sil in ({lst})", f"SIL ≥ {v}"


def _f_iso13849_category_min(v):
    v = _int("iso13849_category_min", v)
    return f"iso13849_category >= {v}", f"categoría ISO 13849 ≥ {v}"


def _f_outdoor(v):
    v = _bool("outdoor", v)
    if v:
        return "outdoor is true", "apto para exterior"
    # `is not true` y no `= false`: un NULL significa "no consta", y para
    # equipo de seguridad "no consta" no es "sirve para exterior".
    return "outdoor is not true", "uso en interior"


def _f_ip_rating_in(v):
    if not isinstance(v, (list, tuple)) or not v:
        raise FilterError("ip_rating_in: se esperaba una lista no vacía")
    vals = [_enum("ip_rating_in", x, IP_RATINGS) for x in v]
    lst = ", ".join(f"'{x}'" for x in vals)
    return f"ip_rating in ({lst})", f"grado de protección en {', '.join(vals)}"


def _f_temp_operating_covers_c(v):
    """El rango de servicio del producto debe cubrir la temperatura dada."""
    v = _num("temp_operating_covers_c", v)
    return (
        f"temp_min_c <= {v} and temp_max_c >= {v}",
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

SELECT_COLUMNS = """part_number, family, variant, device_category,
       protective_field_min_m, protective_field_max_m,
       warning_field_max_m, resolution_mm,
       response_time_min_ms, response_time_max_ms,
       pl, sil, iso13849_category, ip_rating, outdoor,
       temp_min_c, temp_max_c,
       raw->>'url_fuente'    as source_url,
       raw->>'fecha_revision' as revision_date"""


def build_query(filters: dict, limit: int = 20) -> tuple[str, list[str]]:
    """
    Filtros validados -> (SQL, explicaciones).

    Lanza FilterError ante un campo desconocido o un valor del tipo equivocado.
    Es deliberado: un filtro que el modelo se inventa debe fallar ruidosamente,
    no devolver el catálogo entero como si nada.
    """
    if not isinstance(filters, dict):
        raise FilterError("filters debe ser un dict")

    unknown = set(filters) - set(FILTERS)
    if unknown:
        raise FilterError(f"campos no permitidos: {sorted(unknown)}")

    predicates, notes = [], []
    for key in sorted(filters):
        value = filters[key]
        if value is None:
            continue
        sql, note = FILTERS[key](value)
        predicates.append(sql)
        notes.append(note)

    where = " and ".join(predicates) if predicates else "true"
    limit = _int("limit", limit)
    if not 1 <= limit <= 100:
        raise FilterError("limit fuera de rango (1-100)")

    sql = (
        f"select {SELECT_COLUMNS}\n"
        f"from product_specs\nwhere {where}\n"
        f"order by protective_field_max_m desc nulls last, part_number\n"
        f"limit {limit};"
    )
    return sql, notes


def explain_failures(row: dict, filters: dict) -> list[dict]:
    """
    Por qué un candidato concreto NO cumple.

    El motor Structured filtra, pero el nodo `shortlist` del grafo necesita
    enseñar tradeoffs — y para eso hace falta el fallo, no solo el acierto.
    Devuelve un pass/fail por criterio, con la razón en castellano.
    """
    checks = []
    for key in sorted(filters):
        value = filters[key]
        if value is None or key not in FILTERS:
            continue
        _, note = FILTERS[key](value)
        checks.append({"criterio": note, "resultado": None, "campo": key})
    # El veredicto lo calcula quien tenga la fila delante; aquí se fija la forma
    # del reporte para que la UI no tenga que adivinarla.
    for c in checks:
        c["resultado"] = _evaluate(row, c["campo"], filters[c["campo"]])
    return checks


def _evaluate(row: dict, key: str, value) -> str:
    """pass / fail / desconocido — 'desconocido' cuando el dato no consta."""
    get = row.get
    if key == "protective_field_min_m":
        v = get("protective_field_max_m")
        return "desconocido" if v is None else ("pass" if float(v) >= value else "fail")
    if key == "response_time_max_ms":
        v = get("response_time_max_ms")
        return "desconocido" if v is None else ("pass" if float(v) <= value else "fail")
    if key == "resolution_max_mm":
        rs = get("resolution_mm")
        if not rs:
            return "desconocido"
        return "pass" if any(float(r) <= value for r in rs) else "fail"
    if key == "pl_min":
        v = get("pl")
        return "desconocido" if not v else ("pass" if PL_ORDER.get(v, 0) >= PL_ORDER[value] else "fail")
    if key == "sil_min":
        v = get("sil")
        return "desconocido" if not v else ("pass" if SIL_ORDER.get(v, 0) >= SIL_ORDER[value] else "fail")
    if key == "device_category":
        return "pass" if get("device_category") == value else "fail"
    if key == "outdoor":
        v = get("outdoor")
        if v is None:
            return "desconocido"
        return "pass" if bool(v) == value else "fail"
    return "desconocido"
