import { useEffect, useRef, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useFonts } from "@/contexts/FontContext";
import { useTheme } from "@/contexts/ThemeContext";
import ReactMarkdown from 'react-markdown';

export interface NarrativeSection {
  type: "you" | "storyteller";
  content: string;
}

export interface NarrativeChunk {
  id: number;
  season: number;
  episode: number;
  scene: number;
  sections: NarrativeSection[];
  metadata: {
    location: string;
    timestamp: string;
    characters: string[];
  };
}

interface NarrativePaneProps {
  chunks: NarrativeChunk[];
  currentChunk: number;
  mode?: "read" | "stream";
  isLoading?: boolean;
  provisionalSection?: string | null;
  isTyping?: boolean;
  typingChunk?: number | null;
}

function TypewriterText({ text, delay = 50 }: { text: string; delay?: number }) {
  const [displayText, setDisplayText] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (currentIndex < text.length) {
      const timeout = setTimeout(() => {
        setDisplayText((prev) => prev + text[currentIndex]);
        setCurrentIndex((prev) => prev + 1);
      }, delay);
      return () => clearTimeout(timeout);
    }
  }, [currentIndex, text, delay]);

  return <span>{displayText}</span>;
}

export function NarrativePane({
  chunks,
  currentChunk,
  mode = "read",
  isLoading,
  provisionalSection,
  isTyping,
  typingChunk,
}: NarrativePaneProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const { currentBodyFont } = useFonts();
  const { isGilded, isCyberpunk } = useTheme();
  const glowClass = isGilded ? "deco-glow" : "terminal-glow";

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [chunks, provisionalSection]);

  const currentChunkData = chunks.find((c) => c.id === currentChunk);
  const typingChunkData = isTyping && typingChunk ? chunks.find((c) => c.id === typingChunk) : null;

  return (
    <div className={`flex-1 flex flex-col bg-background overflow-hidden ${isCyberpunk ? "terminal-scanlines" : ""}`}>
      <ScrollArea className="flex-1" data-testid="scroll-narrative">
        <div
          ref={scrollRef}
          className="p-3 md:p-6 space-y-4 md:space-y-8 text-xs md:text-sm leading-relaxed"
          style={{ fontFamily: currentBodyFont }}
        >
          {currentChunkData && (
            <div key={currentChunkData.id} className="space-y-4">
              <div className="border border-border p-3 md:p-4 rounded-md bg-card" data-testid={`chunk-header-${currentChunkData.id}`}>
                <div className="flex flex-wrap items-center gap-2 md:gap-4 text-[10px] md:text-xs text-muted-foreground">
                  <span>S{currentChunkData.season}E{currentChunkData.episode}S{currentChunkData.scene}</span>
                  <span className={`text-primary ${glowClass}`}>{currentChunkData.metadata.location}</span>
                  <span>{currentChunkData.metadata.timestamp}</span>
                </div>
                <div className="mt-2 text-[10px] md:text-xs text-muted-foreground">
                  {currentChunkData.metadata.characters.join(" • ")}
                </div>
              </div>

              {currentChunkData.sections.map((section, idx) => (
                <div
                  key={idx}
                  className={`${
                    section.type === "you"
                      ? `text-primary ${glowClass}`
                      : "text-foreground"
                  } leading-relaxed`}
                  data-testid={`section-${section.type}-${idx}`}
                >
                  <span className="text-muted-foreground mr-2">
                    {section.type === "you" ? ">" : ">>"}
                  </span>
                  {mode === "stream" && idx === currentChunkData.sections.length - 1 ? (
                    <TypewriterText text={section.content} />
                  ) : (
                    <ReactMarkdown
                      components={{
                        p: ({node, ...props}) => <>{props.children}</>,
                        strong: ({node, ...props}) => <strong className="font-bold" {...props} />,
                        em: ({node, ...props}) => <em className="italic" {...props} />,
                      }}
                    >
                      {section.content}
                    </ReactMarkdown>
                  )}
                </div>
              ))}

              {provisionalSection && (
                <div className="text-primary/50 leading-relaxed italic" data-testid="text-provisional">
                  <span className="text-muted-foreground mr-2">{">"}</span>
                  {provisionalSection}
                </div>
              )}
            </div>
          )}

          {typingChunkData && (
            <div key={typingChunkData.id} className="space-y-4">
              <div className="border border-border p-3 md:p-4 rounded-md bg-card">
                <TypewriterText
                  text={`S${typingChunkData.season}E${typingChunkData.episode}S${typingChunkData.scene} ${typingChunkData.metadata.location} ${typingChunkData.metadata.timestamp}`}
                  delay={30}
                />
              </div>
              {typingChunkData.sections.map((section, idx) => (
                <div key={idx} className="text-foreground leading-relaxed">
                  <span className="text-muted-foreground mr-2">{">>"}</span>
                  <ReactMarkdown
                    components={{
                      p: ({node, ...props}) => <>{props.children}</>,
                      strong: ({node, ...props}) => <strong className="font-bold" {...props} />,
                      em: ({node, ...props}) => <em className="italic" {...props} />,
                    }}
                  >
                    {section.content}
                  </ReactMarkdown>
                </div>
              ))}
            </div>
          )}

          {isLoading && (
            <div className={`text-primary ${glowClass} animate-pulse`} data-testid="text-loading">
              <span className="mr-2">{">"}</span>
              Processing...
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
