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
 *
 * Selecting a choice (click or its number key) never sends a turn: it loads
 * the choice into slot 0 as an editable draft that remembers which choice it
 * came from. Only Enter or the send glyph commits the draft - as the choice
 * number plus its (possibly edited) text, or as freeform text once the draft
 * is cleared and retyped.
 *
 * The pending block carries a quiet regenerate glyph while nothing is
 * generating. It opens one optional note; Enter or its send glyph re-rolls
 * the draft. The pending prose stays on screen until the replacement lands,
 * and a failed re-roll leaves it there beneath a failure line.
 *
 * Just above the latest committed chunk, a history glyph opens the return
 * recap (ReturnRecapCard), whether or not a draft is pending below. When that
 * chunk lies past the fetched page of a long episode, the glyph follows the
 * last chunk shown instead, still above any pending draft. It opens on its
 * own after a real-world hiatus, and the next accepted action closes it; the
 * reader shell holds that state (recapState) so it outlives this pane.
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
import { Intertitle } from "./Intertitle";
import { InlineMarkdown, ProseMarkdown } from "./ProseMarkdown";
import {
  ReturnRecapCard,
  recapBeside,
  useReturnRecapVisibility,
  type ReaderRecapState,
} from "./ReturnRecapCard";
import {
  REGENERATE_NOTE_MAX_CHARS,
  getChunk,
  getChunkContext,
  getEpisodeChunks,
  getLatestChunk,
  getOutline,
  getReturnRecap,
} from "@/lib/narrative-api";
import {
  freeformPresentation,
  resolveReaderNav,
  type NavTarget,
  type OutlineRow,
  type ReaderNav,
} from "@/lib/narrative-nav";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import { useReaderDraft } from "@/hooks/useReaderDraft";
import {
  PHASE_LABELS,
  type ChunkContext,
  type ChunkWithMetadata,
} from "@/types/narrative";
import type { ReturnRecap } from "@shared/schema";

interface NarrativePaneProps {
  slot: number;
  engine: NarrativeEngine;
  /** null = live frontier; a chunk id = historical reading. */
  readingChunkId: number | null;
  /** Navigate the reading position (null returns to the live frontier). */
  onNavigate: (chunkId: number | null) => void;
  /** Recap visibility, held by the reader shell so it outlives this pane. */
  recapState: ReaderRecapState;
}

interface SceneGrounding {
  season: number;
  episode: number;
  scene: number;
  worldLayer: string | null;
  worldTime: string | null;
  worldTimeFace: string | null;
}

