import {useEffect, useRef, useState} from 'react';
import {Button} from '@/components/ui/button';
import {ScrollArea} from '@/components/ui/scroll-area';

interface GenerationStats {
  total: number;
  remaining: number;
  completed: number;
  failed: number;
}

export function GenerateMode() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [stats, setStats] = useState<GenerationStats>({
    total: 0,
    remaining: 0,
    completed: 0,
    failed: 0,
  });
  const [output, setOutput] = useState<string>('');
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Start generation job
  const startGeneration = async () => {
    setError(null);
    try {
      const response = await fetch('/api/audition/generate/start', {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error('Failed to start generation job');
      }

      const data = await response.json();
      setJobId(data.job_id);
      setIsRunning(true);
      setOutput('');
      setStats({total: 0, remaining: 0, completed: 0, failed: 0});
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  // Poll for output and stats
  useEffect(() => {
    if (!jobId || !isRunning) return;

    const interval = setInterval(async () => {
      try {
        const response = await fetch(
          `/api/audition/generate/output?job_id=${jobId}`
        );

        if (!response.ok) {
          throw new Error('Failed to fetch job output');
        }

        const data = await response.json();

        setOutput(data.output || '');
        if (data.stats) {
          setStats(data.stats);
        }
        if (data.status === 'completed') {
          setIsRunning(false);
        }
      } catch (err) {
        console.error('Error fetching job output:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
        setIsRunning(false);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [jobId, isRunning]);

  // Auto-scroll to bottom when output changes
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [output]);

  // Calculate progress percentages
  const total = stats.total || 0;
  const completed = stats.completed || 0;
  const failed = stats.failed || 0;
  const completedPercent = total > 0 ? (completed / total) * 100 : 0;
  const failedPercent = total > 0 ? (failed / total) * 100 : 0;

  return (
    <div className="flex flex-col h-full">
      {/* Status Bar */}
      <div className="border-b border-border bg-card p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Generate Mode</h2>
          <Button
            onClick={startGeneration}
            disabled={isRunning}
            variant={isRunning ? 'secondary' : 'default'}
          >
            {isRunning ? 'Running...' : 'Start Regeneration'}
          </Button>
        </div>

        {/* Stats */}
        <div className="flex gap-6 text-sm">
          <div>
            <span className="text-muted-foreground">Total:</span>{' '}
            <span className="font-mono font-semibold">{stats.total}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Remaining:</span>{' '}
            <span className="font-mono font-semibold">{stats.remaining}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Completed:</span>{' '}
            <span className="font-mono font-semibold text-blue-600">
              {stats.completed}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">Failed:</span>{' '}
            <span className="font-mono font-semibold text-red-600">
              {stats.failed}
            </span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="h-6 bg-secondary rounded-md overflow-hidden">
          <div className="h-full flex">
            {/* Completed (blue) */}
            <div
              className="bg-blue-500 transition-all duration-300"
              style={{width: `${completedPercent}%`}}
            />
            {/* Failed (red) */}
            <div
              className="bg-red-500 transition-all duration-300"
              style={{width: `${failedPercent}%`}}
            />
          </div>
        </div>

        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded p-2">
            Error: {error}
          </div>
        )}
      </div>

      {/* Terminal Output */}
      <div className="flex-1 bg-background p-4 overflow-hidden flex flex-col">
        <div className="text-sm text-muted-foreground mb-2">
          Terminal Output:
        </div>
        <ScrollArea
          className="flex-1 rounded border border-border bg-muted/30"
          ref={scrollRef}
        >
          <pre className="p-4 text-xs font-mono text-foreground whitespace-pre-wrap">
            {output || 'No output yet. Click "Start Regeneration" to begin.'}
          </pre>
        </ScrollArea>
      </div>
    </div>
  );
}
