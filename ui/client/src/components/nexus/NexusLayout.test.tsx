import { useEffect, useRef } from "react";
import { useMapView } from "./MapViewContext";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DeveloperModeProvider } from "@/contexts/DeveloperModeContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { SETTINGS_QUERY_KEY } from "@/hooks/useSettings";
import type { BackstageTurnResponse } from "@/types/backstage";
import type { GenerationSession } from "@/types/narrative";
import type { SettingsPayload } from "@/types/settings";
import { NexusLayout } from "./NexusLayout";

const engine = vi.hoisted(() => {
  const failedGeneration: GenerationSession = {
    slot: 4,
    session_id: "failed-8",
    operation: "continue",
    status: "error",
    phase: "writer",
    terminal_outcome: "error",
    replaced_by_session_id: null,
    supersedes_session_id: null,
    chunk_id: null,
    parent_chunk_id: 9,
    created_at: "2026-09-26T08:00:00Z",
    heartbeat_at: "2026-09-26T08:01:00Z",
    expires_at: null,
    error: "Writer timed out",
    error_class: "TimeoutError",
  };
  return { failedGeneration };
});
const mapViews = vi.hoisted(() => ({ boxes: [] as Array<{ x: number; y: number; width: number; height: number }> }));
const topBar = vi.hoisted(() => ({ props: [] as Array<Record<string, unknown>> }));

vi.mock("@/hooks/useNarrativeEngine", () => ({
  useNarrativeEngine: () => ({
    slotState: undefined,
    slotStateError: null,
    isSlotStateLoading: false,
    phase: null,
    skaldStatus: "READY",
    elapsedMs: 0,
    generationError: null,
    failedGeneration: engine.failedGeneration,
    toastedFailureSessionId: null,
    isGenerating: false,
    completedGenerations: 0,
    submitTurn: vi.fn(),
  }),
}));

vi.mock("@/lib/narrative-api", () => ({
  getUserCharacter: () => Promise.resolve(null),
}));

vi.mock("./TopBar", () => ({
  TopBar: (props: Record<string, unknown>) => {
    topBar.props.push(props);
    return <header data-testid="mock-topbar" />;
  },
}));
vi.mock("./NarrativePane", () => ({
  NarrativePane: () => <div data-testid="mock-narrative" />,
}));
vi.mock("./RightLedger", () => ({ RightLedger: () => <aside /> }));
vi.mock("./CharactersPane", () => ({ CharactersPane: () => <div /> }));
vi.mock("./MapPane", () => ({
  MapPane: () => {
    const { viewBox, setViewBox } = useMapView();
    const initial = useRef(viewBox);
    useEffect(() => {
      mapViews.boxes.push(initial.current);
      setViewBox({ x: 15, y: 20, width: 300, height: 200 });
    }, [setViewBox]);
    return <div />;
  },
}));
vi.mock("./SettingsPane", () => ({ SettingsPane: () => <div /> }));

const PAYLOAD: BackstageTurnResponse = {
  header: {
    slot: 4,
    chunk_id: 203,
    chunk_label: "S01E07_203",
    turn_label: "t.17",
    world_time: "2189-10-17T18:24:00-04:00",
    skald_status: "idle",
  },
  correspondence: {
    digest: "Victor is cultivating Celia as an informant.",
    compacted_through_chunk_id: 200,
    digest_fresh: false,
    exchanges: [
      {
        chunk_id: 203,
        turn_label: "t.17",
        letters: [
          { seat: "writer", body: "Keep the marker beneath the prose." },
          { seat: "gaia", body: "Acknowledged; state remains quiet." },
        ],
      },
    ],
    held_threads: [
      {
        template_id: "evade_pursuers",
        actor_name: "Celia",
        streak_length: 2,
        start_tick: 196,
        start_turn_label: "t.12",
      },
    ],
  },
  state_writes: {
    rows: [
      {
        kind: "character",
        label: "Celia",
        field: "characters.current_activity",
        old_value: null,
        new_value: "watching",
        operation: "set",
        mechanism: null,
        held: false,
      },
      {
        kind: "relation",
        label: "Celia → Victor",
        field: "valence",
        old_value: 0.1,
        new_value: 0.12,
        operation: "set",
        mechanism: null,
        held: true,
      },
      {
        kind: "place",
        label: "The Glow",
        field: "crowded",
        old_value: null,
        new_value: "crowded",
        operation: "bestow",
        mechanism: null,
        held: false,
      },
    ],
    history: [
      {
        chunk_id: 202,
        turn_label: "t.202",
        writes: 3,
        fired: null,
        pressures: null,
        events: null,
      },
    ],
  },
  orrery: {
    rows: [
      {
        template_id: "evade_pursuers",
        actor_name: "Celia",
        target_name: "Victor",
        magnitude: 0.75,
        brief: "Celia moves toward safety.",
        branch_label: "danger closes in",
        event_type: "threat_issued",
        drive_band: "crisis_constraint",
      },
    ],
    counts: { fired: 1, pressures: 1, events: 1 },
    history: [
      {
        chunk_id: 202,
        turn_label: "t.202",
        writes: null,
        fired: 0,
        pressures: 1,
        events: 0,
      },
    ],
  },
};

