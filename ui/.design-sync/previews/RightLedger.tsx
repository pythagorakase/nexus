import { RightLedger } from "nexus-ui";

// The 320px right rail (narrative tab only). Two things live here:
//  - generation telemetry (phase stream + progress strip + elapsed clock),
//    driven entirely by the `engine` prop — present only while a request is
//    in flight. We mock a mid-generation engine so the full stream renders.
//  - the story tree (season → episode → scene), populated from the
//    /api/narrative/outline fetch. That fetch returns empty headlessly, so the
//    tree is empty in these stills; only the telemetry band carries content.
//
// nexus-layout.css hides .rail-right entirely below a 1100px viewport
// (@media max-width:1100px → display:none) and the review capture runs at
// 900px wide, so a scoped style override below restores it to its real
// flex layout for the still. The telemetry styling itself is unchanged.

const noop = () => {};
const noAsync = async () => {};

function makeEngine(phase: string, elapsedMs: number) {
  return {
    slotState: {
      slot: 2,
      is_empty: false,
      is_wizard_mode: false,
      phase,
      subphase: null,
      thread_id: "thread-cinder-07",
      current_chunk_id: 1421,
      has_pending: false,
      storyteller_text: null,
      choices: [],
      session_id: "sess-live",
      model: "@anthropic.default",
    },
    slotStateError: null,
    isSlotStateLoading: false,
    phase,
    skaldStatus: "GENERATING",
    elapsedMs,
    generationError: null,
    isGenerating: true,
    completedGenerations: 0,
    submitTurn: noAsync,
  } as never;
}

const Frame = ({ children }: { children: React.ReactNode }) => (
  <div style={{ height: 420, width: 320, display: "flex" }}>
    {/* Counteract the <1100px responsive hide so the rail renders in-frame. */}
    <style>{`.rail-right{display:flex !important}`}</style>
    {children}
  </div>
);

// Early in a turn: the first phases are marked done, the current phase carries
// the ▸ glyph, and the progress strip is part-filled.
export const TelemetryEarly = () => (
  <Frame>
    <RightLedger
      slot={2}
      engine={makeEngine("building_context", 2100)}
      readingChunkId={null}
      onNavigate={noop}
    />
  </Frame>
);

// Deeper into the turn: more phases complete, the strip nearly full, the
// elapsed clock advanced.
export const TelemetryWriting = () => (
  <Frame>
    <RightLedger
      slot={2}
      engine={makeEngine("calling_llm", 7800)}
      readingChunkId={null}
      onNavigate={noop}
    />
  </Frame>
);
