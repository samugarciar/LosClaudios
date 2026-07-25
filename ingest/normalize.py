"""
Normalización de los datasheets consolidados de SICK (data/sick_datasheets.json).

Dos responsabilidades, las dos deterministas — sin LLM en ningún punto. El README
§4 dice que el modelo nunca es la fuente de una especificación; aquí eso se cumple
literalmente: cada número de product_specs sale de una regex sobre el JSON de
origen, y el string original se conserva íntegro para la cita.

  1. parse_bounds()  — '<=100', '0,2 a 5', 3.9  ->  (min, max) numéricos
  2. linearize()     — registro estructurado    ->  frase embebible (INV-3)

Sobre (2): el JSON no trae prosa. `aplicacion` es literalmente 'Indoor'. Como no
hay texto que embeber, el content_embed se SINTETIZA desde los campos tipados.
Es la misma idea de INV-3 (linealización fila-a-frase de una tabla), aplicada al
registro completo en vez de a una fila.
"""

from __future__ import annotations

import re
import unicodedata

# --- Reglas de bounds ---------------------------------------------------------
# El corpus real solo produce estas formas (verificado sobre los 15 registros):
#   3 | 3.9              valor exacto
#   '<=100' | '>=55'     desigualdad
#   '0,2 a 5' | '1 a 2'  rango
#   '<=2 (4 m en modo alcance ampliado)'   desigualdad + matiz entre paréntesis
#   '2 bicanal (libremente configurables)' valor + cualificador textual
# Coma decimal en todos los casos: es documentación en español.

_NUM = r"-?\d+(?:[.,]\d+)?"
_RE_RANGE = re.compile(rf"^\s*({_NUM})\s+a\s+({_NUM})")
_RE_LTE = re.compile(rf"^\s*<=\s*({_NUM})")
_RE_GTE = re.compile(rf"^\s*>=\s*({_NUM})")
_RE_LEAD = re.compile(rf"^\s*({_NUM})")

# '-10 C a +50 C' / '-10 C a +50 C (disipador necesario desde 40 C)'
_RE_TEMP = re.compile(rf"^\s*({_NUM})\s*C\s+a\s+\+?({_NUM})\s*C")

_RE_IP = re.compile(r"\bIP\s?(\d{2}[Kk]?)")
_RE_PL = re.compile(r"\bPL\s*([a-e])\b", re.IGNORECASE)
_RE_SIL = re.compile(r"\bSIL\s*(\d)\b", re.IGNORECASE)
_RE_CAT = re.compile(r"Categoria\s*(\d)", re.IGNORECASE)
_RE_TYPE = re.compile(r"\bTipo\s*(\d)\b", re.IGNORECASE)


def _to_float(tok: str) -> float:
    """'16,8' -> 16.8 — coma decimal española."""
    return float(tok.replace(",", "."))


def parse_bounds(value) -> tuple[float | None, float | None, bool]:
    """
    Devuelve (min, max, exacto).

    Convención uniforme para que el motor Structured pueda filtrar por
    desigualdad sin ramificar por tipo:

        3          -> (3.0, 3.0, True)     valor exacto
        '<=100'    -> (None, 100.0, False) solo cota superior
        '>=55'     -> (55.0, None, False)  solo cota inferior
        '0,2 a 5'  -> (0.2, 5.0, False)    rango cerrado
        None       -> (None, None, False)

    'exacto' distingue un valor único de un rango degenerado, que importa al
    explicar por qué un candidato pasa o falla.
    """
    if value is None:
        return (None, None, False)

    if isinstance(value, bool):  # bool es subclase de int; no es una medida
        return (None, None, False)

    if isinstance(value, (int, float)):
        return (float(value), float(value), True)

    if not isinstance(value, str):
        return (None, None, False)

    s = value.strip()
    if not s:
        return (None, None, False)

    if m := _RE_RANGE.match(s):
        return (_to_float(m.group(1)), _to_float(m.group(2)), False)
    if m := _RE_LTE.match(s):
        return (None, _to_float(m.group(1)), False)
    if m := _RE_GTE.match(s):
        return (_to_float(m.group(1)), None, False)
    if m := _RE_LEAD.match(s):
        # '2 bicanal (...)': el número es exacto, el resto es cualificador.
        return (_to_float(m.group(1)), _to_float(m.group(1)), True)

    return (None, None, False)


def parse_temp_range(value) -> tuple[float | None, float | None]:
    """'-10 C a +50 C' -> (-10.0, 50.0)"""
    if not isinstance(value, str):
        return (None, None)
    if m := _RE_TEMP.match(value.strip()):
        return (_to_float(m.group(1)), _to_float(m.group(2)))
    return (None, None)


def _first(rx: re.Pattern, value, fmt) -> str | None:
    if not isinstance(value, str):
        return None
    m = rx.search(value)
    return fmt(m) if m else None


def parse_ip(value) -> str | None:
    """'IP65 (IEC 60529)' -> 'IP65'. 'IP65 / IP67 (...)' -> 'IP65' (el menor)."""
    return _first(_RE_IP, value, lambda m: f"IP{m.group(1).upper()}")


def parse_pl(value) -> str | None:
    """'PL d' -> 'PL d'"""
    return _first(_RE_PL, value, lambda m: f"PL {m.group(1).lower()}")


