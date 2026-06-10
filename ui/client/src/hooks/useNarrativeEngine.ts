/**
 * useNarrativeEngine - generation lifecycle for the narrative reading surface.
 *
 * Owns:
 * - the /ws/narrative WebSocket (phase telemetry, auto-reconnect)
 * - slot state polling via react-query (pending chunk + choices)
 * - turn submission through POST /api/narrative/continue
 * - the elapsed-time clock while a generation is in flight
 * - SKALD operator status derivation (READY / TRANSMITTING / GENERATING /
 *   RECEIVING / OFFLINE)
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/hooks/use-toast";
import { continueNarrative, getSlotState } from "@/lib/narrative-api";
import {
  ACTIVE_GENERATION_PHASES,
  type NarrativePhase,
  type NarrativeProgressPayload,
  type SkaldStatus,
  type SlotState,
} from "@/types/narrative";

const RECEIVING_HOLD_MS = 1200;
const WS_RECONNECT_MS = 3000;
const CONNECTIVITY_POLL_MS = 10000;

const isActivePhase = (phase: NarrativePhase | null): boolean =>
  phase !== null && ACTIVE_GENERATION_PHASES.includes(phase);

export interface NarrativeEngine {
  slotState: SlotState | undefined;
  slotStateError: Error | null;
  isSlotStateLoading: boolean;
  phase: NarrativePhase | null;
  skaldStatus: SkaldStatus;
  elapsedMs: number;
  generationError: string | null;
  isGenerating: boolean;
  /** Increments each time a generation completes; keys the typewriter reveal. */
  completedGenerations: number;
  submitTurn: (params: { choice?: number; userText?: string }) => Promise<void>;
}

