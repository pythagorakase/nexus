/**
 * TypeScript types for narrative generation and incubator data.
 * Replaces `any` types with properly structured interfaces.
 */

export interface EntityChange {
  id: number;
  name: string;
  changeType: 'created' | 'updated' | 'mentioned' | 'removed';
  description?: string;
  category?: string;
}

export interface EntityChanges {
  characters?: EntityChange[];
  locations?: EntityChange[];
  places?: EntityChange[];
  events?: EntityChange[];
  threats?: EntityChange[];
  relationships?: EntityChange[];
  factions?: EntityChange[];
}

export interface ReferenceUpdate {
  chunkId: number;
  entityId: number;
  entityType: string;
  referenceType?: string;
}

/**
 * Choice object structure from incubator JSONB column.
 * presented: Array of choice strings from Skald
 * selected: User's selection (populated after choice is made)
 */
export interface IncubatorChoiceObject {
  presented: string[];
  selected?: {
    label: number | "freeform";
    text: string;
    edited: boolean;
  };
}

export interface IncubatorViewPayload {
  chunk_id: number;
  parent_chunk_id: number;
  parent_chunk_text?: string | null;
  user_text?: string | null;
  storyteller_text?: string | null;
  choice_object?: IncubatorChoiceObject | null;
  episode_transition?: string | null;
  time_delta?: string | null;
  world_layer?: string | null;
  pacing?: string | null;
  entity_update_count?: number;
  entity_changes?: EntityChanges;
  references?: ReferenceUpdate[];
  status?: string;
  session_id?: string;
  created_at?: string;
}

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
