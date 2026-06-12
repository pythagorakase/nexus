/**
 * NarrativePane - the typeset book-chapter reading surface.
 *
 * Two reading positions (see lib/narrative-nav.ts for the ladder model):
 * - LIVE (readingChunkId null): the current episode's committed chunks plus
 *   the pending (incubator) chunk from slot state, with choices / freeform
 *   input at the frontier.
 * - HISTORICAL (readingChunkId set): a single committed chunk, read-only.
 *   The choice/input block is replaced by the navigation context; nothing
 *   about the story's actual position changes.
 *
 * Prev/next controls render at the top and bottom of the displayed chunk as
 * "<" / ">" glyphs in the theme's menu font; "»" returns to the frontier.
 * Prose renders as real markdown via ProseMarkdown, with the voice color
 * carried by the .md-part wrapper: storyteller prose in warm cream (--fg),
 * player responses in muted cream (--fg-muted), a thin centered rule between
 * speaker changes. The current chunk carries a 3px magenta edge marker;
 * historical chunks carry a bronze one. Choices 1-3 render with key boxes;
 * the freeform directive is slot 0 - an unboxed italic input indented to the
 * choice-text line. When a chunk presents no structured choices the freeform
 * input has no placeholder and takes focus, so the blinking caret is the
 * invitation to type.
 */
import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { DecoDivider } from "@/components/deco";
import { Textarea } from "@/components/ui/textarea";
import { InlineMarkdown, ProseMarkdown } from "./ProseMarkdown";
import { TypewriterText } from "./TypewriterText";
import {
  getChunk,
  getChunkContext,
  getEpisodeChunks,
  getLatestChunk,
  getOutline,
} from "@/lib/narrative-api";
import {
  freeformPresentation,
  resolveReaderNav,
  type NavTarget,
  type OutlineRow,
  type ReaderNav,
} from "@/lib/narrative-nav";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import {
  PHASE_LABELS,
  type ChunkContext,
  type ChunkWithMetadata,
} from "@/types/narrative";

interface NarrativePaneProps {
  slot: number;
  engine: NarrativeEngine;
  typewriterMsPerChar: number;
  /** null = live frontier; a chunk id = historical reading. */
  readingChunkId: number | null;
  /** Navigate the reading position (null returns to the live frontier). */
  onNavigate: (chunkId: number | null) => void;
}

/** "<" / ">" pagination pair (plus "»" back to the frontier while reading
 * history). Rendered at the top and bottom of the displayed chunk. */
function ReaderNavRow({
  nav,
  isHistorical,
  onNavigate,
  edge,
}: {
  nav: ReaderNav;
  isHistorical: boolean;
  onNavigate: (chunkId: number | null) => void;
  edge: "top" | "bottom";
}) {
  const go = (target: NavTarget) => {
    if (target === null) return;
    onNavigate(target === "live" ? null : target);
  };
  return (
    <nav className="reader-nav" data-testid={`reader-nav-${edge}`}>
      <button
        className="reader-nav-btn"
        disabled={nav.back === null}
        onClick={() => go(nav.back)}
        aria-label="Previous scene"
        data-testid={`nav-back-${edge}`}
      >
        {"<"}
      </button>
      {isHistorical && (
        <button
          className="reader-nav-btn"
          onClick={() => onNavigate(null)}
          aria-label="Return to the story's frontier"
          title="Return to now"
          data-testid={`nav-live-${edge}`}
        >
          {"»"}
        </button>
      )}
      <button
        className="reader-nav-btn"
        disabled={nav.forward === null}
        onClick={() => go(nav.forward)}
        aria-label="Next scene"
        data-testid={`nav-forward-${edge}`}
      >
        {">"}
      </button>
    </nav>
  );
}

