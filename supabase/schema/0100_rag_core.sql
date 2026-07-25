-- ============================================================================
-- 0100_rag_core.sql — Capa de recuperación (RAG)
--
-- Propiedad: equipo de RAG. Rango 0100+ según supabase/README.md §Reglas.
-- Independiente de 0001–0004: no referencia ninguna tabla del agente.
--
-- Crea: documents, chunks, product_specs, ingest_review_queue.
-- Habilita pgvector (regla 5 del README: lo habilitamos nosotros, no ellos).
--
-- Idempotente. Verificado contra PostgreSQL 17 + pgvector.
-- ============================================================================

create extension if not exists vector;


-- ============================================================================
-- documents — un datasheet en una versión concreta
-- ============================================================================
-- Una revisión del PDF NO actualiza la fila: crea otra con version+1. Las
-- versiones antiguas se conservan para poder auditar una recomendación emitida
-- hace meses contra el documento que se usó entonces (README §6, Versionado).
-- Es la contraparte de `citations.doc_version is not null` de 0001_core.

create table if not exists public.documents (
  id            uuid primary key default gen_random_uuid(),
  title         text not null,
  family        text,                                  -- nanoScan3 | safeRS3 | Flexi Compact | ...
  kind          text not null default 'datasheet',     -- enruta el motor Glossary (§4)
  language      text not null,
  version       int  not null,
  revision_date date,
  source_url    text not null,
  sha256        text not null,
  etag          text,
  ingested_at   timestamptz not null default now(),

  constraint documents_version_positive check (version >= 1),
  constraint documents_kind_valid
    check (kind in ('datasheet', 'application_note', 'glossary')),
  constraint documents_source_version_unique unique (source_url, version)
);

create index if not exists documents_family_idx on public.documents (family);
create index if not exists documents_kind_idx   on public.documents (kind);


-- ============================================================================
-- chunks — corpus del motor Semantic
-- ============================================================================
-- INV-3 (doble representación) vive en la separación content_md / content_embed:
--   content_md    → lo que se envía al modelo y lo que respalda la cita
--   content_embed → linealización a frases; lo ÚNICO que se embebe

create table if not exists public.chunks (
  id            bigserial primary key,
  document_id   uuid   not null references public.documents(id) on delete cascade,
  parent_id     bigint references public.chunks(id) on delete cascade,
  node_type     text   not null default 'text',       -- text | table | summary
  page          int,
  section_path  text,                                 -- INV-2
  table_id      text,                                 -- INV-5
  content_md    text   not null,
  content_embed text   not null,
  embedding     vector(1024),
  metadata      jsonb  not null default '{}',

  -- Canal léxico de la fusión híbrida (§4). Config 'simple' a propósito: el
  -- corpus es ES+EN y lo que este canal debe acertar son números de parte y
  -- códigos exactos, que el stemming de cualquier idioma degradaría.
  -- Generada: no puede quedar desincronizada del contenido.
  ts tsvector generated always as (
    to_tsvector('simple', coalesce(content_md, '') || ' ' || coalesce(content_embed, ''))
  ) stored,

  constraint chunks_node_type_valid
    check (node_type in ('text', 'table', 'summary')),

  -- INV-2: una tabla sin identificador de origen no es resoluble ⇒ es ruido.
  constraint chunks_table_needs_table_id
    check (node_type <> 'table' or table_id is not null),

  constraint chunks_parent_not_self
    check (parent_id is null or parent_id <> id)
);

-- vector(1024) sirve para voyage-multilingual-2 y para bge-m3, los dos
-- candidatos abiertos del README §3. Otro proveedor con otra dimensión obliga a
-- recrear la columna y su índice.
create index if not exists chunks_embedding_hnsw_idx
  on public.chunks using hnsw (embedding vector_cosine_ops);

create index if not exists chunks_ts_gin_idx     on public.chunks using gin (ts);
create index if not exists chunks_document_id_idx on public.chunks (document_id);
create index if not exists chunks_parent_id_idx   on public.chunks (parent_id);

create index if not exists chunks_tables_idx
  on public.chunks (document_id, table_id) where node_type = 'table';


-- ============================================================================
-- product_specs — catálogo tipado, fuente de verdad de todo número
-- ============================================================================
-- Nada de esta tabla se rellena a mano ni desde el conocimiento del modelo:
-- solo desde la ingesta, validado (INV-4).
--
-- COTAS EN VEZ DE ESCALARES. El corpus real no trae números limpios: el mismo
-- campo aparece como valor, como desigualdad y como rango —
--   campo_proteccion_m: 3 | '0,2 a 5' | '<=2 (4 m en modo alcance ampliado)'
--   tiempo_respuesta_ms: 70 | '<=100' | '>=55'
-- Una columna `numeric` no sostiene eso, y el motor Structured necesita filtrar
-- por desigualdad sin ramificar por tipo. Se normaliza a (min, max):
--   '<=100' → (null, 100)   '>=55' → (55, null)   '0,2 a 5' → (0.2, 5)   70 → (70, 70)
-- Así "necesito 4 m" es siempre `protective_field_max_m >= 4`.

