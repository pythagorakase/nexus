import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/contexts/ThemeContext";
import type { NarrativeEngine } from "@/hooks/useNarrativeEngine";
import type { ChunkWithMetadata, SlotState } from "@/types/narrative";
import { NarrativePane } from "./NarrativePane";

const SLOT = 2;

beforeAll(() => {
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true,
    value: vi.fn(),
  });
});

function makeChunk(
  id: number,
  scene: number,
  hasInlineSceneMarkup = false,
): ChunkWithMetadata {
  return {
    id,
    rawText: `Chunk ${id}`,
    storytellerText: `Chunk ${id}`,
    choiceText: null,
    choiceObject: null,
    createdAt: new Date("2026-07-10T12:00:00Z"),
    hasInlineSceneMarkup,
    metadata: {
      id,
      chunkId: id,
      season: 5,
      episode: 6,
      scene,
      worldLayer: "primary",
      worldTime: "2087-11-03T22:47:00+00:00",
      timeDelta: null,
      generationDate: new Date("2026-07-10T12:00:00Z"),
      slug: `S05E06_${String(scene).padStart(3, "0")}`,
    },
  };
}

function makeEngine(slotState: SlotState): NarrativeEngine {
  return {
    slotState,
    slotStateError: null,
    isSlotStateLoading: false,
    phase: null,
    skaldStatus: "READY",
    elapsedMs: 0,
    generationError: null,
    isGenerating: false,
    completedGenerations: 0,
    submitTurn: vi.fn(async () => undefined),
  };
}

function renderPane(
  chunks: ChunkWithMetadata[],
  readingChunkId: number | null = null,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  const latest = chunks[chunks.length - 1];
  queryClient.setQueryData(["/api/settings"], { ui: { theme: "veil" } });
  queryClient.setQueryData(["/api/narrative/latest-chunk", SLOT], latest);
  queryClient.setQueryData(
    ["/api/narrative/outline", SLOT],
    chunks.map((chunk) => ({
      id: chunk.id,
      season: chunk.metadata!.season,
      episode: chunk.metadata!.episode,
      scene: chunk.metadata!.scene,
      slug: chunk.metadata!.slug,
    })),
  );
  queryClient.setQueryData(
    ["/api/narrative/chunks", 5, 6, SLOT],
    { chunks, total: chunks.length },
  );
  const headChunkId = readingChunkId ?? latest.id;
  queryClient.setQueryData(["/api/narrative/chunks/context", headChunkId, SLOT], {
    characters: [],
    places: [],
  });
  if (readingChunkId !== null) {
    queryClient.setQueryData(
      ["/api/narrative/chunk", readingChunkId, SLOT],
      chunks.find((chunk) => chunk.id === readingChunkId),
    );
  }
  const slotState: SlotState = {
    slot: SLOT,
    is_empty: false,
    is_wizard_mode: false,
    phase: null,
    subphase: null,
    thread_id: null,
    current_chunk_id: latest.id,
    has_pending: readingChunkId === null,
    storyteller_text: readingChunkId === null ? "Pending prose" : null,
    choices: [],
    session_id: null,
    model: null,
  };

  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <NarrativePane
          slot={SLOT}
          engine={makeEngine(slotState)}
          typewriterMsPerChar={0}
          readingChunkId={readingChunkId}
          onNavigate={vi.fn()}
        />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("NarrativePane intertitle boundaries", () => {
  it("shows the first scene and scene changes, but not repeats or inline markup", () => {
    renderPane([
      makeChunk(101, 1),
      makeChunk(102, 1),
      makeChunk(103, 2),
      makeChunk(104, 3, true),
    ]);

    const intertitles = screen.getAllByTestId("intertitle");
    expect(intertitles).toHaveLength(2);
    expect(intertitles[0]).toHaveTextContent("S05E06 · Scene 1");
    expect(intertitles[1]).toHaveTextContent("S05E06 · Scene 2");
    expect(screen.queryByText("S05E06 · Scene 3")).not.toBeInTheDocument();
    expect(screen.getByTestId("chunk-pending")).toBeInTheDocument();
  });

  it("shows the first historical chunk when it has no inline scene markup", () => {
    renderPane([makeChunk(201, 7)], 201);

    expect(screen.getByTestId("intertitle")).toHaveTextContent(
      "S05E06 · Scene 7",
    );
  });

  it("suppresses the historical intertitle for legacy inline markup", () => {
    renderPane([makeChunk(202, 8, true)], 202);

    expect(screen.queryByTestId("intertitle")).not.toBeInTheDocument();
  });
});
