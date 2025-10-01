import { ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useState } from "react";

interface ChunkItem {
  id: number;
  label: string;
  location: string;
}

interface EpisodeGroup {
  episode: number;
  chunks: ChunkItem[];
}

interface SeasonGroup {
  season: number;
  episodes: EpisodeGroup[];
}

interface NavigationPaneProps {
  currentChunk: number;
  onChunkSelect: (chunkId: number) => void;
  isCollapsed?: boolean;
}

export function NavigationPane({
  currentChunk,
  onChunkSelect,
  isCollapsed = false,
}: NavigationPaneProps) {
  const [openSeasons, setOpenSeasons] = useState<number[]>([1]);
  const [openEpisodes, setOpenEpisodes] = useState<string[]>(["1-1"]);

  const navigationData: SeasonGroup[] = [
    {
      season: 1,
      episodes: [
        {
          episode: 1,
          chunks: [
            { id: 1, label: "Scene 1", location: "Downtown Neo-Tokyo" },
            { id: 2, label: "Scene 1 (cont.)", location: "Downtown Neo-Tokyo" },
            { id: 3, label: "Scene 2", location: "Safe House" },
            { id: 4, label: "Scene 2 (cont.)", location: "Safe House" },
          ],
        },
      ],
    },
  ];

  if (isCollapsed) {
    return null;
  }

  const toggleSeason = (season: number) => {
    setOpenSeasons((prev) =>
      prev.includes(season) ? prev.filter((s) => s !== season) : [...prev, season]
    );
  };

  const toggleEpisode = (key: string) => {
    setOpenEpisodes((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  return (
    <div className="w-full md:w-80 border-l border-border bg-card terminal-scanlines overflow-hidden flex flex-col h-full">
      <div className="p-3 md:p-4 border-b border-border">
        <h2 className="text-xs md:text-sm font-mono text-primary terminal-glow" data-testid="text-navigation-title">
          [NAVIGATION]
        </h2>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {navigationData.map((season) => (
            <Collapsible
              key={season.season}
              open={openSeasons.includes(season.season)}
              onOpenChange={() => toggleSeason(season.season)}
            >
              <CollapsibleTrigger className="w-full" data-testid={`button-season-${season.season}`}>
                <Button
                  variant="ghost"
                  className="w-full justify-start gap-2 font-mono text-xs hover-elevate h-8 md:h-9"
                >
                  <ChevronRight
                    className={`h-3 w-3 transition-transform ${
                      openSeasons.includes(season.season) ? "rotate-90" : ""
                    }`}
                  />
                  Season {season.season}
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="pl-4 space-y-1">
                {season.episodes.map((episode) => {
                  const episodeKey = `${season.season}-${episode.episode}`;
                  return (
                    <Collapsible
                      key={episodeKey}
                      open={openEpisodes.includes(episodeKey)}
                      onOpenChange={() => toggleEpisode(episodeKey)}
                    >
                      <CollapsibleTrigger className="w-full" data-testid={`button-episode-${episodeKey}`}>
                        <Button
                          variant="ghost"
                          className="w-full justify-start gap-2 font-mono text-xs hover-elevate h-8 md:h-9"
                        >
                          <ChevronRight
                            className={`h-3 w-3 transition-transform ${
                              openEpisodes.includes(episodeKey) ? "rotate-90" : ""
                            }`}
                          />
                          Episode {episode.episode}
                        </Button>
                      </CollapsibleTrigger>
                      <CollapsibleContent className="pl-4 space-y-1">
                        {episode.chunks.map((chunk) => (
                          <Button
                            key={chunk.id}
                            variant="ghost"
                            className={`w-full justify-start font-mono text-xs hover-elevate h-8 md:h-9 ${
                              currentChunk === chunk.id ? "bg-accent text-accent-foreground" : ""
                            }`}
                            onClick={() => onChunkSelect(chunk.id)}
                            data-testid={`button-chunk-${chunk.id}`}
                          >
                            <span className="truncate">{chunk.label}</span>
                          </Button>
                        ))}
                      </CollapsibleContent>
                    </Collapsible>
                  );
                })}
              </CollapsibleContent>
            </Collapsible>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
