import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BackstageTurnResponse } from "@/types/backstage";
import { BackstageDrawer } from "./BackstageDrawer";

const PAYLOAD: BackstageTurnResponse = {
  header: {
    slot: 4,
    chunk_id: 203,
    chunk_label: "S01E07_203",
    turn_label: "t.17",
    world_time: null,
    skald_status: "idle",
  },
  correspondence: {
    digest: null,
    compacted_through_chunk_id: null,
    digest_fresh: false,
    exchanges: [],
    held_threads: [],
  },
  state_writes: { rows: [], history: [] },
  orrery: {
    rows: [
      {
        template_id: "stroll",
        actor_name: "Celia",
        target_name: null,
        magnitude: 0.1,
        brief: "Celia walks nearby.",
        branch_label: "Pace the near ground",
        event_type: "stroll_taken",
        drive_band: "anchored_routine",
        attention: "background",
      },
      {
        template_id: "evade_pursuers",
        actor_name: "Victor",
        target_name: null,
        magnitude: 0.75,
        brief: "Victor moves toward safety.",
        branch_label: "Take cover",
        event_type: "threat_issued",
        drive_band: "crisis_constraint",
        attention: "meaningful",
      },
    ],
    counts: { fired: 2, pressures: 0, events: 2 },
    history: [],
  },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Backstage attention", () => {
  it("marks each existing row without adding attention text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify(PAYLOAD), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
      ),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    try {
      render(
        <QueryClientProvider client={client}>
          <BackstageDrawer slot={4} onClose={() => {}} />
        </QueryClientProvider>,
      );
      const stroll = await screen.findByText("stroll");
      expect(stroll.closest(".nexus-backstage-orrery-row")).toHaveAttribute(
        "data-attention",
        "background",
      );
      expect(
        screen.getByText("evade_pursuers").closest(".nexus-backstage-orrery-row"),
      ).toHaveAttribute("data-attention", "meaningful");
      expect(screen.getByTestId("backstage-drawer")).not.toHaveTextContent(
        "background",
      );
    } finally {
      cleanup();
      client.clear();
    }
  });
});
