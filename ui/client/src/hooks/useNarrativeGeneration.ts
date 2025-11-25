/**
 * Custom hook for managing narrative generation lifecycle.
 *
 * Encapsulates:
 * - WebSocket connection for real-time progress updates
 * - Narrative session state management
 * - Incubator data fetching and approval flow
 * - Timer management for elapsed time tracking
 * - Error handling and recovery
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { ChunkWithMetadata } from "../components/NarrativeTab";
import type { IncubatorViewPayload, NarrativeProgressPayload, NarrativePhase } from "../types/narrative";
import { toast } from "./use-toast";

interface UseNarrativeGenerationOptions {
  onPhaseChange?: (phase: NarrativePhase | null) => void;
  onComplete?: () => void;
  onError?: () => void;
  allowedChunkId?: number | null;
  slot?: number | null;
}

export function useNarrativeGeneration(options: UseNarrativeGenerationOptions = {}) {
  const { onPhaseChange, onComplete, onError, allowedChunkId = null, slot = null } = options;
  const queryClient = useQueryClient();

  const withSlot = useCallback(
    (path: string) => {
      if (!slot) return path;
      const separator = path.includes("?") ? "&" : "?";
      return `${path}${separator}slot=${slot}`;
    },
    [slot],
  );

  // Session state
  const [activeNarrativeSession, setActiveNarrativeSession] = useState<string | null>(null);
  const activeNarrativeSessionRef = useRef<string | null>(null);
  const [narrativePhase, setNarrativePhase] = useState<NarrativePhase | null>(null);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [lastUserInput, setLastUserInput] = useState<string>("Continue.");
  const [generationParentChunk, setGenerationParentChunk] = useState<ChunkWithMetadata | null>(null);

  // Incubator and approval state
  const [incubatorData, setIncubatorData] = useState<IncubatorViewPayload | null>(null);
  const [showApprovalModal, setShowApprovalModal] = useState(false);

  // Timer state
  const [elapsedMs, setElapsedMs] = useState(0);
  const elapsedTimerRef = useRef<number | null>(null);

  // WebSocket state
  const narrativeStreamRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isMountedRef = useRef(true);

  // Sync activeNarrativeSession with ref for closure stability
  useEffect(() => {
    activeNarrativeSessionRef.current = activeNarrativeSession;
  }, [activeNarrativeSession]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      stopElapsedTimer();
      if (reconnectTimeoutRef.current !== null) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (narrativeStreamRef.current) {
        narrativeStreamRef.current.close();
        narrativeStreamRef.current = null;
      }
    };
  }, []);

  const stopElapsedTimer = useCallback(() => {
    if (elapsedTimerRef.current !== null) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  }, []);

  const startElapsedTimer = useCallback(
    (startTime: number) => {
      stopElapsedTimer();
      setElapsedMs(0);
      elapsedTimerRef.current = window.setInterval(() => {
        setElapsedMs(Date.now() - startTime);
      }, 500); // Update every 500ms
    },
    [stopElapsedTimer],
  );

  const fetchIncubatorData = useCallback(async () => {
    try {
      const response = await fetch(withSlot("/api/narrative/incubator"));
      if (!response.ok) {
        const message = (await response.text()) || "Failed to load incubator contents";
        throw new Error(message);
      }
      const payload = await response.json();
      if (payload?.message === "Incubator is empty") {
        setIncubatorData(null);
        return;
      }
      setIncubatorData(payload as IncubatorViewPayload);
      setShowApprovalModal(true);
    } catch (error) {
      console.error("Unable to load incubator data:", error);
      setGenerationError(error instanceof Error ? error.message : "Unable to load incubator");
    }
  }, [withSlot]);

  const handleNarrativeProgress = useCallback(
    (payload: NarrativeProgressPayload) => {
      if (!payload || typeof payload !== "object") {
        return;
      }

      const sessionId = payload.session_id;
      const phase = payload.status as NarrativePhase;

      if (!sessionId || !phase) {
        return;
      }

      // Ignore updates for other sessions
      if (activeNarrativeSessionRef.current && activeNarrativeSessionRef.current !== sessionId) {
        console.warn(
          `[NarrativeProgress] Ignoring update from session ${sessionId}, active session is ${activeNarrativeSessionRef.current}`,
        );
        return;
      }

      if (!activeNarrativeSessionRef.current) {
        setActiveNarrativeSession(sessionId);
      }

      setNarrativePhase(phase);
      setGenerationError(null);
      onPhaseChange?.(phase);

      if (phase === "complete") {
        stopElapsedTimer();
        fetchIncubatorData();
        onComplete?.();
      } else if (phase === "error") {
        stopElapsedTimer();
        const errorMessage = (payload.data?.error as string) || "Narrative generation failed";
        setGenerationError(errorMessage);
        setShowApprovalModal(false);
        setActiveNarrativeSession(null);
        setGenerationParentChunk(null);
        onError?.();
      }
    },
    [fetchIncubatorData, onPhaseChange, onComplete, onError, stopElapsedTimer],
  );

  // WebSocket connection setup
  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const websocketUrl = `${protocol}//${window.location.host}/ws/narrative`;

    const connectWebSocket = () => {
      if (!isMountedRef.current) return;

      const ws = new WebSocket(websocketUrl);
      narrativeStreamRef.current = ws;

      ws.onopen = () => {
        console.log("[NarrativeWS] Connected");
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          handleNarrativeProgress(payload);
        } catch (error) {
          console.error("[NarrativeWS] Failed to parse message:", error);
        }
      };

      ws.onerror = (error) => {
        console.error("[NarrativeWS] Error:", error);
      };

      ws.onclose = () => {
        console.log("[NarrativeWS] Disconnected");
        narrativeStreamRef.current = null;
        // Attempt reconnection after delay if still mounted
        if (isMountedRef.current) {
          reconnectTimeoutRef.current = window.setTimeout(connectWebSocket, 3000);
        }
      };
    };

    connectWebSocket();

    return () => {
      if (reconnectTimeoutRef.current !== null) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (narrativeStreamRef.current) {
        narrativeStreamRef.current.close();
      }
    };
  }, [handleNarrativeProgress]);

  const triggerNarrativeTurn = useCallback(
    async (selectedChunk: ChunkWithMetadata | null, userInput: string = "Continue.") => {
      if (!selectedChunk) {
        toast({
          title: "Select a chunk",
          description: "Choose the current narrative chunk before continuing.",
        });
        return;
      }

      // Rollout guard - caller passes the latest chunk id; avoid continuing stale chunks
      if (allowedChunkId === null || allowedChunkId === undefined) {
        toast({
          title: "Latest chunk unavailable",
          description: "Cannot continue until the latest chunk is loaded.",
          variant: "destructive",
        });
        return;
      }

      if (selectedChunk.id !== allowedChunkId) {
        toast({
          title: "Continue latest chunk",
          description: `Continue is limited to the newest chunk (${allowedChunkId}).`,
          variant: "destructive",
        });
        return;
      }

      // Prevent concurrent generations
      if (
        activeNarrativeSessionRef.current &&
        ["initiated", "loading_chunk", "building_context", "calling_llm", "processing_response"].includes(
          narrativePhase ?? "",
        )
      ) {
        toast({
          title: "Generation in progress",
          description: "Wait for the current turn to finish or cancel before starting another.",
        });
        return;
      }

      const trimmedInput = userInput.trim() || "Continue.";
      setLastUserInput(trimmedInput);
      setGenerationParentChunk(selectedChunk);
      setNarrativePhase("initiated");
      setGenerationError(null);
      setIncubatorData(null);
      setShowApprovalModal(false);
      setActiveNarrativeSession(null);

      const startedAt = Date.now();
      startElapsedTimer(startedAt);
      onPhaseChange?.("initiated");

      try {
        const response = await fetch(withSlot("/api/narrative/continue"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chunk_id: selectedChunk.id,
            user_text: trimmedInput,
          }),
        });

        if (!response.ok) {
          const error = await response.text();
          throw new Error(error || "Failed to start narrative turn");
        }

        const result = await response.json();
        setActiveNarrativeSession(result.session_id);

        toast({
          title: "Generation started",
          description: `Session ${result.session_id.substring(0, 8)}... initiated`,
        });
      } catch (error) {
        stopElapsedTimer();
        const errorMessage = error instanceof Error ? error.message : "Failed to start narrative turn";
        setGenerationError(errorMessage);
        setNarrativePhase("error");
        onPhaseChange?.(null);
        onError?.();

        toast({
          title: "Generation failed",
          description: errorMessage,
          variant: "destructive",
        });
      }
    },
    [allowedChunkId, narrativePhase, onPhaseChange, onError, startElapsedTimer, stopElapsedTimer, withSlot],
  );

  const handleApprove = useCallback(async () => {
    if (!activeNarrativeSessionRef.current) {
      toast({
        title: "No active session",
        description: "Cannot approve without an active generation session.",
        variant: "destructive",
      });
      return;
    }

    try {
      const response = await fetch(withSlot(`/api/narrative/approve/${activeNarrativeSessionRef.current}`), {
        method: "POST",
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(error || "Failed to approve narrative");
      }

      toast({
        title: "Narrative approved",
        description: "The generated narrative has been committed to the database.",
      });

      // Ensure dependent data reflects the newly committed chunk
      queryClient.invalidateQueries({ queryKey: ["/api/narrative/latest-chunk", slot ?? null] });
      queryClient.invalidateQueries({
        predicate: (query) => Array.isArray(query.queryKey) && query.queryKey[0] === "/api/narrative/chunks",
      });

      setShowApprovalModal(false);
      setIncubatorData(null);
      setActiveNarrativeSession(null);
      setNarrativePhase(null);
      setGenerationParentChunk(null);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Failed to approve narrative";
      toast({
        title: "Approval failed",
        description: errorMessage,
        variant: "destructive",
      });
    }
  }, [queryClient, slot, withSlot]);

  const handleRegenerate = useCallback(() => {
    if (!generationParentChunk) {
      toast({
        title: "Cannot regenerate",
        description: "Parent chunk information is missing.",
        variant: "destructive",
      });
      return;
    }

    setShowApprovalModal(false);
    setIncubatorData(null);
    setActiveNarrativeSession(null);

    // Trigger new generation with same parent and user input
    triggerNarrativeTurn(generationParentChunk, lastUserInput);
  }, [generationParentChunk, lastUserInput, triggerNarrativeTurn]);

  const handleCancel = useCallback(() => {
    setShowApprovalModal(false);
    setIncubatorData(null);
    setActiveNarrativeSession(null);
    setNarrativePhase(null);
    setGenerationError(null);
    setGenerationParentChunk(null);
    stopElapsedTimer();
  }, [stopElapsedTimer]);

  return {
    // State
    activeNarrativeSession,
    narrativePhase,
    generationError,
    lastUserInput,
    generationParentChunk,
    incubatorData,
    showApprovalModal,
    elapsedMs,

    // Actions
    triggerNarrativeTurn,
    handleApprove,
    handleRegenerate,
    handleCancel,
    fetchIncubatorData,

    // Computed
    isMidGeneration: ["initiated", "loading_chunk", "building_context", "calling_llm", "processing_response"].includes(
      narrativePhase ?? "",
    ),
  };
}
