/**
 * Pure logic for the reader's story navigation.
 *
 * The reading model is a ladder of positions in story (chunk-id) order with
 * the live frontier as the top rung:
 *
 *   chunk 1  <->  ...  <->  latest committed chunk  <->  LIVE
 *
 * "LIVE" is the normal reading surface (current episode stream, pending
 * chunk, input affordances). Every other rung is a single committed chunk
 * displayed read-only ("historical" mode). Navigation is symmetric: one
 * step back then one step forward always returns to the starting position.
 *
 * When the slot has a pending (incubator) chunk, the live position sits one
 * step past the latest committed chunk, so stepping back from live lands ON
 * the latest committed chunk. Without a pending chunk the live surface
 * already ends at the latest committed chunk, so stepping back lands on the
 * one before it.
 *
 * In the legacy and modern corpora alike, `scene` is 1:1 with chunk
 * (verified against save_01: every episode has exactly as many scenes as
 * chunks), so chunk-by-chunk stepping IS scene-by-scene stepping; the tree
 * provides direct jumps.
 */

/**
 * One committed chunk's coordinates, in story order. Client-side mirror of
 * the GET /api/narrative/outline payload (`nexus/api/reader_endpoints.py`);
 * keep the two in lockstep if the outline ever gains a column.
 */
export interface OutlineRow {
  id: number;
  season: number | null;
  episode: number | null;
  scene: number | null;
  slug: string | null;
}

export interface OutlineEpisode {
  season: number;
  episode: number;
  chunks: OutlineRow[];
}

export interface OutlineSeason {
  season: number;
  episodes: OutlineEpisode[];
}

/**
 * Group flat outline rows into season -> episode -> chunk nodes.
 * Rows arrive in story (chunk-id) order; grouping preserves it. A season or
 * episode that reappears later in story order (e.g. interleaved world
 * layers) folds into its existing node.
 */
export function buildOutlineTree(rows: OutlineRow[]): OutlineSeason[] {
  const seasons: OutlineSeason[] = [];
  const seasonIndex = new Map<number, OutlineSeason>();
  const episodeIndex = new Map<string, OutlineEpisode>();

  for (const row of rows) {
    const s = row.season ?? 0;
    const e = row.episode ?? 0;

    let seasonNode = seasonIndex.get(s);
    if (!seasonNode) {
      seasonNode = { season: s, episodes: [] };
      seasonIndex.set(s, seasonNode);
      seasons.push(seasonNode);
    }

    const epKey = `${s}:${e}`;
    let episodeNode = episodeIndex.get(epKey);
    if (!episodeNode) {
      episodeNode = { season: s, episode: e, chunks: [] };
      episodeIndex.set(epKey, episodeNode);
      seasonNode.episodes.push(episodeNode);
    }

    episodeNode.chunks.push(row);
  }

  return seasons;
}

/**
 * A navigation target: a chunk id (historical), "live" (return to the
 * frontier), or null (no step available - control disabled).
 */
export type NavTarget = number | "live" | null;

export interface ReaderNav {
  back: NavTarget;
  forward: NavTarget;
}

/**
 * Resolve the back/forward targets for the current reading position.
 *
 * @param readingChunkId null = live frontier; otherwise the historical chunk
 * @param outlineIds     committed chunk ids in story order
 * @param hasPending     whether an unapproved (incubator) chunk exists
 */
export function resolveReaderNav(args: {
  readingChunkId: number | null;
  outlineIds: number[];
  hasPending: boolean;
}): ReaderNav {
  const { readingChunkId, outlineIds, hasPending } = args;
  const latest =
    outlineIds.length > 0 ? outlineIds[outlineIds.length - 1] : null;

  if (readingChunkId === null) {
    // Live frontier: forward never exists. Back steps to the chunk one
    // before the live position (see module doc).
    if (latest === null) return { back: null, forward: null };
    if (hasPending) return { back: latest, forward: null };
    const beforeLatest =
      outlineIds.length > 1 ? outlineIds[outlineIds.length - 2] : null;
    return { back: beforeLatest, forward: null };
  }

  const idx = outlineIds.indexOf(readingChunkId);
  if (idx === -1) {
    // Outline and reading position disagree (transient while queries
    // settle): keep controls inert rather than guessing.
    return { back: null, forward: null };
  }

  const back = idx > 0 ? outlineIds[idx - 1] : null;

  if (idx === outlineIds.length - 1) {
    // Reading the latest committed chunk - only one step from live.
    return { back, forward: "live" };
  }

  const nextId = outlineIds[idx + 1];
  const forward: NavTarget =
    nextId === latest && !hasPending ? "live" : nextId;
  return { back, forward };
}

/**
 * The tree row that represents the live frontier. With a pending chunk the
 * frontier is the pending row itself; otherwise it is the latest committed
 * chunk's row (clicking it restores the live reading surface).
 */
export function isLiveRow(
  chunkId: number,
  outlineIds: number[],
  hasPending: boolean,
): boolean {
  if (hasPending) return false;
  return (
    outlineIds.length > 0 && chunkId === outlineIds[outlineIds.length - 1]
  );
}

/**
 * Freeform-input presentation (slot 0 of the choice block).
 *
 * With structured choices the input is the "...or something else" escape
 * hatch. Without them (legacy unstructured chunks, prose-presented choices)
 * the input IS the turn affordance: no placeholder, preemptively focused so
 * the blinking caret invites typing.
 */
export function freeformPresentation(choiceCount: number): {
  placeholder: string | undefined;
  autoFocus: boolean;
} {
  if (choiceCount > 0) {
    return { placeholder: "…or something else", autoFocus: false };
  }
  return { placeholder: undefined, autoFocus: true };
}
