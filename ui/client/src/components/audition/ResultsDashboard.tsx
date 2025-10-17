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
      <div className="flex-1 overflow-auto p-4">
        <LeaderboardView />
      </div>
    </div>
  );
}
