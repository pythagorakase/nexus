/**
 * TypeScript types for the narrative reading surface.
 *
 * Mirrors the FastAPI Pydantic schemas in `nexus/api/narrative_schemas.py`
 * and the gateway read routes in `nexus/api/reader_endpoints.py`.
 */
import type { NarrativeChunk, ChunkMetadata } from "@shared/schema";

/** A committed chunk joined with its metadata row (gateway read routes). */
export type ChunkWithMetadata = Omit<NarrativeChunk, "choiceObject"> & {
  choiceObject?: ChoiceObject | null;
  hasInlineSceneMarkup: boolean;
  metadata?: ChunkMetadata & { worldTime: string | null; worldTimeFace: string | null };
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

/** The server-formatted clock of the latest accepted playable chunk. */
export interface FrontierClock {
  instant: string;
  face: string;
}

/** Response model for GET /api/slot/{slot}/state (SlotStateResponse). */
export interface GenerationSettings {
  request_timeout_seconds: number;
  poll_interval_seconds: number;
  wake_gap_threshold_seconds: number;
  stale_lease_timeout_seconds: number;
}

export interface GenerationSession {
  slot: number;
  session_id: string;
  status: "initiated" | "complete" | "error";
  phase: NarrativePhase;
  terminal_outcome: "accepted" | "superseded" | "error" | null;
  replaced_by_session_id: string | null;
  chunk_id: number | null;
  created_at: string;
  heartbeat_at: string;
  expires_at: string | null;
  error: string | null;
  error_class: string | null;
}

export interface SlotState {
  narrative_generation: GenerationSettings;
  slot: number;
  is_empty: boolean;
  is_wizard_mode: boolean;
  phase: string | null;
  subphase: string | null;
  thread_id: string | null;
  current_chunk_id: number | null;
  has_pending: boolean;
  frontier_clock: FrontierClock | null;
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
  slot: number;
  session_id: string;
  status: string;
  message?: string;
  data?: {
    error?: string;
    phase?: string;
    [key: string]: unknown;
  };
}

/** The durable phase order, shown once in the reader's progress ledger. */
export const GENERATION_PHASES = [
  "retrieval", "assembly", "writer", "gaia", "staging", "complete",
] as const;
export type DurableNarrativePhase = typeof GENERATION_PHASES[number];
export const LEGACY_GENERATION_PHASES = {
  initiated: "retrieval",
  loading_chunk: "retrieval",
  building_context: "assembly",
  calling_llm: "writer",
  processing_response: "staging",
} as const;
export type NarrativePhase = DurableNarrativePhase | "error";

/** Normalize older wire names at the parsing boundary, never in the ledger. */
export function parseNarrativePhase(phase: string): NarrativePhase {
  if (phase in LEGACY_GENERATION_PHASES) {
    return LEGACY_GENERATION_PHASES[phase as keyof typeof LEGACY_GENERATION_PHASES];
  }
  if (phase === "error" || GENERATION_PHASES.includes(phase as DurableNarrativePhase)) {
    return phase as NarrativePhase;
  }
  throw new Error(`Unknown generation phase: ${phase}`);
}

export const ACTIVE_GENERATION_PHASES: readonly NarrativePhase[] =
  GENERATION_PHASES.filter((phase) => phase !== "complete");

/**
 * Reader-facing labels for the active generation phases (telemetry rail and
 * in-reader status line). Plain language only - no internal module names.
 */
export const PHASE_LABELS: Partial<Record<NarrativePhase, string>> = {
  retrieval: "Loading context…",
  assembly: "Assembling context…",
  writer: "Writing…",
  gaia: "Updating the world…",
  staging: "Preparing scene…",
  complete: "Complete",
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
  chunk_id: number | null;
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
