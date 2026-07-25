-- ============================================================================
-- 0001_core.sql — Sesión y conversación
--
-- Propiedad: equipo de plataforma / agente.
-- Aplicar en orden numérico. Ver supabase/README.md antes de tocar nada.
--
-- Idempotente: se puede reaplicar sin efecto si ya existe.
-- ============================================================================

create extension if not exists pgcrypto;

-- ----------------------------------------------------------------------------
-- sessions
-- ----------------------------------------------------------------------------
-- Sesión anónima. No hay login (README §10): la identidad la establece un JWT
-- httpOnly emitido por el backend, y el cliente nunca elige su propio id.
--
-- NOTA DE DISEÑO: no existe `sessions.lead_id`. El README original lo tenía
-- junto a `leads.session_id`, lo que forma una FK circular que no se puede
-- crear en un solo paso. Se consulta por `leads.session_id` y punto.

create table if not exists public.sessions (
  id                uuid        primary key default gen_random_uuid(),

  -- Hash con sal de IP+User-Agent. NUNCA la IP en claro (RGPD, README §10).
  anon_hash         text        not null,

  locale            text        not null default 'es'
                                check (locale in ('es', 'en')),
  stage             text        not null default 'discovery'
                                check (stage in ('discovery', 'shortlist', 'compare', 'handoff')),

  -- Atribución de marketing (top-of-funnel).
  referrer          text,
  utm               jsonb,

  -- Contadores de abuso. El límite por sesión se aplica en el backend, pero se
  -- persiste aquí para que sobreviva a un reinicio del proceso.
  turn_count        integer     not null default 0 check (turn_count >= 0),
  tokens_used       integer     not null default 0 check (tokens_used >= 0),

  created_at        timestamptz not null default now(),
  last_seen         timestamptz not null default now()
);

create index if not exists sessions_last_seen_idx  on public.sessions (last_seen desc);
create index if not exists sessions_anon_hash_idx  on public.sessions (anon_hash);
create index if not exists sessions_stage_idx      on public.sessions (stage);

comment on column public.sessions.anon_hash is
  'Hash con sal de IP+UA. Prohibido almacenar la IP en claro.';

-- ----------------------------------------------------------------------------
-- messages
-- ----------------------------------------------------------------------------

create table if not exists public.messages (
  id            bigserial   primary key,
  session_id    uuid        not null references public.sessions(id) on delete cascade,

  role          text        not null check (role in ('user', 'assistant', 'system')),
  content       text        not null,

  -- Telemetría por turno. Permite reconstruir coste y latencia sin depender de
  -- un proveedor externo de tracing.
  model         text,
  effort        text,
  input_tokens  integer,
  output_tokens integer,
  cache_read_input_tokens integer,
  latency_ms    integer,

  created_at    timestamptz not null default now()
);

create index if not exists messages_session_created_idx
  on public.messages (session_id, created_at);

-- ----------------------------------------------------------------------------
-- citations
-- ----------------------------------------------------------------------------
-- Trazabilidad (README §7). `doc_version` es obligatorio: es lo que permite
-- auditar una recomendación contra el documento que se usó, no contra la
-- versión actual.
--
-- NOTA DE FRONTERA: `doc_id` es TEXT y NO tiene foreign key contra
-- `documents`. Esa tabla es propiedad del equipo de RAG y puede no existir
-- todavía. Una FK aquí acoplaría nuestro esquema a su calendario.

create table if not exists public.citations (
  id            bigserial   primary key,
  message_id    bigint      not null references public.messages(id) on delete cascade,

  marker        smallint    not null check (marker > 0),

  doc_id        text        not null,
  doc_version   integer     not null check (doc_version >= 0),
  doc_title     text        not null,
  page          integer     check (page is null or page > 0),
  section_path  text,
  snippet       text        not null,
  source_url    text        not null,
  score         real,

  created_at    timestamptz not null default now(),

  -- Un marcador no puede repetirse dentro del mismo mensaje.
  constraint citations_message_marker_key unique (message_id, marker)
);

create index if not exists citations_message_idx on public.citations (message_id);
create index if not exists citations_doc_idx     on public.citations (doc_id, doc_version);

comment on column public.citations.doc_version is
  'Ancla de auditoría. Sin versión, una recomendación pasada no es reconstruible.';
comment on column public.citations.doc_id is
  'Sin FK contra documents a propósito: esa tabla es del equipo de RAG.';
