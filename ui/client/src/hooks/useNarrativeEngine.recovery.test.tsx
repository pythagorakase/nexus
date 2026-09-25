import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { NarrativePane } from "@/components/nexus/NarrativePane";
import type { GenerationSession, SlotState } from "@/types/narrative";
import * as api from "@/lib/narrative-api";
import { useNarrativeEngine } from "./useNarrativeEngine";

vi.mock("@/lib/narrative-api", () => ({
  continueNarrative: vi.fn(), retryNarrative: vi.fn(), getSlotState: vi.fn(),
  getActiveGeneration: vi.fn(), getGenerationStatus: vi.fn(), getRecoveryPreferences: vi.fn(),
  getLatestChunk: vi.fn(async () => null), getOutline: vi.fn(async () => []),
}));
vi.mock("@/hooks/use-toast", () => ({ toast: vi.fn() }));

const settings = {
  request_timeout_seconds: 10, poll_interval_seconds: 1000,
  wake_gap_threshold_seconds: 15, stale_lease_timeout_seconds: 3600,
};
const failure: GenerationSession = {
  slot: 4, session_id: "failed-8", status: "error", phase: "staging",
  terminal_outcome: "error", replaced_by_session_id: null, chunk_id: null, parent_chunk_id: 9,
  created_at: "2026-09-25T08:00:00Z", heartbeat_at: "2026-09-25T08:01:00Z",
  expires_at: null, error: "Unresolved place state update", error_class: "WireContractViolation",
};
const state: SlotState = {
  slot: 4, story_id: "story-951", is_empty: false, is_wizard_mode: false,
  phase: null, subphase: null, thread_id: null, current_chunk_id: 9, has_pending: false,
  frontier_clock: null, storyteller_text: "The preceding scene.",
  choices: ["Already consumed choice"], session_id: null, model: "TEST",
  narrative_generation: settings,
};
let currentState: SlotState;
let currentSession: GenerationSession | null;
let engine: ReturnType<typeof useNarrativeEngine>;

beforeAll(() => {
  Object.defineProperty(Element.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
});
beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  currentState = { ...state };
  currentSession = { ...failure };
  vi.mocked(api.getSlotState).mockImplementation(async () => currentState);
  vi.mocked(api.getActiveGeneration).mockImplementation(async () => currentSession);
  vi.mocked(api.getGenerationStatus).mockImplementation(async () => currentSession!);
  vi.mocked(api.getRecoveryPreferences).mockResolvedValue({ narrative_generation: settings });
  vi.stubGlobal("WebSocket", class { close() {} });
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true })));
});
afterEach(() => vi.unstubAllGlobals());

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["/api/settings"], { ui: { theme: "veil" } });
  function Reader() {
    engine = useNarrativeEngine(4);
    return <NarrativePane slot={4} engine={engine} readingChunkId={null} onNavigate={vi.fn()} />;
  }
  return render(<QueryClientProvider client={client}><ThemeProvider><Reader /></ThemeProvider></QueryClientProvider>);
}
const boundary = () => act(() => { document.dispatchEvent(new Event("visibilitychange")); });

async function expectFailure() {
  await waitFor(() => expect(screen.getByTestId("generation-recovery")).toBeInTheDocument());
  expect(screen.queryByTestId("choice-1")).not.toBeInTheDocument();
  expect(screen.queryByTestId("input-freeform")).not.toBeInTheDocument();
}

