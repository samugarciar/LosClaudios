/**
 * ════════════════════════════════════════════════════════════════════════════
 *  ⚠️  DATOS FICTICIOS — NO SON ESPECIFICACIONES REALES DE PRODUCTO
 * ════════════════════════════════════════════════════════════════════════════
 *
 * Guion de conversación simulada para desarrollar y verificar la interfaz sin
 * backend. Existe por una razón concreta: la UI debe poder construirse y
 * probarse antes de que la fase 1 (ingesta) esté lista.
 *
 * Reglas de este fichero:
 *
 *  1. NINGÚN valor técnico de aquí es real. Los nombres de familia sí lo son
 *     (nanoScan3, microScan3, outdoorScan3), pero todo alcance, resolución,
 *     tiempo de respuesta o nivel PL que aparezca está marcado como [EJEMPLO].
 *  2. Las cifras reales solo pueden venir de la ingesta con procedencia a
 *     página (README §5, INV-4/INV-5). Nunca de este fichero ni de la memoria
 *     del modelo.
 *  3. Cuando el backend real esté conectado (`BACKEND_URL`), este guion deja
 *     de ejecutarse por completo.
 *
 * Si alguna vez ves un número de este fichero en producción, es un bug grave.
 */

import type {
  Candidate,
  Chip,
  Citation,
  HandoffRequest,
  Locale,
  Stage,
} from "@/lib/protocol";

/**
 * Paso de alto nivel del guion. El route handler lo traduce a eventos SSE:
 * `say` se trocea en eventos `token`, el resto va uno a uno.
 */
export type MockStep =
  | { kind: "stage"; stage: Stage }
  | { kind: "say"; text: string }
  | { kind: "chips"; chips: Chip[] }
  | { kind: "citations"; citations: Citation[] }
  | { kind: "candidates"; candidates: Candidate[] }
  | { kind: "handoff"; request: HandoffRequest };

const t = (locale: Locale, es: string, en: string): string =>
  locale === "es" ? es : en;

const CONSENT_VERSION =
  process.env.NEXT_PUBLIC_CONSENT_TEXT_VERSION ?? "unset";

// ---------------------------------------------------------------------------
// Citas de ejemplo
// ---------------------------------------------------------------------------

function exampleCitations(locale: Locale): Citation[] {
  return [
    {
      marker: 1,
      docId: "mock-doc-microscan3",
      docVersion: 1,
      docTitle: t(
        locale,
        "[EJEMPLO] Hoja de datos — microScan3 Core",
        "[EXAMPLE] Data sheet — microScan3 Core",
      ),
      page: 4,
      sectionPath: t(
        locale,
        "Datos técnicos › Campo de protección",
        "Technical data › Protective field",
      ),
      snippet: t(
        locale,
        "[VALOR FICTICIO] Fragmento de ejemplo para verificar el panel de " +
          "fuentes. El texto real vendrá de la ingesta con su página exacta.",
        "[FICTIONAL VALUE] Example snippet used to verify the sources panel. " +
          "Real text will come from ingestion with its exact page.",
      ),
      sourceUrl: "https://example.invalid/mock/microscan3.pdf",
      score: 0.82,
    },
    {
      marker: 2,
      docId: "mock-doc-outdoorscan3",
      docVersion: 2,
      docTitle: t(
        locale,
        "[EJEMPLO] Información técnica — outdoorScan3",
        "[EXAMPLE] Technical information — outdoorScan3",
      ),
      page: 11,
      sectionPath: t(
        locale,
        "Condiciones ambientales",
        "Environmental conditions",
      ),
      snippet: t(
        locale,
        "[VALOR FICTICIO] Segundo fragmento de ejemplo, para comprobar que se " +
          "acumulan varias fuentes en la misma conversación.",
        "[FICTIONAL VALUE] Second example snippet, to check that multiple " +
          "sources accumulate within one conversation.",
      ),
      sourceUrl: "https://example.invalid/mock/outdoorscan3.pdf",
      score: 0.74,
    },
  ];
}

// ---------------------------------------------------------------------------
// Candidatos de ejemplo
// ---------------------------------------------------------------------------
// Deliberadamente sin cifras: los pros y contras son cualitativos. Las cifras
// son responsabilidad de la capa estructurada (product_specs), no del texto.