export function useNarrativeEngine(slot: number | null): NarrativeEngine {
  const queryClient = useQueryClient();

  const [phase, setPhase] = useState<NarrativePhase | null>(null);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [backendReachable, setBackendReachable] = useState(true);
  const [receiving, setReceiving] = useState(false);
  const [completedGenerations, setCompletedGenerations] = useState(0);

  const sessionRef = useRef<string | null>(null);
  const phaseRef = useRef<NarrativePhase | null>(null);
  const timerRef = useRef<number | null>(null);
  const receivingTimeoutRef = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  const stopClock = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const startClock = useCallback(() => {
    stopClock();
    const startedAt = Date.now();
    setElapsedMs(0);
    timerRef.current = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt);
    }, 200);
  }, [stopClock]);

  // Slot state: the single source of truth for pending chunk + choices.
  const {
    data: slotState,
    error: slotStateError,
    isLoading: isSlotStateLoading,
  } = useQuery<SlotState, Error>({
    queryKey: ["/api/slot/state", slot],
    queryFn: () => getSlotState(slot as number),
    enabled: slot !== null,
  });

  // Adopt an in-flight session after a page reload: the slot state carries
  // the live session id while incubator content is pending.
  useEffect(() => {
    if (slotState?.session_id && !sessionRef.current) {
      sessionRef.current = slotState.session_id;
    }
  }, [slotState?.session_id]);

  // Refetch slot state + narrative reads. Needed after `complete` (a new
  // pending chunk exists) AND after `error`: submitting from a pending chunk
  // auto-approves it before generation runs, so even a failed turn can leave
  // the previously displayed state stale (chunk now committed, choices gone).
  const invalidateNarrativeQueries = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["/api/slot/state", slot] });
    queryClient.invalidateQueries({
      predicate: (query) =>
        Array.isArray(query.queryKey) &&
        typeof query.queryKey[0] === "string" &&
        query.queryKey[0].startsWith("/api/narrative"),
    });
  }, [queryClient, slot]);

  const handleProgress = useCallback(
    (payload: NarrativeProgressPayload) => {
      const { session_id: sessionId, status } = payload;
      if (!sessionId || !status) return;

      // Ignore telemetry from sessions other than ours (but adopt the
      // session if we don't have one - e.g. generation started elsewhere).
      if (sessionRef.current && sessionRef.current !== sessionId) return;
      if (!sessionRef.current) sessionRef.current = sessionId;

      const nextPhase = status as NarrativePhase;
      setPhase(nextPhase);

      if (nextPhase === "complete") {
        stopClock();
        setGenerationError(null);
        setReceiving(true);
        if (receivingTimeoutRef.current !== null) {
          window.clearTimeout(receivingTimeoutRef.current);
        }
        receivingTimeoutRef.current = window.setTimeout(() => {
          if (!mountedRef.current) return;
          setReceiving(false);
          setPhase(null);
        }, RECEIVING_HOLD_MS);
        sessionRef.current = null;
        setCompletedGenerations((n) => n + 1);
        // The new pending chunk lives in slot state + incubator.
        invalidateNarrativeQueries();
      } else if (nextPhase === "error") {
        stopClock();
        const message =
          (payload.data?.error as string) || "Narrative generation failed";
        setGenerationError(message);
        sessionRef.current = null;
        // The submitted chunk may already be committed (auto-approval runs
        // before generation) - resync so the reader doesn't show it as
        // pending with stale choices.
        invalidateNarrativeQueries();
        toast({
          title: "Generation Failed",
          description: message,
          variant: "destructive",
        });
      } else {
        setGenerationError(null);
      }
    },
    [invalidateNarrativeQueries, stopClock],
  );

  const handleProgressRef = useRef(handleProgress);
  useEffect(() => {
    handleProgressRef.current = handleProgress;
  }, [handleProgress]);

  // WebSocket lifecycle with auto-reconnect.
  useEffect(() => {
    mountedRef.current = true;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws/narrative`;

    const connect = () => {
      if (!mountedRef.current) return;
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onmessage = (event) => {
        try {
          handleProgressRef.current(JSON.parse(event.data));
        } catch (error) {
          console.error("[NarrativeWS] Failed to parse message:", error);
        }
      };
      ws.onclose = () => {
        wsRef.current = null;
        if (mountedRef.current) {
          reconnectRef.current = window.setTimeout(connect, WS_RECONNECT_MS);
        }
      };
    };

    connect();
    return () => {
      mountedRef.current = false;
      if (reconnectRef.current !== null) window.clearTimeout(reconnectRef.current);
      if (receivingTimeoutRef.current !== null) {
        window.clearTimeout(receivingTimeoutRef.current);
      }
      stopClock();
      wsRef.current?.close();
    };
  }, [stopClock]);

  // Backend connectivity probe - drives the OFFLINE status.
  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch("/api/settings", { method: "HEAD" });
        if (!cancelled) setBackendReachable(res.ok);
      } catch {
        if (!cancelled) setBackendReachable(false);
      }
    };
    check();
    const interval = window.setInterval(check, CONNECTIVITY_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const submitTurn = useCallback(
    async (params: { choice?: number; userText?: string }) => {
      if (slot === null) throw new Error("No active slot");
      if (isActivePhase(phaseRef.current)) {
        toast({
          title: "Generation Active",
          description: "Wait for the current turn to finish.",
        });
        return;
      }

      setPhase("initiated");
      setGenerationError(null);
      sessionRef.current = null;
      startClock();

      try {
        const result = await continueNarrative({ slot, ...params });
        sessionRef.current = result.session_id;
      } catch (error) {
        stopClock();
        setPhase("error");
        const message =
          error instanceof Error ? error.message : "Failed to start turn";
        setGenerationError(message);
        // A mid-endpoint failure can still land after the server-side
        // auto-approve - resync rather than trust the cached state.
        invalidateNarrativeQueries();
        toast({
          title: "Generation Failed",
          description: message,
          variant: "destructive",
        });
      }
    },
    [slot, startClock, stopClock, invalidateNarrativeQueries],
  );

  let skaldStatus: SkaldStatus = "READY";
  if (!backendReachable) {
    skaldStatus = "OFFLINE";
  } else if (receiving) {
    skaldStatus = "RECEIVING";
  } else if (phase === "calling_llm" || phase === "processing_response") {
    skaldStatus = "GENERATING";
  } else if (isActivePhase(phase)) {
    skaldStatus = "TRANSMITTING";
  } else if (phase === "error") {
    skaldStatus = "OFFLINE";
  }

  return {
    slotState,
    slotStateError: slotStateError ?? null,
    isSlotStateLoading,
    phase,
    skaldStatus,
    elapsedMs,
    generationError,
    isGenerating: isActivePhase(phase),
    completedGenerations,
    submitTurn,
  };
}