function renderLayout(settings: SettingsPayload) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  queryClient.setQueryData([...SETTINGS_QUERY_KEY], settings);
  render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <DeveloperModeProvider>
          <NexusLayout />
        </DeveloperModeProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("NexusLayout Backstage", () => {
  let healthStatus: number;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("activeSlot", "4");
    healthStatus = 404;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        if (String(input).endsWith("/api/dev/backstage/health")) {
          return Promise.resolve(new Response(null, { status: healthStatus }));
        }
        return Promise.resolve(
          new Response(JSON.stringify(PAYLOAD), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }),
    );
  });

  it("hides the sigil when the health probe reports the gate closed", async () => {
    localStorage.setItem("nexus-developer-mode", "true");
    renderLayout({
      ui: { theme: "veil" },
    });

    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith("/api/dev/backstage/health"),
    );
    expect(screen.queryByTestId("rail-backstage")).not.toBeInTheDocument();
    expect(screen.queryByTestId("backstage-drawer")).not.toBeInTheDocument();
  });

  it("opens, renders, and closes through the sigil and guarded keyboard", async () => {
    healthStatus = 200;
    localStorage.setItem("nexus-developer-mode", "true");
    renderLayout({
      ui: { theme: "veil" },
      orrery: {
        dashboard: {
          backstage_poll_busy_ms: 2000,
          backstage_poll_idle_ms: 8000,
        },
      },
    });

    fireEvent.click(await screen.findByTestId("rail-backstage"));
    expect(await screen.findByTestId("backstage-drawer")).toBeInTheDocument();
    expect(await screen.findByTestId("backstage-digest")).toHaveTextContent(
      "Victor is cultivating Celia as an informant.",
    );
    expect(screen.getByText(/SKALD → GAIA/)).toBeInTheDocument();
    expect(screen.getByText(/GAIA → SKALD/)).toBeInTheDocument();
    expect(screen.getByText(/SKALD → GAIA · t\.17/)).toBeInTheDocument();
    expect(screen.getByTestId("backstage-held-thread")).toHaveTextContent(
      /seeded\s+t\.12 · 2 deferred · unfired/,
    );
    expect(screen.queryByText(/digest refreshed/)).not.toBeInTheDocument();
    expect(screen.getByText("held")).toBeInTheDocument();
    expect(screen.getByLabelText("magnitude")).toBeInTheDocument();
    expect(screen.getByText(/1 fired · 1 pressures · 1 events/)).toBeInTheDocument();
    expect(
      screen.getByText(
        "read-only · entries fade as turns commit · #617 exclusions untouched",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Close Backstage"));
    expect(screen.queryByTestId("backstage-drawer")).not.toBeInTheDocument();

    fireEvent.keyDown(window, { key: "`" });
    expect(await screen.findByTestId("backstage-drawer")).toBeInTheDocument();

    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    fireEvent.keyDown(input, { key: "`" });
    expect(screen.getByTestId("backstage-drawer")).toBeInTheDocument();

    input.blur();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByTestId("backstage-drawer")).not.toBeInTheDocument(),
    );
    input.remove();
  });
});

describe("NexusLayout operator strip", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("activeSlot", "4");
    topBar.props.length = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 404 })),
    );
  });

  it("hands the strip the engine's durable failure for its announcer", () => {
    renderLayout({ ui: { theme: "veil" } });

    const latest = topBar.props[topBar.props.length - 1];
    expect(latest.failedGeneration).toBe(engine.failedGeneration);
    expect(latest.toastedFailureSessionId).toBeNull();
    expect(latest.skaldStatus).toBe("READY");
  });
});


describe("NexusLayout pane ownership and rail order", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("activeSlot", "4");
    window.history.replaceState(null, "", "/nexus");
    mapViews.boxes.length = 0;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })));
  });

  it("keeps one map view owner across tab switches", () => {
    renderLayout({ ui: { theme: "veil" } });
    fireEvent.click(screen.getByRole("button", { name: "Map" }));
    fireEvent.click(screen.getByRole("button", { name: "Characters" }));
    fireEvent.click(screen.getByRole("button", { name: "Map" }));
    expect(mapViews.boxes).toEqual([
      { x: 0, y: 0, width: 800, height: 600 },
      { x: 15, y: 20, width: 300, height: 200 },
    ]);
  });

  it("puts the rail after the content at narrow width", () => {
    let notify: (event: { matches: boolean }) => void = () => {};
    vi.stubGlobal("matchMedia", vi.fn((media: string) => ({
      matches: true,
      media,
      addEventListener: (_: string, listener: typeof notify) => { notify = listener; },
      removeEventListener: vi.fn(),
    })));
    renderLayout({ ui: { theme: "veil" } });
    const main = document.querySelector("main.nexus-content")!;
    const nav = () => screen.getByRole("navigation", { name: "Primary navigation" });
    expect(main.compareDocumentPosition(nav()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    act(() => notify({ matches: false }));
    expect(main.compareDocumentPosition(nav()) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    act(() => notify({ matches: true }));
    expect(main.compareDocumentPosition(nav()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
