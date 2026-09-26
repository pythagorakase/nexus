import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { useNarrativeEngine } from "@/hooks/useNarrativeEngine";
import type { GenerationSession, SlotState } from "@/types/narrative";
import { NarrativePane } from "./NarrativePane";

vi.mock("@/hooks/use-toast", () => ({ toast: vi.fn() }));

// The gateway is the boundary: the real engine, narrative-api fetchers and
// pane run against these routes, which answer from the durable state below.
const settings = {
  request_timeout_seconds: 10, poll_interval_seconds: 1000,
  wake_gap_threshold_seconds: 15, stale_lease_timeout_seconds: 3600,
};
const INCUMBENT = "The ledger lies open on the counter.";
const REPLACEMENT = "The ledger is gone; only its dust remains.";
const pendingState: SlotState = {
  slot: 4, story_id: "story-773", is_empty: false, is_wizard_mode: false,
  phase: null, subphase: null, thread_id: null, current_chunk_id: 9, has_pending: true,
  frontier_clock: null, storyteller_text: INCUMBENT,
  choices: ["Read the ledger", "Ask Sana"], session_id: "draft-12", recovery: null,
  model: "TEST", narrative_generation: settings,
};
const session = (overrides: Partial<GenerationSession>): GenerationSession => ({
  slot: 4, session_id: "draft-12", operation: "continue", status: "complete",
  phase: "complete", terminal_outcome: null, replaced_by_session_id: null,
  chunk_id: null, parent_chunk_id: 9, created_at: "2026-09-26T08:00:00Z",
  heartbeat_at: "2026-09-26T08:01:00Z", expires_at: null, error: null,
  error_class: null, ...overrides,
});

let slotState: SlotState;
let sessions: Map<string, GenerationSession>;
let latest: string | null;
let regenerate: (body: Record<string, unknown>) => Response | Promise<Response>;
let regenerateBodies: Array<Record<string, unknown>>;
let engine: ReturnType<typeof useNarrativeEngine>;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  });

beforeAll(() => {
  Object.defineProperty(Element.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
});
beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  slotState = { ...pendingState };
  sessions = new Map([["draft-12", session({})]]);
  latest = "draft-12";
  regenerateBodies = [];
  regenerate = () => {
    sessions.set("regen-13", session({
      session_id: "regen-13", operation: "regenerate", status: "initiated",
      phase: "writer", created_at: "2026-09-26T08:02:00Z",
    }));
    latest = "regen-13";
    return json({ session_id: "regen-13", status: "processing", message: "Regenerating" });
  };
  vi.stubGlobal("WebSocket", class { close() {} });
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://reader.test");
    if (url.pathname === "/api/settings") return new Response(null, { status: 200 });
    if (url.pathname === "/api/preferences") return json({ narrative_generation: settings });
    if (url.pathname === "/api/slot/4/state") return json(slotState);
    if (url.pathname === "/api/narrative/latest-chunk") return new Response("", { status: 404 });
    if (url.pathname === "/api/narrative/outline") return json([]);
    if (url.pathname === "/api/narrative/active") return json(latest ? sessions.get(latest) : null);
    if (url.pathname.startsWith("/api/narrative/status/")) {
      return json(sessions.get(decodeURIComponent(url.pathname.split("/").pop()!)));
    }
    if (url.pathname === "/api/narrative/regenerate" && init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      regenerateBodies.push(body);
      return await regenerate(body);
    }
    throw new Error(`Unexpected ${init?.method ?? "GET"} ${url.pathname}`);
  }));
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
const pending = () => screen.getByTestId("chunk-pending");
const toggle = () => screen.getByRole("button", { name: "Regenerate" });
const note = () => screen.getByRole("textbox", { name: "Note for the regenerated scene" });

async function openNote() {
  await waitFor(() => expect(toggle()).toBeEnabled());
  fireEvent.click(toggle());
  expect(toggle()).toHaveAttribute("aria-expanded", "true");
  return note();
}

