import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown, { type Components } from "react-markdown";
import { ChevronRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useFonts } from "@/contexts/FontContext";
import type { Episode, NarrativeChunk, ChunkMetadata, Season } from "@shared/schema";

interface ChunkWithMetadata extends NarrativeChunk {
  metadata?: ChunkMetadata;
}

interface ChunkResponse {
  chunks: ChunkWithMetadata[];
  total: number;
}

const markdownComponents: Components = {
  p: ({ node, ...props }) => (
    <p className="mb-4 last:mb-0 text-base leading-relaxed" {...props} />
  ),
  strong: ({ node, ...props }) => (
    <strong className="font-semibold text-foreground" {...props} />
  ),
  em: ({ node, ...props }) => <em className="italic" {...props} />,
  ul: ({ node, ...props }) => (
    <ul className="mb-4 ml-5 list-disc space-y-2 marker:text-primary" {...props} />
  ),
  ol: ({ node, ...props }) => (
    <ol className="mb-4 ml-5 list-decimal space-y-2 marker:text-primary" {...props} />
  ),
  li: ({ node, ...props }) => <li className="text-base leading-relaxed" {...props} />,
  h1: ({ node, ...props }) => (
    <h1 className="mt-6 mb-3 text-2xl font-semibold tracking-wide" {...props} />
  ),
  h2: ({ node, ...props }) => (
    <h2 className="mt-5 mb-3 text-xl font-semibold tracking-wide" {...props} />
  ),
  h3: ({ node, ...props }) => (
    <h3 className="mt-4 mb-2 text-lg font-semibold tracking-wide" {...props} />
  ),
  blockquote: ({ node, ...props }) => (
    <blockquote
      className="mb-4 border-l-2 border-primary/60 pl-4 italic text-foreground/90"
      {...props}
    />
  ),
  code: ({ node, inline, ...props }: any) => (
    <code
      className={
        inline
          ? "rounded bg-muted px-1.5 py-0.5 text-sm"
          : "block rounded bg-muted px-3 py-2 text-sm"
      }
      {...props}
    />
  ),
};

interface EpisodeNodeProps {
  seasonId: number;
  episode: Episode;
  isOpen: boolean;
  onToggle: () => void;
  onSelectChunk: (chunk: ChunkWithMetadata) => void;
  selectedChunkId: number | null;
  onEnsureChunkSelected: (chunk: ChunkWithMetadata) => void;
}

