import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { NarrativePane } from "@/components/nexus/NarrativePane";
import type { GenerationSession, NarrativeRecovery, SlotState } from "@/types/narrative";
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
// The server's retry predicate holds: the failure is latest, bound to the
// unchanged frontier, whose recorded action consumed its menu.
const recovery: NarrativeRecovery = {
  session_id: "failed-8", parent_chunk_id: 9,
  error: "Unresolved place state update", error_class: "WireContractViolation",
};
const state: SlotState = {
  slot: 4, story_id: "story-951", is_empty: false, is_wizard_mode: false,
  phase: null, subphase: null, thread_id: null, current_chunk_id: 9, has_pending: false,
  frontier_clock: null, storyteller_text: "The preceding scene.",
  choices: [], session_id: null, recovery, model: "TEST",
  narrative_generation: settings,
};
// The same frontier with no recorded action: its menu is a live decision.
const openFrontier: SlotState = { ...state, choices: ["Live choice"], recovery: null };
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
  expect(screen.getByTestId("generation-failure")).toHaveTextContent("The next scene failed.");
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

  it("presents the failure as one short line and one Retry control", async () => {
    mount();
    await expectFailure();
    const line = screen.getByTestId("generation-failure");
    expect(line).toHaveAttribute("title", "Unresolved place state update");
    const section = screen.getByTestId("generation-recovery");
    expect(section).toHaveTextContent(/^◆Retry$/);
    expect(section.querySelectorAll("p, h3, details")).toHaveLength(0);
  });

  it("offers the committed menu as a live decision when no action is recorded", async () => {
    currentSession = null;
    currentState = { ...openFrontier };
    vi.mocked(api.continueNarrative).mockResolvedValue({ session_id: "next-10", status: "processing", message: "started" });
    mount();
    await waitFor(() => expect(screen.getByTestId("choice-1")).toBeEnabled());
    expect(screen.getByTestId("choice-1")).toHaveTextContent("Live choice");
    expect(screen.queryByTestId("generation-failure")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("choice-1"));
    expect(api.continueNarrative).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByTestId("input-freeform"), { key: "Enter" });
    await waitFor(() => expect(api.continueNarrative).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.continueNarrative).mock.calls[0][0]).toMatchObject({
      slot: 4, choice: 1, userText: "Live choice",
    });
  });

  it("never offers a Retry the server would reject once the recorded action is gone", async () => {
    // A restart or undo cleared the action; the failed session still names it.
    currentState = { ...openFrontier };
    mount();
    await waitFor(() => expect(screen.getByTestId("choice-1")).toBeEnabled());
    expect(screen.getByTestId("generation-failure")).toBeInTheDocument();
    expect(screen.queryByTestId("button-retry-generation")).not.toBeInTheDocument();
    await act(async () => { expect(await engine.retryGeneration()).toBe(false); });
    expect(api.retryNarrative).not.toHaveBeenCalled();
    vi.mocked(api.continueNarrative).mockResolvedValue({ session_id: "next-10", status: "processing", message: "started" });
    await act(async () => { expect(await engine.submitTurn({ choice: 1 })).toBe(true); });
    expect(api.continueNarrative).toHaveBeenCalledTimes(1);
  });

  it("keeps input closed until the failed frontier has been re-read", async () => {
    currentSession = { ...failure, status: "initiated", phase: "writer", terminal_outcome: null, error: null };
    currentState = { ...state, recovery: null };
    mount();
    await waitFor(() => expect(engine.phase).toBe("writer"));
    const pending: Array<(value: SlotState) => void> = [];
    vi.mocked(api.getSlotState).mockImplementation(
      () => new Promise<SlotState>((resolve) => { pending.push(resolve); }),
    );
    currentSession = { ...failure };
    boundary();
    await waitFor(() => expect(screen.getByTestId("generation-failure")).toBeInTheDocument());
    expect(engine.isRecoveryLoading).toBe(true);
    expect(screen.getByTestId("input-freeform")).toBeDisabled();
    fireEvent.change(screen.getByTestId("input-freeform"), { target: { value: "Too soon" } });
    fireEvent.keyDown(screen.getByTestId("input-freeform"), { key: "Enter" });
    expect(api.continueNarrative).not.toHaveBeenCalled();
    await act(async () => { pending.forEach((resolve) => resolve(state)); });
    await expectFailure();
    expect(engine.isRecoveryLoading).toBe(false);
  });

  it("disables Retry until the first durable read completes", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    vi.mocked(api.getActiveGeneration).mockImplementation(async () => {
      await gate;
      return currentSession;
    });
    mount();
    await waitFor(() => expect(screen.getByTestId("button-retry-generation")).toBeInTheDocument());
    expect(engine.isRecoveryLoading).toBe(true);
    expect(screen.getByTestId("button-retry-generation")).toBeDisabled();
    fireEvent.click(screen.getByTestId("button-retry-generation"));
    expect(api.retryNarrative).not.toHaveBeenCalled();
    await act(async () => { release(); });
    await waitFor(() => expect(screen.getByTestId("button-retry-generation")).toBeEnabled());
    expect(engine.isRecoveryLoading).toBe(false);
    vi.mocked(api.retryNarrative).mockResolvedValue({ session_id: "retry-9", status: "processing", message: "started" });
    fireEvent.click(screen.getByTestId("button-retry-generation"));
    await waitFor(() => expect(api.retryNarrative).toHaveBeenCalledTimes(1));
    expect(api.retryNarrative).toHaveBeenCalledWith(4, "failed-8");
  });

  it("disables Retry while a newer failure's frontier is re-read", async () => {
    mount();
    await expectFailure();
    await waitFor(() => expect(screen.getByTestId("button-retry-generation")).toBeEnabled());
    const pending: Array<(value: SlotState) => void> = [];
    vi.mocked(api.getSlotState).mockImplementation(
      () => new Promise<SlotState>((resolve) => { pending.push(resolve); }),
    );
    // A later attempt failed elsewhere; the displayed recovery is now stale.
    currentSession = { ...failure, session_id: "failed-9" };
    boundary();
    await waitFor(() => expect(engine.isRecoveryLoading).toBe(true));
    expect(screen.getByTestId("button-retry-generation")).toBeDisabled();
    fireEvent.click(screen.getByTestId("button-retry-generation"));
    expect(api.retryNarrative).not.toHaveBeenCalled();
    const newer = { ...state, recovery: { ...recovery, session_id: "failed-9" } };
    await act(async () => { pending.forEach((resolve) => resolve(newer)); });
    await waitFor(() => expect(screen.getByTestId("button-retry-generation")).toBeEnabled());
    vi.mocked(api.retryNarrative).mockResolvedValue({ session_id: "retry-10", status: "processing", message: "started" });
    fireEvent.click(screen.getByTestId("button-retry-generation"));
    await waitFor(() => expect(api.retryNarrative).toHaveBeenCalledTimes(1));
    expect(api.retryNarrative).toHaveBeenCalledWith(4, "failed-9");
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
    currentState = { ...openFrontier };
    vi.mocked(api.continueNarrative).mockImplementation(async () => {
      currentSession = { ...failure, session_id: "again-10", status: "initiated", phase: "writer", terminal_outcome: null, error: null };
      return { session_id: "again-10", status: "processing", message: "started" };
    });
    mount();
    await waitFor(() => expect(engine.generationError).toBe("Ambiguous acceptance result"));
    // The failure stays visible, but nothing recorded means nothing to retry.
    expect(screen.getByTestId("generation-failure")).toHaveAttribute("title", "Ambiguous acceptance result");
    expect(screen.queryByTestId("generation-recovery")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("input-freeform")).toBeEnabled());
    expect(screen.getByTestId("choice-1")).toHaveTextContent("Live choice");
    expect(screen.getByTestId("choice-1")).toBeEnabled();
    await act(async () => { expect(await engine.submitTurn({ userText: "Try the door" })).toBe(true); });
    expect(api.continueNarrative).toHaveBeenCalledTimes(1);
    expect(api.retryNarrative).not.toHaveBeenCalled();
  });

  it("enters recovery when the same failed session gains its parent on a later poll", async () => {
    const { toast } = await import("@/hooks/use-toast");
    currentSession = { ...failure, parent_chunk_id: null, error: "CancelledError" };
    currentState = { ...openFrontier };
    mount();
    await waitFor(() => expect(engine.generationError).toBe("CancelledError"));
    expect(screen.queryByTestId("generation-recovery")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("input-freeform")).toBeEnabled());
    // The cancelled route abandoned first; the worker's commit binds the parent afterwards.
    currentSession = { ...failure, parent_chunk_id: 9, error: "CancelledError" };
    currentState = { ...state, recovery: { ...recovery, error: "CancelledError" } };
    boundary();
    await waitFor(() => expect(screen.getByTestId("generation-recovery")).toBeInTheDocument());
    expect(engine.failedGeneration?.parent_chunk_id).toBe(9);
    expect(screen.queryByTestId("input-freeform")).not.toBeInTheDocument();
    expect(screen.queryByTestId("choice-1")).not.toBeInTheDocument();
    expect(api.continueNarrative).not.toHaveBeenCalled();
    expect(api.retryNarrative).not.toHaveBeenCalled();
    expect(vi.mocked(toast)).toHaveBeenCalledTimes(1);
    // The retry now targets the bound failure without any remount.
    vi.mocked(api.retryNarrative).mockImplementation(async () => {
      currentSession = { ...failure, session_id: "retry-9", status: "complete", phase: "complete", terminal_outcome: "accepted", error: null };
      currentState = { ...state, has_pending: true, session_id: "retry-9", choices: ["New live choice"] };
      return { session_id: "retry-9", status: "processing", message: "started" };
    });
    fireEvent.click(screen.getByTestId("button-retry-generation"));
    await waitFor(() => expect(screen.getByTestId("choice-1")).toHaveTextContent("New live choice"));
    expect(api.retryNarrative).toHaveBeenCalledWith(4, "failed-8");
  });

  it("rejects a mismatched terminal status and leaves controls disabled", async () => {
    vi.mocked(api.getGenerationStatus).mockResolvedValue({ ...failure, session_id: "another-session" });
    currentState = { ...openFrontier };
    mount();
    await waitFor(() => expect(engine.generationError).toBe("Generation response identity mismatch"));
    expect(engine.failedGeneration).toBeNull();
    await waitFor(() => expect(screen.getByTestId("choice-1")).toBeDisabled());
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
