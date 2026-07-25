/**
 * Contrato frontend ↔ agente.
 *
 * Este fichero es la frontera del sistema: define exactamente qué viaja por el
 * stream SSE entre el route handler `/api/chat` y el navegador, en ambos modos
 * (guion simulado y backend FastAPI real). El backend de la fase 2 debe emitir
 * estos mismos eventos; cualquier cambio aquí es un cambio de contrato y hay
 * que aplicarlo en los dos lados a la vez.
 *
 * Todo evento entrante se valida con zod antes de tocar el estado de la UI.
 * Un evento que no valida se descarta y se registra: preferimos perder un
 * evento a corromper el estado de la conversación.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Idioma
// ---------------------------------------------------------------------------
// El locale viaja en el cuerpo de la petición, así que forma parte del
// contrato y vive aquí. `lib/i18n.ts` importa el tipo desde este fichero.

export const LOCALES = ["es", "en"] as const;
export const LocaleSchema = z.enum(LOCALES);
export type Locale = z.infer<typeof LocaleSchema>;

// ---------------------------------------------------------------------------
// Etapas del grafo (README §8)
// ---------------------------------------------------------------------------

export const STAGES = ["discovery", "shortlist", "compare", "handoff"] as const;
export const StageSchema = z.enum(STAGES);
export type Stage = z.infer<typeof StageSchema>;

// ---------------------------------------------------------------------------
// Slots del perfil de requisitos (README §8)
// ---------------------------------------------------------------------------
// La UI no interpreta los slots: solo los usa para etiquetar chips y para
// listar qué falta en el handoff. La lógica de qué preguntar y en qué orden
// es del agente, nunca del frontend.

export const PROFILE_SLOTS = [
  "application_type",
  "body_part",
  "area_geometry",
  "mounting",
  "environment",
  "access_frequency",
  "material_passthrough",
  "existing_control",
  "region",
  "stopping_time",
] as const;
export const SlotSchema = z.enum(PROFILE_SLOTS);
export type Slot = z.infer<typeof SlotSchema>;

// ---------------------------------------------------------------------------
// Cita
// ---------------------------------------------------------------------------

export const CitationSchema = z.object({
  /** Número mostrado inline en el texto: [1], [2]… Único dentro de un turno. */
  marker: z.number().int().positive(),
  docId: z.string().min(1),
  /**
   * Ancla de auditoría (README §7). Una recomendación debe poder revisarse
   * contra la versión de documento que se usó, no contra la actual. Por eso
   * este campo NO es opcional.
   */
  docVersion: z.number().int().nonnegative(),
  docTitle: z.string().min(1),
  page: z.number().int().positive().nullable(),
  sectionPath: z.string().nullable(),
  snippet: z.string(),
  sourceUrl: z.string().min(1),
  score: z.number().nullable(),
});
export type Citation = z.infer<typeof CitationSchema>;

// ---------------------------------------------------------------------------
// Chip (opción sugerida)
// ---------------------------------------------------------------------------

export const ChipSchema = z.object({
  id: z.string().min(1),
  /** Texto que ve el usuario. */
  label: z.string().min(1),
  /** Texto que se envía como mensaje al pulsarlo. */
  value: z.string().min(1),
  /** Slot al que responde, si aplica. Informativo para telemetría. */
  slot: SlotSchema.nullable(),
});
export type Chip = z.infer<typeof ChipSchema>;

// ---------------------------------------------------------------------------
// Candidato de la preselección
// ---------------------------------------------------------------------------

export const CandidateSchema = z.object({
  partNumber: z.string().min(1),
  family: z.string().min(1),
  variant: z.string().nullable(),
  rank: z.number().int().positive(),
  /** Una frase en lenguaje llano: por qué está en la lista. */
  headline: z.string().min(1),
  pros: z.array(z.string()),
  /**
   * Regla de diseño (README §8): un shortlist honesto siempre expone contras.
   * El esquema es permisivo a propósito — descartar un candidato entero por no
   * traer contras sería peor que mostrarlo — pero un candidato con `cons`
   * vacío es un defecto del agente, no un caso normal.
   */
  cons: z.array(z.string()),
  /** Marcadores de cita que respaldan este candidato. */
  citationMarkers: z.array(z.number().int().positive()),
  confidence: z.number().min(0).max(1).nullable(),
});
export type Candidate = z.infer<typeof CandidateSchema>;

// ---------------------------------------------------------------------------
// Solicitud de handoff (estado terminal, README §13)
// ---------------------------------------------------------------------------

export const HANDOFF_REASONS = [
  /** Perfil suficiente: se deriva para cerrar la selección. */
  "profile_complete",
  /** Falta un dato que no se puede obtener por chat (p. ej. tiempo de parada). */
  "missing_critical_data",
  /** El usuario pidió hablar con una persona. */
  "user_request",
  /** Consulta fuera del alcance del MVP. */
  "out_of_scope",
] as const;
export const HandoffReasonSchema = z.enum(HANDOFF_REASONS);
export type HandoffReason = z.infer<typeof HandoffReasonSchema>;

