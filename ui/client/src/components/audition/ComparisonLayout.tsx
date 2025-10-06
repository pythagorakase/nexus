/**
 * Main comparison layout with side-by-side generations.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ComparisonQueueItem } from '@/lib/audition-api';
import { useJudgment } from '@/hooks/useJudgment';
import { GenerationPane } from './GenerationPane';
import { JudgmentBar } from './JudgmentBar';
import { useToast } from '@/hooks/use-toast';
import { useFonts } from '@/contexts/FontContext';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import ReactMarkdown from 'react-markdown';

interface ComparisonLayoutProps {
  comparison: ComparisonQueueItem;
  evaluator: string;
  onComplete?: () => void;
  onSkip?: () => void;
  onExit?: () => void;
}

interface WarmChunk {
  chunk_id?: number;
  id?: number;
  text?: string;
  raw_text?: string;
  rawText?: string;
}

function extractWarmChunks(context: Record<string, unknown> | undefined): WarmChunk[] {
  if (!context || typeof context !== 'object') return [];

  const possibleCollections = [
    (context as any)?.warm_slice?.chunks,
    (context as any)?.context_payload?.warm_slice?.chunks,
    (context as any)?.warmSlice?.chunks,
  ];

  for (const collection of possibleCollections) {
    if (Array.isArray(collection)) {
      return collection as WarmChunk[];
    }
  }

  return [];
}

function getChunkText(chunk: WarmChunk | undefined) {
  if (!chunk) return '';
  return (
    chunk.text ||
    chunk.raw_text ||
    chunk.rawText ||
    ''
  );
}

function buildSnippet(text: string) {
  if (!text) return '';
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length <= 6) {
    return text.trim();
  }
  const tail = lines.slice(-6);
  return ['…', ...tail].join('\n');
}

export function ComparisonLayout({
  comparison,
  evaluator,
  onComplete,
  onSkip,
  onExit,
}: ComparisonLayoutProps) {
  const [highlightedPane, setHighlightedPane] = useState<'A' | 'B' | null>(null);
  const [isContextDialogOpen, setIsContextDialogOpen] = useState(false);
  const precedingScrollRef = useRef<HTMLDivElement>(null);
  const { recordJudgmentAsync, isRecording } = useJudgment();
  const { toast } = useToast();
  const { fonts } = useFonts();

  const warmChunks = useMemo(
    () => extractWarmChunks(comparison.prompt.context),
    [comparison.prompt.context],
  );

  const precedingChunk = useMemo(() => {
    if (!warmChunks.length) return undefined;
    const currentChunkId = comparison.prompt.chunk_id;
    const chunksBefore = warmChunks
      .filter((chunk) => (chunk.chunk_id ?? chunk.id ?? -Infinity) <= currentChunkId);
    if (chunksBefore.length === 0) {
      return warmChunks[warmChunks.length - 1];
    }
    return chunksBefore[chunksBefore.length - 1];
  }, [warmChunks, comparison.prompt.chunk_id]);

  const precedingText = useMemo(() => getChunkText(precedingChunk), [precedingChunk]);
  const precedingSnippet = useMemo(() => buildSnippet(precedingText), [precedingText]);

  // Auto-scroll previous chunk to bottom when loaded
  useEffect(() => {
    if (precedingScrollRef.current) {
      precedingScrollRef.current.scrollTop = precedingScrollRef.current.scrollHeight;
    }
  }, [precedingText]);

  const resetHighlightSoon = useCallback(() => {
    setTimeout(() => setHighlightedPane(null), 400);
  }, []);

  const handleJudgment = useCallback(async (winnerConditionId: number | null) => {
    if (isRecording) {
      return;
    }

    try {
      if (winnerConditionId === comparison.condition_a.id) {
        setHighlightedPane('A');
      } else if (winnerConditionId === comparison.condition_b.id) {
        setHighlightedPane('B');
      } else {
        setHighlightedPane(null);
      }

      await recordJudgmentAsync({
        prompt_id: comparison.prompt.id,
        condition_a_id: comparison.condition_a.id,
        condition_b_id: comparison.condition_b.id,
        winner_condition_id: winnerConditionId ?? undefined,
        evaluator,
      });

      // Build description with condition slugs revealed
      let description = '';
      if (winnerConditionId === null) {
        description = `Tie\nLeft: ${comparison.condition_a.slug}\nRight: ${comparison.condition_b.slug}`;
      } else if (winnerConditionId === comparison.condition_a.id) {
        description = `Winner: Left passage, ${comparison.condition_a.slug}\nLoser: Right passage, ${comparison.condition_b.slug}`;
      } else {
        description = `Winner: Right passage, ${comparison.condition_b.slug}\nLoser: Left passage, ${comparison.condition_a.slug}`;
      }

      toast({
        title: 'Judgment recorded',
        description,
      });

      // Delay loading next comparison to give user time to see the reveal
      setTimeout(() => {
        onComplete?.();
        resetHighlightSoon();
      }, 2500);
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to record judgment',
        variant: 'destructive',
      });
      setHighlightedPane(null);
    }
  }, [
    comparison.condition_a.id,
    comparison.condition_b.id,
    comparison.condition_a.slug,
    comparison.condition_b.slug,
    comparison.prompt.id,
    evaluator,
    isRecording,
    onComplete,
    recordJudgmentAsync,
    resetHighlightSoon,
    toast,
  ]);

  const handleSkip = useCallback(() => {
    if (isRecording) {
      return;
    }

    setPendingNote('');
    setHighlightedPane(null);
    toast({
      title: 'Comparison skipped',
      description: 'Fetching the next pair.',
    });
    onSkip?.();
  }, [isRecording, onSkip, toast]);

  const handleExit = useCallback(() => {
    if (isRecording) {
      return;
    }
    setHighlightedPane(null);
    onExit?.();
  }, [isRecording, onExit]);

  const handleNote = useCallback(async (leftNote: string, rightNote: string) => {
    if (isRecording) return;

    try {
      const updates = [];

      if (leftNote.trim()) {
        updates.push(
          fetch(`/api/audition/conditions/${comparison.condition_a.id}/notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note: leftNote }),
          })
        );
      }

      if (rightNote.trim()) {
        updates.push(
          fetch(`/api/audition/conditions/${comparison.condition_b.id}/notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note: rightNote }),
          })
        );
      }

      await Promise.all(updates);

      toast({
        title: 'Notes saved',
        description: `Added note${updates.length > 1 ? 's' : ''} to condition${updates.length > 1 ? 's' : ''}`,
      });
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to save notes',
        variant: 'destructive',
      });
    }
  }, [comparison.condition_a.id, comparison.condition_b.id, isRecording, toast]);

  const handleExport = useCallback(() => {
    if (isRecording) return;

    const exportData = {
      previous_chunk: {
        id: precedingChunk?.chunk_id || precedingChunk?.id,
        text: precedingText,
      },
      left_passage: {
        condition_slug: comparison.condition_a.slug,
        text: comparison.generation_a.output,
      },
      right_passage: {
        condition_slug: comparison.condition_b.slug,
        text: comparison.generation_b.output,
      },
    };

    navigator.clipboard.writeText(JSON.stringify(exportData, null, 2));

    toast({
      title: 'Exported to clipboard',
      description: 'Comparison data copied as JSON',
    });
  }, [comparison, precedingChunk, precedingText, isRecording, toast]);

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (isRecording) return;
      if (event.key === '1') {
        event.preventDefault();
        handleJudgment(comparison.condition_a.id);
      } else if (event.key === '2') {
        event.preventDefault();
        handleJudgment(comparison.condition_b.id);
      } else if (event.key === '3') {
        event.preventDefault();
        handleJudgment(null);
      } else if (event.key === 'Escape') {
        event.preventDefault();
        handleExit();
      } else if (event.key === '0' && onSkip) {
        event.preventDefault();
        handleSkip();
      }
    };

    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [comparison.condition_a.id, comparison.condition_b.id, handleExit, handleJudgment, handleSkip, isRecording, onSkip]);

  const hasPrecedingChunk = Boolean(precedingSnippet);

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-border px-4 py-3 space-y-3 bg-card/40">
        <div className="flex items-center justify-between text-xs text-muted-foreground uppercase tracking-wide">
          <span>Chunk {comparison.prompt.chunk_id}</span>
          {comparison.prompt.label && <span>{comparison.prompt.label}</span>}
        </div>

        {hasPrecedingChunk ? (
          <div className="border border-border/70 rounded-md bg-background/70 p-3">
            <div className="text-[11px] uppercase text-muted-foreground tracking-wider mb-2">
              Previous chunk
            </div>
            <ScrollArea className="h-32" ref={precedingScrollRef} style={{ transform: 'translateZ(0)', contain: 'layout style' }}>
              <div
                className="text-sm leading-relaxed text-foreground pr-4 pl-3"
                style={{ fontFamily: fonts.narrativeFont }}
              >
                <ReactMarkdown
                  components={{
                    p: ({node, ...props}) => <p className="mb-3 last:mb-0" {...props} />,
                    strong: ({node, ...props}) => <strong className="font-bold" {...props} />,
                    em: ({node, ...props}) => <em className="italic" {...props} />,
                    ol: ({node, ...props}) => (
                      <ol className="pl-10 list-decimal space-y-1 my-3" style={{ listStylePosition: 'outside' }} {...props} />
                    ),
                    ul: ({node, ...props}) => (
                      <ul className="pl-6 list-disc space-y-1 my-3" style={{ listStylePosition: 'outside' }} {...props} />
                    ),
                    li: ({node, ...props}) => <li className="leading-relaxed pl-1" {...props} />,
                    h1: ({node, ...props}) => <h1 className="text-lg font-bold mb-2 mt-4 first:mt-0" {...props} />,
                    h2: ({node, ...props}) => <h2 className="text-base font-bold mb-2 mt-3 first:mt-0" {...props} />,
                    h3: ({node, ...props}) => <h3 className="font-bold mb-1 mt-2 first:mt-0" {...props} />,
                  }}
                >
                  {precedingText}
                </ReactMarkdown>
              </div>
            </ScrollArea>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">
            No preceding chunk found in context package.
          </div>
        )}
      </div>

      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4 p-4 overflow-hidden min-h-0">
        <div className="min-h-0 h-full">
          <GenerationPane
            generation={comparison.generation_a}
            label="1"
            highlighted={highlightedPane === 'A'}
          />
        </div>
        <div className="min-h-0 h-full">
          <GenerationPane
            generation={comparison.generation_b}
            label="2"
            highlighted={highlightedPane === 'B'}
          />
        </div>
      </div>

      <JudgmentBar
        onChooseLeft={() => handleJudgment(comparison.condition_a.id)}
        onChooseRight={() => handleJudgment(comparison.condition_b.id)}
        onTie={() => handleJudgment(null)}
        onExit={handleExit}
        onSkip={onSkip ? handleSkip : undefined}
        onNote={handleNote}
        onExport={handleExport}
        disabled={isRecording}
      />

      <Dialog open={isContextDialogOpen} onOpenChange={setIsContextDialogOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Previous chunk (full)</DialogTitle>
          </DialogHeader>
          <div className="max-h-[60vh] overflow-y-auto">
            <pre className="font-mono text-sm whitespace-pre-wrap leading-relaxed text-foreground">
              {precedingText || 'No preceding chunk available.'}
            </pre>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
