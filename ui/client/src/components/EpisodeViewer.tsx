/**
 * EpisodeViewer - Displays narrative chunks as a chat-style conversation
 *
 * Renders an episode's chunks as alternating user choices and storyteller responses,
 * using the shadcn AI components for consistent chat UI.
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Sparkles, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { useFonts } from "@/contexts/FontContext";
import { useTheme } from "@/contexts/ThemeContext";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
  Response,
} from "@/components/ai";

/**
 * Choice object structure from database JSONB column
 */
interface ChoiceObject {
  presented: string[];
  selected?: {
    label: number | "freeform";
    text: string;
    edited: boolean;
  };
}

interface ChunkMetadata {
  slug?: string;
  scene?: number;
  timeDelta?: string;
}

export interface EpisodeChunk {
  id: number;
  rawText?: string | null;
  storytellerText?: string | null;
  choiceObject?: ChoiceObject | null;
  metadata?: ChunkMetadata;
  createdAt?: string;
}

interface EpisodeViewerProps {
  seasonId: number;
  episodeId: number;
  slot: number;
  className?: string;
  onChunkClick?: (chunk: EpisodeChunk) => void;
}

/**
 * Renders a single chunk as chat messages
 * - User choice (if selected) appears as a user message
 * - Storyteller text appears as an assistant message
 */
function ChunkMessages({
  chunk,
  isFirst,
  onChunkClick,
}: {
  chunk: EpisodeChunk;
  isFirst: boolean;
  onChunkClick?: (chunk: EpisodeChunk) => void;
}) {
  const { currentBodyFont } = useFonts();
  const { isVector } = useTheme();
  const glowClass = isVector ? "text-glow" : "";

  const hasChoice = chunk.choiceObject?.selected;
  const narrativeText = hasChoice
    ? chunk.rawText || chunk.storytellerText || ""
    : chunk.storytellerText || chunk.rawText || "";

  return (
    <div
      className="space-y-4 cursor-pointer hover:bg-accent/5 rounded-lg p-2 -mx-2 transition-colors"
      onClick={() => onChunkClick?.(chunk)}
    >
      {/* Scene/time marker for context */}
      {chunk.metadata?.slug && (
        <div className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground/60">
          <span className={cn("text-primary/60", glowClass)}>
            {chunk.metadata.slug}
          </span>
          {chunk.metadata.timeDelta && (
            <span className="text-muted-foreground/40">
              {chunk.metadata.timeDelta}
            </span>
          )}
        </div>
      )}

      {/* User's choice (if made) */}
      {hasChoice && (
        <div className="flex w-full justify-end">
          <div className="max-w-[80%] p-3 rounded-lg bg-primary/20 border border-primary/30 text-foreground">
            <div className="flex items-center gap-1.5 mb-1.5 text-[10px] font-mono text-primary/70">
              <User className="w-3 h-3" />
              <span>Your choice</span>
            </div>
            <p className="text-sm">{chunk.choiceObject!.selected!.text}</p>
          </div>
        </div>
      )}

      {/* Storyteller response */}
      {narrativeText && (
        <div className="flex w-full justify-start">
          <div className="max-w-[90%] p-4 rounded-lg bg-background/80 border border-border text-foreground">
            <div className="flex items-center gap-1.5 mb-2 pb-1 border-b border-primary/20">
              <Sparkles className="w-3 h-3 text-primary" />
              <span className="text-[10px] font-mono text-primary uppercase tracking-widest">
                {isFirst ? "Prologue" : "Storyteller"}
              </span>
            </div>
            <div
              className="prose prose-invert max-w-none prose-p:leading-relaxed text-sm"
              style={{ fontFamily: currentBodyFont }}
            >
              <Response>{narrativeText}</Response>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function EpisodeViewer({
  seasonId,
  episodeId,
  slot,
  className,
  onChunkClick,
}: EpisodeViewerProps) {
  const {
    data,
    isLoading,
    isError,
    error,
  } = useQuery<{ chunks: EpisodeChunk[]; total: number }>({
    queryKey: ["/api/narrative/chunks", seasonId, episodeId, slot],
    queryFn: async () => {
      const response = await fetch(
        `/api/narrative/chunks/${seasonId}/${episodeId}?limit=200&slot=${slot}`
      );
      if (!response.ok) {
        const message = (await response.text()) || "Failed to load chunks";
        throw new Error(message);
      }
      return response.json();
    },
    staleTime: 5 * 60 * 1000,
  });

  const chunks = useMemo(() => data?.chunks ?? [], [data]);

  if (isLoading) {
    return (
      <div className={cn("flex items-center justify-center h-full", className)}>
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-sm font-mono">Loading episode...</span>
        </div>
      </div>
    );
  }

  if (isError) {
    // Sanitize error messages to avoid leaking sensitive backend details
    const safeErrorMessage = error instanceof Error &&
      !error.message.includes('stack') &&
      !error.message.includes('SQL') &&
      error.message.length < 200
        ? error.message
        : "Unable to load episode. Please try again.";

    return (
      <div className={cn("flex items-center justify-center h-full", className)}>
        <div className="text-sm text-destructive font-mono">
          Failed to load episode: {safeErrorMessage}
        </div>
      </div>
    );
  }

  if (chunks.length === 0) {
    return (
      <div className={cn("flex items-center justify-center h-full", className)}>
        <div className="text-sm text-muted-foreground font-mono">
          No chunks in this episode yet.
        </div>
      </div>
    );
  }

  return (
    <Conversation className={cn("flex-1", className)}>
      <ConversationContent className="p-4 space-y-6">
        {chunks.map((chunk, index) => (
          <ChunkMessages
            key={chunk.id}
            chunk={chunk}
            isFirst={index === 0}
            onChunkClick={onChunkClick}
          />
        ))}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  );
}

export default EpisodeViewer;
