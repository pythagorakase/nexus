/**
 * Typed fetchers for the narrative reading surface.
 *
 * Read routes are served by the Express layer (direct Postgres);
 * generation/slot routes are proxied through Express to FastAPI :8002.
 * Errors surface as thrown exceptions — no silent fallbacks.
 */
import type { Season, Episode, Character, CharacterImage } from "@shared/schema";
import type {
  ChunkContext,
  ChunkWithMetadata,
  ContinueNarrativeResponse,
  IncubatorPayload,
  SlotState,
} from "@/types/narrative";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const text = (await res.text()) || res.statusText;
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export function getSlotState(slot: number): Promise<SlotState> {
  return getJson(`/api/slot/${slot}/state`);
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

export function getCharacters(slot: number): Promise<Character[]> {
  return getJson(`/api/characters?slot=${slot}`);
}

export function getCharacterImages(
  characterId: number,
  slot: number,
): Promise<CharacterImage[]> {
  return getJson(`/api/characters/${characterId}/images?slot=${slot}`);
}

export function getUserCharacter(slot: number): Promise<{ name: string } | null> {
  return getJson(`/api/user-character?slot=${slot}`);
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
}): Promise<ContinueNarrativeResponse> {
  const body: Record<string, unknown> = { slot: params.slot };
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