create table if not exists public.product_specs (
  part_number            text primary key,
  family                 text not null,
  variant                text,
  device_category        text,

  -- Campo de detección (cotas)
  protective_field_min_m    numeric,
  protective_field_max_m    numeric,
  warning_field_min_m       numeric,
  warning_field_max_m       numeric,
  measuring_range_max_m     numeric,
  response_time_min_ms      numeric,
  response_time_max_ms      numeric,
  resolution_mm             int[],
  scan_angle_deg            numeric,
  n_fields_max              int,
  n_monitoring_cases_max    int,
  n_simultaneous_fields_max int,
  n_ossd_pairs_max          int,

  -- Seguridad funcional
  pl                     text,
  sil                    text,
  iso13849_category      int,
  iec61496_type          int,
  pfhd                   double precision,

  -- Montaje y entorno
  mounting               text[],
  outdoor                boolean,
  ip_rating              text,
  temp_min_c             numeric,
  temp_max_c             numeric,
  interfaces             text[],

  extra                  jsonb not null default '{}',

  -- INV-4 promueve los números que filtran a columnas tipadas. Pero la cita
  -- debe mostrar el valor TAL COMO estaba: si el datasheet dice
  -- '<=2 (4 m en modo alcance ampliado)', el usuario ve eso, no el 2.0.
  raw                    jsonb,

  -- Procedencia (INV-5). Sin `on delete`: borrar un documento con specs vivas
  -- debe fallar, porque dejaría cifras sin origen resoluble.
  source_doc_id          uuid not null references public.documents(id),
  source_doc_version     int  not null,
  provenance             jsonb not null,

  constraint product_specs_provenance_not_empty
    check (provenance <> '{}'::jsonb),
  constraint product_specs_raw_not_empty
    check (raw is null or raw <> '{}'::jsonb),
  constraint product_specs_device_category_valid
    check (device_category in
      ('laser_scanner', 'safety_controller', 'safety_camera_3d', 'safety_radar')),
  constraint product_specs_temp_range_coherent
    check (temp_min_c is null or temp_max_c is null or temp_min_c <= temp_max_c),
  -- Una cota inferior mayor que la superior es un fallo de normalización: debe
  -- reventar en la ingesta, no llegar al motor Structured.
  constraint product_specs_bounds_coherent check (
        (protective_field_min_m is null or protective_field_max_m is null
         or protective_field_min_m <= protective_field_max_m)
    and (warning_field_min_m is null or warning_field_max_m is null
         or warning_field_min_m <= warning_field_max_m)
    and (response_time_min_ms is null or response_time_max_ms is null
         or response_time_min_ms <= response_time_max_ms)
  )
);

create index if not exists product_specs_family_idx          on public.product_specs (family);
create index if not exists product_specs_source_idx          on public.product_specs (source_doc_id);
create index if not exists product_specs_device_category_idx on public.product_specs (device_category);

-- Los tres filtros que el README §4 nombra como consulta real.
create index if not exists product_specs_protective_field_idx
  on public.product_specs (protective_field_max_m);
create index if not exists product_specs_response_time_idx
  on public.product_specs (response_time_max_ms);
create index if not exists product_specs_resolution_idx
  on public.product_specs using gin (resolution_mm);

comment on column public.product_specs.raw is
  'Registro de origen verbatim. Las columnas tipadas son para filtrar; este JSON '
  'es para mostrar el valor original sin reinterpretar. Es lo que respalda la cita.';
comment on column public.product_specs.protective_field_max_m is
  'Cota superior del campo de protección. Un valor exacto guarda min = max.';


-- ============================================================================
-- ingest_review_queue — cuarentena (INV-6)
-- ============================================================================
-- Si el parseo o la validación de una tabla falla, el documento entero NO entra
-- al índice. Nunca se indexa una tabla dudosa.

create table if not exists public.ingest_review_queue (
  id          bigserial primary key,
  source_url  text not null,
  stage       text not null,          -- parse | normalize | validate
  reason      text not null,
  payload     jsonb,
  created_at  timestamptz not null default now(),
  resolved_at timestamptz,

  constraint ingest_review_stage_valid
    check (stage in ('parse', 'normalize', 'validate'))
);

-- Lo que importa consultar es lo pendiente, no el histórico.
create index if not exists ingest_review_pending_idx
  on public.ingest_review_queue (created_at) where resolved_at is null;
