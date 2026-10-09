import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BackstageTurnObservation, BackstageTurnResponse } from "@/types/backstage";
import { BackstageDrawer, formatElapsed } from "./BackstageDrawer";

const ACCEPTED: BackstageTurnObservation = {
  schema_version: 3,
  generation_session: "a-1",
  read_at: "2026-10-07T23:00:00Z",
  ledger_days_read: ["2026-10-07"],
  terminal_outcome: "accepted",
  wall_time: { seconds: 11.059 },
  choice_ready_at: "2026-10-07T22:59:58Z",
  seconds_to_choice_ready: 11.059,
  attempts: ["skald_writer", "gaia"].map((seat) => ({
    generation_session: "a-1", seat, attempt: 1, model: "TEST", outcome: "accepted",
    window: { provenance: "attempt_manifest", input_tokens: 4420 },
    usage: { provenance: "provider_usage_ledger", input_tokens: 1000, output_tokens: 800 },
  })),
  usage_totals: {
    critical_path: { provenance: "provider_usage_ledger", events: 2, providers: ["test"], comparable: true, input_tokens: 2000, output_tokens: 1600 },
    background: { provenance: "unknown", events: 0, providers: [], comparable: true, input_tokens: "unknown", output_tokens: "unknown" },
    overall: { provenance: "provider_usage_ledger", events: 2, providers: ["test"], comparable: true, input_tokens: "unknown", output_tokens: "unknown" },
  },
  jobs: { total: 1, entries: [{ queue: "correspondence_compaction", id: 4, state: "queued", terminal: false, usage: { provenance: "unknown", input_tokens: "unknown", output_tokens: "unknown" } }] },
};

const PENDING: BackstageTurnObservation = {
  schema_version: 3,
  generation_session: "p-1",
  read_at: "2026-10-07T23:05:10Z",
  ledger_days_read: ["2026-10-07"],
  terminal_outcome: null,
  wall_time: { seconds: 6.2 },
  choice_ready_at: "2026-10-07T23:05:06Z",
  seconds_to_choice_ready: 6.2,
  attempts: [{ generation_session: "p-1", seat: "skald_writer", attempt: 1, model: "TEST", outcome: null, window: { provenance: "attempt_manifest", input_tokens: 4420 }, usage: { provenance: "provider_usage_ledger", input_tokens: 1000, output_tokens: 800 } }],
  usage_totals: {
    critical_path: { provenance: "provider_usage_ledger", events: 1, providers: ["test"], comparable: true, input_tokens: 1000, output_tokens: 800 },
    background: { provenance: null, events: 0, providers: [], comparable: true, input_tokens: 0, output_tokens: 0 },
    overall: { provenance: "provider_usage_ledger", events: 1, providers: ["test"], comparable: true, input_tokens: 1000, output_tokens: 800 },
  },
  jobs: { total: 0, entries: [] },
};

const ACCEPTED_SUMMARY = "critical 2,000/1,600 · background unknown/unknown · wall 11.1s · choices ready 11.1s";
const PENDING_SUMMARY = "critical 1,000/800 · background 0/0 · wall 6.2s · choices ready 6.2s";
const LEGACY_DETAIL = "chunk 203: no generation session (accepted before session binding)";
const PENDING_DETAIL = "session p-1: no generation session (staged before session binding)";

const PAYLOAD: BackstageTurnResponse = {
  header: {
    slot: 4,
    chunk_id: 203,
    chunk_label: "S01E07_203",
    turn_label: "t.17",
    world_time: null,
    elapsed_seconds: null,
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
  economics: {
    accepted: { status: "unavailable", generation_session: null, detail: LEGACY_DETAIL, observation: null },
    pending: null,
  },
};

const clients: QueryClient[] = [];
function renderDrawer(payload: BackstageTurnResponse) {
  vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(
    new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } }),
  )));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  return render(<QueryClientProvider client={client}><BackstageDrawer slot={4} onClose={() => {}} /></QueryClientProvider>);
}

function observedPayload(): BackstageTurnResponse {
  return {
    ...PAYLOAD,
    header: { ...PAYLOAD.header, elapsed_seconds: 420 },
    economics: {
      accepted: { status: "observed", generation_session: "a-1", detail: null, observation: structuredClone(ACCEPTED) },
      pending: { status: "observed", generation_session: "p-1", detail: null, observation: structuredClone(PENDING) },
    },
  };
}

