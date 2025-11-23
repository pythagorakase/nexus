import { NarrativeChunk } from "@shared/schema";

export interface ChunkState {
  id: number;
  state: "draft" | "pending_review" | "finalized" | "embedded";
  finalized_at?: string;
  embedding_generated_at?: string;
  regeneration_count: number;
}

export interface AcceptChunkResponse {
  chunk_id: number;
  state: string;
  previous_chunk_embedded: boolean;
  embedding_job_id?: string;
}

export interface RejectChunkResponse {
  chunk_id: number;
  state: string;
  action_taken: string;
  regeneration_count?: number;
  edit_enabled: boolean;
}

export interface EditChunkInputResponse {
  previous_chunk_id: number;
  updated: boolean;
  new_generation_triggered: boolean;
}

export async function acceptChunk(chunkId: number, sessionId: string): Promise<AcceptChunkResponse> {
  const response = await fetch("/api/chunks/accept", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chunk_id: chunkId, session_id: sessionId }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "Failed to accept chunk");
  }

  return response.json();
}

export async function rejectChunk(
  chunkId: number,
  sessionId: string,
  action: "regenerate" | "edit_previous"
): Promise<RejectChunkResponse> {
  const response = await fetch("/api/chunks/reject", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chunk_id: chunkId,
      session_id: sessionId,
      action
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "Failed to reject chunk");
  }

  return response.json();
}

export async function editChunkInput(
  chunkId: number,
  newUserInput: string,
  sessionId: string
): Promise<EditChunkInputResponse> {
  const response = await fetch(`/api/chunks/${chunkId}/edit-user-input`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chunk_id: chunkId,
      new_user_input: newUserInput,
      session_id: sessionId
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "Failed to edit chunk input");
  }
  return response.json();
}

// New Story Wizard API
export async function startSetup(slot: number, model?: string): Promise<{ status: string; thread_id: string; slot: number }> {
  const response = await fetch("/api/story/new/setup/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slot, model }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function resumeSetup(slot: number): Promise<any> {
  const response = await fetch(`/api/story/new/setup/resume?slot=${slot}`);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function recordDrafts(data: {
  slot: number;
  setting?: any;
  character?: any;
  seed?: any;
  location?: any;
  base_timestamp?: string;
}): Promise<{ status: string; slot: number }> {
  const response = await fetch("/api/story/new/setup/record", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function resetSetup(slot: number): Promise<{ status: string; slot: number }> {
  const response = await fetch("/api/story/new/setup/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slot }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function selectSlot(slot: number): Promise<{ status: string; results: any }> {
  const response = await fetch("/api/story/new/slot/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slot }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function getSlotsStatus(): Promise<Array<{ slot: number; is_active: boolean; thread_id: string | null }>> {
  const response = await fetch("/api/story/new/slots");
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function getChunkStates(startId: number, endId: number): Promise<ChunkState[]> {
  const response = await fetch(`/api/chunks/states?start=${startId}&end=${endId}`);

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "Failed to get chunk states");
  }

  return response.json();
}
