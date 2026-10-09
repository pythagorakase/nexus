import {
  QueryClient,
  QueryClientProvider,
  focusManager,
} from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReturnRecap } from "@shared/schema";
import { ThemeProvider } from "@/contexts/ThemeContext";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import type { ChunkWithMetadata, SlotState } from "@/types/narrative";
import { NarrativePane } from "./NarrativePane";
import type { RecapSlotStates } from "./ReturnRecapCard";

// The pane and card run for real on seeded reader queries; the engine's turn
// submission is the gateway boundary. Each fixture is a response the gateway
// can produce for the slot state beside it.
const SLOT = 4;
const OTHER_SLOT = 3;
const MEMORIAL_CHOICES = [
  "Close your hand around the brass key and follow Rook into the rain.",
  "Show Ren the warrant is premature and ask for an hour.",
  "Take Ivo's call on the viaduct stairs.",
];
const DRAFT_CHOICES = [
  "Hand Ren the warrant and walk out into the rain.",
  "Ask Sister Calyx who signed it.",
];
const DRAFT_SESSION = "5f0c2a4e-8d6b-4f3e-9a51-2c7d1e0b8a93";
const EARLIER_ACTION = "Step in out of the rain.";
const LAST_ACTION = "Offer Rook the *thumb-to-temple* greeting.";

// The live reading loop at rest: chunk 102 was committed with the player's
// action, and the next draft waits below it with its own menu.
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
        sources: [{ kind: "chunk", id: 102 }],
      },
      {
        kind: "open_decision",
        text: DRAFT_CHOICES.join("\n"),
        sources: [{ kind: "draft", id: DRAFT_SESSION }],
      },
    ],
    ...overrides,
  };
}

