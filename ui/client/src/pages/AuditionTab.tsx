/**
 * Apex Audition tab for comparing model generations.
 */
import { useState } from 'react';
import { useComparison } from '@/hooks/useComparison';
import { ComparisonLayout } from '@/components/audition/ComparisonLayout';
import { LeaderboardView } from '@/components/audition/LeaderboardView';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';

export default function AuditionTab() {
  const [evaluator] = useState(() => {
    // Get evaluator name from localStorage or default
    return localStorage.getItem('audition_evaluator') || 'default';
  });

  const [activeView, setActiveView] = useState<'compare' | 'leaderboard'>('compare');
  const [comparisonCount, setComparisonCount] = useState(0);

  const { comparison, isLoading, isError, error, refetch } = useComparison({
    enabled: activeView === 'compare',
  });

  const handleComparisonComplete = () => {
    setComparisonCount((c) => c + 1);
    refetch(); // Fetch next comparison
  };

  const handleSkip = () => {
    refetch();
  };

  if (activeView === 'leaderboard') {
    return (
      <div className="h-full flex flex-col">
        <div className="border-b border-border px-4 py-3 flex items-center justify-between">
          <h2 className="text-xl font-mono font-semibold">Leaderboard</h2>
          <Button
            variant="outline"
            onClick={() => setActiveView('compare')}
          >
            Back to Comparisons
          </Button>
        </div>
        <div className="flex-1 overflow-auto p-6">
          <LeaderboardView />
        </div>
      </div>
    );
  }

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
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="font-mono text-destructive">
            Error loading comparison: {error?.message || 'Unknown error'}
          </p>
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
          <Button onClick={() => setActiveView('leaderboard')}>
            View Leaderboard
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-border px-4 py-2 flex items-center justify-between font-mono text-sm">
        <span className="text-primary">
          Comparisons judged: {comparisonCount}
        </span>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setActiveView('leaderboard')}
          >
            [Q] View Leaderboard
          </Button>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        <ComparisonLayout
          comparison={comparison}
          evaluator={evaluator}
          onComplete={handleComparisonComplete}
          onSkip={handleSkip}
        />
      </div>
    </div>
  );
}
