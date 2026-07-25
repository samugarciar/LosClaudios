-- ============================================================================
-- 0002_business.sql — Salida de negocio: recomendaciones, leads, feedback
--
-- Propiedad: equipo de plataforma / agente.
-- Requiere 0001_core.sql aplicado.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- recommendations
-- ----------------------------------------------------------------------------
-- Artefacto de conversación: se borra con la sesión. `profile_snapshot` guarda
-- el perfil exacto que produjo esta preselección, para poder explicar a
-- posteriori por qué se recomendó lo que se recomendó.

create table if not exists public.recommendations (
  id                bigserial   primary key,
  session_id        uuid        not null references public.sessions(id) on delete cascade,

  part_number       text        not null,
  family            text        not null,
  variant           text,
  rank              smallint    not null check (rank > 0),

  headline          text        not null,
  pros              text[]      not null default '{}',
  cons              text[]      not null default '{}',
  citation_markers  smallint[]  not null default '{}',
  confidence        real        check (confidence is null or (confidence >= 0 and confidence <= 1)),

  profile_snapshot  jsonb       not null,

  created_at        timestamptz not null default now()
);

create index if not exists recommendations_session_idx
  on public.recommendations (session_id, created_at desc);
create index if not exists recommendations_part_idx
  on public.recommendations (part_number);

-- ----------------------------------------------------------------------------
-- leads
-- ----------------------------------------------------------------------------
-- Registro de negocio. DEBE sobrevivir a la purga de la sesión:
--
--   session_id es NULLABLE y usa ON DELETE SET NULL, no CASCADE.
--
-- Si cascadease, purgar conversaciones antiguas (0004_retention.sql) borraría
-- leads que el equipo comercial todavía está trabajando. Por eso el contexto
-- necesario se desnormaliza en `handoff_summary`: el lead es autocontenido.

create table if not exists public.leads (
  id                    uuid        primary key default gen_random_uuid(),
  session_id            uuid        references public.sessions(id) on delete set null,

  name                  text        not null,
  email                 text        not null,
  company               text,
  country               text,

  -- Consentimiento: se audita por VERSIÓN del texto, no por su contenido.
  consent_at            timestamptz not null default now(),
  consent_text_version  text        not null,

  -- Copia autocontenida del handoff (perfil, candidatos, citas, qué falta).
  handoff_summary       jsonb       not null default '{}',

  notified_at           timestamptz,
  created_at            timestamptz not null default now()
);

create index if not exists leads_session_idx on public.leads (session_id);
create index if not exists leads_created_idx  on public.leads (created_at desc);

-- Cola de notificación pendiente: índice parcial, solo lo que falta por enviar.
create index if not exists leads_pending_notification_idx
  on public.leads (created_at)
  where notified_at is null;

comment on column public.leads.session_id is
  'ON DELETE SET NULL: el lead sobrevive a la purga de la conversación.';
comment on column public.leads.handoff_summary is
  'Contexto desnormalizado para que el lead siga siendo útil sin la sesión.';

-- ----------------------------------------------------------------------------
-- feedback
-- ----------------------------------------------------------------------------
-- Un voto por mensaje; reenviar sustituye el anterior (upsert por message_id).

create table if not exists public.feedback (
  id          bigserial   primary key,
  message_id  bigint      not null references public.messages(id) on delete cascade,
  thumbs      smallint    not null check (thumbs in (-1, 1)),
  comment     text,
  created_at  timestamptz not null default now(),

  constraint feedback_message_key unique (message_id)
);

create index if not exists feedback_thumbs_idx on public.feedback (thumbs, created_at desc);
