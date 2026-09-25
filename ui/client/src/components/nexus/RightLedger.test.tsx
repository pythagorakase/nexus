import { describe, expect, it } from "vitest";
import type { OutlineRow } from "@/lib/narrative-nav";
import { render, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import { GENERATION_PHASES, PHASE_LABELS, parseNarrativePhase } from "@/types/narrative";
import { RightLedger, outlineSceneLabel } from "./RightLedger";

const row = (overrides: Partial<OutlineRow>): OutlineRow => ({
  id: 91_337,
  season: 2,
  episode: 4,
  scene: 7,
  slug: null,
  ...overrides,
});

describe("outlineSceneLabel", () => {
  it("prefers the narrative slug", () => {
    expect(outlineSceneLabel(row({ slug: "S02E04_007" }), 3)).toBe(
      "S02E04_007",
    );
  });

  it("falls back to scene metadata rather than the raw chunk id", () => {
    expect(outlineSceneLabel(row({}), 3)).toBe("Scene 7");
  });

  it("uses episode order when legacy metadata has no scene", () => {
    expect(outlineSceneLabel(row({ scene: null }), 3)).toBe("Scene 3");
  });
});


it("renders only durable phases in order with monotonic progress and nothing at rest", () => {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } });
  client.setQueryData(["/api/narrative/outline", 4], []);
  const engine: NarrativeEngine = {
    slotState: undefined, slotStateError: null, isSlotStateLoading: false,
    phase: null, skaldStatus: "READY", elapsedMs: 0, generationError: null,
    isGenerating: true, completedGenerations: 0, submitTurn: async () => true,
  };
  const view = () => <QueryClientProvider client={client}>
    <RightLedger slot={4} engine={engine} readingChunkId={null} onNavigate={() => {}} />
  </QueryClientProvider>;
  const rendered = render(view());
  let previous = 0;
  for (const phase of GENERATION_PHASES) {
    engine.phase = phase;
    rendered.rerender(view());
    expect(Array.from(rendered.container.querySelectorAll(".phase-label"), node => node.textContent))
      .toEqual(GENERATION_PHASES.map(phase => PHASE_LABELS[phase]));
    expect(rendered.container.querySelector(".phase-row.active .phase-label")?.textContent).toBe(PHASE_LABELS[phase]);
    const progress = parseFloat((rendered.container.querySelector(".phase-strip-bar") as HTMLElement).style.width);
    expect(progress).toBeGreaterThan(previous);
    previous = progress;
  }
  expect(previous).toBe(100);
  engine.isGenerating = false;
  rendered.rerender(view());
  expect(rendered.queryByTestId("telemetry")).toBeNull();
  expect(parseNarrativePhase("initiated")).toBe("retrieval");
  expect(parseNarrativePhase("calling_llm")).toBe("writer");
  expect(() => parseNarrativePhase("unknown")).toThrow();
  cleanup();
});