function exampleCandidates(locale: Locale): Candidate[] {
  return [
    {
      partNumber: "MOCK-MS3-CORE",
      family: "microScan3",
      variant: "Core",
      rank: 1,
      headline: t(
        locale,
        "Encaja con protección de área en interior y montaje horizontal.",
        "Fits horizontal-mount area protection indoors.",
      ),
      pros: [
        t(
          locale,
          "Pensado para vigilar un área en el suelo alrededor de la máquina.",
          "Designed to monitor a floor-level area around the machine.",
        ),
        t(
          locale,
          "Permite conmutar entre varios campos según la fase del ciclo.",
          "Supports switching between several fields per cycle phase.",
        ),
      ],
      cons: [
        t(
          locale,
          "Hace falta el tiempo de parada de la máquina para fijar la distancia de montaje.",
          "The machine's stopping time is needed to set the mounting distance.",
        ),
        t(locale, "No apto para exterior.", "Not suitable for outdoor use."),
      ],
      citationMarkers: [1],
      confidence: 0.78,
    },
    {
      partNumber: "MOCK-NS3-COMPACT",
      family: "nanoScan3",
      variant: null,
      rank: 2,
      headline: t(
        locale,
        "Alternativa compacta si el hueco de montaje es muy justo.",
        "Compact alternative when mounting space is tight.",
      ),
      pros: [
        t(
          locale,
          "Carcasa más pequeña, para emplazamientos con poco espacio.",
          "Smaller housing, for installations with little room.",
        ),
      ],
      cons: [
        t(
          locale,
          "Menor alcance de campo protector — hay que verificarlo contra la hoja de datos.",
          "Shorter protective-field range — must be checked against the data sheet.",
        ),
        t(
          locale,
          "Puede no cubrir áreas grandes con un solo sensor.",
          "May not cover large areas with a single sensor.",
        ),
      ],
      citationMarkers: [1],
      confidence: 0.55,
    },
    {
      partNumber: "MOCK-OS3-OUTDOOR",
      family: "outdoorScan3",
      variant: null,
      rank: 3,
      headline: t(
        locale,
        "Solo si la zona está a la intemperie.",
        "Only if the area is exposed to the weather.",
      ),
      pros: [
        t(
          locale,
          "Diseñado para exterior, con lluvia y niebla.",
          "Built for outdoor use, including rain and fog.",
        ),
      ],
      cons: [
        t(
          locale,
          "Sobredimensionado y más caro si la instalación es en interior.",
          "Over-specified and more expensive for an indoor installation.",
        ),
        t(
          locale,
          "Conviene confirmar el rango de temperatura del emplazamiento.",
          "Worth confirming the site's temperature range.",
        ),
      ],
      citationMarkers: [2],
      confidence: 0.31,
    },
  ];
}

// ---------------------------------------------------------------------------
// Guion por turno
// ---------------------------------------------------------------------------

function discoveryTurns(locale: Locale): MockStep[][] {
  return [
    // Turno 0 — application_type
    [
      { kind: "stage", stage: "discovery" },
      {
        kind: "say",
        text: t(
          locale,
          "Cuéntame un poco más para poder acotar. ¿Lo que quieres evitar es " +
            "que alguien **entre** en una zona peligrosa, o que pueda **meter " +
            "la mano** en un punto concreto de la máquina?\n\nSi no lo tienes " +
            "claro, elige lo que más se parezca y lo ajustamos después.",
          "Tell me a bit more so I can narrow this down. Do you need to stop " +
            "someone from **entering** a hazardous area, or from **reaching " +
            "into** a specific point on the machine?\n\nIf you're unsure, pick " +
            "the closest option and we'll refine it.",
        ),
      },
      {
        kind: "chips",
        chips: [
          {
            id: "app-area",
            label: t(
              locale,
              "Que alguien entre en la zona",
              "Someone entering the area",
            ),
            value: t(
              locale,
              "Quiero evitar que alguien entre en la zona peligrosa.",
              "I need to stop someone from entering the hazardous area.",
            ),
            slot: "application_type",
          },
          {
            id: "app-point",
            label: t(
              locale,
              "Que meta la mano en un punto",
              "Someone reaching into a point",
            ),
            value: t(
              locale,
              "Quiero evitar que alguien meta la mano en un punto de la máquina.",
              "I need to stop someone reaching into a point on the machine.",
            ),
            slot: "application_type",
          },
          {
            id: "app-unsure",
            label: t(locale, "No estoy seguro", "I'm not sure"),
            value: t(
              locale,
              "No estoy seguro de cuál de los dos es mi caso.",
              "I'm not sure which of the two applies to me.",
            ),
            slot: "application_type",
          },
        ],
      },
    ],

    // Turno 1 — area_geometry
    [
      {
        kind: "say",
        text: t(
          locale,
          "Entendido. ¿Cómo describirías la zona? No necesito medidas exactas " +
            "todavía, solo la forma general.",
          "Got it. How would you describe the area? I don't need exact " +
            "measurements yet, just the general shape.",
        ),
      },
      {
        kind: "chips",
        chips: [
          {
            id: "geo-floor",
            label: t(
              locale,
              "Un área en el suelo alrededor de la máquina",
              "A floor area around the machine",
            ),
            value: t(
              locale,
              "Es un área en el suelo alrededor de la máquina.",
              "It's a floor area around the machine.",
            ),
            slot: "area_geometry",
          },
          {
            id: "geo-passage",
            label: t(locale, "Un paso de acceso", "An access passage"),
            value: t(
              locale,
              "Es un paso por el que se accede a la máquina.",
              "It's a passage used to reach the machine.",
            ),
            slot: "area_geometry",
          },
        ],
      },
    ],

    // Turno 2 — environment
    [
      {
        kind: "say",
        text: t(
          locale,
          "Última cosa antes de proponerte opciones: ¿cómo es el entorno?",
          "One last thing before I suggest options: what's the environment like?",
        ),
      },
      {
        kind: "chips",
        chips: [
          {
            id: "env-indoor",
            label: t(locale, "Interior limpio", "Clean indoor"),
            value: t(
              locale,
              "Es interior y bastante limpio.",
              "It's indoors and fairly clean.",
            ),
            slot: "environment",
          },
          {
            id: "env-dust",
            label: t(locale, "Interior con polvo", "Dusty indoor"),
            value: t(
              locale,
              "Es interior pero hay bastante polvo.",
              "It's indoors but quite dusty.",
            ),
            slot: "environment",
          },
          {
            id: "env-outdoor",
            label: t(locale, "Exterior", "Outdoor"),
            value: t(
              locale,
              "Está a la intemperie, en exterior.",
              "It's outdoors, exposed to the weather.",
            ),
            slot: "environment",
          },
        ],
      },
    ],
  ];
}