function EpisodeNode({
  seasonId,
  episode,
  isOpen,
  onToggle,
  onSelectChunk,
  selectedChunkId,
  onEnsureChunkSelected,
}: EpisodeNodeProps) {
  const episodeKey = `${seasonId}-${episode.episode}`;

  const {
    data,
    isLoading,
    isError,
    error,
    isFetching,
  } = useQuery<ChunkResponse>({
    queryKey: ["/api/narrative/chunks", seasonId, episode.episode],
    queryFn: async () => {
      const response = await fetch(`/api/narrative/chunks/${episode.episode}?limit=200`);
      if (!response.ok) {
        const message = (await response.text()) || "Failed to load chunks";
        throw new Error(message);
      }
      return response.json();
    },
    enabled: isOpen,
    staleTime: 5 * 60 * 1000,
  });

  const chunks = data?.chunks ?? [];

  useEffect(() => {
    if (!isOpen || chunks.length === 0) {
      return;
    }

    const containsSelected =
      selectedChunkId !== null && chunks.some((chunk) => chunk.id === selectedChunkId);

    if (!containsSelected) {
      onEnsureChunkSelected(chunks[0]);
    }
  }, [chunks, isOpen, onEnsureChunkSelected, selectedChunkId]);

  return (
    <Collapsible open={isOpen} onOpenChange={onToggle}>
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          className="w-full justify-start gap-2 font-mono text-xs hover-elevate h-8 text-foreground"
          data-testid={`button-episode-${episodeKey}`}
        >
          <ChevronRight
            className={`h-3 w-3 transition-transform ${isOpen ? "rotate-90" : ""}`}
          />
          Episode {episode.episode}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pl-4 space-y-1">
        {isLoading && (
          <div className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Loading chunks…
          </div>
        )}
        {isError && (
          <div className="px-2 py-3 text-xs text-destructive">
            Failed to load chunks: {error instanceof Error ? error.message : "Unknown error"}
          </div>
        )}
        {chunks.map((chunk) => {
          const isSelected = chunk.id === selectedChunkId;
          return (
            <Button
              key={chunk.id}
              variant="ghost"
              className={`w-full justify-start font-mono text-xs hover-elevate h-8 text-foreground ${
                isSelected ? "bg-accent text-accent-foreground" : ""
              }`}
              onClick={() => onSelectChunk(chunk)}
              data-testid={`button-chunk-${chunk.id}`}
            >
              <span className="truncate">
                {chunk.metadata?.slug || `Chunk ${chunk.id}`}
              </span>
            </Button>
          );
        })}
        {isOpen && !isLoading && !chunks.length && !isError && (
          <div className="px-2 py-3 text-xs text-muted-foreground">
            No chunks found for this episode.
          </div>
        )}
        {isFetching && !isLoading && (
          <div className="px-2 py-2 text-[11px] text-muted-foreground/70">
            Refreshing…
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

interface SeasonNodeProps {
  season: Season;
  isOpen: boolean;
  onToggle: () => void;
  openEpisodes: string[];
  onToggleEpisode: (episodeKey: string) => void;
  onEnsureEpisodeOpen: (episodeKey: string) => void;
  onSelectChunk: (chunk: ChunkWithMetadata) => void;
  selectedChunkId: number | null;
  onEnsureChunkSelected: (chunk: ChunkWithMetadata) => void;
}

function SeasonNode({
  season,
  isOpen,
  onToggle,
  openEpisodes,
  onToggleEpisode,
  onEnsureEpisodeOpen,
  onSelectChunk,
  selectedChunkId,
  onEnsureChunkSelected,
}: SeasonNodeProps) {
  const {
    data: episodes = [],
    isLoading,
    isError,
    error,
  } = useQuery<Episode[]>({
    queryKey: ["/api/narrative/episodes", season.id],
    enabled: isOpen,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!isOpen || !episodes.length) {
      return;
    }

    const hasOpenEpisode = openEpisodes.some((key) => key.startsWith(`${season.id}-`));
    if (!hasOpenEpisode) {
      const firstEpisode = episodes[0];
      onEnsureEpisodeOpen(`${season.id}-${firstEpisode.episode}`);
    }
  }, [episodes, isOpen, onEnsureEpisodeOpen, openEpisodes, season.id]);

  return (
    <Collapsible open={isOpen} onOpenChange={onToggle}>
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          className="w-full justify-start gap-2 font-mono text-xs hover-elevate h-8 text-foreground"
          data-testid={`button-season-${season.id}`}
        >
          <ChevronRight
            className={`h-3 w-3 transition-transform ${isOpen ? "rotate-90" : ""}`}
          />
          Season {season.id}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pl-4 space-y-1">
        {isLoading && (
          <div className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Loading episodes…
          </div>
        )}
        {isError && (
          <div className="px-2 py-3 text-xs text-destructive">
            Failed to load episodes: {error instanceof Error ? error.message : "Unknown error"}
          </div>
        )}
        {episodes.map((episode) => {
          const episodeKey = `${season.id}-${episode.episode}`;
          const isEpisodeOpen = openEpisodes.includes(episodeKey);
          return (
            <EpisodeNode
              key={episodeKey}
              seasonId={season.id}
              episode={episode}
              isOpen={isEpisodeOpen}
              onToggle={() => onToggleEpisode(episodeKey)}
              onSelectChunk={onSelectChunk}
              selectedChunkId={selectedChunkId}
              onEnsureChunkSelected={onEnsureChunkSelected}
            />
          );
        })}
        {isOpen && !isLoading && !episodes.length && !isError && (
          <div className="px-2 py-3 text-xs text-muted-foreground">
            No episodes found for this season.
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

export function NarrativeTab() {
  const [openSeasons, setOpenSeasons] = useState<number[]>([]);
  const [openEpisodes, setOpenEpisodes] = useState<string[]>([]);
  const [selectedChunk, setSelectedChunk] = useState<ChunkWithMetadata | null>(null);
  const { fonts } = useFonts();

  const {
    data: seasons = [],
    isLoading: seasonsLoading,
    isError: seasonsError,
    error: seasonsErrorData,
  } = useQuery<Season[]>({
    queryKey: ["/api/narrative/seasons"],
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!seasons.length) {
      return;
    }
    if (openSeasons.length === 0) {
      setOpenSeasons([seasons[0].id]);
    }
  }, [openSeasons.length, seasons]);

  const toggleSeason = useCallback((seasonId: number) => {
    setOpenSeasons((prev) =>
      prev.includes(seasonId) ? prev.filter((id) => id !== seasonId) : [...prev, seasonId],
    );
  }, []);

  const toggleEpisode = useCallback((episodeKey: string) => {
    setOpenEpisodes((prev) =>
      prev.includes(episodeKey) ? prev.filter((key) => key !== episodeKey) : [...prev, episodeKey],
    );
  }, []);

  const ensureEpisodeOpen = useCallback((episodeKey: string) => {
    setOpenEpisodes((prev) => (prev.includes(episodeKey) ? prev : [...prev, episodeKey]));
  }, []);

  const ensureChunkSelected = useCallback((chunk: ChunkWithMetadata) => {
    setSelectedChunk((current) => (current ? current : chunk));
  }, []);

  const activeSeasonIds = useMemo(() => new Set(openSeasons), [openSeasons]);

  return (
    <div className="flex h-full flex-col md:flex-row">
      <div className="md:w-80 border-b md:border-b-0 md:border-r border-border bg-card/50 flex flex-col h-1/3 md:h-full">
        <div className="p-3 md:p-4 border-b border-border">
          <h2 className="text-xs md:text-sm font-mono text-primary terminal-glow" data-testid="text-narrative-title">
            [NARRATIVE HIERARCHY]
          </h2>
        </div>
        <ScrollArea className="flex-1">
          <div className="p-2 space-y-0.5 text-foreground/90">
            {seasonsLoading ? (
              <div className="flex items-center justify-center p-8">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
              </div>
            ) : seasonsError ? (
              <div className="p-4 text-xs text-destructive font-mono">
                Failed to load seasons: {seasonsErrorData instanceof Error ? seasonsErrorData.message : "Unknown error"}
              </div>
            ) : (
              seasons.map((season) => (
                <SeasonNode
                  key={season.id}
                  season={season}
                  isOpen={activeSeasonIds.has(season.id)}
                  onToggle={() => toggleSeason(season.id)}
                  openEpisodes={openEpisodes}
                  onToggleEpisode={toggleEpisode}
                  onEnsureEpisodeOpen={ensureEpisodeOpen}
                  onSelectChunk={setSelectedChunk}
                  selectedChunkId={selectedChunk?.id ?? null}
                  onEnsureChunkSelected={ensureChunkSelected}
                />
              ))
            )}
          </div>
        </ScrollArea>
      </div>

      <div className="flex-1 flex flex-col bg-background terminal-scanlines">
        <ScrollArea className="flex-1">
          <div className="p-6 space-y-6">
            {selectedChunk ? (
              <div className="space-y-4">
                {selectedChunk.metadata && (
                  <div className="border border-border p-4 rounded-md bg-card/30">
                    <div className="flex items-center gap-4 text-xs text-muted-foreground font-mono">
                      <span className="text-primary terminal-glow">
                        {selectedChunk.metadata.slug}
                      </span>
                      {selectedChunk.metadata.scene !== null && (
                        <span>Scene {selectedChunk.metadata.scene}</span>
                      )}
                    </div>
                  </div>
                )}

                <div
                  className="text-foreground text-base leading-relaxed"
                  style={{ fontFamily: fonts.narrativeFont }}
                >
                  <ReactMarkdown components={markdownComponents}>
                    {selectedChunk.rawText || ""}
                  </ReactMarkdown>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full py-16 text-muted-foreground">
                <p className="font-mono text-sm">Select a chunk to view its content</p>
              </div>
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
