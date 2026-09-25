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
import {
  continueNarrative,
  retryNarrative,
  getSlotState,
  getActiveGeneration,
  getGenerationStatus,
  getRecoveryPreferences,
} from "@/lib/narrative-api";
import {
  ACTIVE_GENERATION_PHASES,
  type NarrativePhase,
  type GenerationSettings,
  type GenerationSession,
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
  failedGeneration: GenerationSession | null;
  isRecoveryLoading: boolean;
  retryGeneration: () => Promise<boolean>;
  isGenerating: boolean;
  /** Increments on completion to restore frontier scrolling and input focus. */
  completedGenerations: number;
  /** True only after the server acknowledged this submission. */
  submitTurn: (params: { choice?: number; userText?: string }) => Promise<boolean>;
}

export function useNarrativeEngine(slot: number | null): NarrativeEngine {
  const queryClient = useQueryClient();

  const [phase, setPhase] = useState<NarrativePhase | null>(null);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [failedGeneration, setFailedGeneration] = useState<GenerationSession | null>(null);
  const [isRecoveryLoading, setIsRecoveryLoading] = useState(true);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [backendReachable, setBackendReachable] = useState(true);
  const [receiving, setReceiving] = useState(false);
  const [completedGenerations, setCompletedGenerations] = useState(0);

  const sessionRef = useRef<string | null>(null);
  const submittingRef = useRef(false);
  const submissionEpochRef = useRef(0);
  const phaseRef = useRef<NarrativePhase | null>(null);
  const timerRef = useRef<number | null>(null);
  const receivingTimeoutRef = useRef<number | null>(null);
  const recoverRef = useRef<() => void>(() => {});
  const activeSlotRef = useRef(slot);
  activeSlotRef.current = slot;

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  const stopClock = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const startClock = useCallback((startedAt = Date.now()) => {
    stopClock();
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
    queryFn: ({ signal }) => getSlotState(slot as number, signal),
    enabled: slot !== null,
  });

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

  // Preferences need no slot/database read. Retry bootstrap failures even when
  // the application QueryClient disables retries; lifecycle listeners below
  // can also cancel and restart a stalled bootstrap request.
  const { data: recoveryPreferences, error: recoverySettingsError } = useQuery({
    queryKey: ["/api/preferences", "narrative-recovery"],
    queryFn: ({ signal }) => getRecoveryPreferences(signal),
    enabled: slot !== null,
    retry: true,
  });
  const settings =
    slotState?.narrative_generation ?? recoveryPreferences?.narrative_generation;
  const settingsRef = useRef<GenerationSettings | undefined>(settings);
  settingsRef.current = settings;
  useEffect(() => {
    recoverRef.current();
  }, [settings]);

  // PostgreSQL owns the lifecycle. Every boundary discovers the server's
  // attempt; socket payloads only request an earlier durable read.
  useEffect(() => {
    sessionRef.current = null;
    submittingRef.current = false;
    phaseRef.current = null;
    setPhase(null);
    setGenerationError(null);
    setFailedGeneration(null);
    setIsRecoveryLoading(true);
    setReceiving(false);
    stopClock();
    if (slot === null) return;
    let cancelled = false;
    let currentRequest: AbortController | null = null;
    let interval: number | undefined;
    let lastTerminal = "";
    let lastTick = Date.now();
    let ws: WebSocket | null = null;
    let reconnect: number | undefined;

    const recover = async (interrupt = false) => {
      if (cancelled) return;
      if (interrupt) {
        currentRequest?.abort();
        currentRequest = null;
      }
      const config = settingsRef.current;
      if (!config) return;
      if (interval === undefined) {
        interval = window.setTimeout(tick, config.poll_interval_seconds * 1000);
      }
      if (currentRequest) return;
      const request = new AbortController();
      currentRequest = request;
      const epoch = submissionEpochRef.current;
      const obsolete = () =>
        cancelled || request.signal.aborted || epoch !== submissionEpochRef.current;
      // Each read gets its own timeout, including response-body consumption.
      const read = async <T,>(
        fetcher: (signal: AbortSignal) => Promise<T>,
      ): Promise<T> => {
        const controller = new AbortController();
        const abort = () => controller.abort();
        request.signal.addEventListener("abort", abort, { once: true });
        const timeout = window.setTimeout(
          () => controller.abort(), config.request_timeout_seconds * 1000,
        );
        try {
          return await fetcher(controller.signal);
        } finally {
          window.clearTimeout(timeout);
          request.signal.removeEventListener("abort", abort);
        }
      };
      try {
        const active = await read((signal) => getActiveGeneration(slot, signal));
        if (obsolete()) return;
        // A previous owner may have been superseded. Read that terminal state
        // before adopting the new owner, then follow the server's current one.
        if (sessionRef.current && active?.session_id !== sessionRef.current) {
          await read((signal) => getGenerationStatus(slot, sessionRef.current!, signal));
          if (obsolete()) return;
          invalidateNarrativeQueries();
        }
        const terminalKey = active
          ? `${active.session_id}:${active.status}:${active.terminal_outcome}`
          : "";
        const state =
          active && (active.status === "initiated" || terminalKey !== lastTerminal)
            ? await read((signal) => getGenerationStatus(slot, active.session_id, signal))
            : active;
        if (obsolete()) return;
        if (state && (state.slot !== slot || state.session_id !== active?.session_id)) {
          throw new Error("Generation response identity mismatch");
        }
        setIsRecoveryLoading(false);
        setBackendReachable(true);
        if (!state) {
          setFailedGeneration(null);
          if (lastTerminal) {
            lastTerminal = "";
            invalidateNarrativeQueries();
          }
          setGenerationError(null);
          setReceiving(false);
          sessionRef.current = null;
          phaseRef.current = null;
          setPhase(null);
          stopClock();
          return;
        }
        if (state.slot !== slot) throw new Error("Generation response slot mismatch");
        if (state.status === "initiated" && !state.terminal_outcome) {
          if (sessionRef.current !== state.session_id) {
            startClock(Date.parse(state.created_at));
          }
          setFailedGeneration(null);
          sessionRef.current = state.session_id;
          phaseRef.current = state.phase;
          setPhase(state.phase);
          setGenerationError(null);
          setReceiving(false);
        } else {
          sessionRef.current = null;
          phaseRef.current = null;
          setPhase(null);
          stopClock();
          const terminal = `${state.session_id}:${state.status}:${state.terminal_outcome}`;
          if (terminal !== lastTerminal) {
            lastTerminal = terminal;
            invalidateNarrativeQueries();
            if (state.terminal_outcome === "discarded") {
              setFailedGeneration(null);
              setGenerationError(null);
              setReceiving(false);
            } else if (state.terminal_outcome === "error" || state.status === "error") {
              setFailedGeneration(state);
              setReceiving(false);
              const message =
                state.error || state.error_class || "Narrative generation failed";
              setGenerationError(message);
              toast({
                title: "Generation Failed",
                description: message,
                variant: "destructive",
              });
            } else {
              setFailedGeneration(null);
              setGenerationError(null);
              setCompletedGenerations((n) => n + 1);
              setReceiving(true);
              if (receivingTimeoutRef.current !== null) {
                window.clearTimeout(receivingTimeoutRef.current);
              }
              receivingTimeoutRef.current = window.setTimeout(() => {
                if (!cancelled) setReceiving(false);
              }, RECEIVING_HOLD_MS);
            }
          }
        }
      } catch (error) {
        if (!obsolete()) {
          // Connectivity alone drives OFFLINE. A durable generation failure
          // clears the transient phase and is surfaced independently.
          setGenerationError(
            error instanceof Error ? error.message : String(error),
          );
          if (
            error instanceof TypeError ||
            (error instanceof DOMException && error.name === "AbortError")
          ) setBackendReachable(false);
        }
      } finally {
        // A cancelled request must never clear its replacement.
        if (currentRequest === request) {
          currentRequest = null;
        }
      }
    };
    const boundary = () => {
      invalidateNarrativeQueries();
      if (!settingsRef.current) {
        const queryKey = ["/api/preferences", "narrative-recovery"];
        void queryClient.cancelQueries({ queryKey }).then(() => {
          if (!cancelled) void queryClient.refetchQueries({ queryKey });
        });
      }
      void recover(true);
    };
    const tick = () => {
      interval = undefined;
      const now = Date.now();
      const config = settingsRef.current;
      if (config && now - lastTick > config.wake_gap_threshold_seconds * 1000) boundary();
      else void recover();
      lastTick = now;
    };
    recoverRef.current = () => { void recover(true); };
    const onVisible = () => {
      if (document.visibilityState === "visible") boundary();
    };
    const connect = () => {
      if (cancelled) return;
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(
        `${protocol}//${window.location.host}/ws/narrative?slot=${slot}`,
      );
      ws.onopen = boundary;
      ws.onmessage = (event) => {
        try {
          const payload: NarrativeProgressPayload = JSON.parse(event.data);
          if (payload.slot !== slot || !payload.session_id) return;
          if (sessionRef.current && payload.session_id !== sessionRef.current) return;
          void recover();
        } catch (error) {
          console.error("[NarrativeWS] Failed to parse message:", error);
        }
      };
      ws.onclose = () => {
        if (!cancelled) reconnect = window.setTimeout(connect, WS_RECONNECT_MS);
      };
    };
    boundary();
    connect();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      recoverRef.current = () => {};
      currentRequest?.abort();
      window.clearTimeout(interval);
      window.clearTimeout(reconnect);
      if (receivingTimeoutRef.current !== null) {
        window.clearTimeout(receivingTimeoutRef.current);
      }
      document.removeEventListener("visibilitychange", onVisible);
      stopClock();
      ws?.close();
    };
  }, [
    slot, queryClient,
    invalidateNarrativeQueries, startClock, stopClock,
  ]);

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

  const submitRequest = useCallback(
    async (params: { choice?: number; userText?: string }, retrySession?: string) => {
      if (slot === null) throw new Error("No active slot");
      if (submittingRef.current || isActivePhase(phaseRef.current)) {
        toast({
          title: "Generation Active",
          description: "Wait for the current turn to finish.",
        });
        return false;
      }

      submissionEpochRef.current += 1;
      submittingRef.current = true;
      phaseRef.current = "retrieval";
      setPhase("retrieval");
      setGenerationError(null);
      sessionRef.current = null;
      startClock();

      try {
        if (!retrySession && slotState?.has_pending && !slotState.session_id) {
          throw new Error("Pending turn is missing its session ID");
        }
        const result = retrySession ? await retryNarrative(slot, retrySession) : await continueNarrative({
          slot,
          ...params,
          sessionId: slotState?.has_pending
            ? slotState.session_id ?? undefined
            : undefined,
        });
        if (activeSlotRef.current !== slot) return true;
        setFailedGeneration(null);
        sessionRef.current = result.session_id;
        submittingRef.current = false;
        recoverRef.current();
        // Continue accepts the previous draft before starting generation.
        // Refresh its frontier clock now, without waiting for the next draft.
        invalidateNarrativeQueries();
        return true;
      } catch (error) {
        if (activeSlotRef.current !== slot) return false;
        submittingRef.current = false;
        stopClock();
        phaseRef.current = null;
        setPhase(null);
        recoverRef.current();
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
        return false;
      }
    },
    [slot, slotState, startClock, stopClock, invalidateNarrativeQueries],
  );

  const submitTurn = useCallback(
    (params: { choice?: number; userText?: string }) => {
      if (failedGeneration && !slotState?.has_pending) return Promise.resolve(false);
      return submitRequest(params);
    }, [failedGeneration, slotState?.has_pending, submitRequest],
  );
  const retryGeneration = useCallback(() => {
    if (!failedGeneration || slotState?.has_pending) return Promise.resolve(false);
    return submitRequest({}, failedGeneration.session_id);
  }, [failedGeneration, slotState?.has_pending, submitRequest]);

  let skaldStatus: SkaldStatus = "READY";
  if (!backendReachable) {
    skaldStatus = "OFFLINE";
  } else if (receiving) {
    skaldStatus = "RECEIVING";
  } else if (
    phase === "writer" || phase === "gaia" || phase === "staging"
  ) {
    skaldStatus = "GENERATING";
  } else if (isActivePhase(phase)) {
    skaldStatus = "TRANSMITTING";

  }

  return {
    slotState,
    slotStateError: slotStateError ?? null,
    isSlotStateLoading,
    phase,
    skaldStatus,
    elapsedMs,
    generationError: generationError ?? recoverySettingsError?.message ?? null,
    failedGeneration,
    isRecoveryLoading,
    retryGeneration,
    isGenerating: isActivePhase(phase),
    completedGenerations,
    submitTurn,
  };
}
