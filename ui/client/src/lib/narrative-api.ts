/**
 * Typed fetchers for the narrative reading surface.
 *
 * All routes are served by the FastAPI gateway — the single origin for
 * reads, generation, slots, and websockets (issue #396). In dev, the Vite
 * server proxies these paths to the gateway.
 * Errors surface as thrown exceptions — no silent fallbacks.
 */
import type {
  Season,
  Episode,
  CharacterImage,
  CharacterListEntry,
  CurrentPlace,
  Place,
  PlaceImage,
  Zone,
} from "@shared/schema";
import type {
  ChunkContext,
  ChunkWithMetadata,
  ContinueNarrativeResponse,
  GenerationSession,
  GenerationSettings,
  IncubatorPayload,
  SlotState,
} from "@/types/narrative";
import { parseNarrativePhase } from "@/types/narrative";
import type { OutlineRow } from "@/lib/narrative-nav";

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await (signal ? fetch(url, { signal }) : fetch(url));
  if (!res.ok) {
    const text = (await res.text()) || res.statusText;
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export function getSlotState(slot: number, signal?: AbortSignal): Promise<SlotState> {
  return getJson(`/api/slot/${slot}/state`, signal);
}

/** Returns null when the slot has no committed chunks yet (404 = new story). */
export async function getLatestChunk(slot: number): Promise<ChunkWithMetadata | null> {
  const res = await fetch(`/api/narrative/latest-chunk?slot=${slot}`);
  if (res.status === 404) return null;
  if (!res.ok) {
    const text = (await res.text()) || res.statusText;
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export function getSeasons(slot: number): Promise<Season[]> {
  return getJson(`/api/narrative/seasons?slot=${slot}`);
}

export function getEpisodes(seasonId: number, slot: number): Promise<Episode[]> {
  return getJson(`/api/narrative/episodes/${seasonId}?slot=${slot}`);
}

export function getEpisodeChunks(
  seasonId: number,
  episodeId: number,
  slot: number,
  limit = 200,
): Promise<{ chunks: ChunkWithMetadata[]; total: number }> {
  return getJson(
    `/api/narrative/chunks/${seasonId}/${episodeId}?limit=${limit}&slot=${slot}`,
  );
}

export function getChunkContext(chunkId: number, slot: number): Promise<ChunkContext> {
  return getJson(`/api/narrative/chunks/${chunkId}/context?slot=${slot}`);
}

/** Story outline: one row per committed chunk, story order. */
export function getOutline(slot: number): Promise<OutlineRow[]> {
  return getJson(`/api/narrative/outline?slot=${slot}`);
}

/** A single committed chunk (with metadata) for historical reading. */
export function getChunk(chunkId: number, slot: number): Promise<ChunkWithMetadata> {
  return getJson(`/api/narrative/chunks/${chunkId}?slot=${slot}`);
}

export function getCharacters(slot: number): Promise<CharacterListEntry[]> {
  return getJson(`/api/characters?slot=${slot}`);
}

export function getCharacterImages(
  characterId: number,
  slot: number,
): Promise<CharacterImage[]> {
  return getJson(`/api/characters/${characterId}/images?slot=${slot}`);
}

export async function uploadCharacterPortrait(
  characterId: number,
  slot: number,
  file: File,
): Promise<CharacterImage> {
  const form = new FormData();
  form.append("images", file);
  const res = await fetch(`/api/characters/${characterId}/images?slot=${slot}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const text = (await res.text()) || res.statusText;
    throw new Error(`${res.status}: ${text}`);
  }
  const data: { images: CharacterImage[] } = await res.json();
  if (!data.images?.length) {
    throw new Error("Upload returned no image record");
  }
  return data.images[0];
}

export async function setMainCharacterImage(
  characterId: number,
  imageId: number,
  slot: number,
): Promise<void> {
  const res = await fetch(
    `/api/characters/${characterId}/images/${imageId}/main?slot=${slot}`,
    { method: "PUT" },
  );
  if (!res.ok) {
    const text = (await res.text()) || res.statusText;
    throw new Error(`${res.status}: ${text}`);
  }
}

export function getUserCharacter(slot: number): Promise<{ name: string } | null> {
  return getJson(`/api/user-character?slot=${slot}`);
}

/** Slot-qualified query string; the map tab is reachable without a bound slot. */
function slotQuery(slot: number | null): string {
  return slot === null ? "" : `?slot=${slot}`;
}

export function getPlaces(slot: number | null): Promise<Place[]> {
  return getJson(`/api/places${slotQuery(slot)}`);
}

export function getZones(slot: number | null): Promise<Zone[]> {
  return getJson(`/api/zones${slotQuery(slot)}`);
}

export function getPlaceImages(
  placeId: number,
  slot: number | null,
): Promise<PlaceImage[]> {
  return getJson(`/api/places/${placeId}/images${slotQuery(slot)}`);
}

/** All historical settings; empty when none have been recorded (404). */
export async function getCurrentPlace(
  slot: number | null,
): Promise<CurrentPlace[]> {
  const res = await fetch(`/api/current-place${slotQuery(slot)}`);
  if (res.status === 404) return [];
  if (!res.ok) {
    const text = (await res.text()) || res.statusText;
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export function getIncubator(slot: number): Promise<IncubatorPayload> {
  return getJson(`/api/narrative/incubator?slot=${slot}`);
}

/**
 * Submit a player turn through the unified continue endpoint.
 *
 * The backend resolves the current chunk from slot state, records the
 * player's response on the pending chunk (auto-approving incubator content),
 * and kicks off generation of the next chunk. Exactly one of `choice`
 * (1-indexed) or `userText` (freeform, slot 0) should be provided.
 */
export async function continueNarrative(params: {
  slot: number;
  choice?: number;
  userText?: string;
  sessionId?: string;
}): Promise<ContinueNarrativeResponse> {
  const body: Record<string, unknown> = { slot: params.slot };
  if (params.sessionId !== undefined) body.session_id = params.sessionId;
  if (params.choice !== undefined) body.choice = params.choice;
  if (params.userText !== undefined) body.user_text = params.userText;

  const res = await fetch("/api/narrative/continue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = (await res.text()) || res.statusText;
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

/** Deliberately retry one durable failure; the server fences stale attempts. */
export async function retryNarrative(slot: number, expectedSessionId: string): Promise<ContinueNarrativeResponse> {
  const res = await fetch("/api/narrative/retry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slot, expected_session_id: expectedSessionId }),
  });
  if (!res.ok) throw new Error(`${res.status}: ${(await res.text()) || res.statusText}`);
  return res.json();
}

/** Bootstrap timing independently of slot/database reads. */
export function getRecoveryPreferences(signal: AbortSignal): Promise<{ narrative_generation: GenerationSettings }> {
  return getJson("/api/preferences", signal);
}

/** Discover even a generation that completed while the reader was disconnected. */
export async function getActiveGeneration(slot: number, signal: AbortSignal): Promise<GenerationSession | null> {
  const state = await getJson<GenerationSession | null>(`/api/narrative/active?slot=${slot}`, signal);
  return state ? { ...state, phase: parseNarrativePhase(state.phase) } : null;
}

export async function getGenerationStatus(slot: number, session: string, signal: AbortSignal): Promise<GenerationSession> {
  const state = await getJson<GenerationSession>(`/api/narrative/status/${encodeURIComponent(session)}?slot=${slot}`, signal);
  return { ...state, phase: parseNarrativePhase(state.phase) };
}

/**
 * Wizard-time Retrograde stages in pipeline order: RETROGRADE_WIZARD_STAGES
 * in nexus/agents/orrery/retrograde_orchestrator.py, less its terminal "done".
 */
export const RETROGRADE_STAGES = [
  "packet",
  "seed_candidates",
  "expansion",
  "persistence",
  "embedding",
] as const;
export type RetrogradeStage = (typeof RETROGRADE_STAGES)[number];

/** One stage transition recorded by the gateway during a transition run. */
export interface RetrogradeStageRecord {
  stage: RetrogradeStage | "done" | "failed";
  at: string;
  detail: Record<string, unknown>;
}

interface RetrogradeStatusRecord {
  /**
   * The transition run that owns this record; null before any run in this
   * gateway process. Each run starts a record under a new identity.
   */
  run: string | null;
  stages: RetrogradeStageRecord[];
  /** nexus.toml [orrery.retrograde.wizard] status_poll_interval_seconds. */
  status_poll_interval_seconds: number;
}

/**
 * GET /api/story/new/retrograde/status. "idle" means the run has recorded no
 * stage yet (or no run has started); "failed" names the stage that failed
 * in detail.stage.
 */
export type RetrogradeStatus = RetrogradeStatusRecord &
  (
    | { stage: "idle" }
    | { stage: RetrogradeStage | "done"; detail: Record<string, unknown> }
    | {
        stage: "failed";
        detail: Record<string, unknown> & { stage: RetrogradeStage };
      }
  );

const RETROGRADE_STATUS_STAGES: readonly string[] = [
  ...RETROGRADE_STAGES,
  "done",
  "failed",
  "idle",
];

/**
 * Read a slot's Retrograde record: the run that owns it, its stage, and the
 * interval to read it at (a player route, unlike GET /api/settings).
 */
export async function getRetrogradeStatus(
  slot: number,
  signal?: AbortSignal,
): Promise<RetrogradeStatus> {
  const status = await getJson<RetrogradeStatus>(
    `/api/story/new/retrograde/status?slot=${slot}`,
    signal,
  );
  if (
    !RETROGRADE_STATUS_STAGES.includes(status?.stage) ||
    !Array.isArray(status.stages) ||
    !(typeof status.run === "string" || status.run === null)
  ) {
    throw new Error(`Unrecognized Retrograde status: ${JSON.stringify(status)}`);
  }
  if (
    status.stage === "failed" &&
    !(RETROGRADE_STAGES as readonly unknown[]).includes(status.detail?.stage)
  ) {
    throw new Error(`Retrograde failure names no known stage: ${JSON.stringify(status.detail)}`);
  }
  const seconds: unknown = status.status_poll_interval_seconds;
  if (typeof seconds !== "number" || !(seconds > 0)) {
    throw new Error(
      "nexus.toml [orrery.retrograde.wizard] status_poll_interval_seconds must be a positive number",
    );
  }
  return status;
}

/**
 * The pipeline stage a status places the run at: the stage in progress, or
 * the stage that failed. Null while idle and once done.
 */
export function retrogradeStageOf(status: RetrogradeStatus): RetrogradeStage | null {
  if (status.stage === "idle" || status.stage === "done") return null;
  return status.stage === "failed" ? status.detail.stage : status.stage;
}
