/**
 * Diccionarios ES/EN (README §3).
 *
 * `es` es la fuente de verdad: el tipo `Dictionary` se deriva de él, así que
 * cualquier clave que falte en `en` es un error de compilación.
 *
 * IMPORTANTE — el texto de `handoff.consentText` es texto legal. Debe pasar
 * revisión antes de producción, y cualquier cambio en su redacción obliga a
 * subir `NEXT_PUBLIC_CONSENT_TEXT_VERSION` (README §9): el consentimiento se
 * audita por versión, no por contenido.
 */

import { LOCALES, LocaleSchema, type Locale } from "@/lib/protocol";

const es = {
  app: {
    title: "Asesor de seguridad para zonas fijas",
    subtitle: "Cuéntame qué necesitas proteger y te ayudo a acotar el producto.",
  },
  disclaimer: {
    title: "Esto es una orientación, no un dictamen de seguridad",
    body:
      "Te ayudo a preseleccionar producto y a preparar la conversación con un ingeniero " +
      "de seguridad de SICK. No determino el nivel de prestaciones (PL) requerido ni la " +
      "distancia mínima de seguridad: eso depende de la evaluación de riesgos de tu " +
      "instalación y del tiempo de parada de la máquina.",
    more: "Más información",
  },
  composer: {
    placeholder: "Describe la zona que quieres proteger…",
    send: "Enviar",
    stop: "Detener",
    hint: "Enter para enviar · Mayús+Enter para salto de línea",
  },
  chat: {
    thinking: "Pensando…",
    retrieving: "Consultando documentación…",
    you: "Tú",
    advisor: "Asesor",
    errorGeneric: "Algo ha fallado por nuestro lado.",
    retry: "Reintentar",
  },
  stages: {
    discovery: "Entendiendo tu caso",
    shortlist: "Preseleccionando",
    compare: "Comparando opciones",
    handoff: "Preparando el contacto",
  },
  /**
   * Etiquetas legibles de los slots del perfil. Las claves deben coincidir
   * exactamente con PROFILE_SLOTS de `lib/protocol.ts`: el usuario nunca debe
   * ver un identificador técnico como `stopping_time`.
   */
  slots: {
    application_type: "Tipo de protección",
    body_part: "Qué hay que detectar",
    area_geometry: "Forma y tamaño de la zona",
    mounting: "Montaje del sensor",
    environment: "Condiciones del entorno",
    access_frequency: "Frecuencia de acceso",
    material_passthrough: "Paso de material",
    existing_control: "Control de seguridad existente",
    region: "Región y normativa aplicable",
    stopping_time: "Tiempo de parada de la máquina",
  },
  citations: {
    title: "Fuentes",
    empty: "Todavía no hay fuentes citadas en esta conversación.",
    page: "Página",
    version: "Versión del documento",
    section: "Sección",
    open: "Abrir documento original",
    close: "Cerrar",
    badgeAria: "Ver fuente",
  },
  candidates: {
    title: "Opciones a considerar",
    why: "Por qué encaja",
    whyNot: "Qué tener en cuenta",
    confidence: "Confianza",
    rank: "Opción",
  },
  handoff: {
    title: "Sigamos con un ingeniero",
    body:
      "Le paso a nuestro equipo el resumen de esta conversación para que no tengas " +
      "que repetirlo.",
    reason: {
      profile_complete: "Tenemos lo suficiente para que un ingeniero cierre la selección.",
      missing_critical_data:
        "Falta un dato que no se puede resolver por chat y sí con un ingeniero.",
      user_request: "Has pedido hablar con una persona.",
      out_of_scope: "Tu caso queda fuera de lo que puedo cubrir aquí.",
    },
    missingIntro: "Datos que quedan pendientes:",
    name: "Nombre",
    email: "Email",
    company: "Empresa",
    country: "País",
    consentText:
      "Acepto que SICK trate mis datos para contactarme sobre esta consulta.",
    submit: "Enviar y solicitar contacto",
    submitting: "Enviando…",
    done: "Recibido. Nuestro equipo te contactará con este resumen a mano.",
    required: "Este campo es obligatorio",
    invalidEmail: "Revisa el formato del email",
  },
};

