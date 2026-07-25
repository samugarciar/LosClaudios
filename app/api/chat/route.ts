/**
 * Único punto de contacto del navegador con el agente.
 *
 * Dos modos, decididos por `BACKEND_URL`:
 *
 *   vacío  → SIMULADO: emite el guion de `lib/mock/scenario.ts` como SSE.
 *   con URL → PROXY: reenvía el stream del backend real sin reinterpretarlo.
 *
 * Conectar el backend de la fase 2 no debería tocar ningún otro fichero del
 * frontend: si hace falta, es que el contrato de `lib/protocol.ts` se ha
 * quedado corto y hay que arreglarlo ahí, no aquí.
 */

import type { NextRequest } from "next/server";
import {
  ChatRequestSchema,
  encodeServerEvent,
  type Locale,
  type ServerEvent,
} from "@/lib/protocol";
import { mockLeadAck, mockTurn, type MockStep } from "@/lib/mock/scenario";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Un turno con pensamiento adaptativo tarda entre 20 y 60 segundos. El límite
 * por defecto de una función en Vercel es de 10 s en el plan Hobby, así que sin
 * esto el stream se corta a mitad de respuesta y el usuario ve un mensaje
 * truncado sin ningún error.
 *
 * 60 es el máximo de Hobby. En Pro se puede subir hasta 300.
 */
export const maxDuration = 60;

const TURN_COOKIE = "sa_mock_turn";

const SSE_HEADERS: Record<string, string> = {
  "content-type": "text/event-stream; charset=utf-8",
  "cache-control": "no-cache, no-transform",
  connection: "keep-alive",
  // Evita el buffering de proxies intermedios, que rompe el streaming.
  "x-accel-buffering": "no",
};

function jsonError(status: number, code: string, message: string): Response {
  return new Response(JSON.stringify({ code, message }), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

export async function POST(req: NextRequest): Promise<Response> {
  const raw: unknown = await req.json().catch(() => null);
  const parsed = ChatRequestSchema.safeParse(raw);

  if (!parsed.success) {
    return jsonError(400, "invalid_request", "El cuerpo no cumple el contrato.");
  }

  const backendUrl = process.env.BACKEND_URL?.trim();
  return backendUrl
    ? proxyToBackend(req, backendUrl, parsed.data)
    : mockResponse(req, parsed.data);
}

// ---------------------------------------------------------------------------
// Modo proxy (backend real)
// ---------------------------------------------------------------------------

async function proxyToBackend(
  req: NextRequest,
  backendUrl: string,
  body: unknown,
): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl.replace(/\/$/, "")}/chat`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "text/event-stream",
        // La sesión la identifica el backend por cookie httpOnly (README §10).
        cookie: req.headers.get("cookie") ?? "",
      },
      body: JSON.stringify(body),
      signal: req.signal,
      cache: "no-store",
    });
  } catch {
    return jsonError(502, "backend_unreachable", "El backend no responde.");
  }

  if (!upstream.ok || !upstream.body) {
    return jsonError(502, "backend_error", `Backend devolvió ${upstream.status}.`);
  }

  const headers = new Headers(SSE_HEADERS);
  // Propaga la cookie de sesión que emita el backend.
  for (const cookie of upstream.headers.getSetCookie()) {
    headers.append("set-cookie", cookie);
  }

  return new Response(upstream.body, { status: 200, headers });
}

// ---------------------------------------------------------------------------
// Modo simulado
// ---------------------------------------------------------------------------

function mockResponse(
  req: NextRequest,
  body: { kind: "message" | "lead"; locale: Locale },
): Response {
  const turnRaw = req.cookies.get(TURN_COOKIE)?.value ?? "0";
  const turn = Number.parseInt(turnRaw, 10);
  const currentTurn = Number.isFinite(turn) && turn >= 0 ? turn : 0;

  const isLead = body.kind === "lead";
  const steps = isLead
    ? mockLeadAck(body.locale)
    : mockTurn(currentTurn, body.locale);

  if (isLead) {
    // En simulado el lead no sale de aquí. Deliberadamente no se registra el
    // contenido: son datos personales y esto es solo un guion de desarrollo.
    console.info("[mock] lead recibido — no se envía a ningún destino");
  }

  const delayMs = Number.parseInt(process.env.MOCK_STREAM_DELAY_MS ?? "18", 10);
  const stream = buildMockStream(steps, Number.isFinite(delayMs) ? delayMs : 18, req.signal);

  const headers = new Headers(SSE_HEADERS);
  if (!isLead) {
    // El turno solo avanza con mensajes de usuario. Cookie de desarrollo:
    // en el backend real el estado vive en el checkpointer de LangGraph.
    headers.append(
      "set-cookie",
      `${TURN_COOKIE}=${currentTurn + 1}; Path=/; SameSite=Lax; HttpOnly`,
    );
  }

  return new Response(stream, { status: 200, headers });
}

function buildMockStream(
  steps: MockStep[],
  delayMs: number,
  signal: AbortSignal,
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();

  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (event: ServerEvent): void => {
        controller.enqueue(encoder.encode(encodeServerEvent(event)));
      };

      const sleep = (ms: number): Promise<void> =>
        new Promise((resolve) => setTimeout(resolve, ms));

      try {
        for (const step of steps) {
          if (signal.aborted) break;

          switch (step.kind) {
            case "stage":
              send({ type: "stage", stage: step.stage });
              await sleep(delayMs * 6);
              break;

            case "say": {
              // Trocea por palabra conservando los espacios, para que el
              // render incremental no dependa de dónde caen los cortes.
              const chunks = step.text.match(/\S+\s*/g) ?? [step.text];
              for (const chunk of chunks) {
                if (signal.aborted) break;
                send({ type: "token", text: chunk });
                await sleep(delayMs);
              }
              break;
            }

            case "chips":
              send({ type: "chips", chips: step.chips });
              break;

            case "citations":
              send({ type: "citations", citations: step.citations });
              break;

            case "candidates":
              send({ type: "candidates", candidates: step.candidates });
              break;

            case "handoff":
              send({ type: "handoff_request", request: step.request });
              break;
          }
        }

        if (!signal.aborted) {
          send({ type: "done", messageId: crypto.randomUUID() });
        }
      } catch {
        send({
          type: "error",
          code: "mock_stream_failed",
          message: "El guion simulado falló.",
          retryable: true,
        });
      } finally {
        controller.close();
      }
    },
  });
}