function shortlistTurn(locale: Locale): MockStep[] {
  return [
    { kind: "stage", stage: "shortlist" },
    {
      kind: "say",
      text: t(
        locale,
        "Con lo que me has contado, estas son las opciones que tienen sentido " +
          "mirar [1]. Te las doy con lo bueno y lo que hay que vigilar de cada " +
          "una, porque la elección final depende de un dato que todavía no " +
          "tenemos.\n\nOjo con esto: **no puedo darte la distancia de montaje**. " +
          "Depende del tiempo que tarda tu máquina en pararse, y eso se mide en " +
          "la instalación [2].",
        "Based on what you've told me, these are the options worth looking at " +
          "[1]. I'm giving you the upside and the caveat for each, because the " +
          "final choice depends on a figure we don't have yet.\n\nImportant: " +
          "**I can't give you the mounting distance.** It depends on how long " +
          "your machine takes to stop, and that is measured on site [2].",
      ),
    },
    { kind: "citations", citations: exampleCitations(locale) },
    { kind: "candidates", candidates: exampleCandidates(locale) },
  ];
}

function handoffTurn(locale: Locale): MockStep[] {
  const request: HandoffRequest = {
    reason: "missing_critical_data",
    missing: ["stopping_time", "existing_control"],
    summaryForUser: t(
      locale,
      "Protección de área en zona fija, acceso ocasional de personas, con " +
        "preselección de tres opciones. Falta el tiempo de parada de la máquina " +
        "y saber si ya tienes un PLC de seguridad.",
      "Area protection in a stationary application, occasional human access, " +
        "with three shortlisted options. Missing: the machine's stopping time " +
        "and whether you already have a safety PLC.",
    ),
    consentTextVersion: CONSENT_VERSION,
  };

  return [
    { kind: "stage", stage: "handoff" },
    {
      kind: "say",
      text: t(
        locale,
        "Aquí es donde te paso a una persona. Con el tiempo de parada de la " +
          "máquina en la mano, un ingeniero de seguridad cierra la selección y " +
          "la distancia de montaje en una llamada.",
        "This is where I hand you over to a person. With the machine's stopping " +
          "time in hand, a safety engineer can settle the selection and the " +
          "mounting distance in one call.",
      ),
    },
    { kind: "handoff", request },
  ];
}

/**
 * Devuelve los pasos del turno `turnIndex` (0-based). A partir del último
 * turno del guion se repite el handoff: el usuario ya está en el estado
 * terminal y no hay más conversación simulada que dar.
 */
export function mockTurn(turnIndex: number, locale: Locale): MockStep[] {
  const discovery = discoveryTurns(locale);
  const step = discovery[turnIndex];
  if (step) return step;
  if (turnIndex === discovery.length) return shortlistTurn(locale);
  return handoffTurn(locale);
}

/** Respuesta al envío del formulario de lead en modo simulado. */
export function mockLeadAck(locale: Locale): MockStep[] {
  return [
    { kind: "stage", stage: "handoff" },
    {
      kind: "say",
      text: t(
        locale,
        "Recibido. En modo simulado no se envía nada a ningún sitio: solo se " +
          "registra en la consola del servidor.",
        "Received. In mock mode nothing is sent anywhere: it's only logged to " +
          "the server console.",
      ),
    },
  ];
}
