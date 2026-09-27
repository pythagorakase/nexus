import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReturnRecap } from "@shared/schema";
import { ThemeProvider } from "@/contexts/ThemeContext";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import type { ChunkWithMetadata, SlotState } from "@/types/narrative";
import { NarrativePane } from "./NarrativePane";

// The pane and card run for real on seeded reader queries; the engine's turn
// submission is the gateway boundary.
const SLOT = 4;
const MEMORIAL_CHOICES = [
  "Close your hand around the brass key and follow Rook into the rain.",
  "Show Ren the warrant is premature and ask for an hour.",
  "Take Ivo's call on the viaduct stairs.",
];
const LAST_ACTION = "Offer Rook the *thumb-to-temple* greeting.";

function recapOf(overrides: Partial<ReturnRecap> = {}): ReturnRecap {
  return {
    due: true,
    last_played: "2026-09-26T09:00:00+00:00",
    items: [
      {
        kind: "location",
        text: "Lantern Quay Memorial Hall, Transit Viaduct",
        sources: [
          { kind: "chunk", id: 102 },
          { kind: "place", id: 7 },
          { kind: "place", id: 12 },
        ],
      },
      {
        kind: "roster",
        text: "Mara Vey, Elian Rook, Ren Vale",
        sources: [
          { kind: "chunk", id: 102 },
          { kind: "character", id: 1 },
          { kind: "character", id: 4 },
          { kind: "character", id: 5 },
        ],
      },
      {
        kind: "last_action",
        text: LAST_ACTION,
        sources: [{ kind: "chunk", id: 101 }],
      },
      {
        kind: "open_decision",
        text: MEMORIAL_CHOICES.join("\n"),
        sources: [{ kind: "chunk", id: 102 }],
      },
    ],
    ...overrides,
  };
}

function chunk(id: number, scene: number): ChunkWithMetadata {
  return {
    id,
    rawText: `Rain on the memorial glass, scene ${scene}.`,
    storytellerText: `Rain on the memorial glass, scene ${scene}.`,
    choiceText: id === 101 ? LAST_ACTION : null,
    choiceObject: null,
    createdAt: new Date("2026-09-25T12:00:00Z"),
    hasInlineSceneMarkup: false,
    metadata: {
      id,
      chunkId: id,
      season: 1,
      episode: 1,
      scene,
      worldLayer: "primary",
      worldTime: "2189-10-17T19:12:00+00:00",
      worldTimeFace: "17 Oct 2189 · 19:12",
      timeDelta: null,
      generationDate: new Date("2026-09-25T12:00:00Z"),
      slug: `S01E01_${String(scene).padStart(3, "0")}`,
    },
  };
}

const CHUNKS = [chunk(101, 1), chunk(102, 2)];

function slotStateOf(pending: boolean): SlotState {
  return {
    narrative_generation: {
      request_timeout_seconds: 10,
      poll_interval_seconds: 2,
      wake_gap_threshold_seconds: 15,
      stale_lease_timeout_seconds: 3600,
    },
    slot: SLOT,
    story_id: "story-832",
    is_empty: false,
    is_wizard_mode: false,
    phase: null,
    subphase: null,
    thread_id: null,
    current_chunk_id: 102,
    has_pending: pending,
    frontier_clock: null,
    storyteller_text: pending ? "Ren's warrant is courteous and exact." : null,
    choices: MEMORIAL_CHOICES,
    session_id: pending ? "draft-832" : null,
    model: null,
  };
}

let submitTurn: ReturnType<typeof vi.fn<NarrativeEngine["submitTurn"]>>;

function engineOf(slotState: SlotState): NarrativeEngine {
  return {
    slotState,
    slotStateError: null,
    isSlotStateLoading: false,
    phase: null,
    skaldStatus: "READY",
    elapsedMs: 0,
    generationError: null,
    failedGeneration: null,
    isRecoveryLoading: false,
    retryGeneration: vi.fn(async () => true),
    isGenerating: false,
    completedGenerations: 0,
    submitTurn,
    regenerateTurn: vi.fn(async () => true),
  };
}

function renderPane(recap: ReturnRecap, { pending = false } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(["/api/settings"], { ui: { theme: "veil" } });
  client.setQueryData(["/api/narrative/latest-chunk", SLOT], CHUNKS[1]);
  client.setQueryData(
    ["/api/narrative/outline", SLOT],
    CHUNKS.map((c) => ({
      id: c.id,
      season: 1,
      episode: 1,
      scene: c.metadata!.scene,
      slug: c.metadata!.slug,
    })),
  );
  client.setQueryData(["/api/narrative/chunks", 1, 1, SLOT], {
    chunks: CHUNKS,
    total: CHUNKS.length,
  });
  for (const id of [101, 102]) {
    client.setQueryData(["/api/narrative/chunks/context", id, SLOT], {
      characters: [],
      places: [],
    });
    client.setQueryData(
      ["/api/narrative/chunk", id, SLOT],
      CHUNKS.find((c) => c.id === id),
    );
  }
  client.setQueryData(["/api/narrative/recap", SLOT], recap);
  const engine = engineOf(slotStateOf(pending));
  const pane = (readingChunkId: number | null) => (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <NarrativePane
          slot={SLOT}
          engine={engine}
          readingChunkId={readingChunkId}
          onNavigate={vi.fn()}
        />
      </ThemeProvider>
    </QueryClientProvider>
  );
  const view = render(pane(null));
  return { ...view, readAt: (id: number | null) => view.rerender(pane(id)) };
}

