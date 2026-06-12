/**
 * NarrativePane - the typeset book-chapter reading surface.
 *
 * Renders the current episode's committed chunks plus the pending
 * (incubator) chunk from slot state. Prose renders as real markdown via
 * ProseMarkdown (committed path and typewriter reveal path alike), with the
 * voice color carried by the .md-part wrapper.
 * Voice is differentiated by color only:
 * storyteller prose in warm cream (--fg), player responses in muted cream
 * (--fg-muted), with a thin centered rule between speaker changes. The
 * current chunk carries a 3px magenta edge marker; earlier chunks read at
 * 0.78 opacity. Choices 1-3 render with key boxes; the freeform directive
 * is slot 0 - an unboxed italic input indented to the choice-text line.
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
import { ProseMarkdown } from "./ProseMarkdown";
import { TypewriterText } from "./TypewriterText";
import {
  getChunkContext,
  getEpisodeChunks,
  getLatestChunk,
} from "@/lib/narrative-api";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import type { ChunkContext, ChunkWithMetadata } from "@/types/narrative";

interface NarrativePaneProps {
  slot: number;
  engine: NarrativeEngine;
  typewriterMsPerChar: number;
}

export function NarrativePane({
  slot,
  engine,
  typewriterMsPerChar,
}: NarrativePaneProps) {
  const { slotState, isGenerating, completedGenerations, submitTurn, phase } =
    engine;
  const [freeform, setFreeform] = useState("");
  const freeformRef = useRef<HTMLTextAreaElement>(null);
  const tailRef = useRef<HTMLDivElement>(null);

  const { data: latestChunk } = useQuery<ChunkWithMetadata | null>({
    queryKey: ["/api/narrative/latest-chunk", slot],
    queryFn: () => getLatestChunk(slot),
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

  // Scene context (cast + setting place) keys off the latest committed
  // chunk - pending chunks have no reference rows until approval.
  const { data: chunkContext } = useQuery<ChunkContext>({
    queryKey: ["/api/narrative/chunks/context", latestChunk?.id, slot],
    queryFn: () => getChunkContext(latestChunk!.id, slot),
    enabled: !!latestChunk?.id,
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
  const presentCast =
    chunkContext?.characters.filter((c) => c.reference === "present") ?? [];

  const sceneCoord = useMemo(() => {
    const m = latestChunk?.metadata;
    if (!m) return null;
    return `S${m.season ?? 0}·E${m.episode ?? 0}·S${m.scene ?? 0}`;
  }, [latestChunk?.metadata]);

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
  useEffect(() => {
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
  }, [choices.length, handleChoice]);

  // Keep the frontier in view when new content lands or generation starts.
  useEffect(() => {
    tailRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [pendingText, isGenerating, completedGenerations]);

  if (!slotState) {
    return (
      <div className="pane-notice">
        <span className="notice-text">LOADING SLOT STATE…</span>
      </div>
    );
  }

  if (slotState.is_wizard_mode) {
    return (
      <div className="pane-notice">
        <span className="notice-text">[ SETUP INCOMPLETE ]</span>
        <span className="notice-detail">
          This slot is still in the New Story wizard. Finish setup to begin
          reading.
        </span>
      </div>
    );
  }

  if (slotState.is_empty) {
    return (
      <div className="pane-notice">
        <span className="notice-text">[ EMPTY SLOT ]</span>
        <span className="notice-detail">
          No story lives here yet. Start a new story from the splash menu.
        </span>
      </div>
    );
  }

  return (
    <article className="reader" data-testid="narrative-reader">
      <div className="reader-frame">
        <div className="reader-inner">
          <header className="scene-head">
            {sceneCoord && (
              <span className="eyebrow brass-glow">[ SCENE {sceneCoord} ]</span>
            )}
            <h2 className="scene-title" data-testid="text-scene-location">
              {settingPlace?.name ?? "UNCHARTED"}
            </h2>
            {presentCast.length > 0 && (
              <div className="scene-meta">
                <span className="caption">
                  {presentCast.map((c) => c.name).join(" · ")}
                </span>
              </div>
            )}
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

          {isGenerating && (
            <div className="reader-status" data-testid="status-generating">
              <span className="glyph">▸</span>
              <span>SKALD · {phase?.replace(/_/g, " ") ?? "WORKING"}</span>
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
                  <span className="choice-text">{text}</span>
                </button>
              ))}
              <label className="choice freeform">
                <Textarea
                  ref={freeformRef}
                  className="choice-input"
                  rows={1}
                  value={freeform}
                  placeholder="…or something else"
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