afterEach(() => {
  cleanup();
  clients.splice(0).forEach((client) => client.clear());
  vi.unstubAllGlobals();
});

describe("Backstage elapsed time and observation", () => {
  it("keeps the first header exact and explains an unavailable accepted turn", async () => {
    renderDrawer({ ...PAYLOAD, header: { ...PAYLOAD.header, turn_label: "t.1" } });
    expect(await screen.findByText("slot 04 · t.1")).toHaveTextContent(/^slot 04 · t\.1$/);
    expect(screen.getByRole("button", { name: /ECONOMICS/ })).toHaveTextContent("unavailable");
    expect(screen.getByText(LEGACY_DETAIL)).toBeInTheDocument();
    expect(screen.queryByTestId("backstage-economics-pending")).not.toBeInTheDocument();
    expect(screen.getByText("stroll")).toBeInTheDocument();
  });

  it("renders both observations with provenance and does not repeat the accepted summary", async () => {
    renderDrawer(observedPayload());
    expect(await screen.findByText("slot 04 · t.17 · +7 min")).toBeInTheDocument();
    const pending = screen.getByTestId("backstage-economics-pending");
    expect(within(pending).getByText(PENDING_SUMMARY)).toBeInTheDocument();
    expect(pending.firstElementChild).toHaveTextContent(PENDING_SUMMARY);
    expect(within(pending).getByText("#1 TEST · open · window 4,420 [attempt_manifest] · 1,000/800 [provider_usage_ledger]")).toBeInTheDocument();
    expect(screen.getAllByText(ACCEPTED_SUMMARY)).toHaveLength(1);
    expect(screen.getByText(ACCEPTED_SUMMARY)).toHaveClass("nexus-backstage-section-summary");
    expect(screen.getAllByText("#1 TEST · accepted · window 4,420 [attempt_manifest] · 1,000/800 [provider_usage_ledger]")).toHaveLength(2);
    expect(screen.getByText("#4 · queued · unknown/unknown [unknown]")).toBeInTheDocument();
    expect(screen.getByText("read 2026-10-07T23:00:00Z").parentElement).toHaveAttribute("title", "a-1");
    expect(within(pending).getByText("read 2026-10-07T23:05:10Z").parentElement).toHaveAttribute("title", "p-1");
    expect(within(pending).getByText("2026-10-07")).toBeInTheDocument();
    expect(within(pending).getByText("skald_writer").closest(".nexus-backstage-write-row")).toHaveAttribute("title", "p-1");
    expect(screen.getByText("stroll").closest(".nexus-backstage-orrery-row")).toHaveAttribute("data-attention", "background");
    expect(screen.getByText("evade_pursuers").closest(".nexus-backstage-orrery-row")).toHaveAttribute("data-attention", "meaningful");
  });

  it("keeps the other sections usable when a pending draft has no bound session", async () => {
    renderDrawer({ ...PAYLOAD, economics: { ...PAYLOAD.economics, pending: { status: "unavailable", generation_session: "p-1", detail: PENDING_DETAIL, observation: null } } });
    const pending = await screen.findByTestId("backstage-economics-pending");
    expect(pending).toHaveTextContent(PENDING_DETAIL);
    expect(screen.getByText("stroll")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /CORRESPONDENCE/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /STATE WRITES/ })).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /ECONOMICS/ });
    fireEvent.click(toggle);
    expect(screen.queryByTestId("backstage-economics-pending")).not.toBeInTheDocument();
    expect(screen.getByText("stroll")).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.getByTestId("backstage-economics-pending")).toHaveTextContent(PENDING_DETAIL);
  });

  it.each([
    [0, "+0 min"], [59, "+0 min"], [420, "+7 min"], [3600, "+1 h"],
    [3660, "+1 h 1 min"], [86400, "+1 d"], [90000, "+1 d 1 h"], [-120, "−2 min"],
  ])("formats %s elapsed seconds as %s", (seconds, expected) => {
    expect(formatElapsed(Number(seconds))).toBe(expected);
  });
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
