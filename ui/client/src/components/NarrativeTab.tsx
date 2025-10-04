import { useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { ChevronRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { Season, Episode, NarrativeChunk, ChunkMetadata } from "@shared/schema";

interface ChunkWithMetadata extends NarrativeChunk {
  metadata?: ChunkMetadata;
}

export function NarrativeTab() {
  const [openSeasons, setOpenSeasons] = useState<number[]>([1]);
  const [openEpisodes, setOpenEpisodes] = useState<string[]>(["1-1"]);
  const [selectedChunk, setSelectedChunk] = useState<ChunkWithMetadata | null>(null);
  const [loadingChunk, setLoadingChunk] = useState<number | null>(null);

  // Fetch seasons
  const {
    data: seasons = [],
    isLoading: seasonsLoading,
    isError: seasonsError,
    error: seasonsErrorData,
  } = useQuery<Season[]>({
    queryKey: ["/api/narrative/seasons"],
  });

  const episodeQueries = useQueries({
    queries: openSeasons.map((seasonId) => ({
      queryKey: ["/api/narrative/episodes", seasonId],
      queryFn: () => fetch(`/api/narrative/episodes/${seasonId}`).then((r) => r.json()),
    })),
  });

  const episodesBySeason = openSeasons.reduce<Record<number, Episode[]>>((acc, seasonId, index) => {
    const queryResult = episodeQueries[index];
    if (queryResult?.data) {
      acc[seasonId] = queryResult.data;
    }
    return acc;
  }, {});

  const chunkQueries = useQueries({
    queries: openEpisodes.map((episodeKey) => {
      const [, episodeId] = episodeKey.split("-").map(Number);
      return {
        queryKey: ["/api/narrative/chunks", episodeId],
        queryFn: () => fetch(`/api/narrative/chunks/${episodeId}?limit=100`).then((r) => r.json()),
      };
    }),
  });

  const chunkQueryStates = openEpisodes.reduce<
    Record<number, {
      data?: { chunks: ChunkWithMetadata[]; total: number };
      isLoading: boolean;
      isFetching: boolean;
    }>
  >((acc, episodeKey, index) => {
    const [, episodeId] = episodeKey.split("-").map(Number);
    const queryResult = chunkQueries[index];
    acc[episodeId] = {
      data: queryResult?.data,
      isLoading: Boolean(queryResult?.isLoading),
      isFetching: Boolean(queryResult?.isFetching),
    };
    return acc;
  }, {});

  const toggleSeason = (seasonId: number) => {
    setOpenSeasons((prev) =>
      prev.includes(seasonId)
        ? prev.filter((s) => s !== seasonId)
        : [...prev, seasonId]
    );
  };

  const toggleEpisode = (key: string) => {
    setOpenEpisodes((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  const handleChunkClick = async (chunk: ChunkWithMetadata) => {
    setLoadingChunk(chunk.id);
    setSelectedChunk(chunk);
    setLoadingChunk(null);
  };

  return (
    <div className="flex h-full flex-col md:flex-row">
      {/* Navigation Panel */}
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
                Failed to load seasons: {seasonsErrorData instanceof Error ? seasonsErrorData.message : 'Unknown error'}
              </div>
            ) : (
              seasons.map((season, seasonIndex) => {
                const episodesData = episodesBySeason[season.id] ?? [];
                const isSeasonOpen = openSeasons.includes(season.id);

                return (
                  <Collapsible
                    key={season.id}
                    open={isSeasonOpen}
                    onOpenChange={() => toggleSeason(season.id)}
                  >
                    <CollapsibleTrigger asChild>
                      <Button
                        variant="ghost"
                        className="w-full justify-start gap-2 font-mono text-xs hover-elevate h-8 text-foreground"
                        data-testid={`button-season-${season.id}`}
                      >
                        <ChevronRight
                          className={`h-3 w-3 transition-transform ${
                            isSeasonOpen ? "rotate-90" : ""
                          }`}
                        />
                        Season {season.id}
                      </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="pl-4 space-y-1">
                      {episodesData.map((episode) => {
                        const episodeKey = `${episode.season}-${episode.episode}`;
                        const isEpisodeOpen = openEpisodes.includes(episodeKey);
                        const [, episodeId] = episodeKey.split("-").map(Number);
                        const chunkState = chunkQueryStates[episodeId];
                        const chunksData = chunkState?.data;
                        const isChunksLoading = chunkState?.isLoading || chunkState?.isFetching;

                        return (
                          <Collapsible
                            key={episodeKey}
                            open={isEpisodeOpen}
                            onOpenChange={() => toggleEpisode(episodeKey)}
                          >
                            <CollapsibleTrigger asChild>
                              <Button
                                variant="ghost"
                                className="w-full justify-start gap-2 font-mono text-xs hover-elevate h-8 text-foreground"
                                data-testid={`button-episode-${episodeKey}`}
                              >
                                <ChevronRight
                                  className={`h-3 w-3 transition-transform ${
                                    isEpisodeOpen ? "rotate-90" : ""
                                  }`}
                                />
                                Episode {episode.episode}
                              </Button>
                            </CollapsibleTrigger>
                            <CollapsibleContent className="pl-4 space-y-1">
                              {isChunksLoading && (
                                <div className="flex items-center justify-start gap-2 px-2 py-3 text-xs text-muted-foreground">
                                  <Loader2 className="h-3 w-3 animate-spin" /> Loading chunks…
                                </div>
                              )}
                              {chunksData?.chunks.map((chunk) => (
                                <Button
                                  key={chunk.id}
                                  variant="ghost"
                                  className={`w-full justify-start font-mono text-xs hover-elevate h-8 text-foreground ${
                                    selectedChunk?.id === chunk.id
                                      ? "bg-accent text-accent-foreground"
                                      : ""
                                  }`}
                                  onClick={() => handleChunkClick(chunk)}
                                  disabled={loadingChunk === chunk.id}
                                  data-testid={`button-chunk-${chunk.id}`}
                                >
                                  {loadingChunk === chunk.id ? (
                                    <Loader2 className="h-3 w-3 animate-spin mr-2" />
                                  ) : null}
                                  <span className="truncate">
                                    {chunk.metadata?.slug || `Chunk ${chunk.id}`}
                                  </span>
                                </Button>
                              ))}
                            </CollapsibleContent>
                          </Collapsible>
                        );
                      })}
                    </CollapsibleContent>
                  </Collapsible>
                );
              })
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Content Display */}
      <div className="flex-1 flex flex-col bg-background terminal-scanlines">
        <ScrollArea className="flex-1">
          <div className="p-6 space-y-6">
            {selectedChunk ? (
              <div className="space-y-4">
                {/* Chunk Header */}
                {selectedChunk.metadata && (
                  <div className="border border-border p-4 rounded-md bg-card/30">
                    <div className="flex items-center gap-4 text-xs text-muted-foreground font-mono">
                      <span className="text-primary terminal-glow">
                        {selectedChunk.metadata.slug}
                      </span>
                      {selectedChunk.metadata.atmosphere && (
                        <span>• {selectedChunk.metadata.atmosphere}</span>
                      )}
                      {selectedChunk.metadata.arcPosition && (
                        <span>• {selectedChunk.metadata.arcPosition}</span>
                      )}
                    </div>
                  </div>
                )}

                {/* Chunk Content */}
                <div className="text-foreground font-mono text-sm leading-relaxed whitespace-pre-wrap">
                  {selectedChunk.rawText}
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
