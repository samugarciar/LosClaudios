"""
data/sick_datasheets.json  ->  SQL de carga (documents + chunks + product_specs).

Emite SQL en vez de escribir en la base directamente, a propósito: el resultado
se revisa como texto, se pega en el SQL Editor de Supabase y queda versionado.
Sin dependencias (ni psycopg ni supabase-py) para que corra en cualquier máquina
del equipo.

    python ingest/build_seed.py > supabase/seed/0100_sick_datasheets.sql

Mapeo, un registro del JSON produce tres filas:

    documents      1 fila   — cada registro trae su propio url_fuente (PDF distinto)
    chunks         1 fila   — content_md verbatim + content_embed sintetizado
    product_specs  1 fila   — cotas normalizadas + registro original en `raw`

NOTA sobre `embedding`: se inserta NULL. Los vectores se calculan en un paso
aparte, cuando esté decidido el proveedor de embeddings (README §3, abierta).
Hasta entonces el canal léxico (tsvector) funciona y el denso no.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from normalize import (  # noqa: E402
    device_category,
    linearize,
    parse_bounds,
    parse_categoria,
    parse_iec61496_type,
    parse_ip,
    parse_outdoor,
    parse_pfhd,
    parse_pl,
    parse_sil,
    parse_temp_range,
    to_markdown,
)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "sick_datasheets.json"


# --- Emisión de literales SQL -------------------------------------------------

def q(value) -> str:
    """Literal SQL. Comilla simple duplicada — seguro para cualquier texto."""
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def qjson(obj) -> str:
    if obj is None:
        return "null"
    return q(json.dumps(obj, ensure_ascii=False, sort_keys=True)) + "::jsonb"


def qnum(value) -> str:
    return "null" if value is None else repr(float(value))


def qint(value) -> str:
    if value is None:
        return "null"
    return str(int(value))


def qintarray(values) -> str:
    if not values:
        return "null"
    try:
        return "'{" + ",".join(str(int(v)) for v in values) + "}'::int[]"
    except (TypeError, ValueError):
        return "null"


def _hi(value):
    """Cota superior de un campo, o None."""
    return parse_bounds(value)[1]


def build() -> str:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    records = data["registros"]

    out: list[str] = [
        "-- GENERADO por ingest/build_seed.py — no editar a mano.",
        f"-- Fuente: data/sick_datasheets.json ({data['meta']['fecha_generacion']})",
        f"-- {len(records)} referencias de {data['meta']['total_referencias_unicas']} únicas;"
        f" {data['meta']['pendientes']} pendientes.",
        "",
        "begin;",
        "",
    ]

    for rec in records:
        ref = rec["referencia"]
        productos = rec.get("productos") or []
        linea = productos[0] if productos else rec.get("familia", "desconocida")

        # sha256 del REGISTRO, no del PDF: nunca tuvimos el binario. Sirve igual
        # para detectar cambios al reingerir el JSON (README §6.2).
        canonical = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        title = f"{rec.get('variante','')} — {linea}"
        doc_var = f"doc_{ref}"

        out.append(f"-- ---- {ref}  {rec.get('variante','')}  ({linea}) ----")
        out.append(f"""with {doc_var} as (
  insert into documents (title, family, kind, language, version, revision_date,
                         source_url, sha256)
  values ({q(title)}, {q(linea)}, 'datasheet', {q(rec.get('idioma_fuente','es'))}, 1,
          {q(rec.get('fecha_revision'))}::date, {q(rec.get('url_fuente'))}, {q(sha)})
  on conflict (source_url, version) do update set title = excluded.title
  returning id
), chunk_{ref} as (
  -- `chunks` no tiene clave natural sobre la que hacer ON CONFLICT, así que la
  -- guarda es explícita: sin este NOT EXISTS, reaplicar el seed duplica cada
  -- chunk en silencio (documents y product_specs sí tienen conflicto declarado,
  -- con lo cual el duplicado pasa desapercibido salvo que se cuenten filas).
  insert into chunks (document_id, node_type, section_path, content_md,
                      content_embed, metadata)
  select d.id, 'summary', {q('Datasheet consolidado')}, {q(to_markdown(rec))},
         {q(linearize(rec))},
         {qjson({
             'part_number': ref,
             'variant': rec.get('variante'),
             'product_family': linea,
             'device_category': device_category(rec.get('familia')),
             'language': rec.get('idioma_fuente'),
             'source_url': rec.get('url_fuente'),
             'revision_date': rec.get('fecha_revision'),
         })}
  from {doc_var} d
  where not exists (
    select 1 from chunks c
    where c.document_id = d.id and c.node_type = 'summary'
  )
  returning document_id
)
insert into product_specs (
  part_number, family, variant, device_category,
  protective_field_min_m, protective_field_max_m,
  warning_field_min_m, warning_field_max_m, measuring_range_max_m,
  response_time_min_ms, response_time_max_ms,
  resolution_mm, n_fields_max, n_monitoring_cases_max,
  n_simultaneous_fields_max, n_ossd_pairs_max,
  pl, sil, iso13849_category, iec61496_type, pfhd,
  ip_rating, outdoor, temp_min_c, temp_max_c,
  raw, source_doc_id, source_doc_version, provenance
)
select
  {q(ref)}, {q(linea)}, {q(rec.get('variante'))}, {q(device_category(rec.get('familia')))},
  {qnum(parse_bounds(rec.get('campo_proteccion_m'))[0])},
  {qnum(parse_bounds(rec.get('campo_proteccion_m'))[1])},
  {qnum(parse_bounds(rec.get('campo_aviso_m'))[0])},
  {qnum(parse_bounds(rec.get('campo_aviso_m'))[1])},
  {qnum(_hi(rec.get('alcance_medida_m')))},
  {qnum(parse_bounds(rec.get('tiempo_respuesta_ms'))[0])},
  {qnum(parse_bounds(rec.get('tiempo_respuesta_ms'))[1])},
  {qintarray(rec.get('resolucion_configurable_mm'))},
  {qint(_hi(rec.get('num_campos')))},
  {qint(_hi(rec.get('num_casos_monitorizacion')))},
  {qint(_hi(rec.get('campos_simultaneos')))},
  {qint(_hi(rec.get('pares_ossd')))},
  {q(parse_pl(rec.get('performance_level')))},
  {q(parse_sil(rec.get('sil')))},
  {qint(parse_categoria(rec.get('categoria_iso13849')))},
  {qint(parse_iec61496_type(rec.get('tipo_iec61496')))},
  {qnum(parse_pfhd(rec.get('pfhd')))},
  {q(parse_ip(rec.get('grado_proteccion_ip')))},
  {'null' if parse_outdoor(rec.get('aplicacion')) is None
     else str(parse_outdoor(rec.get('aplicacion'))).lower()},
  {qnum(parse_temp_range(rec.get('temp_servicio'))[0])},
  {qnum(parse_temp_range(rec.get('temp_servicio'))[1])},
  {qjson(rec)},
  id, 1,
  {qjson({
      'source_url': rec.get('url_fuente'),
      'revision_date': rec.get('fecha_revision'),
      'extraido_de': 'data/sick_datasheets.json',
      'page': None,
      'nota_page': 'El JSON consolidado no conserva el número de página; '
                   'la cita resuelve al documento, no a la página (ver INV-5).',
  })}
-- Se lee de {doc_var}, no de chunk_{ref}: al reaplicar, chunk_{ref} no devuelve
-- filas (el chunk ya existe) y product_specs se quedaría sin insertar en una
-- base donde se hubieran borrado las specs pero no los chunks. Los CTE que
-- modifican datos se ejecutan aunque la consulta principal no los referencie.
from {doc_var}
on conflict (part_number) do nothing;
""")

    out.append("commit;")
    return "\n".join(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(build())
