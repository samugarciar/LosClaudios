-- ============================================================================
-- 0003_rls.sql — Cierre de acceso
--
-- Propiedad: equipo de plataforma / agente.
-- Requiere 0001 y 0002 aplicados.
--
-- MODELO DE ACCESO (README §10): el frontend NO habla con Supabase. El backend
-- es el único cliente y usa la service role, que por diseño en Supabase
-- ignora RLS. Por tanto:
--
--   RLS activado + CERO políticas para anon/authenticated = denegación total.
--
-- Esto no es decorativo. Si mañana alguien expone la anon key en el navegador
-- (por prisa, por copiar un tutorial), estas tablas siguen cerradas.
--
-- ⚠️ Los REVOKE de abajo están enumerados tabla por tabla A PROPÓSITO.
--    `revoke ... on all tables in schema public` afectaría también a las
--    tablas del equipo de RAG (documents, chunks, product_specs) y podría
--    romperles su acceso sin que se enteren. No lo generalices.
-- ============================================================================

alter table public.sessions        enable row level security;
alter table public.messages        enable row level security;
alter table public.citations       enable row level security;
alter table public.recommendations enable row level security;
alter table public.leads           enable row level security;
alter table public.feedback        enable row level security;

-- Fuerza RLS incluso para el propietario de la tabla. Sin esto, una conexión
-- con el rol propietario saltaría las políticas.
alter table public.sessions        force row level security;
alter table public.messages        force row level security;
alter table public.citations       force row level security;
alter table public.recommendations force row level security;
alter table public.leads           force row level security;
alter table public.feedback        force row level security;

-- Revocación explícita de privilegios a los roles expuestos por PostgREST.
-- Enumeradas una a una para no tocar tablas de otro equipo.
revoke all on public.sessions        from anon, authenticated;
revoke all on public.messages        from anon, authenticated;
revoke all on public.citations       from anon, authenticated;
revoke all on public.recommendations from anon, authenticated;
revoke all on public.leads           from anon, authenticated;
revoke all on public.feedback        from anon, authenticated;

-- Las secuencias de las tablas con bigserial también.
revoke all on sequence public.messages_id_seq        from anon, authenticated;
revoke all on sequence public.citations_id_seq       from anon, authenticated;
revoke all on sequence public.recommendations_id_seq from anon, authenticated;
revoke all on sequence public.feedback_id_seq        from anon, authenticated;

-- Deliberadamente NO se crea ninguna policy. Si en el futuro el frontend
-- necesitara leer algo directamente, la política se añade aquí de forma
-- explícita y revisable, no por omisión.
