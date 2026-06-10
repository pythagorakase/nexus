/**
 * RightLedger - the 320px Session Ledger rail (narrative tab only).
 *
 * Surfaces the generation phase stream + elapsed clock, the scene cast
 * (live chunk_character_references), and the narrative hierarchy
 * (seasons -> episodes -> chunks) in one place.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { DecoDivider } from "@/components/deco";
import {
  getChunkContext,
  getEpisodeChunks,
  getLatestChunk,
  getSeasons,
} from "@/lib/narrative-api";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import type { ChunkContext, ChunkWithMetadata, NarrativePhase } from "@/types/narrative";
import type { Season } from "@shared/schema";

const PHASES: Array<{ key: NarrativePhase; label: string }> = [
  { key: "initiated", label: "Request received…" },
  { key: "loading_chunk", label: "Loading parent chunk…" },
  { key: "building_context", label: "Assembling context package…" },
  { key: "calling_llm", label: "Calling LORE / LOGON…" },
  { key: "processing_response", label: "Processing response…" },
  { key: "complete", label: "Awaiting approval" },
];

interface RightLedgerProps {
  slot: number;
  engine: NarrativeEngine;
}

export function RightLedger({ slot, engine }: RightLedgerProps) {
  const { phase, elapsedMs, isGenerating, slotState } = engine;

  const { data: latestChunk } = useQuery<ChunkWithMetadata | null>({
    queryKey: ["/api/narrative/latest-chunk", slot],
    queryFn: () => getLatestChunk(slot),
  });

  const { data: chunkContext } = useQuery<ChunkContext>({
    queryKey: ["/api/narrative/chunks/context", latestChunk?.id, slot],
    queryFn: () => getChunkContext(latestChunk!.id, slot),
    enabled: !!latestChunk?.id,
  });

  const { data: seasons } = useQuery<Season[]>({
    queryKey: ["/api/narrative/seasons", slot],
    queryFn: () => getSeasons(slot),
  });

  const season = latestChunk?.metadata?.season ?? null;
  const episode = latestChunk?.metadata?.episode ?? null;

  const { data: episodeChunks } = useQuery<{
    chunks: ChunkWithMetadata[];
    total: number;
  }>({
    queryKey: ["/api/narrative/chunks", season, episode, slot],
    queryFn: () => getEpisodeChunks(season as number, episode as number, slot),
    enabled: season !== null && episode !== null,
  });

  // Phase index: -1 when idle (all rows dim); the "complete" row lights
  // while the engine holds the RECEIVING beat.
  const phaseIdx = phase ? PHASES.findIndex((p) => p.key === phase) : -1;
  const stripPct =
    phaseIdx >= 0 ? ((phaseIdx + 1) / PHASES.length) * 100 : 0;

  const cast = chunkContext?.characters ?? [];
  const currentChunkId = slotState?.has_pending
    ? null
    : slotState?.current_chunk_id ?? null;

  // Early stories may have chunk metadata before the seasons table is
  // populated (e.g. a season-0 prologue) - synthesize the current season
  // node so the hierarchy still renders.
  const seasonNodes: Array<{ id: number }> =
    seasons && seasons.length > 0
      ? seasons
      : season !== null
        ? [{ id: season }]
        : [];

  return (
    <aside className="rail-right" data-testid="session-ledger">
      {/* SESSION TELEMETRY */}
      <section className="ledger-section">
        <div className="ledger-head">
          <span className="eyebrow brass-glow">SESSION TELEMETRY</span>
          <span className="caption dim">
            {isGenerating ? "SKALD · LIVE" : "SKALD · IDLE"}
          </span>
        </div>
        <div className="phase-stream" data-testid="phase-stream">
          {PHASES.map((p, i) => (
            <div
              key={p.key}
              className={`phase-row ${phaseIdx >= 0 && i < phaseIdx ? "done" : ""} ${
                i === phaseIdx ? "active" : ""
              }`}
            >
              <span className="phase-glyph">
                {phaseIdx >= 0 && i < phaseIdx ? "✓" : i === phaseIdx ? "▸" : "·"}
              </span>
              <span className="phase-label">{p.label}</span>
            </div>
          ))}
        </div>
        {isGenerating && (
          <>
            <div className="phase-strip">
              <div className="phase-strip-bar" style={{ width: `${stripPct}%` }} />
            </div>
            <div className="phase-stat">
              <span className="caption">ELAPSED</span>
              <span className="phase-clock" data-testid="text-elapsed">
                {(elapsedMs / 1000).toFixed(1)}s
              </span>
            </div>
          </>
        )}
      </section>

      <DecoDivider variant="glyph" />

      {/* SCENE CAST */}
      <section className="ledger-section">
        <div className="ledger-head">
          <span className="eyebrow brass-glow">SCENE CAST</span>
          <span className="caption dim">
            {cast.filter((c) => c.reference === "present").length}
          </span>
        </div>
        <ul className="cast-list" data-testid="cast-list">
          {cast.length === 0 && (
            <li className="cast-row off">
              <span className="cast-glyph dim">·</span>
              <span className="cast-role">no references recorded</span>
            </li>
          )}
          {cast.map((member) => (
            <li
              key={member.id}
              className={`cast-row ${member.reference === "mentioned" ? "off" : ""}`}
            >
              <span className={`cast-glyph ${member.reference === "mentioned" ? "dim" : ""}`}>
                {member.name.charAt(0).toUpperCase()}
              </span>
              <span className="cast-name">{member.name}</span>
              <span className="cast-role">· {member.reference}</span>
            </li>
          ))}
        </ul>
      </section>

      <DecoDivider variant="glyph" />

      {/* NARRATIVE HIERARCHY */}
      <section className="ledger-section">
        <div className="ledger-head">
          <span className="eyebrow brass-glow">HIERARCHY</span>
          {season !== null && episode !== null && (
            <span className="caption dim">
              S{season}·E{episode}
            </span>
          )}
        </div>
        <ul className="hier-list" data-testid="hierarchy">
          {seasonNodes.map((s) => {
            const isOpen = s.id === season;
            return (
              <li key={s.id} className={`hier-season ${isOpen ? "open" : ""}`}>
                <div className="hier-row">
                  {isOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                  <span className="hier-label">SEASON {s.id}</span>
                </div>
                {isOpen && episode !== null && (
                  <ul>
                    <li className="hier-ep open">
                      <div className="hier-row">
                        <ChevronDown size={10} />
                        <span className="hier-label">Episode {episode}</span>
                      </div>
                      <ul>
                        {(episodeChunks?.chunks ?? []).map((chunk) => {
                          const m = chunk.metadata;
                          return (
                            <li
                              key={chunk.id}
                              className={`hier-chunk ${
                                chunk.id === currentChunkId ? "current" : ""
                              }`}
                            >
                              <span className="hier-coord">
                                S{m?.season ?? 0}·E{m?.episode ?? 0}·S{m?.scene ?? 0}
                              </span>
                              <span className="hier-slug">
                                {m?.slug ?? `chunk ${chunk.id}`}
                              </span>
                            </li>
                          );
                        })}
                        {slotState?.has_pending && (
                          <li className="hier-chunk current">
                            <span className="hier-coord">PENDING</span>
                            <span className="hier-slug">awaiting response</span>
                          </li>
                        )}
                      </ul>
                    </li>
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </aside>
  );
}