function sceneGrounding(chunk: ChunkWithMetadata): SceneGrounding | null {
  const metadata = chunk.metadata;
  if (
    metadata?.season == null ||
    metadata.episode == null ||
    metadata.scene == null
  ) {
    return null;
  }
  return {
    season: metadata.season,
    episode: metadata.episode,
    scene: metadata.scene,
    worldLayer: metadata.worldLayer,
    worldTime: metadata.worldTime,
    worldTimeFace: metadata.worldTimeFace,
  };
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
  readingChunkId,
  onNavigate,
  recapState,
}: NarrativePaneProps) {
  const { slotState, isGenerating, completedGenerations, submitTurn, phase } =
    engine;
  const draft = useReaderDraft(slotState);
  const freeform = draft.text;
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

  // Where the story stands, for a returning player. It sits above the latest
  // committed chunk, so it waits for one; the reader's "/api/narrative"
  // invalidation after an accepted action refreshes it. The gateway decides
  // `due` against the hiatus clock, so a reader left open across the hiatus
  // asks again when the player returns to the tab.
  const { data: recap } = useQuery<ReturnRecap>({
    queryKey: ["/api/narrative/recap", slot],
    queryFn: () => getReturnRecap(slot),
    enabled: !isHistorical && !!latestChunk,
    refetchOnWindowFocus: "always",
  });

  const chunks = episodeChunks?.chunks ?? [];
  const hasPending = slotState?.has_pending ?? false;
  const pendingText = hasPending ? slotState?.storyteller_text ?? null : null;
  // Slot state lists only live choices: an action already recorded on the
  // committed frontier consumed its menu.
  const choices = slotState?.choices ?? [];
  // Retryable exactly when the retry route would accept it; the failure line
  // also covers a failed attempt that recorded no action (input stays open).
  const recovery = hasPending ? null : slotState?.recovery ?? null;
  const needsRecovery = recovery !== null;
  // A failed attempt that set out to supersede the draft still pending is a
  // re-roll which failed and left that draft in place.
  const pendingSessionId = hasPending ? slotState?.session_id ?? null : null;
  const regenerationFailure =
    pendingSessionId !== null &&
    engine.failedGeneration?.supersedes_session_id === pendingSessionId
      ? engine.failedGeneration
      : null;
  const failure = hasPending
    ? regenerationFailure
    : recovery ?? engine.failedGeneration;
  const isBootstrapNeeded =
    !!slotState &&
    !slotState.is_empty &&
    !slotState.is_wizard_mode &&
    !hasPending &&
    slotState.current_chunk_id === 0;

  const settingNames = chunkContext?.places
    .filter((place) => place.referenceType === "setting")
    .map((place) => place.name)
    .join(", ");

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
    let previousSceneKey: string | null | undefined;
    const renders = chunks.map((chunk, index) => {
      const parts: Array<{ voice: "st" | "you"; text: string; divider: boolean }> =
        [];
      const grounding = sceneGrounding(chunk);
      const sceneKey = grounding
        ? `${grounding.season}:${grounding.episode}:${grounding.scene}`
        : null;
      const showIntertitle =
        grounding !== null &&
        !chunk.hasInlineSceneMarkup &&
        (index === 0 || sceneKey !== previousSceneKey);
      previousSceneKey = sceneKey;
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
      return {
        id: chunk.id,
        isCurrent: chunk.id === currentChunkId,
        intertitle: showIntertitle ? grounding : null,
        parts,
      };
    });
    return {
      chunkRenders: renders,
      pendingDivider: previousVoice !== null && previousVoice !== "st",
    };
  }, [chunks, currentChunkId]);

  // The recap sits just above the latest committed chunk, whose setting and
  // cast it reports, even while a draft is pending below that chunk. The
  // episode page is fetched from its start, so in a long episode that chunk
  // may not be on it: once the page has loaded, the recap then follows the
  // last chunk shown, above any pending draft.
  const recapChunkId = latestChunk?.id ?? null;
  const recapIndex = chunkRenders.findIndex((chunk) => chunk.id === recapChunkId);
  const recapAfterChunks = recapIndex === -1 && episodeChunks !== undefined;
  const shownRecap = useMemo(() => {
    // The committed chunks bordering the card. After the page, only the
    // pending draft, which records no player line, can follow it.
    const beside = recapAfterChunks
      ? chunkRenders.slice(-1)
      : recapIndex === -1
        ? []
        : chunkRenders.slice(Math.max(recapIndex - 1, 0), recapIndex + 1);
    return recapBeside(
      recap,
      beside
        .filter((chunk) => chunk.parts.some((part) => part.voice === "you"))
        .map((chunk) => chunk.id),
    );
  }, [recap, chunkRenders, recapIndex, recapAfterChunks]);
  const recapView = useReturnRecapVisibility(shownRecap, slot, recapState);

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

  const historicalGrounding = historicalChunk
    ? sceneGrounding(historicalChunk)
    : null;
  const historicalIntertitle =
    historicalGrounding && !historicalChunk?.hasInlineSceneMarkup
      ? historicalGrounding
      : null;

  const canSubmit = !isGenerating && !engine.isRecoveryLoading && !needsRecovery
    && !!slotState && !slotState.is_wizard_mode;

  // Regenerate: pending-only, idle-only, one optional note. The note survives
  // a failed re-roll and is dropped once a different draft is pending.
  const canRegenerate = canSubmit && pendingSessionId !== null;
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [regenerateNote, setRegenerateNote] = useState("");
  const regenerating = useRef(false);
  useEffect(() => {
    setRegenerateOpen(false);
    setRegenerateNote("");
  }, [pendingSessionId]);
  const handleRegenerate = useCallback(async () => {
    if (!canRegenerate || regenerating.current) return;
    regenerating.current = true;
    try {
      const note = regenerateNote.trim();
      if (await engine.regenerateTurn(note || undefined)) setRegenerateOpen(false);
    } finally {
      regenerating.current = false;
    }
  }, [canRegenerate, regenerateNote, engine.regenerateTurn]);
  const handleRegenerateKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "Escape") {
        setRegenerateOpen(false);
      } else if (
        event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing
      ) {
        event.preventDefault();
        void handleRegenerate();
      }
    },
    [handleRegenerate],
  );

  // Selecting loads the choice into the draft, caret at its end, and never
  // submits. The epoch re-focuses even when the same choice is reselected.
  const [selectionEpoch, setSelectionEpoch] = useState(0);
  const handleSelect = useCallback(
    (index: number) => {
      if (!canSubmit) return;
      draft.select(index, choices[index - 1]);
      setSelectionEpoch((epoch) => epoch + 1);
    },
    [canSubmit, choices, draft.select],
  );
  useEffect(() => {
    if (selectionEpoch === 0) return;
    const field = freeformRef.current;
    if (!field) return;
    field.focus();
    field.setSelectionRange(field.value.length, field.value.length);
  }, [selectionEpoch]);

  // The one commit path. A draft that came from a choice sends its number and
  // text together; the server records an edit only when the text differs.
  // An accepted action closes the recap.
  const selectedChoice = draft.choice;
  const closeRecap = recapView.close;
  const handleSend = useCallback(() => {
    const text = freeform.trim();
    if (!text || !canSubmit) return;
    void draft.submit(
      async () => {
        const accepted = await submitTurn(
          selectedChoice === null
            ? { userText: text }
            : { choice: selectedChoice, userText: text },
        );
        if (accepted) closeRecap();
        return accepted;
      },
      true,
    );
  }, [freeform, selectedChoice, canSubmit, submitTurn, draft.submit, closeRecap]);

  const handleFreeformKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (
        event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing
      ) {
        event.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );
  // The draft names only a choice on this menu (useReaderDraft validates it).
  const selectedEdited =
    selectedChoice !== null
    && freeform.trim() !== choices[selectedChoice - 1].trim();

  // Number keys 1-N select choices when focus is outside the freeform field.
  // Inert while reading history - no submission affordances exist there.
  // Browser chords (Cmd/Ctrl/Alt+digit switch tabs), held-key repeats and IME
  // composition are never a choice.
  useEffect(() => {
    if (isHistorical) return;
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (
        event.metaKey || event.ctrlKey || event.altKey || event.repeat
        || event.isComposing
      ) return;
      if (document.activeElement === freeformRef.current) return;
      // A digit typed into any editable control belongs to that control.
      const target = event.target as HTMLElement | null;
      if (
        target
        && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable)
      ) return;
      const n = parseInt(event.key, 10);
      if (!isNaN(n) && n >= 1 && n <= choices.length) {
        event.preventDefault();
        handleSelect(n);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [choices.length, handleSelect, isHistorical]);

  // Keep the frontier in view when new content lands or generation starts.
  useEffect(() => {
    if (isHistorical) return;
    tailRef.current?.scrollIntoView({ behavior: "instant", block: "end" });
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
                {settingNames || "UNCHARTED"}
              </h2>
              <DecoDivider variant="glyph" />
            </header>

            <section className="chunk-stream">
              {historicalChunk && (
                <>
                  {historicalIntertitle && (
                    <Intertitle {...historicalIntertitle} />
                  )}
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
                </>
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

  const recapCard = (
    <ReturnRecapCard
      recap={shownRecap}
      open={recapView.open}
      onToggle={recapView.toggle}
    />
  );

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
              {settingNames || "UNCHARTED"}
            </h2>
            <DecoDivider variant="glyph" />
          </header>

          <section className="chunk-stream">
            {chunkRenders.map((chunk) => (
              <Fragment key={chunk.id}>
                {chunk.id === recapChunkId && recapCard}
                {chunk.intertitle && <Intertitle {...chunk.intertitle} />}
                <div
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
              </Fragment>
            ))}
            {recapAfterChunks && recapCard}

            {pendingText && (
              <div className="chunk-block current" data-testid="chunk-pending">
                <div className="prose-block">
                  {pendingDivider && <hr className="voice-divider" />}
                  <div className="md-part st">
                    <ProseMarkdown text={pendingText} />
                  </div>
                </div>
                {canRegenerate && (
                  <div className="regenerate-row">
                    {regenerateOpen && (
                      <>
                        <input
                          className="choice-input regenerate-note"
                          value={regenerateNote}
                          maxLength={REGENERATE_NOTE_MAX_CHARS}
                          onChange={(e) => setRegenerateNote(e.target.value)}
                          onKeyDown={handleRegenerateKeyDown}
                          autoFocus
                          aria-label="Note for the regenerated scene"
                          data-testid="input-regenerate-note"
                        />
                        <button
                          type="button"
                          className="reader-nav-btn"
                          onClick={() => void handleRegenerate()}
                          aria-label="Regenerate now"
                          data-testid="button-confirm-regenerate"
                        >
                          ↵
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      className="reader-nav-btn regenerate-toggle"
                      onClick={() => setRegenerateOpen((open) => !open)}
                      aria-label="Regenerate"
                      aria-expanded={regenerateOpen}
                      data-testid="button-regenerate"
                    >
                      ↻
                    </button>
                  </div>
                )}
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

          <div className="choices">
              {draft.previousActions.map((action) => (
                <details key={action.attempt} data-testid="unconfirmed-action">
                  <summary>Unconfirmed previous action</summary>
                  <p>
                    Its send was not confirmed. Check the latest scene before
                    using this text again.
                  </p>
                  <Textarea
                    readOnly
                    autoSize
                    value={action.text}
                    aria-label="Saved unconfirmed action"
                  />
                  <button type="button" onClick={() => draft.dismissAction(action.attempt)}>
                    Dismiss saved action
                  </button>
                </details>
              ))}
              {draft.storageError && (
                <p role="alert">
                  This draft could not be saved in your browser. Keep this page
                  open or copy your text before leaving.
                </p>
              )}
          </div>

          {failure && !isGenerating && (
            <div
              className="reader-status failed"
              role="alert"
              title={failure.error ?? failure.error_class ?? undefined}
              data-testid="generation-failure"
            >
              <span className="glyph">✕</span>
              <span>
                {regenerationFailure
                  ? "The regeneration failed."
                  : "The next scene failed."}
              </span>
            </div>
          )}

          {needsRecovery && !isGenerating && (
            <section className="choices" data-testid="generation-recovery">
              <button
                className="choice"
                onClick={() => void engine.retryGeneration()}
                disabled={engine.isRecoveryLoading}
                data-testid="button-retry-generation"
              >
                <span className="choice-glyph">◆</span>
                <span className="choice-text">Retry</span>
              </button>
            </section>
          )}

          {isBootstrapNeeded && canSubmit && (
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
          {!isGenerating && !isBootstrapNeeded && !needsRecovery && (
            <section className="choices" data-testid="story-choices">
              {choices.map((text, i) => {
                const isSelected = selectedChoice === i + 1;
                const state = isSelected
                  ? selectedEdited ? " selected edited" : " selected"
                  : "";
                return (
                  <button
                    key={`${i}-${text}`}
                    className={`choice${state}`}
                    onClick={() => handleSelect(i + 1)}
                    disabled={!canSubmit}
                    aria-pressed={isSelected}
                    data-testid={`choice-${i + 1}`}
                  >
                    <span className="choice-key">{i + 1}</span>
                    <span className="choice-glyph">◆</span>
                    <span className="choice-text">
                      <InlineMarkdown text={text} />
                    </span>
                  </button>
                );
              })}
              <div className="freeform-row">
                <label className="choice freeform">
                  <Textarea
                    ref={freeformRef}
                    autoSize
                    className="choice-input"
                    rows={1}
                    value={freeform}
                    placeholder={freeformPresent.placeholder}
                    autoFocus={freeformPresent.autoFocus}
                    onChange={(e) => draft.update(e.target.value)}
                    onKeyDown={handleFreeformKeyDown}
                    disabled={!canSubmit}
                    data-testid="input-freeform"
                  />
                </label>
                <button
                  type="button"
                  className="reader-nav-btn freeform-send"
                  onClick={handleSend}
                  disabled={!canSubmit || !freeform.trim()}
                  aria-label="Send"
                  data-testid="button-send-turn"
                >
                  ↵
                </button>
              </div>
            </section>
          )}

          <div ref={tailRef} />
        </div>
      </div>
    </article>
  );
}
