/**
 * RightLedger - the 320px right rail (narrative tab only).
 *
 * Two things live here, both unlabeled (self-evident per the visual
 * minimalism doctrine):
 * - generation telemetry: the phase stream + progress strip + elapsed clock,
 *   rendered ONLY while a generation request is actually in flight (keyed
 *   off the websocket phase signal) - it vanishes entirely when idle;
 * - the story tree: season -> episode -> scene(chunk) slugs, expandable and
 *   clickable. Clicking an older scene loads it in the reader (read-only);
 *   the live frontier row is highlighted and clicking it restores the
 *   normal reading surface with its input affordances.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { getOutline } from "@/lib/narrative-api";
import {
  buildOutlineTree,
  isLiveRow,
  type OutlineRow,
} from "@/lib/narrative-nav";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import {
  ACTIVE_GENERATION_PHASES,
  PHASE_LABELS,
  type NarrativePhase,
} from "@/types/narrative";

interface RightLedgerProps {
  slot: number;
  engine: NarrativeEngine;
  /** null = live frontier; a chunk id = historical reading. */
  readingChunkId: number | null;
  /** Navigate the reading position (null returns to the live frontier). */
  onNavigate: (chunkId: number | null) => void;
}

/** Build a player-facing scene label without exposing the storage PK. */
export function outlineSceneLabel(row: OutlineRow, episodeOrder: number): string {
  const slug = row.slug?.trim();
  if (slug) return slug;
  if (row.scene !== null) return `Scene ${row.scene}`;
  return `Scene ${episodeOrder}`;
}

export function RightLedger({
  slot,
  engine,
  readingChunkId,
  onNavigate,
}: RightLedgerProps) {
  const { phase, elapsedMs, isGenerating, slotState } = engine;

  const { data: outline } = useQuery<OutlineRow[]>({
    queryKey: ["/api/narrative/outline", slot],
    queryFn: () => getOutline(slot),
  });

  const rows = useMemo(() => outline ?? [], [outline]);
  const tree = useMemo(() => buildOutlineTree(rows), [rows]);
  const outlineIds = useMemo(() => rows.map((r) => r.id), [rows]);
  const hasPending = slotState?.has_pending ?? false;

  // The highlighted row: the chunk being read, or the live frontier.
  const latestId =
    outlineIds.length > 0 ? outlineIds[outlineIds.length - 1] : null;
  const activeChunkId = readingChunkId ?? latestId;
  const activeRow = useMemo(
    () => rows.find((r) => r.id === activeChunkId) ?? null,
    [rows, activeChunkId],
  );

  // Expanded season / episode nodes. The path to the active row stays open
  // (auto-expands as the reading position moves); everything else toggles.
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  useEffect(() => {
    if (!activeRow) return;
    const sKey = `s${activeRow.season ?? 0}`;
    const eKey = `s${activeRow.season ?? 0}e${activeRow.episode ?? 0}`;
    setExpanded((prev) => {
      if (prev.has(sKey) && prev.has(eKey)) return prev;
      const next = new Set(prev);
      next.add(sKey);
      next.add(eKey);
      return next;
    });
  }, [activeRow]);

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const phaseIdx = phase
    ? ACTIVE_GENERATION_PHASES.findIndex((p) => p === phase)
    : -1;
  const stripPct =
    phaseIdx >= 0
      ? ((phaseIdx + 1) / ACTIVE_GENERATION_PHASES.length) * 100
      : 0;

  return (
    <aside className="rail-right" data-testid="session-ledger">
      {/* Generation telemetry - present only while a request is in flight. */}
      {isGenerating && (
        <section className="ledger-section" data-testid="telemetry">
          <div className="phase-stream" data-testid="phase-stream">
            {ACTIVE_GENERATION_PHASES.map((p: NarrativePhase, i) => (
              <div
                key={p}
                className={`phase-row ${phaseIdx >= 0 && i < phaseIdx ? "done" : ""} ${
                  i === phaseIdx ? "active" : ""
                }`}
              >
                <span className="phase-glyph">
                  {phaseIdx >= 0 && i < phaseIdx
                    ? "✓"
                    : i === phaseIdx
                      ? "▸"
                      : "·"}
                </span>
                <span className="phase-label">{PHASE_LABELS[p]}</span>
              </div>
            ))}
          </div>
          <div className="phase-strip">
            <div className="phase-strip-bar" style={{ width: `${stripPct}%` }} />
          </div>
          <div className="phase-stat">
            <span className="phase-clock" data-testid="text-elapsed">
              {(elapsedMs / 1000).toFixed(1)}s
            </span>
          </div>
        </section>
      )}

      {/* Story tree */}
      <section className="ledger-section">
        <ul className="hier-list" data-testid="hierarchy">
          {tree.map((seasonNode) => {
            const sKey = `s${seasonNode.season}`;
            const sOpen = expanded.has(sKey);
            return (
              <li
                key={seasonNode.season}
                className={`hier-season ${sOpen ? "open" : ""}`}
              >
                <button
                  className="hier-row"
                  onClick={() => toggle(sKey)}
                  data-testid={`tree-season-${seasonNode.season}`}
                >
                  {sOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                  <span className="hier-label">SEASON {seasonNode.season}</span>
                </button>
                {sOpen && (
                  <ul>
                    {seasonNode.episodes.map((ep) => {
                      const eKey = `s${ep.season}e${ep.episode}`;
                      const eOpen = expanded.has(eKey);
                      return (
                        <li
                          key={ep.episode}
                          className={`hier-ep ${eOpen ? "open" : ""}`}
                        >
                          <button
                            className="hier-row"
                            onClick={() => toggle(eKey)}
                            data-testid={`tree-episode-${ep.season}-${ep.episode}`}
                          >
                            {eOpen ? (
                              <ChevronDown size={10} />
                            ) : (
                              <ChevronRight size={10} />
                            )}
                            <span className="hier-label">
                              Episode {ep.episode}
                            </span>
                          </button>
                          {eOpen && (
                            <ul>
                              {ep.chunks.map((chunk, chunkIndex) => {
                                const live = isLiveRow(
                                  chunk.id,
                                  outlineIds,
                                  hasPending,
                                );
                                const isReading = readingChunkId === chunk.id;
                                const isFrontierHighlight =
                                  readingChunkId === null &&
                                  !hasPending &&
                                  live;
                                return (
                                  <li key={chunk.id}>
                                    <button
                                      className={`hier-chunk ${
                                        isReading || isFrontierHighlight
                                          ? "current"
                                          : ""
                                      } ${live ? "live" : ""}`}
                                      onClick={() =>
                                        onNavigate(live ? null : chunk.id)
                                      }
                                      data-testid={`tree-chunk-${chunk.id}`}
                                    >
                                      <span className="hier-slug">
                                        {outlineSceneLabel(chunk, chunkIndex + 1)}
                                      </span>
                                    </button>
                                  </li>
                                );
                              })}
                              {hasPending &&
                                latestId !== null &&
                                ep.chunks.some((c) => c.id === latestId) && (
                                  <li>
                                    <button
                                      className={`hier-chunk live ${
                                        readingChunkId === null ? "current" : ""
                                      }`}
                                      onClick={() => onNavigate(null)}
                                      data-testid="tree-chunk-pending"
                                    >
                                      <span className="hier-slug pending">
                                        PENDING
                                      </span>
                                    </button>
                                  </li>
                                )}
                            </ul>
                          )}
                        </li>
                      );
                    })}
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