// No draft pending and frontier 102 still open: the last action is the one
// chunk 101 records, and the open decision is chunk 102's own menu.
function openFrontierRecap(): ReturnRecap {
  const [location, roster] = recapOf().items;
  return recapOf({
    items: [
      location,
      roster,
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
  });
}

// The same recap told `by` chunks further into the episode: every chunk it
// cites moves on with the frontier.
function shifted(recap: ReturnRecap, by: number): ReturnRecap {
  return {
    ...recap,
    items: recap.items.map((item) => ({
      ...item,
      sources: item.sources.map((source) =>
        source.kind === "chunk" ? { ...source, id: source.id + by } : source,
      ),
    })),
  };
}

function chunk(
  id: number,
  scene: number,
  choiceText: string | null,
): ChunkWithMetadata {
  return {
    id,
    rawText: `Rain on the memorial glass, scene ${scene}.`,
    storytellerText: `Rain on the memorial glass, scene ${scene}.`,
    choiceText,
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

const PENDING_CHUNKS = [
  chunk(101, 1, EARLIER_ACTION),
  chunk(102, 2, LAST_ACTION),
];
const OPEN_FRONTIER_CHUNKS = [chunk(101, 1, LAST_ACTION), chunk(102, 2, null)];

function slotStateOf(slot: number, pending: boolean, frontier: number): SlotState {
  return {
    narrative_generation: {
      request_timeout_seconds: 10,
      poll_interval_seconds: 2,
      wake_gap_threshold_seconds: 15,
      stale_lease_timeout_seconds: 3600,
    },
    slot,
    story_id: "story-832",
    is_empty: false,
    is_wizard_mode: false,
    phase: null,
    subphase: null,
    thread_id: null,
    // A provisional draft has no chunk id until acceptance.
    current_chunk_id: pending ? null : frontier,
    has_pending: pending,
    frontier_clock: null,
    storyteller_text: pending ? "Ren's warrant is courteous and exact." : null,
    choices: pending ? DRAFT_CHOICES : MEMORIAL_CHOICES,
    session_id: pending ? DRAFT_SESSION : null,
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
    toastedFailureSessionId: null,
    isRecoveryLoading: false,
    retryGeneration: vi.fn(async () => true),
    isGenerating: false,
    completedGenerations: 0,
    submitTurn,
    regenerateTurn: vi.fn(async () => true),
  };
}

interface Story {
  recap: ReturnRecap;
  pending?: boolean;
  /** The page of the episode the reader fetched, in story order. */
  page?: ChunkWithMetadata[];
  /** The latest committed chunk, when it is not the last one on the page. */
  latest?: ChunkWithMetadata;
}

function seed(client: QueryClient, slot: number, story: Story) {
  const pending = story.pending ?? true;
  const page = story.page ?? (pending ? PENDING_CHUNKS : OPEN_FRONTIER_CHUNKS);
  const committed = story.latest ? [...page, story.latest] : page;
  const latest = committed[committed.length - 1];
  client.setQueryData(["/api/narrative/latest-chunk", slot], latest);
  client.setQueryData(
    ["/api/narrative/outline", slot],
    committed.map((c) => ({
      id: c.id,
      season: 1,
      episode: 1,
      scene: c.metadata!.scene,
      slug: c.metadata!.slug,
    })),
  );
  client.setQueryData(["/api/narrative/chunks", 1, 1, slot], {
    chunks: page,
    total: committed.length,
  });
  for (const c of committed) {
    client.setQueryData(["/api/narrative/chunks/context", c.id, slot], {
      characters: [],
      places: [],
    });
    client.setQueryData(["/api/narrative/chunk", c.id, slot], c);
  }
  client.setQueryData(["/api/narrative/recap", slot], story.recap);
  return engineOf(slotStateOf(slot, pending, latest.id));
}

interface ReaderView {
  slot: number;
  tab: "narrative" | "map";
  readingChunkId: number | null;
}

// The reader shell's part, played as NexusLayout plays it: it holds the recap
// state and mounts the narrative pane only while that tab is shown.
function Reader({
  view,
  engines,
}: {
  view: ReaderView;
  engines: ReadonlyMap<number, NarrativeEngine>;
}) {
  const recapState = useState<RecapSlotStates>({});
  if (view.tab !== "narrative") return <div data-testid="map-pane" />;
  return (
    <NarrativePane
      slot={view.slot}
      engine={engines.get(view.slot)!}
      readingChunkId={view.readingChunkId}
      onNavigate={vi.fn()}
      recapState={recapState}
    />
  );
}

function renderReader(story: Story) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(["/api/settings"], { ui: { theme: "veil" } });
  const engines = new Map([[SLOT, seed(client, SLOT, story)]]);
  let view: ReaderView = { slot: SLOT, tab: "narrative", readingChunkId: null };
  const tree = () => (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <Reader view={view} engines={engines} />
      </ThemeProvider>
    </QueryClientProvider>
  );
  const rendered = render(tree());
  const show = (next: Partial<ReaderView>) => {
    view = { ...view, ...next };
    rendered.rerender(tree());
  };
  return {
    ...rendered,
    client,
    show,
    readAt: (readingChunkId: number | null) => show({ readingChunkId }),
    seedSlot: (slot: number, other: Story) => {
      engines.set(slot, seed(client, slot, other));
    },
  };
}

function renderPane(recap: ReturnRecap, { pending = true } = {}) {
  return renderReader({ recap, pending });
}

// A long episode: the reader's page ends at chunk 102, before chunk 103, the
// latest committed chunk, which the recap describes and whose action it
// reports. None of the recap's lines is on screen already.
function pastThePage(): Story {
  return {
    recap: shifted(recapOf(), 1),
    page: [chunk(101, 1, EARLIER_ACTION), chunk(102, 2, "Knock twice, then wait.")],
    latest: chunk(103, 3, LAST_ACTION),
  };
}

const card = () => screen.queryByTestId("recap-card");
const trigger = () => screen.getByRole("button", { name: "Recap" });

function expectInOrder(elements: HTMLElement[]) {
  for (const [earlier, later] of elements.slice(1).map((el, i) => [elements[i], el])) {
    expect(earlier.compareDocumentPosition(later)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  }
}

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
afterEach(() => {
  vi.unstubAllGlobals();
  focusManager.setFocused(undefined);
});

describe("return recap card", () => {
  it("opens on its own when due, above the chunk it describes, not the draft", () => {
    renderPane(recapOf());

    const recap = screen.getByTestId("return-recap");
    expect(card()).toBeInTheDocument();
    expect(trigger()).toHaveAttribute("aria-expanded", "true");
    // chunk 101, then the recap, then chunk 102 (its setting, cast and
    // action), then the pending draft whose menu is the open decision.
    const stream = [
      screen.getByTestId("chunk-101"),
      recap,
      screen.getByTestId("chunk-102"),
      screen.getByTestId("chunk-pending"),
    ];
    for (const [earlier, later] of stream.slice(1).map((el, i) => [stream[i], el])) {
      expect(earlier.compareDocumentPosition(later)).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING,
      );
    }
    expect(
      Array.from(
        screen.getByTestId("recap-open_decision").querySelectorAll(".recap-text > div"),
        (line) => line.textContent,
      ),
    ).toEqual(DRAFT_CHOICES);
  });

  it("renders each sourced fact as served, names in natural case", () => {
    renderReader(pastThePage());

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
    expect(Array.from(options, (line) => line.textContent)).toEqual(DRAFT_CHOICES);
  });

  it("leads lines with icons: no heading, label or prose", () => {
    renderReader(pastThePage());

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
        ...DRAFT_CHOICES,
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

  it("stays closed across pane switches until a new action moves last_played", async () => {
    const { client, show } = renderPane(recapOf());
    fireEvent.click(trigger());
    expect(card()).not.toBeInTheDocument();

    // To the map and back: the narrative pane unmounts in between.
    show({ tab: "map" });
    expect(screen.queryByTestId("narrative-reader")).not.toBeInTheDocument();
    show({ tab: "narrative" });
    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    expect(card()).not.toBeInTheDocument();

    // An action accepted elsewhere, then another hiatus: a new recap is due.
    act(() => {
      client.setQueryData(
        ["/api/narrative/recap", SLOT],
        recapOf({ last_played: "2026-09-27T21:00:00+00:00" }),
      );
    });
    await waitFor(() => expect(card()).toBeInTheDocument());
    expect(fetch).not.toHaveBeenCalled();
  });

  it("keeps an on-demand recap open across pane switches", () => {
    const { show } = renderPane(recapOf({ due: false }));
    fireEvent.click(trigger());
    expect(card()).toBeInTheDocument();

    show({ tab: "map" });
    show({ tab: "narrative" });

    expect(card()).toBeInTheDocument();
    expect(trigger()).toHaveAttribute("aria-expanded", "true");
  });

  it("never lets one slot's closed recap close another's", () => {
    const { show, seedSlot } = renderPane(recapOf());
    // A clone of the same story, down to its last_played.
    seedSlot(OTHER_SLOT, { recap: recapOf() });
    fireEvent.click(trigger());
    expect(card()).not.toBeInTheDocument();

    show({ slot: OTHER_SLOT });
    expect(card()).toBeInTheDocument();

    show({ slot: SLOT });
    expect(card()).not.toBeInTheDocument();
  });

  it("falls in above the draft when its chunk lies past the fetched page", () => {
    renderReader(pastThePage());

    expect(screen.queryByTestId("chunk-103")).not.toBeInTheDocument();
    const recap = screen.getByTestId("return-recap");
    expect(card()).toBeInTheDocument();
    expect(trigger()).toHaveAttribute("aria-expanded", "true");
    expectInOrder([
      screen.getByTestId("chunk-101"),
      screen.getByTestId("chunk-102"),
      recap,
      screen.getByTestId("chunk-pending"),
    ]);
    // Chunk 103's action is not on screen, so the card carries it.
    expect(screen.getByTestId("recap-last_action")).toHaveTextContent(
      /^Offer Rook the thumb-to-temple greeting\.$/,
    );
  });

  it("falls in after the last fetched chunk, not repeating its action", () => {
    renderReader({
      recap: shifted(openFrontierRecap(), 1),
      pending: false,
      page: [chunk(101, 1, EARLIER_ACTION), chunk(102, 2, LAST_ACTION)],
      latest: chunk(103, 3, null),
    });

    const recap = screen.getByTestId("return-recap");
    expectInOrder([
      screen.getByTestId("chunk-102"),
      recap,
      screen.getByTestId("reader-nav-bottom"),
    ]);
    // Chunk 102 ends with the last action, just above the card.
    expect(
      Array.from(card()!.querySelectorAll("li"), (item) => item.dataset.testid),
    ).toEqual(["recap-location", "recap-roster", "recap-open_decision"]);
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

  it("does not repeat the action the chunk below it closes with", () => {
    renderPane(recapOf());

    // Chunk 102 was committed with the player's action when it was accepted
    // as a draft, and prints that action after its prose, below the card.
    const recap = screen.getByTestId("return-recap");
    const frontier = screen.getByTestId("chunk-102");
    expectInOrder([recap, frontier, screen.getByTestId("chunk-pending")]);
    expect(frontier.querySelector(".md-part.you")).toHaveTextContent(
      "Offer Rook the thumb-to-temple greeting.",
    );
    expect(screen.queryByTestId("recap-last_action")).not.toBeInTheDocument();
    expect(
      Array.from(card()!.querySelectorAll("li"), (item) => item.dataset.testid),
    ).toEqual(["recap-location", "recap-roster", "recap-open_decision"]);
  });

  it("does not repeat the action printed directly above it", () => {
    renderPane(openFrontierRecap(), { pending: false });

    const recap = screen.getByTestId("return-recap");
    expect(
      screen.getByTestId("chunk-101").compareDocumentPosition(recap),
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(
      recap.compareDocumentPosition(screen.getByTestId("chunk-102")),
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    // Chunk 101 ends with that action, just above the card.
    expect(screen.getByTestId("chunk-101")).toHaveTextContent(
      "Offer Rook the thumb-to-temple greeting.",
    );
    expect(screen.queryByTestId("recap-last_action")).not.toBeInTheDocument();
    expect(
      Array.from(card()!.querySelectorAll("li"), (item) => item.dataset.testid),
    ).toEqual(["recap-location", "recap-roster", "recap-open_decision"]);
  });

  it("asks the gateway again when the player returns to a tab left open", async () => {
    renderPane(recapOf({ due: false }));
    expect(card()).not.toBeInTheDocument();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url === `/api/narrative/recap?slot=${SLOT}`
          ? new Response(JSON.stringify(recapOf()), { status: 200 })
          : new Response(null, { status: 404 }),
      ),
    );

    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });

    await waitFor(() => expect(card()).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(`/api/narrative/recap?slot=${SLOT}`);
  });

  it("shows no glyph at all when nothing can be sourced", () => {
    renderPane(recapOf({ items: [] }));

    expect(screen.queryByTestId("return-recap")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Recap" })).not.toBeInTheDocument();
  });
});
