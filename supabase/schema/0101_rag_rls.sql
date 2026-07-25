-- ============================================================================
-- 0101_rag_rls.sql — Cierre de acceso de las tablas de RAG
--
-- Propiedad: equipo de RAG. Requiere 0100 aplicado.
--
-- Mismo modelo que 0003_rls.sql (plataforma): el frontend no habla con
-- Supabase, el backend es el único cliente y usa la service role, que ignora
-- RLS por diseño. RLS activo + CERO políticas = denegación total.
--
-- Fichero aparte y no dentro de 0100 por la misma razón que ellos: el cierre de
-- acceso se revisa como una unidad, no disperso entre los create table.
--
-- ⚠️ REVOKE enumerados tabla por tabla, igual que en 0003. Un
--    `revoke ... on all tables in schema public` tocaría las tablas del equipo
--    de plataforma. No lo generalices (README §Reglas, punto 4).
-- ============================================================================

alter table public.documents           enable row level security;
alter table public.chunks              enable row level security;
alter table public.product_specs       enable row level security;
alter table public.ingest_review_queue enable row level security;

-- Fuerza RLS incluso para el propietario de la tabla. Sin esto, una conexión
-- con el rol propietario saltaría las políticas.
alter table public.documents           force row level security;
alter table public.chunks              force row level security;
alter table public.product_specs       force row level security;
alter table public.ingest_review_queue force row level security;

-- Revocación explícita de privilegios a los roles expuestos por PostgREST.
revoke all on public.documents           from anon, authenticated;
revoke all on public.chunks              from anon, authenticated;
revoke all on public.product_specs       from anon, authenticated;
revoke all on public.ingest_review_queue from anon, authenticated;

-- Las secuencias de las tablas con bigserial también.
revoke all on sequence public.chunks_id_seq              from anon, authenticated;
revoke all on sequence public.ingest_review_queue_id_seq from anon, authenticated;

-- Deliberadamente NO se crea ninguna policy. `documents` y `product_specs`
-- pueden parecer catálogo público e inofensivo, pero exponerlas por PostgREST
-- publicaría la documentación de producto de SICK extraída a una API abierta,
-- que es justo lo que la revisión legal pendiente (README §6) tiene que
-- resolver antes. Si algún día hace falta lectura directa, se añade aquí de
-- forma explícita y revisable, no por omisión.
