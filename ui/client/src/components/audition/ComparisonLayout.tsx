/**
 * Main comparison layout with side-by-side generations.
 */
import { useState } from 'react';
import { ComparisonQueueItem } from '@/lib/audition-api';
import { useJudgment } from '@/hooks/useJudgment';
import { GenerationPane } from './GenerationPane';
import { JudgmentBar } from './JudgmentBar';
import { ContextDrawer } from './ContextDrawer';
import { useToast } from '@/hooks/use-toast';

interface ComparisonLayoutProps {
  comparison: ComparisonQueueItem;
  evaluator: string;
  onComplete?: () => void;
  onSkip?: () => void;
}

export function ComparisonLayout({
  comparison,
  evaluator,
  onComplete,
  onSkip
}: ComparisonLayoutProps) {
  const [highlightedPane, setHighlightedPane] = useState<'A' | 'B' | null>(null);
  const [pendingNote, setPendingNote] = useState<string>('');
  const { recordJudgmentAsync, isRecording } = useJudgment();
  const { toast } = useToast();

  const handleJudgment = async (winnerConditionId: number | null) => {
    if (isRecording) {
      return;
    }

    try {
      // Highlight the winning pane briefly
      if (winnerConditionId === comparison.condition_a.id) {
        setHighlightedPane('A');
      } else if (winnerConditionId === comparison.condition_b.id) {
        setHighlightedPane('B');
      }

      await recordJudgmentAsync({
        prompt_id: comparison.prompt.id,
        condition_a_id: comparison.condition_a.id,
        condition_b_id: comparison.condition_b.id,
        winner_condition_id: winnerConditionId,
        evaluator,
        notes: pendingNote || undefined,
      });

      // Clear note after successful judgment
      setPendingNote('');

      toast({
        title: 'Judgment recorded',
        description: winnerConditionId
          ? `Winner: ${winnerConditionId === comparison.condition_a.id ? 'A' : 'B'}`
          : 'Recorded as tie',
      });

      // Call onComplete callback
      onComplete?.();

      // Clear highlight
      setTimeout(() => setHighlightedPane(null), 500);
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to record judgment',
        variant: 'destructive',
      });
      setHighlightedPane(null);
    }
  };

  const handleSkip = () => {
    if (isRecording) {
      return;
    }

    setPendingNote('');
    setHighlightedPane(null);
    toast({
      title: 'Comparison skipped',
      description: 'No judgment recorded. Fetching the next pair.',
    });
    onSkip?.();
  };

  return (
    <div className="flex flex-col h-full">
      {/* Status bar */}
      <div className="border-b border-border px-4 py-2 font-mono text-sm">
        <div className="flex justify-between items-center">
          <span className="text-primary">
            {comparison.condition_a.model} vs {comparison.condition_b.model}
          </span>
          <span className="text-muted-foreground">
            Chunk {comparison.prompt.chunk_id}
          </span>
        </div>
      </div>

      {/* Split pane with generations */}
      <div className="flex-1 grid grid-cols-2 gap-4 p-4 overflow-hidden">
        <GenerationPane
          condition={comparison.condition_a}
          generation={comparison.generation_a}
          label="A"
          highlighted={highlightedPane === 'A'}
        />
        <GenerationPane
          condition={comparison.condition_b}
          generation={comparison.generation_b}
          label="B"
          highlighted={highlightedPane === 'B'}
        />
      </div>

      {/* Context drawer */}
      <ContextDrawer prompt={comparison.prompt} />

      {/* Judgment controls */}
      <JudgmentBar
        onChooseA={() => handleJudgment(comparison.condition_a.id)}
        onChooseB={() => handleJudgment(comparison.condition_b.id)}
        onTie={() => handleJudgment(null)}
        onSkip={handleSkip}
        onNote={(note) => setPendingNote(note)}
        disabled={isRecording}
      />
    </div>
  );
}
