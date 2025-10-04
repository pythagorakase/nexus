import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { auditionAPI, GenerationRun } from '@/lib/audition-api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Loader2, RefreshCcw } from 'lucide-react';
import { LeaderboardView } from './LeaderboardView';

interface ResultsDashboardProps {
  sessionSummary: {
    judged: number;
    skipped: number;
  };
  onResumeJudge: () => void;
}

function formatDate(value?: string) {
  if (!value) return 'In progress';
  try {
    const date = new Date(value);
    return date.toLocaleString();
  } catch {
    return value;
  }
}

function RunProgressCard({ run }: { run: GenerationRun }) {
  const { total_generations, completed_generations, failed_generations } = run;
  const processed = completed_generations + failed_generations;
  const pending = Math.max(total_generations - processed, 0);
  const progress = total_generations > 0 ? (completed_generations / total_generations) * 100 : 0;

  return (
    <Card className="border-border/60 bg-card/80">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="font-mono text-sm md:text-base">{run.label || run.id}</CardTitle>
          <span className="text-xs text-muted-foreground">{formatDate(run.started_at)}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <Progress value={progress} className="h-2" />
        <div className="grid grid-cols-3 gap-3 text-xs md:text-sm font-mono">
          <div>
            <span className="block text-muted-foreground">Completed</span>
            <span className="text-primary">
              {completed_generations}/{total_generations}
            </span>
          </div>
          <div>
            <span className="block text-muted-foreground">Pending</span>
            <span>{pending}</span>
          </div>
          <div>
            <span className="block text-muted-foreground">Failed</span>
            <span className="text-destructive">{failed_generations}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function ResultsDashboard({ sessionSummary, onResumeJudge }: ResultsDashboardProps) {
  const { data: runs, isLoading: runsLoading, refetch: refetchRuns, isRefetching } = useQuery({
    queryKey: ['audition', 'runs'],
    queryFn: () => auditionAPI.getGenerationRuns(),
    refetchInterval: 15000,
  });

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
      <div className="border-b border-border/60 bg-card/60 px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="text-xs uppercase text-muted-foreground tracking-wide">Session summary</div>
          <div className="font-mono text-sm sm:text-base flex gap-4">
            <span>Judged: <span className="text-primary">{sessionSummary.judged}</span></span>
            <span>Skipped: {sessionSummary.skipped}</span>
          </div>
        </div>
        <Button size="sm" onClick={onResumeJudge}>
          Resume judging [J]
        </Button>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-6">
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-mono text-sm tracking-wide uppercase text-muted-foreground">
              Generation runs
            </h3>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetchRuns()}
              disabled={runsLoading || isRefetching}
              className="gap-2"
            >
              {runsLoading || isRefetching ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCcw className="h-4 w-4" />
              )}
              Refresh
            </Button>
          </div>

          {runsLoading ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading runs…
            </div>
          ) : runs && runs.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {runs.map((run) => (
                <RunProgressCard key={run.id} run={run} />
              ))}
            </div>
          ) : (
            <Card className="border-dashed border-border/60">
              <CardContent className="py-10 text-center text-muted-foreground font-mono text-sm">
                No generation runs found.
              </CardContent>
            </Card>
          )}
        </section>

        <section className="space-y-3">
          <h3 className="font-mono text-sm tracking-wide uppercase text-muted-foreground">
            Leaderboard
          </h3>
          <LeaderboardView />
        </section>
      </div>
    </div>
  );
}
