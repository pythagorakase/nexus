/**
 * The generation announcer driven by the real narrative engine through the
 * real layout: only the narrative HTTP fetchers (the network boundary) and
 * the panes that do not take part are replaced.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DeveloperModeProvider } from "@/contexts/DeveloperModeContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { LOCAL_MODELS_STATUS_KEY } from "@/hooks/useLocalModels";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import * as api from "@/lib/narrative-api";
import type {
  ContinueNarrativeResponse,
  GenerationSession,
  SkaldStatus,
  SlotState,
} from "@/types/narrative";
import { NexusLayout } from "./NexusLayout";

vi.mock("@/lib/narrative-api", () => ({
  continueNarrative: vi.fn(),
  retryNarrative: vi.fn(),
  getSlotState: vi.fn(),
  getActiveGeneration: vi.fn(),
  getGenerationStatus: vi.fn(),
  getRecoveryPreferences: vi.fn(),
  getUserCharacter: vi.fn(async () => null),
}));

const reader = vi.hoisted(() => ({ engine: null as NarrativeEngine | null }));
vi.mock("./NarrativePane", () => ({
  NarrativePane: ({ engine }: { engine: NarrativeEngine }) => {
    reader.engine = engine;
    return <div />;
  },
}));
vi.mock("./RightLedger", () => ({ RightLedger: () => <aside /> }));

const settings = {
  request_timeout_seconds: 10,
  poll_interval_seconds: 1000,
  wake_gap_threshold_seconds: 1000,
  stale_lease_timeout_seconds: 3600,
};
const frontier: SlotState = {
  slot: 4,
  story_id: "story-777",
  is_empty: false,
  is_wizard_mode: false,
  phase: null,
  subphase: null,
  thread_id: null,
  current_chunk_id: 9,
  has_pending: false,
  frontier_clock: null,
  storyteller_text: "The preceding scene.",
  choices: ["Go on"],
  session_id: null,
  recovery: null,
  model: "TEST",
  narrative_generation: settings,
};
const running: GenerationSession = {
  slot: 4,
  session_id: "next-10",
  operation: "continue",
  status: "initiated",
  phase: "writer",
  terminal_outcome: null,
  replaced_by_session_id: null,
  supersedes_session_id: null,
  chunk_id: null,
  parent_chunk_id: null,
  created_at: "2026-09-26T08:00:00Z",
  heartbeat_at: "2026-09-26T08:00:30Z",
  expires_at: null,
  error: null,
  error_class: null,
};

/** The running attempt as the server records it after a failure. */
const failed = (): GenerationSession => ({
  ...running,
  status: "error",
  terminal_outcome: "error",
  error: "Writer timed out",
  error_class: "TimeoutError",
});

let session: GenerationSession | null;

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("activeSlot", "4");
  vi.clearAllMocks();
  reader.engine = null;
  session = null;
  vi.mocked(api.getSlotState).mockImplementation(async () => frontier);
  vi.mocked(api.getActiveGeneration).mockImplementation(async () => session);
  vi.mocked(api.getGenerationStatus).mockImplementation(async () => session!);
  vi.mocked(api.getRecoveryPreferences).mockResolvedValue({
    narrative_generation: settings,
  });
  vi.stubGlobal("WebSocket", class { close() {} });
  // Connectivity probe reachable; developer gate closed.
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 404 })));
});
afterEach(() => vi.unstubAllGlobals());

function mountLayout() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(["/api/settings"], { ui: { theme: "veil" } });
  client.setQueryData([...LOCAL_MODELS_STATUS_KEY], {
    models_dir: "/models",
    system_ram_gb: 48,
    catalog: [],
    installed: [],
    active: null,
  });
  render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <DeveloperModeProvider>
          <NexusLayout />
        </DeveloperModeProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
  // Every message the live region presents, sampled at each checkpoint.
  const spoken: string[] = [];
  const settle = async (status: SkaldStatus) => {
    await waitFor(() => expect(reader.engine?.skaldStatus).toBe(status));
    const text = screen.getByRole("status").textContent ?? "";
    if (text && text !== spoken[spoken.length - 1]) spoken.push(text);
  };
  return { spoken, settle };
}

/** A read the engine makes on any boundary (tab visible, socket open). */
const boundary = () =>
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });

/** Submit a turn whose continue request stays pending until released. */
async function submitPending() {
  let release!: (response: ContinueNarrativeResponse) => void;
  vi.mocked(api.continueNarrative).mockImplementation(
    () =>
      new Promise((resolve) => {
        release = resolve;
      }),
  );
  let accepted!: Promise<boolean>;
  await act(async () => {
    accepted = reader.engine!.submitTurn({ choice: 1 });
  });
  return async () => {
    session = { ...running };
    await act(async () => {
      release({ session_id: "next-10", status: "processing", message: "started" });
      expect(await accepted).toBe(true);
    });
  };
}

describe("generation announcer on the live engine", () => {
  it("does not report a failure when a read clears the phase mid-submit", async () => {
    const { spoken, settle } = mountLayout();
    await waitFor(() => expect(reader.engine?.isRecoveryLoading).toBe(false));
    await settle("READY");

    const release = await submitPending();
    await settle("TRANSMITTING");
    // The server has not recorded the attempt yet, so this read finds no
    // active session and the engine drops its optimistic phase.
    await boundary();
    await settle("READY");
    expect(reader.engine!.failedGeneration).toBeNull();

    await release();
    await settle("GENERATING");
    session = {
      ...running,
      status: "complete",
      phase: "complete",
      terminal_outcome: "accepted",
      chunk_id: 10,
    };
    await boundary();
    await settle("RECEIVING");

    expect(spoken).toEqual(["Generation started", "Generation complete"]);
  });

  it("reports the engine's durable failure of the observed turn once", async () => {
    const { spoken, settle } = mountLayout();
    await waitFor(() => expect(reader.engine?.isRecoveryLoading).toBe(false));

    const release = await submitPending();
    await settle("TRANSMITTING");
    await release();
    await settle("GENERATING");

    session = failed();
    await boundary();
    await waitFor(() =>
      expect(reader.engine!.failedGeneration?.session_id).toBe("next-10"),
    );
    await settle("READY");
    // The engine re-reports the same failure once its parent chunk binds.
    session = { ...session, parent_chunk_id: 9 };
    await boundary();
    await waitFor(() =>
      expect(reader.engine!.failedGeneration?.parent_chunk_id).toBe(9),
    );
    await settle("READY");

    expect(spoken).toEqual(["Generation started", "Generation failed"]);
  });

  it("stays silent for the failure the engine replays on load", async () => {
    session = failed();
    const { spoken, settle } = mountLayout();

    await waitFor(() =>
      expect(reader.engine?.failedGeneration?.session_id).toBe("next-10"),
    );
    await settle("READY");

    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    expect(spoken).toEqual([]);
  });
});
