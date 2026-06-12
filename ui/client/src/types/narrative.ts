/**
 * TypeScript types for the narrative reading surface.
 *
 * Mirrors the FastAPI Pydantic schemas in `nexus/api/narrative_schemas.py`
 * and the Express read routes in `ui/server/routes.ts`.
 */
import type { NarrativeChunk, ChunkMetadata } from "@shared/schema";

/** A committed chunk joined with its metadata row (Express read routes). */
export type ChunkWithMetadata = Omit<NarrativeChunk, "choiceObject"> & {
  choiceObject?: ChoiceObject | null;
  metadata?: ChunkMetadata;
};

/**
 * Choice object structure from the chunk / incubator JSONB column.
 * `presented`: choice strings from the storyteller.
 * `selected`: the user's recorded selection (after a choice is made).
 */
export interface ChoiceObject {
  presented: string[];
  selected?: ChoiceSelection;
}

/** Matches backend `ChoiceSelection` (label 0/freeform = custom input). */
export interface ChoiceSelection {
  label: number | "freeform";
  text: string;
  edited: boolean;
}

/** Response model for GET /api/slot/{slot}/state (SlotStateResponse). */
export interface SlotState {
  slot: number;
  is_empty: boolean;
  is_wizard_mode: boolean;
  phase: string | null;
  subphase: string | null;
  thread_id: string | null;
  current_chunk_id: number | null;
  has_pending: boolean;
  storyteller_text: string | null;
  choices: string[];
  session_id: string | null;
  model: string | null;
}

/** Response from POST /api/narrative/continue. */
export interface ContinueNarrativeResponse {
  session_id: string;
  status: string;
  message: string;
}

/** WebSocket progress payload from /ws/narrative. */
export interface NarrativeProgressPayload {
  session_id: string;
  status: string;
  message?: string;
  data?: {
    error?: string;
    phase?: string;
    [key: string]: unknown;
  };
}

export type NarrativePhase =
  | "initiated"
  | "loading_chunk"
  | "building_context"
  | "calling_llm"
  | "processing_response"
  | "complete"
  | "error";

/** Phases that indicate generation is actively in progress. */
export const ACTIVE_GENERATION_PHASES: NarrativePhase[] = [
  "initiated",
  "loading_chunk",
  "building_context",
  "calling_llm",
  "processing_response",
];

/**
 * Reader-facing labels for the active generation phases (telemetry rail and
 * in-reader status line). Plain language only - no internal module names.
 */
export const PHASE_LABELS: Partial<Record<NarrativePhase, string>> = {
  initiated: "Request received…",
  loading_chunk: "Loading scene…",
  building_context: "Assembling context…",
  calling_llm: "Writing…",
  processing_response: "Processing response…",
};

/** Operator-strip status derived from the generation phase. */
export type SkaldStatus =
  | "OFFLINE"
  | "READY"
  | "TRANSMITTING"
  | "GENERATING"
  | "RECEIVING";

/** GET /api/narrative/chunks/:chunkId/context (Express). */
export interface ChunkContext {
  characters: Array<{
    id: number;
    name: string;
    reference: "present" | "mentioned";
  }>;
  places: Array<{
    id: number;
    name: string;
    referenceType: "setting" | "mentioned" | "transit";
  }>;
}

/** GET /api/narrative/incubator (FastAPI incubator_view). */
export interface IncubatorPayload {
  chunk_id: number;
  parent_chunk_id: number;
  parent_chunk_text?: string | null;
  user_text?: string | null;
  storyteller_text?: string | null;
  choice_object?: ChoiceObject | null;
  episode_transition?: string | null;
  time_delta?: string | null;
  world_layer?: string | null;
  status?: string;
  session_id?: string;
  created_at?: string;
  /** Sentinel from the API when the incubator table is empty. */
  message?: string;
}
