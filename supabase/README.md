# Esquema de Supabase

Ficheros SQL numerados, aplicables a mano. **No hay Supabase CLI en este
proyecto**: es una decisión tomada. Los ficheros van versionados en el repo
para que exista historial aunque la aplicación sea manual.

## Cómo aplicar

En el SQL Editor del proyecto de Supabase, **en orden numérico**:

```
0001_core.sql        sessions, messages, citations
0002_business.sql    recommendations, leads, feedback
0003_rls.sql         RLS + revocación de privilegios
0004_retention.sql   función de purga (no se programa sola)
```

Todos son idempotentes: reaplicarlos no rompe nada. Verificado contra
PostgreSQL 16.

Después de `0004`, hay que **elegir cómo se programa la purga** (pg_cron o un
job del backend). Está anotado al final de ese fichero. Una función de purga
que nadie invoca da la falsa impresión de que la retención está resuelta.

## Propiedad de las tablas

Compartimos base de datos entre dos equipos. Antes de crear cualquier objeto,
comprueba esta tabla.

| Tabla | Propiedad | Fichero |
|---|---|---|
| `sessions` | plataforma / agente | `0001_core.sql` |
| `messages` | plataforma / agente | `0001_core.sql` |
| `citations` | plataforma / agente | `0001_core.sql` |
| `recommendations` | plataforma / agente | `0002_business.sql` |
| `leads` | plataforma / agente | `0002_business.sql` |
| `feedback` | plataforma / agente | `0002_business.sql` |
| `documents` | **equipo de RAG** | — (no lo creamos nosotros) |
| `chunks` | **equipo de RAG** | — |
| `product_specs` | **equipo de RAG** | — |
| `ingest_review_queue` | **equipo de RAG** | — |
| `checkpoints` | plataforma / agente | **las crea LangGraph** ⚠️ |
| `checkpoint_blobs` | plataforma / agente | **las crea LangGraph** ⚠️ |
| `checkpoint_writes` | plataforma / agente | **las crea LangGraph** ⚠️ |
| `checkpoint_migrations` | plataforma / agente | **las crea LangGraph** ⚠️ |

⚠️ Las cuatro tablas `checkpoint*` **no están en `supabase/schema/`**: las crea
automáticamente `langgraph-checkpoint-postgres` la primera vez que el backend
arranca con `DATABASE_URL` definido. Son nuestras, pero las gestiona la
librería. Aparecerán en el esquema sin que nadie las haya escrito a mano: que
no sorprenda a nadie ni se borren por parecer basura.

### Reglas de convivencia

1. **No crees tablas de otro equipo**, ni siquiera "para desbloquearte". Si
   necesitas una, pídela.
2. **Numera tus ficheros en un rango propio.** Nosotros usamos `0001–0099`.
   El equipo de RAG debería usar `0100+` para que dos ficheros nunca compitan
   por el mismo número.
3. **`citations.doc_id` es TEXT y no tiene FK contra `documents`.** Deliberado:
   una foreign key acoplaría nuestro esquema a su calendario de entrega. La
   integridad referencial entre citas y documentos se valida en la aplicación,
   no en la base de datos.
4. **No generalices los `REVOKE`.** `0003_rls.sql` enumera las tablas una a
   una. Un `revoke ... on all tables in schema public` tocaría también las
   tablas de RAG y podría romperles el acceso sin aviso.
5. **`pgvector` no lo habilitamos nosotros.** Si hace falta, va en el rango
   `0100+` del equipo de RAG.

## Modelo de acceso

El frontend **no habla con Supabase**. El backend es el único cliente y usa la
`service_role`, que ignora RLS por diseño en Supabase.

`0003_rls.sql` activa RLS y **no crea ninguna política** para `anon` ni
`authenticated`. RLS activo sin políticas equivale a denegación total. Es
intencionado: si algún día la anon key acaba en el navegador, estas tablas
siguen cerradas.

Verificado: con `set role anon`, un `select` sobre `leads` devuelve
`permission denied for table leads`.

## Decisiones de diseño que conviene no revertir por accidente

**`leads.session_id` es NULLABLE y usa `ON DELETE SET NULL`.** No es un
descuido. Si cascadease, la purga de retención borraría leads que el equipo
comercial todavía está trabajando. Por eso el contexto del handoff se
desnormaliza en `leads.handoff_summary`: el lead es autocontenido y sobrevive
a su conversación.

Verificado: tras purgar una sesión de 200 días, el lead permanece con
`session_id` a NULL y `handoff_summary` intacto.

**No existe `sessions.lead_id`.** Junto con `leads.session_id` formaría una FK
circular imposible de crear en un solo paso. Se consulta por
`leads.session_id`.

**`citations.doc_version` es NOT NULL.** Es el ancla de auditoría: sin la
versión del documento, una recomendación pasada no se puede reconstruir contra
la documentación que se usó en su momento.