export const HandoffRequestSchema = z.object({
  reason: HandoffReasonSchema,
  /** Slots que siguen sin resolver. La UI los muestra con transparencia. */
  missing: z.array(SlotSchema),
  /** Resumen legible para el usuario de lo que se ha entendido. */
  summaryForUser: z.string(),
  /** Versión del texto de consentimiento que debe aceptar (README §9). */
  consentTextVersion: z.string().min(1),
});
export type HandoffRequest = z.infer<typeof HandoffRequestSchema>;

// ---------------------------------------------------------------------------
// Eventos servidor → cliente
// ---------------------------------------------------------------------------

export const ServerEventSchema = z.discriminatedUnion("type", [
  /** Fragmento de texto del turno del agente. */
  z.object({ type: z.literal("token"), text: z.string() }),

  /** Cambio de etapa del grafo. La UI lo usa para el indicador de progreso. */
  z.object({ type: z.literal("stage"), stage: StageSchema }),

  /** Reemplaza las opciones sugeridas vigentes. Lista vacía = sin chips. */
  z.object({ type: z.literal("chips"), chips: z.array(ChipSchema) }),

  /** Citas del turno actual. Se acumulan en el drawer. */
  z.object({ type: z.literal("citations"), citations: z.array(CitationSchema) }),

  /** Preselección de producto. */
  z.object({ type: z.literal("candidates"), candidates: z.array(CandidateSchema) }),

  /** El agente pide cerrar con handoff: la UI muestra el formulario. */
  z.object({ type: z.literal("handoff_request"), request: HandoffRequestSchema }),

  /** Fin del turno. `messageId` permite asociar feedback posterior. */
  z.object({ type: z.literal("done"), messageId: z.string().min(1) }),

  /** Error. `retryable` decide si la UI ofrece reintentar. */
  z.object({
    type: z.literal("error"),
    code: z.string().min(1),
    message: z.string(),
    retryable: z.boolean(),
  }),
]);
export type ServerEvent = z.infer<typeof ServerEventSchema>;
export type ServerEventType = ServerEvent["type"];

// ---------------------------------------------------------------------------
// Estado de mensaje en el cliente
// ---------------------------------------------------------------------------

export const MessageSchema = z.object({
  id: z.string().min(1),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  citationMarkers: z.array(z.number().int().positive()),
  /** ISO 8601. Se valida como string: el formato lo fija quien lo produce. */
  createdAt: z.string().min(1),
});
export type Message = z.infer<typeof MessageSchema>;

// ---------------------------------------------------------------------------
// Lead
// ---------------------------------------------------------------------------

export const LeadSchema = z.object({
  name: z.string().min(1).max(120),
  email: z.string().email().max(254),
  company: z.string().max(160).nullable(),
  country: z.string().max(80).nullable(),
  /**
   * `true` literal: sin consentimiento explícito no existe lead válido a nivel
   * de tipo, no solo a nivel de validación de formulario (README §9).
   */
  consentAccepted: z.literal(true),
  consentTextVersion: z.string().min(1),
});
export type Lead = z.infer<typeof LeadSchema>;

// ---------------------------------------------------------------------------
// Peticiones cliente → servidor
// ---------------------------------------------------------------------------

export const MAX_USER_MESSAGE_CHARS = 4000;

export const ChatRequestSchema = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("message"),
    locale: LocaleSchema,
    text: z.string().min(1).max(MAX_USER_MESSAGE_CHARS),
    /** Presente si el mensaje se originó al pulsar un chip. */
    slot: SlotSchema.nullable(),
  }),
  z.object({
    kind: z.literal("lead"),
    locale: LocaleSchema,
    lead: LeadSchema,
  }),
]);
export type ChatRequest = z.infer<typeof ChatRequestSchema>;

// ---------------------------------------------------------------------------
// Serialización SSE
// ---------------------------------------------------------------------------
// Un evento por frame, separados por línea en blanco. El troceado y el
// buffering del stream son responsabilidad de `lib/useChat.ts`; aquí solo
// vive la traducción evento ↔ frame.

/** Serializa un evento como frame SSE listo para escribir en el stream. */
export function encodeServerEvent(event: ServerEvent): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

/**
 * Convierte el cuerpo `data:` de un frame en un evento validado.
 * Devuelve `null` en lugar de lanzar: un frame corrupto no debe tumbar la
 * conversación entera.
 */
export function parseServerEvent(data: string): ServerEvent | null {
  let json: unknown;
  try {
    json = JSON.parse(data);
  } catch {
    return null;
  }
  const parsed = ServerEventSchema.safeParse(json);
  return parsed.success ? parsed.data : null;
}