export type Dictionary = typeof es;

const en: Dictionary = {
  app: {
    title: "Safety advisor for stationary applications",
    subtitle: "Tell me what you need to protect and I'll help narrow down the product.",
  },
  disclaimer: {
    title: "This is guidance, not a safety assessment",
    body:
      "I help you shortlist products and prepare the conversation with a SICK safety " +
      "engineer. I don't determine the required performance level (PL) or the minimum " +
      "safety distance: those depend on your installation's risk assessment and on the " +
      "machine's stopping time.",
    more: "Learn more",
  },
  composer: {
    placeholder: "Describe the area you want to protect…",
    send: "Send",
    stop: "Stop",
    hint: "Enter to send · Shift+Enter for a new line",
  },
  chat: {
    thinking: "Thinking…",
    retrieving: "Checking documentation…",
    you: "You",
    advisor: "Advisor",
    errorGeneric: "Something went wrong on our side.",
    retry: "Try again",
  },
  stages: {
    discovery: "Understanding your case",
    shortlist: "Shortlisting",
    compare: "Comparing options",
    handoff: "Preparing the handover",
  },
  slots: {
    application_type: "Type of protection",
    body_part: "What must be detected",
    area_geometry: "Shape and size of the area",
    mounting: "Sensor mounting",
    environment: "Environmental conditions",
    access_frequency: "Access frequency",
    material_passthrough: "Material pass-through",
    existing_control: "Existing safety control",
    region: "Region and applicable standards",
    stopping_time: "Machine stopping time",
  },
  citations: {
    title: "Sources",
    empty: "No sources cited in this conversation yet.",
    page: "Page",
    version: "Document version",
    section: "Section",
    open: "Open original document",
    close: "Close",
    badgeAria: "View source",
  },
  candidates: {
    title: "Options to consider",
    why: "Why it fits",
    whyNot: "What to watch out for",
    confidence: "Confidence",
    rank: "Option",
  },
  handoff: {
    title: "Let's continue with an engineer",
    body:
      "I'll pass our team a summary of this conversation so you don't have to repeat it.",
    reason: {
      profile_complete: "We have enough for an engineer to finalise the selection.",
      missing_critical_data:
        "A required detail can't be settled over chat, but an engineer can settle it.",
      user_request: "You asked to talk to a person.",
      out_of_scope: "Your case falls outside what I can cover here.",
    },
    missingIntro: "Still outstanding:",
    name: "Name",
    email: "Email",
    company: "Company",
    country: "Country",
    consentText:
      "I agree that SICK may process my data to contact me about this enquiry.",
    submit: "Send and request contact",
    submitting: "Sending…",
    done: "Got it. Our team will reach out with this summary in hand.",
    required: "This field is required",
    invalidEmail: "Check the email format",
  },
};

const dictionaries: Record<Locale, Dictionary> = { es, en };

export function getDictionary(locale: Locale): Dictionary {
  return dictionaries[locale];
}

export const DEFAULT_LOCALE: Locale =
  LocaleSchema.safeParse(process.env.NEXT_PUBLIC_DEFAULT_LOCALE).data ?? "es";

/**
 * Resuelve el idioma a partir de una cabecera `Accept-Language`.
 * No implementa negociación con pesos `q=`: para dos idiomas, la primera
 * coincidencia por orden de aparición es suficiente y predecible.
 */
export function resolveLocale(
  acceptLanguage: string | null | undefined,
  fallback: Locale = DEFAULT_LOCALE,
): Locale {
  if (!acceptLanguage) return fallback;

  for (const part of acceptLanguage.split(",")) {
    const tag = part.split(";")[0]?.trim().toLowerCase();
    if (!tag) continue;
    const base = tag.split("-")[0];
    const match = LOCALES.find((l) => l === base);
    if (match) return match;
  }
  return fallback;
}
