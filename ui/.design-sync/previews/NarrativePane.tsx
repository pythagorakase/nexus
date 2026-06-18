import { NarrativePane } from "nexus-ui";

// The typeset book-chapter reading surface. Its content is driven entirely by
// the `engine` prop (a plain object we mock here); the committed-chunk list
// comes from a headless fetch that returns empty, so each cell shows the
// scene head + the live frontier — the pending storyteller prose rendered
// through TypewriterText/ProseMarkdown and the choice block beneath it.

const noop = () => {};
const noAsync = async () => {};

const STORY = `The lift doors parted onto the **Cinder Concourse**, and the smell hit her first — ozone and burnt sugar, the perfume of a city that never quite finished burning.

*She had been here before.* In another life, before the Veil took her name and gave her this one instead. The Archivist waited by the brass orrery, turning a single gear with one finger.

"You came back," he said, not looking up. "They always do."`;

function makeEngine(overrides: Record<string, unknown> = {}) {
  return {
    slotState: {
      slot: 2,
      is_empty: false,
      is_wizard_mode: false,
      phase: null,
      subphase: null,
      thread_id: "thread-cinder-07",
      current_chunk_id: 1421,
      has_pending: true,
      storyteller_text: STORY,
      choices: [
        "Ask the Archivist what *they* always come back for.",
        "Cross to the orrery and stop the gear with your hand.",
        "Say nothing. Let the silence make him talk first.",
      ],
      session_id: null,
      model: "@anthropic.default",
    },
    slotStateError: null,
    isSlotStateLoading: false,
    phase: null,
    skaldStatus: "READY",
    elapsedMs: 0,
    generationError: null,
    isGenerating: false,
    completedGenerations: 0,
    submitTurn: noAsync,
    ...overrides,
  } as never;
}

// Frontier with three structured choices plus the freeform slot-0 input.
export const Frontier = () => (
  <div
    className="nexus-content"
    style={{ width: 720, height: 560, position: "relative", overflow: "hidden" }}
  >
    <NarrativePane
      slot={2}
      engine={makeEngine()}
      typewriterMsPerChar={35}
      readingChunkId={null}
      onNavigate={noop}
    />
  </div>
);

// Mid-generation: the in-reader status line shows the active phase, and the
// choice block is suppressed while the storyteller writes.
export const Generating = () => (
  <div
    className="nexus-content"
    style={{ width: 720, height: 560, position: "relative", overflow: "hidden" }}
  >
    <NarrativePane
      slot={2}
      engine={makeEngine({
        isGenerating: true,
        phase: "calling_llm",
        skaldStatus: "GENERATING",
        elapsedMs: 4200,
      })}
      typewriterMsPerChar={35}
      readingChunkId={null}
      onNavigate={noop}
    />
  </div>
);
