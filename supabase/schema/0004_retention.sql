-- ============================================================================
-- 0004_retention.sql — Retención y purga
--
-- Propiedad: equipo de plataforma / agente.
-- Requiere 0001 y 0002 aplicados.
--
-- README §10 exige retención definida para las conversaciones. Esta función
-- NO se ejecuta sola: hay que programarla (ver el final del fichero).
--
-- Qué se borra y qué no:
--   sessions      → se borra (arrastra messages, citations, recommendations)
--   leads         → SOBREVIVE (session_id queda a NULL; ver 0002)
--   feedback      → se borra con su mensaje
-- ============================================================================

create or replace function public.purge_expired_sessions(
  retention_days integer default 90
)
returns table (deleted_sessions bigint)
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  cutoff timestamptz;
begin
  if retention_days is null or retention_days < 1 then
    raise exception 'retention_days debe ser >= 1, recibido: %', retention_days;
  end if;

  cutoff := now() - make_interval(days => retention_days);

  with removed as (
    delete from public.sessions
    where last_seen < cutoff
    returning 1
  )
  select count(*)::bigint into deleted_sessions from removed;

  return next;
end;
$$;

comment on function public.purge_expired_sessions(integer) is
  'Borra sesiones inactivas y su conversación. Los leads sobreviven con session_id a NULL.';

revoke all on function public.purge_expired_sessions(integer) from anon, authenticated;

-- ----------------------------------------------------------------------------
-- Programación (NO se aplica automáticamente)
-- ----------------------------------------------------------------------------
-- Opción A — pg_cron, si está habilitado en el proyecto:
--
--   select cron.schedule(
--     'purge-expired-sessions',
--     '0 3 * * *',
--     $$select public.purge_expired_sessions(90)$$
--   );
--
-- Opción B — llamada desde el backend en un job diario.
--
-- Elegir una y dejarlo anotado. Una función de purga que nadie invoca es peor
-- que no tenerla: da la impresión de que la retención está resuelta.