describe("durable reader generation recovery", () => {
  it("restores a persistent failure after remount and reconnect without replaying", async () => {
    const view = mount();
    await expectFailure();
    view.unmount();
    mount();
    await expectFailure();
    boundary();
    await expectFailure();
    expect(api.retryNarrative).not.toHaveBeenCalled();
    expect(api.continueNarrative).not.toHaveBeenCalled();
    await act(async () => { expect(await engine.submitTurn({ choice: 1 })).toBe(false); });
    expect(api.continueNarrative).not.toHaveBeenCalled();
  });

  it("retries only the displayed failed session and restores choices after success", async () => {
    vi.mocked(api.retryNarrative).mockImplementation(async () => {
      currentSession = { ...failure, session_id: "retry-9", status: "complete", phase: "complete", terminal_outcome: "accepted", error: null };
      currentState = { ...state, has_pending: true, session_id: "retry-9", choices: ["New live choice"] };
      return { session_id: "retry-9", status: "processing", message: "started" };
    });
    mount();
    await expectFailure();
    fireEvent.click(screen.getByTestId("button-retry-generation"));
    await waitFor(() => expect(screen.getByTestId("choice-1")).toHaveTextContent("New live choice"));
    expect(api.retryNarrative).toHaveBeenCalledTimes(1);
    expect(api.retryNarrative).toHaveBeenCalledWith(4, "failed-8");
    expect(api.continueNarrative).not.toHaveBeenCalled();
    expect(screen.queryByTestId("generation-recovery")).not.toBeInTheDocument();
  });

  it("ignores an old terminal read that arrives after an explicit retry", async () => {
    let stale!: (session: GenerationSession) => void;
    mount();
    await expectFailure();
    vi.mocked(api.getActiveGeneration).mockImplementationOnce(() => new Promise((resolve) => { stale = resolve; }));
    boundary();
    await waitFor(() => expect(stale).toBeDefined());
    vi.mocked(api.retryNarrative).mockImplementation(async () => {
      currentSession = { ...failure, session_id: "retry-9", status: "initiated", phase: "writer", terminal_outcome: null, error: null };
      return { session_id: "retry-9", status: "processing", message: "started" };
    });
    fireEvent.click(screen.getByTestId("button-retry-generation"));
    await waitFor(() => expect(engine.phase).toBe("writer"));
    await act(async () => { stale(failure); });
    expect(engine.phase).toBe("writer");
    expect(engine.failedGeneration).toBeNull();
    expect(screen.queryByTestId("generation-recovery")).not.toBeInTheDocument();
    expect(api.retryNarrative).toHaveBeenCalledTimes(1);
  });

  it("leaves normal input open for a failure recorded before a committed action", async () => {
    currentSession = { ...failure, parent_chunk_id: null, error: "Ambiguous acceptance result" };
    vi.mocked(api.continueNarrative).mockImplementation(async () => {
      currentSession = { ...failure, session_id: "again-10", status: "initiated", phase: "writer", terminal_outcome: null, error: null };
      return { session_id: "again-10", status: "processing", message: "started" };
    });
    mount();
    await waitFor(() => expect(engine.generationError).toBe("Ambiguous acceptance result"));
    expect(engine.failedGeneration).toBeNull();
    expect(screen.queryByTestId("generation-recovery")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("input-freeform")).toBeEnabled());
    await act(async () => { expect(await engine.submitTurn({ userText: "Try the door" })).toBe(true); });
    expect(api.continueNarrative).toHaveBeenCalledTimes(1);
    expect(api.retryNarrative).not.toHaveBeenCalled();
  });

  it("rejects a mismatched terminal status and leaves controls disabled", async () => {
    vi.mocked(api.getGenerationStatus).mockResolvedValue({ ...failure, session_id: "another-session" });
    mount();
    await waitFor(() => expect(engine.generationError).toBe("Generation response identity mismatch"));
    expect(engine.failedGeneration).toBeNull();
    expect(screen.queryByTestId("choice-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("input-freeform")).toBeDisabled();
    expect(api.retryNarrative).not.toHaveBeenCalled();
  });

  it("a stale retry rejection refreshes the newer pending scene without replaying", async () => {
    vi.mocked(api.retryNarrative).mockImplementation(async () => {
      currentSession = { ...failure, session_id: "elsewhere-9", status: "complete", phase: "complete", terminal_outcome: "accepted", error: null };
      currentState = { ...state, has_pending: true, session_id: "elsewhere-9", choices: ["New live choice"] };
      throw new Error("409: Failed session changed");
    });
    mount();
    await expectFailure();
    fireEvent.click(screen.getByTestId("button-retry-generation"));
    await waitFor(() => expect(screen.getByTestId("choice-1")).toHaveTextContent("New live choice"));
    expect(api.retryNarrative).toHaveBeenCalledTimes(1);
    expect(api.continueNarrative).not.toHaveBeenCalled();
    expect(engine.failedGeneration).toBeNull();
  });
});