describe("pending-turn regeneration", () => {
  it("offers one quiet glyph on the pending block, with a capped, unlabeled note", async () => {
    mount();
    const field = await openNote();
    expect(pending()).toContainElement(toggle());
    expect(toggle()).toHaveTextContent(/^↻$/);
    expect(field).toHaveFocus();
    expect(field).toHaveAttribute("maxLength", "500");
    expect(field).not.toHaveAttribute("placeholder");
    expect(screen.getByRole("button", { name: "Regenerate now" })).toHaveTextContent(/^↵$/);
    // Glyphs only: no label, heading or prose beside the note.
    const row = toggle().parentElement!;
    expect(row.querySelectorAll("label, p, h3")).toHaveLength(0);
    expect(row).toHaveTextContent(/^↵↻$/);
    fireEvent.keyDown(field, { key: "Escape" });
    expect(screen.queryByRole("textbox", { name: "Note for the regenerated scene" })).not.toBeInTheDocument();
    expect(regenerateBodies).toEqual([]);
  });

  it.each([
    ["nothing is pending", { has_pending: false, session_id: null, storyteller_text: "Committed." }],
    ["the pending draft has no session", { session_id: null }],
  ])("is absent when %s", async (_case, overrides) => {
    slotState = { ...pendingState, ...overrides };
    mount();
    await waitFor(() => expect(screen.getByTestId("choice-1")).toBeEnabled());
    expect(screen.queryByRole("button", { name: "Regenerate" })).not.toBeInTheDocument();
  });

  it("re-rolls the pending session with its note and keeps the incumbent until the replacement lands", async () => {
    mount();
    const field = await openNote();
    fireEvent.change(field, { target: { value: "  darker, plz  " } });
    fireEvent.keyDown(field, { key: "Enter" });
    await waitFor(() => expect(engine.phase).toBe("writer"));
    expect(regenerateBodies).toEqual([{ slot: 4, session_id: "draft-12", note: "darker, plz" }]);
    // Generating: the incumbent stays, every affordance is gone.
    expect(pending()).toHaveTextContent(INCUMBENT);
    expect(screen.getByTestId("status-generating")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Regenerate" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("choice-1")).not.toBeInTheDocument();
    // The replacement is staged: the next durable read swaps the prose.
    sessions.set("regen-13", session({
      session_id: "regen-13", operation: "regenerate", created_at: "2026-09-26T08:02:00Z",
    }));
    slotState = { ...pendingState, session_id: "regen-13", storyteller_text: REPLACEMENT };
    boundary();
    await waitFor(() => expect(pending()).toHaveTextContent(REPLACEMENT));
    expect(pending()).not.toHaveTextContent(INCUMBENT);
    await waitFor(() => expect(toggle()).toBeEnabled());
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("generation-failure")).not.toBeInTheDocument();
    expect(regenerateBodies).toHaveLength(1);
  });

  it("sends no note when the note is blank, and one request for a double send", async () => {
    const { toast } = await import("@/hooks/use-toast");
    let release!: () => void;
    const started = regenerate;
    regenerate = async (body) => {
      await new Promise<void>((resolve) => { release = resolve; });
      return started(body);
    };
    mount();
    const field = await openNote();
    const send = screen.getByRole("button", { name: "Regenerate now" });
    fireEvent.keyDown(field, { key: "Enter" });
    fireEvent.keyDown(field, { key: "Enter" });
    fireEvent.click(send);
    fireEvent.click(send);
    await waitFor(() => expect(regenerateBodies).toHaveLength(1));
    await act(async () => { release(); });
    await waitFor(() => expect(engine.phase).toBe("writer"));
    expect(regenerateBodies).toEqual([{ slot: 4, session_id: "draft-12" }]);
    expect(vi.mocked(toast)).not.toHaveBeenCalled();
  });

  it("keeps the incumbent and reports a failed re-roll loudly", async () => {
    const { toast } = await import("@/hooks/use-toast");
    mount();
    const field = await openNote();
    fireEvent.change(field, { target: { value: "Vienna, not Prague" } });
    fireEvent.keyDown(field, { key: "Enter" });
    await waitFor(() => expect(engine.phase).toBe("writer"));
    sessions.set("regen-13", session({
      session_id: "regen-13", operation: "regenerate", status: "error", phase: "writer",
      terminal_outcome: "error", error: "Writer refused the draft",
      error_class: "WireContractViolation", created_at: "2026-09-26T08:02:00Z",
    }));
    boundary();
    await waitFor(() => expect(screen.getByTestId("generation-failure")).toHaveTextContent("The regeneration failed."));
    expect(screen.getByTestId("generation-failure")).toHaveAttribute("title", "Writer refused the draft");
    expect(screen.getByTestId("generation-failure")).toHaveAttribute("role", "alert");
    expect(vi.mocked(toast)).toHaveBeenCalledWith(expect.objectContaining({
      description: "Writer refused the draft", variant: "destructive",
    }));
    expect(pending()).toHaveTextContent(INCUMBENT);
    // The incumbent's draft is still the live decision, and the note survives.
    await waitFor(() => expect(screen.getByTestId("choice-1")).toBeEnabled());
    fireEvent.click(toggle());
    expect(note()).toHaveValue("Vienna, not Prague");
  });

  it("keeps the note open and the incumbent when the server refuses the re-roll", async () => {
    const { toast } = await import("@/hooks/use-toast");
    regenerate = () => json({ detail: { message: "Another narrative generation owns this slot." } }, 409);
    mount();
    const field = await openNote();
    fireEvent.change(field, { target: { value: "darker" } });
    fireEvent.keyDown(field, { key: "Enter" });
    await waitFor(() => expect(vi.mocked(toast)).toHaveBeenCalledWith(expect.objectContaining({
      title: "Generation Failed", variant: "destructive",
    })));
    expect(String(vi.mocked(toast).mock.calls.at(-1)![0].description)).toContain("409");
    expect(engine.phase).toBeNull();
    expect(pending()).toHaveTextContent(INCUMBENT);
    await waitFor(() => expect(note()).toHaveValue("darker"));
    expect(regenerateBodies).toHaveLength(1);
  });
});
