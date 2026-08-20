import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DeveloperModeProvider } from "@/contexts/DeveloperModeContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { SETTINGS_QUERY_KEY } from "@/hooks/useSettings";
import type { BackstageTurnResponse } from "@/types/backstage";
import type { SettingsPayload } from "@/types/settings";
import { NexusLayout } from "./NexusLayout";

vi.mock("@/hooks/useNarrativeEngine", () => ({
  useNarrativeEngine: () => ({
    slotState: undefined,
    slotStateError: null,
    isSlotStateLoading: false,
    phase: null,
    skaldStatus: "READY",
    elapsedMs: 0,
    generationError: null,
    isGenerating: false,
    completedGenerations: 0,
    submitTurn: vi.fn(),
  }),
}));

vi.mock("@/lib/narrative-api", () => ({
  getUserCharacter: () => Promise.resolve(null),
}));

vi.mock("./TopBar", () => ({ TopBar: () => <header data-testid="mock-topbar" /> }));
vi.mock("./NarrativePane", () => ({
  NarrativePane: () => <div data-testid="mock-narrative" />,
}));
vi.mock("./RightLedger", () => ({ RightLedger: () => <aside /> }));
vi.mock("./CharactersPane", () => ({ CharactersPane: () => <div /> }));
vi.mock("./MapPane", () => ({ MapPane: () => <div /> }));
vi.mock("./SettingsPane", () => ({ SettingsPane: () => <div /> }));

const PAYLOAD: BackstageTurnResponse = {
  header: {
    slot: 4,
    chunk_id: 203,
    chunk_label: "S01E07_203",
    turn_label: "t.203",
    world_time: "2189-10-17T18:24:00-04:00",
    skald_status: "idle",
  },
  correspondence: {
    digest: "Victor is cultivating Celia as an informant.",
    compacted_through_chunk_id: 200,
    exchanges: [
      {
        chunk_id: 203,
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
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("activeSlot", "4");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(PAYLOAD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
  });

  it("hides the sigil without effective developer mode", () => {
    localStorage.setItem("nexus-developer-mode", "true");
    renderLayout({
      ui: { theme: "veil" },
      orrery: { dashboard: { enabled: false } },
    });

    expect(screen.queryByTestId("rail-backstage")).not.toBeInTheDocument();
    expect(screen.queryByTestId("backstage-drawer")).not.toBeInTheDocument();
  });

  it("opens, renders, and closes through the sigil and guarded keyboard", async () => {
    localStorage.setItem("nexus-developer-mode", "true");
    renderLayout({
      ui: { theme: "veil" },
      orrery: {
        dashboard: {
          enabled: true,
          backstage_poll_busy_ms: 2000,
          backstage_poll_idle_ms: 8000,
        },
      },
    });

    fireEvent.click(screen.getByTestId("rail-backstage"));
    expect(await screen.findByTestId("backstage-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("backstage-digest")).toHaveTextContent(
      "Victor is cultivating Celia as an informant.",
    );
    expect(screen.getByText(/SKALD → GAIA/)).toBeInTheDocument();
    expect(screen.getByText(/GAIA → SKALD/)).toBeInTheDocument();
    expect(screen.getByText(/seeded t\.196 · 2 deferred · unfired/)).toBeInTheDocument();
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
