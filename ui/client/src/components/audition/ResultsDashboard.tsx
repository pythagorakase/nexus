import { useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { LeaderboardView } from './LeaderboardView';

interface ResultsDashboardProps {
  sessionSummary: {
    judged: number;
    skipped: number;
  };
  onResumeJudge: () => void;
}

export function ResultsDashboard({ onResumeJudge }: ResultsDashboardProps) {
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 'j') {
        event.preventDefault();
        onResumeJudge();
      }
    };

    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onResumeJudge]);

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-border/60 bg-card/60 px-4 py-3 flex items-center justify-end">
        <Button size="sm" onClick={onResumeJudge}>
          Resume judging [J]
        </Button>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <LeaderboardView />
      </div>
    </div>
  );
}
