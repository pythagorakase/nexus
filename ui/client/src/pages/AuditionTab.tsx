/**
 * Apex Audition tab for comparing model generations.
 */
import { useMemo, useState } from 'react';
import { useComparison } from '@/hooks/useComparison';
import { ComparisonLayout } from '@/components/audition/ComparisonLayout';
import { ResultsDashboard } from '@/components/audition/ResultsDashboard';
import { GenerateMode } from '@/components/audition/GenerateMode';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';

type AuditionMode = 'judge' | 'results' | 'generate';

export default function AuditionTab() {
  const [evaluator] = useState(() => {
    return localStorage.getItem('audition_evaluator') || 'default';
  });

  const [mode, setMode] = useState<AuditionMode>('judge');
  const [comparisonCount, setComparisonCount] = useState(0);
  const [skippedCount, setSkippedCount] = useState(0);

  const { comparison, isLoading, isError, error, refetch } = useComparison({
    enabled: mode === 'judge',
  });

  const sessionSummary = useMemo(() => ({
    judged: comparisonCount,
    skipped: skippedCount,
  }), [comparisonCount, skippedCount]);

  const handleComparisonComplete = () => {
    setComparisonCount((c) => c + 1);
    refetch();
  };

  const handleSkip = () => {
    setSkippedCount((c) => c + 1);
    refetch();
  };

  const handleExitJudgeMode = () => {
    setMode('results');
  };

  const renderJudgeMode = () => {
    if (isLoading) {
      return (
        <div className="h-full flex items-center justify-center">
          <div className="text-center space-y-4">
            <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
            <p className="font-mono text-muted-foreground">Loading comparison...</p>
          </div>
        </div>
      );
    }

    if (isError) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      const connectivityHint = errorMessage.toLowerCase().includes('failed to fetch');
      return (
        <div className="h-full flex items-center justify-center">
          <div className="text-center space-y-4">
            <p className="font-mono text-destructive">
              Error loading comparison: {errorMessage}
            </p>
            {connectivityHint && (
              <p className="text-xs text-muted-foreground">
                Ensure the audition API is running (`./iris`) and that the database is reachable at {import.meta.env.VITE_AUDITION_API_URL ?? 'http://localhost:8000/api/audition'}.
              </p>
            )}
            <Button onClick={() => refetch()}>Retry</Button>
          </div>
        </div>
      );
    }

    if (!comparison) {
      return (
        <div className="h-full flex items-center justify-center">
          <div className="text-center space-y-4">
            <p className="font-mono text-xl">🎉 All comparisons complete!</p>
            <p className="text-muted-foreground">
              Judged {comparisonCount} comparison{comparisonCount !== 1 ? 's' : ''} this session.
            </p>
            <Button onClick={() => setMode('results')}>
              View Results
            </Button>
          </div>
        </div>
      );
    }

    return (
      <ComparisonLayout
        comparison={comparison}
        evaluator={evaluator}
        onComplete={handleComparisonComplete}
        onSkip={handleSkip}
        onExit={handleExitJudgeMode}
      />
    );
  };

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-border px-4 py-2 flex items-center justify-between font-mono text-xs sm:text-sm">
        <div className="flex items-center gap-3">
          <Button
            variant={mode === 'judge' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setMode('judge')}
          >
            Judge Mode
          </Button>
          <Button
            variant={mode === 'generate' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setMode('generate')}
          >
            Generate Mode
          </Button>
          <Button
            variant={mode === 'results' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setMode('results')}
          >
            Results Mode
          </Button>
        </div>
        <div className="flex items-center gap-4 text-muted-foreground">
          <span>Judged: {sessionSummary.judged}</span>
          <span>Skipped: {sessionSummary.skipped}</span>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        {mode === 'judge' ? (
          renderJudgeMode()
        ) : mode === 'generate' ? (
          <GenerateMode />
        ) : (
          <ResultsDashboard
            sessionSummary={sessionSummary}
            onResumeJudge={() => setMode('judge')}
          />
        )}
      </div>
    </div>
  );
}