def parse_sil(value) -> str | None:
    """'SIL 2 (IEC 61508)' -> 'SIL 2'"""
    return _first(_RE_SIL, value, lambda m: f"SIL {m.group(1)}")


def parse_categoria(value) -> int | None:
    """'Categoria 4' -> 4"""
    v = _first(_RE_CAT, value, lambda m: m.group(1))
    return int(v) if v else None


def parse_iec61496_type(value) -> int | None:
    """'Tipo 3 (IEC 61496-1)' -> 3"""
    v = _first(_RE_TYPE, value, lambda m: m.group(1))
    return int(v) if v else None


def parse_pfhd(value) -> float | None:
    """'4e-9' / '8,0e-8' -> float. Viene como string en los 15 registros."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return float(value.strip().replace(",", "."))
    except ValueError:
        return None


def parse_outdoor(value) -> bool | None:
    """'Indoor / Outdoor' -> True; 'Indoor' -> False."""
    if not isinstance(value, str):
        return None
    return "outdoor" in value.lower()


# --- Categoría de dispositivo -------------------------------------------------
# El corpus abarca cuatro categorías, no solo escáneres láser. Se deriva del
# campo `familia` del JSON, que es consistente en los 15 registros.

_DEVICE_CATEGORY = {
    "escaner laser de seguridad": "laser_scanner",
    "controladores de seguridad": "safety_controller",
    "camara 3d de seguridad": "safety_camera_3d",
    "sensores de radar seguros": "safety_radar",
}


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def device_category(familia: str | None) -> str | None:
    if not familia:
        return None
    return _DEVICE_CATEGORY.get(_strip_accents(familia).strip().lower())


# --- Linealización para embedding (INV-3) -------------------------------------

_LABELS = [
    ("campo_proteccion_m", "campo de protección", "m"),
    ("campo_aviso_m", "campo de aviso", "m"),
    ("alcance_medida_m", "alcance de medida", "m"),
    ("resolucion_configurable_mm", "resolución configurable", "mm"),
    ("angulo_escaneo", "ángulo de escaneo", ""),
    ("tiempo_respuesta_ms", "tiempo de respuesta", "ms"),
    ("num_campos", "número de campos", ""),
    ("num_casos_monitorizacion", "casos de monitorización", ""),
    ("campos_simultaneos", "campos simultáneos", ""),
    ("pares_ossd", "pares OSSD", ""),
    ("entradas_seguridad", "entradas de seguridad", ""),
    ("salidas_seguridad", "salidas de seguridad", ""),
    ("bus_campo", "bus de campo", ""),
    ("tension_alimentacion", "tensión de alimentación", ""),
    ("grado_proteccion_ip", "grado de protección", ""),
    ("temp_servicio", "temperatura de servicio", ""),
    ("material_carcasa", "material de carcasa", ""),
    ("dimensiones_mm", "dimensiones", "mm"),
    ("montaje", "montaje", ""),
]


def _fmt(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def linearize(rec: dict) -> str:
    """
    Registro -> párrafo en español natural, con nombre de producto y unidades
    explícitas en cada dato. Es lo ÚNICO que se embebe (INV-3).

    El markdown original (content_md) se genera aparte y conserva el registro
    verbatim: es lo que respalda la cita.
    """
    variante = rec.get("variante", "")
    familia = rec.get("familia", "producto")
    productos = ", ".join(rec.get("productos") or []) or familia
    ref = rec.get("referencia", "")

    out = [f"El {productos} {variante} (referencia {ref}) es un {familia.lower()}."]

    specs = []
    for key, label, unit in _LABELS:
        v = rec.get(key)
        if v in (None, "", []):
            continue
        specs.append(f"{label} de {_fmt(v)}{' ' + unit if unit else ''}")
    if specs:
        out.append("Tiene " + "; ".join(specs) + ".")

    seguridad = [
        rec.get("performance_level"),
        rec.get("sil"),
        rec.get("categoria_iso13849"),
        rec.get("tipo_iec61496"),
    ]
    seguridad = [s for s in seguridad if s]
    if seguridad:
        out.append("Nivel de seguridad: " + "; ".join(seguridad) + ".")

    if funcs := rec.get("funciones"):
        out.append("Funciones: " + ", ".join(funcs) + ".")

    if aplic := rec.get("aplicacion"):
        out.append(f"Aplicación: {aplic}.")

    for extra_key in ("nota", "advertencia"):
        if v := rec.get(extra_key):
            out.append(f"{extra_key.capitalize()}: {v}")

    return " ".join(out)


def to_markdown(rec: dict) -> str:
    """
    content_md — el registro verbatim como tabla markdown. Es lo que se envía al
    modelo y lo que respalda la cita, así que no se reescribe ni se reordena
    nada: si el JSON dice '<=2 (4 m en modo alcance ampliado)', eso es lo que ve
    el modelo, no el 2.0 normalizado.
    """
    skip = {"id", "url_fuente", "idioma_fuente", "fecha_revision"}
    head = f"### {rec.get('variante','')} ({rec.get('referencia','')})\n\n"
    rows = ["| Campo | Valor |", "|---|---|"]
    for k, v in rec.items():
        if k in skip or v in (None, "", []):
            continue
        rows.append(f"| {k} | {_fmt(v)} |")
    return head + "\n".join(rows)