const card = () => screen.queryByTestId("recap-card");
const trigger = () => screen.getByRole("button", { name: "Recap" });

async function send(text: string) {
  const field = screen.getByTestId("input-freeform");
  fireEvent.change(field, { target: { value: text } });
  await act(async () => {
    fireEvent.keyDown(field, { key: "Enter" });
  });
}

beforeAll(() => {
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true,
    value: vi.fn(),
  });
});
beforeEach(() => {
  localStorage.clear();
  submitTurn = vi.fn<NarrativeEngine["submitTurn"]>(async () => true);
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 404 })));
});
afterEach(() => vi.unstubAllGlobals());

describe("return recap card", () => {
  it("opens on its own when due, just above the frontier chunk", () => {
    renderPane(recapOf());

    const recap = screen.getByTestId("return-recap");
    expect(card()).toBeInTheDocument();
    expect(trigger()).toHaveAttribute("aria-expanded", "true");
    const order = (a: Element, b: Element) => a.compareDocumentPosition(b);
    expect(order(screen.getByTestId("chunk-101"), recap)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(order(recap, screen.getByTestId("chunk-102"))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("renders each sourced fact as served, names in natural case", () => {
    renderPane(recapOf());

    expect(screen.getByTestId("recap-location")).toHaveTextContent(
      /^Lantern Quay Memorial Hall, Transit Viaduct$/,
    );
    expect(screen.getByTestId("recap-roster")).toHaveTextContent(
      /^Mara Vey, Elian Rook, Ren Vale$/,
    );
    // The player's action keeps its prose dialect.
    const action = screen.getByTestId("recap-last_action");
    expect(action).toHaveTextContent(/^Offer Rook the thumb-to-temple greeting\.$/);
    expect(action.querySelector("em")).toHaveTextContent("thumb-to-temple");
    const options = screen.getByTestId("recap-open_decision")
      .querySelectorAll(".recap-text > div");
    expect(Array.from(options, (line) => line.textContent)).toEqual(MEMORIAL_CHOICES);
  });

  it("leads lines with icons: no heading, label or prose", () => {
    renderPane(recapOf());

    const recap = card()!;
    expect(recap.querySelectorAll("h1, h2, h3, h4, h5, h6, p, label")).toHaveLength(0);
    const items = Array.from(recap.querySelectorAll("li"));
    expect(items).toHaveLength(4);
    for (const item of items) {
      expect(item.querySelector("svg[aria-hidden='true']")).not.toBeNull();
    }
    expect(recap).toHaveTextContent(
      [
        "Lantern Quay Memorial Hall, Transit Viaduct",
        "Mara Vey, Elian Rook, Ren Vale",
        "Offer Rook the thumb-to-temple greeting.",
        ...MEMORIAL_CHOICES,
      ].join(""),
      { normalizeWhitespace: false },
    );
  });

  it("offers an unlabeled glyph that opens the recap on demand when not due", () => {
    renderPane(recapOf({ due: false }));

    expect(card()).not.toBeInTheDocument();
    const glyph = trigger();
    expect(glyph).toHaveTextContent(/^$/);
    expect(glyph).not.toHaveAttribute("title");
    expect(glyph.querySelector("svg[aria-hidden='true']")).not.toBeNull();
    expect(glyph).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(glyph);

    expect(card()).toBeInTheDocument();
    expect(glyph).toHaveAttribute("aria-expanded", "true");
    expect(glyph).toHaveAttribute("aria-controls", card()!.id);
  });

  it("dismisses in client state only, and stays dismissed across history", () => {
    const { readAt } = renderPane(recapOf());

    fireEvent.click(trigger());
    expect(card()).not.toBeInTheDocument();

    readAt(101);
    expect(screen.queryByTestId("return-recap")).not.toBeInTheDocument();
    readAt(null);
    expect(card()).not.toBeInTheDocument();
    expect(trigger()).toHaveAttribute("aria-expanded", "false");

    // Nothing was sent or stored: no request, and no browser record.
    expect(fetch).not.toHaveBeenCalled();
    expect(submitTurn).not.toHaveBeenCalled();
    expect(Object.keys(localStorage).filter((key) => /recap/i.test(key))).toEqual([]);
  });

  it("closes on the next accepted action, but not on a refused one", async () => {
    renderPane(recapOf());

    submitTurn.mockResolvedValueOnce(false);
    await send("Knock twice, then wait.");
    expect(submitTurn).toHaveBeenCalledTimes(1);
    expect(card()).toBeInTheDocument();

    await send("Knock twice, then wait.");
    expect(submitTurn).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(card()).not.toBeInTheDocument());
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
  });

  it("closes an on-demand recap on the next accepted action too", async () => {
    renderPane(recapOf({ due: false }));
    fireEvent.click(trigger());
    expect(card()).toBeInTheDocument();

    await send("Take Ivo's call on the viaduct stairs.");

    await waitFor(() => expect(card()).not.toBeInTheDocument());
  });

  it("sits above a pending draft when the draft is the frontier", () => {
    renderPane(recapOf(), { pending: true });

    const recap = screen.getByTestId("return-recap");
    expect(
      recap.compareDocumentPosition(screen.getByTestId("chunk-pending")),
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(
      screen.getByTestId("chunk-102").compareDocumentPosition(recap),
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("shows no glyph at all when nothing can be sourced", () => {
    renderPane(recapOf({ items: [] }));

    expect(screen.queryByTestId("return-recap")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Recap" })).not.toBeInTheDocument();
  });
});