export function NarrativePane({
  slot,
  engine,
  typewriterMsPerChar,
  readingChunkId,
  onNavigate,
}: NarrativePaneProps) {
  const { slotState, isGenerating, completedGenerations, submitTurn, phase } =
    engine;
  const [freeform, setFreeform] = useState("");
  const freeformRef = useRef<HTMLTextAreaElement>(null);
  const tailRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<HTMLElement>(null);

  const isHistorical = readingChunkId !== null;

  const { data: latestChunk } = useQuery<ChunkWithMetadata | null>({
    queryKey: ["/api/narrative/latest-chunk", slot],
    queryFn: () => getLatestChunk(slot),
  });

  // Full story outline (shared query with the right-rail tree) - the source
  // of story order for prev/next stepping.
  const { data: outline } = useQuery<OutlineRow[]>({
    queryKey: ["/api/narrative/outline", slot],
    queryFn: () => getOutline(slot),
  });
  const outlineIds = useMemo(() => (outline ?? []).map((r) => r.id), [outline]);

  const season = latestChunk?.metadata?.season ?? null;
  const episode = latestChunk?.metadata?.episode ?? null;

  const { data: episodeChunks } = useQuery<{
    chunks: ChunkWithMetadata[];
    total: number;
  }>({
    queryKey: ["/api/narrative/chunks", season, episode, slot],
    queryFn: () => getEpisodeChunks(season as number, episode as number, slot),
    enabled: !isHistorical && season !== null && episode !== null,
  });

  // The single chunk under historical reading.
  const { data: historicalChunk, error: historicalError } =
    useQuery<ChunkWithMetadata>({
      queryKey: ["/api/narrative/chunk", readingChunkId, slot],
      queryFn: () => getChunk(readingChunkId as number, slot),
      enabled: isHistorical,
    });

  // Scene context keys off the displayed position: the historical chunk
  // while reading history, otherwise the latest committed chunk (pending
  // chunks have no reference rows until approval). Used only for the
  // setting-place title.
  const headChunkId = isHistorical ? readingChunkId : latestChunk?.id ?? null;
  const { data: chunkContext } = useQuery<ChunkContext>({
    queryKey: ["/api/narrative/chunks/context", headChunkId, slot],
    queryFn: () => getChunkContext(headChunkId as number, slot),
    enabled: headChunkId !== null,
  });

  const chunks = episodeChunks?.chunks ?? [];
  const hasPending = slotState?.has_pending ?? false;
  const pendingText = hasPending ? slotState?.storyteller_text ?? null : null;
  const choices = slotState?.choices ?? [];
  const isBootstrapNeeded =
    !!slotState &&
    !slotState.is_empty &&
    !slotState.is_wizard_mode &&
    !hasPending &&
    slotState.current_chunk_id === 0;

  const settingPlace = chunkContext?.places.find(
    (p) => p.referenceType === "setting",
  );

  const nav = useMemo(
    () => resolveReaderNav({ readingChunkId, outlineIds, hasPending }),
    [readingChunkId, outlineIds, hasPending],
  );

  const currentChunkId = hasPending
    ? null // the pending block below is current
    : slotState?.current_chunk_id ?? null;

  // Pre-compute the prose segments per chunk. The voice divider appears only
  // on actual speaker changes, tracked across chunk boundaries; doing this in
  // a memo keeps render pure (no mutation during JSX evaluation).
  const { chunkRenders, pendingDivider } = useMemo(() => {
    let previousVoice: "st" | "you" | null = null;
    const renders = chunks.map((chunk) => {
      const parts: Array<{ voice: "st" | "you"; text: string; divider: boolean }> =
        [];
      const storyteller = chunk.storytellerText ?? chunk.rawText;
      if (storyteller) {
        parts.push({
          voice: "st",
          text: storyteller,
          divider: previousVoice !== null && previousVoice !== "st",
        });
        previousVoice = "st";
      }
      if (chunk.choiceText) {
        parts.push({
          voice: "you",
          text: chunk.choiceText,
          divider: previousVoice !== null && previousVoice !== "you",
        });
        previousVoice = "you";
      }
      return { id: chunk.id, isCurrent: chunk.id === currentChunkId, parts };
    });
    return {
      chunkRenders: renders,
      pendingDivider: previousVoice !== null && previousVoice !== "st",
    };
  }, [chunks, currentChunkId]);

  // The historical chunk's prose segments (storyteller + the player's
  // recorded response).
  const historicalParts = useMemo(() => {
    if (!historicalChunk) return [];
    const parts: Array<{ voice: "st" | "you"; text: string; divider: boolean }> =
      [];
    const storyteller =
      historicalChunk.storytellerText ?? historicalChunk.rawText;
    if (storyteller) {
      parts.push({ voice: "st", text: storyteller, divider: false });
    }
    if (historicalChunk.choiceText) {
      parts.push({
        voice: "you",
        text: historicalChunk.choiceText,
        divider: parts.length > 0,
      });
    }
    return parts;
  }, [historicalChunk]);

  const canSubmit = !isGenerating && !!slotState && !slotState.is_wizard_mode;

  const handleChoice = useCallback(
    (index: number) => {
      if (!canSubmit) return;
      setFreeform("");
      void submitTurn({ choice: index });
    },
    [canSubmit, submitTurn],
  );

  const handleFreeformSubmit = useCallback(() => {
    const text = freeform.trim();
    if (!text || !canSubmit) return;
    setFreeform("");
    void submitTurn({ userText: text });
  }, [freeform, canSubmit, submitTurn]);

  const handleFreeformKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleFreeformSubmit();
      }
    },
    [handleFreeformSubmit],
  );

  // Number keys 1-N select choices when focus is outside the freeform field.
  // Inert while reading history - no submission affordances exist there.
  useEffect(() => {
    if (isHistorical) return;
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (document.activeElement === freeformRef.current) return;
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
      const n = parseInt(event.key, 10);
      if (!isNaN(n) && n >= 1 && n <= choices.length) {
        handleChoice(n);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [choices.length, handleChoice, isHistorical]);

  // Keep the frontier in view when new content lands or generation starts.
  useEffect(() => {
    if (isHistorical) return;
    tailRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [pendingText, isGenerating, completedGenerations, isHistorical]);

  // Historical reading starts each chunk from its top.
  useEffect(() => {
    if (!isHistorical) return;
    headRef.current?.scrollIntoView({ block: "start" });
  }, [isHistorical, readingChunkId]);

  // Without structured choices the freeform input is the turn affordance:
  // focus it so the blinking caret invites input. The autoFocus attribute on
  // the Textarea covers the initial mount only; this effect re-focuses after
  // each completed turn.
  const freeformPresent = freeformPresentation(choices.length);
  useEffect(() => {
    if (isHistorical || isGenerating || isBootstrapNeeded || !canSubmit) return;
    if (choices.length > 0) return;
    freeformRef.current?.focus();
  }, [
    isHistorical,
    isGenerating,
    isBootstrapNeeded,
    canSubmit,
    choices.length,
    completedGenerations,
  ]);

  if (!slotState) {
    return (
      <div className="pane-notice">
        <span className="notice-text">LOADING…</span>
      </div>
    );
  }

  if (slotState.is_wizard_mode) {
    return (
      <div className="pane-notice">
        <span className="notice-text">[ SETUP INCOMPLETE ]</span>
      </div>
    );
  }

  if (slotState.is_empty) {
    return (
      <div className="pane-notice">
        <span className="notice-text">[ EMPTY SLOT ]</span>
      </div>
    );
  }

  if (isHistorical && historicalError) {
    return (
      <div className="pane-notice">
        <span className="notice-text">[ CHUNK UNAVAILABLE ]</span>
        <span className="notice-detail">
          {(historicalError as Error).message}
        </span>
      </div>
    );
  }

  if (isHistorical && !historicalChunk) {
    return (
      <div className="pane-notice">
        <span className="notice-text">LOADING…</span>
      </div>
    );
  }

  if (isHistorical) {
    return (
      <article className="reader" data-testid="narrative-reader" ref={headRef}>
        <div className="reader-frame">
          <div className="reader-inner">
            <ReaderNavRow
              nav={nav}
              isHistorical
              onNavigate={onNavigate}
              edge="top"
            />
            <header className="scene-head">
              <h2 className="scene-title" data-testid="text-scene-location">
                {settingPlace?.name ?? "UNCHARTED"}
              </h2>
              <DecoDivider variant="glyph" />
            </header>

            <section className="chunk-stream">
              {historicalChunk && (
                <div
                  className="chunk-block archival"
                  data-testid={`chunk-${historicalChunk.id}`}
                >
                  <div className="prose-block">
                    {historicalParts.map((part, i) => (
                      <Fragment key={i}>
                        {part.divider && <hr className="voice-divider" />}
                        <div className={`md-part ${part.voice}`}>
                          <ProseMarkdown text={part.text} />
                        </div>
                      </Fragment>
                    ))}
                  </div>
                </div>
              )}
            </section>

            <ReaderNavRow
              nav={nav}
              isHistorical
              onNavigate={onNavigate}
              edge="bottom"
            />
          </div>
        </div>
      </article>
    );
  }

  return (
    <article className="reader" data-testid="narrative-reader" ref={headRef}>
      <div className="reader-frame">
        <div className="reader-inner">
          <ReaderNavRow
            nav={nav}
            isHistorical={false}
            onNavigate={onNavigate}
            edge="top"
          />
          <header className="scene-head">
            <h2 className="scene-title" data-testid="text-scene-location">
              {settingPlace?.name ?? "UNCHARTED"}
            </h2>
            <DecoDivider variant="glyph" />
          </header>

          <section className="chunk-stream">
            {chunkRenders.map((chunk) => (
              <div
                key={chunk.id}
                className={`chunk-block ${chunk.isCurrent ? "current" : ""}`}
                data-testid={`chunk-${chunk.id}`}
              >
                <div className="prose-block">
                  {chunk.parts.map((part) => (
                    <Fragment key={part.voice}>
                      {part.divider && <hr className="voice-divider" />}
                      <div className={`md-part ${part.voice}`}>
                        <ProseMarkdown text={part.text} />
                      </div>
                    </Fragment>
                  ))}
                </div>
              </div>
            ))}

            {pendingText && (
              <div className="chunk-block current" data-testid="chunk-pending">
                <div className="prose-block">
                  {pendingDivider && <hr className="voice-divider" />}
                  <div className="md-part st">
                    <TypewriterText
                      key={completedGenerations}
                      text={pendingText}
                      msPerChar={typewriterMsPerChar}
                      animate={completedGenerations > 0}
                      markdown
                    />
                  </div>
                </div>
              </div>
            )}
          </section>

          <ReaderNavRow
            nav={nav}
            isHistorical={false}
            onNavigate={onNavigate}
            edge="bottom"
          />

          {isGenerating && (
            <div className="reader-status" data-testid="status-generating">
              <span className="glyph">▸</span>
              <span>{(phase && PHASE_LABELS[phase]) ?? "Working…"}</span>
            </div>
          )}

          {isBootstrapNeeded && !isGenerating && (
            <section className="choices">
              <button
                className="choice"
                onClick={() => void submitTurn({})}
                data-testid="button-begin-story"
              >
                <span className="choice-glyph">◆</span>
                <span className="choice-text">Begin the story.</span>
              </button>
            </section>
          )}

          {/* Freeform slot 0 stays available even when the storyteller
              presented no numbered choices (matches the CLI continue flow). */}
          {!isGenerating && !isBootstrapNeeded && (
            <section className="choices" data-testid="story-choices">
              {choices.map((text, i) => (
                <button
                  key={`${i}-${text}`}
                  className="choice"
                  onClick={() => handleChoice(i + 1)}
                  disabled={!canSubmit}
                  data-testid={`choice-${i + 1}`}
                >
                  <span className="choice-key">{i + 1}</span>
                  <span className="choice-glyph">◆</span>
                  <span className="choice-text">
                    <InlineMarkdown text={text} />
                  </span>
                </button>
              ))}
              <label className="choice freeform">
                <Textarea
                  ref={freeformRef}
                  className="choice-input"
                  rows={1}
                  value={freeform}
                  placeholder={freeformPresent.placeholder}
                  autoFocus={freeformPresent.autoFocus}
                  onChange={(e) => setFreeform(e.target.value)}
                  onKeyDown={handleFreeformKeyDown}
                  disabled={!canSubmit}
                  data-testid="input-freeform"
                />
              </label>
            </section>
          )}

          <div ref={tailRef} />
        </div>
      </div>
    </article>
  );
}
