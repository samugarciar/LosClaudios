"use client";

/**
 * Estado de la conversación y consumo del stream SSE.
 *
 * Responsabilidades:
 *  - trocear y bufferizar el stream (los frames SSE no llegan alineados con
 *    los chunks de red, así que hay que acumular hasta ver la línea en blanco);
 *  - validar cada evento con el contrato antes de tocar el estado;
 *  - permitir cancelar el turno en curso.
 *
 * Lo que NO hace: interpretar el dominio. No decide qué preguntar, ni ordena
 * candidatos, ni juzga si un perfil está completo. Eso es del agente.
 */

import { useCallback, useRef, useState } from "react";
import {
  parseServerEvent,
  type Candidate,
  type ChatRequest,
  type Chip,
  type Citation,
  type HandoffRequest,
  type Lead,
  type Locale,
  type Message,
  type Slot,
  type Stage,
} from "@/lib/protocol";

export type ChatStatus = "idle" | "streaming" | "error";

export interface ChatError {
  message: string;
  retryable: boolean;
}

const nowIso = (): string => new Date().toISOString();
const newId = (): string => crypto.randomUUID();

export function useChat(locale: Locale) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [stage, setStage] = useState<Stage>("discovery");
  const [chips, setChips] = useState<Chip[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [handoffRequest, setHandoffRequest] = useState<HandoffRequest | null>(null);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [error, setError] = useState<ChatError | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const lastRequestRef = useRef<ChatRequest | null>(null);

  const run = useCallback(async (request: ChatRequest): Promise<void> => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    lastRequestRef.current = request;

    setStatus("streaming");
    setError(null);
    setChips([]);          // los chips del turno anterior dejan de ser válidos
    setStreamingText("");

    // Marcadores de cita vistos en este turno, para asociarlos al mensaje.
    const turnMarkers = new Set<number>();
    let accumulated = "";

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        setError({ message: `HTTP ${response.status}`, retryable: response.status >= 500 });
        setStatus("error");
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Un frame SSE termina en línea en blanco. El último trozo del buffer
        // puede estar incompleto, así que se conserva para la vuelta siguiente.
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          const data = frame
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trimStart())
            .join("\n");

          if (!data) continue;

          const event = parseServerEvent(data);
          if (!event) {
            // Frame corrupto: se descarta el evento, no la conversación.
            console.warn("[chat] evento SSE descartado por no cumplir el contrato");
            continue;
          }

          switch (event.type) {
            case "token":
              accumulated += event.text;
              setStreamingText(accumulated);
              break;

            case "stage":
              setStage(event.stage);
              break;

            case "chips":
              setChips(event.chips);
              break;

            case "citations":
              for (const c of event.citations) turnMarkers.add(c.marker);
              setCitations((prev) => {
                const byMarker = new Map(prev.map((c) => [c.marker, c]));
                for (const c of event.citations) byMarker.set(c.marker, c);
                return [...byMarker.values()].sort((a, b) => a.marker - b.marker);
              });
              break;

            case "candidates":
              setCandidates(event.candidates);
              break;

            case "handoff_request":
              setHandoffRequest(event.request);
              break;

            case "done":
              setMessages((prev) => [
                ...prev,
                {
                  id: event.messageId,
                  role: "assistant",
                  content: accumulated,
                  citationMarkers: [...turnMarkers].sort((a, b) => a - b),
                  createdAt: nowIso(),
                },
              ]);
              setStreamingText("");
              break;

            case "error":
              setError({ message: event.message, retryable: event.retryable });
              setStatus("error");
              return;
          }
        }
      }

      setStatus("idle");
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") {
        // Cancelación del usuario: conserva lo ya recibido como mensaje.
        if (accumulated) {
          setMessages((prev) => [
            ...prev,
            {
              id: newId(),
              role: "assistant",
              content: accumulated,
              citationMarkers: [...turnMarkers].sort((a, b) => a - b),
              createdAt: nowIso(),
            },
          ]);
        }
        setStreamingText("");
        setStatus("idle");
        return;
      }
      setError({ message: "network_error", retryable: true });
      setStatus("error");
    }
  }, []);

  const sendMessage = useCallback(
    async (text: string, slot: Slot | null = null): Promise<void> => {
      const trimmed = text.trim();
      if (!trimmed || status === "streaming") return;

      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "user",
          content: trimmed,
          citationMarkers: [],
          createdAt: nowIso(),
        },
      ]);

      await run({ kind: "message", locale, text: trimmed, slot });
    },
    [locale, run, status],
  );

  const submitLead = useCallback(
    async (lead: Lead): Promise<void> => {
      await run({ kind: "lead", locale, lead });
    },
    [locale, run],
  );

  const stop = useCallback((): void => {
    abortRef.current?.abort();
  }, []);

  const retry = useCallback(async (): Promise<void> => {
    const last = lastRequestRef.current;
    if (last) await run(last);
  }, [run]);

  return {
    messages,
    streamingText,
    stage,
    chips,
    citations,
    candidates,
    handoffRequest,
    status,
    error,
    sendMessage,
    submitLead,
    stop,
    retry,
  };
}
