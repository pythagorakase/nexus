import {useEffect, useRef, useState} from 'react';
import {Button} from '@/components/ui/button';
import {ScrollArea} from '@/components/ui/scroll-area';
import {auditionAPI} from '@/lib/audition-api';

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
  const [missingCount, setMissingCount] = useState<number | null>(null);
  const [limit, setLimit] = useState<string>('');
  const [maxWorkers, setMaxWorkers] = useState<string>('7');
  const scrollRef = useRef<HTMLDivElement>(null);

  // Fetch count of missing generations on mount and when job completes
  useEffect(() => {
    const fetchCount = async () => {
      try {
        const data = await auditionAPI.getMissingGenerationCount();
        setMissingCount(data.count);
      } catch (err) {
        console.error('Error fetching missing generation count:', err);
      }
    };
    fetchCount();
  }, [isRunning]); // Refetch when job starts/stops

  // Start generation job
  const startGeneration = async () => {
    setError(null);
    try {
      const limitValue = limit ? parseInt(limit, 10) : undefined;
      const maxWorkersValue = maxWorkers ? parseInt(maxWorkers, 10) : undefined;
      const data = await auditionAPI.startGeneration(limitValue, maxWorkersValue);
      setJobId(data.job_id);
      setIsRunning(true);
      setOutput('');
      setStats({total: 0, remaining: 0, completed: 0, failed: 0});
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  // Stop generation job
  const stopGeneration = async () => {
    if (!jobId) return;

    try {
      await auditionAPI.stopGeneration(jobId);
      setIsRunning(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  // Poll for output and stats
  useEffect(() => {
    if (!jobId || !isRunning) return;

    const interval = setInterval(async () => {
      try {
        const data = await auditionAPI.getGenerationOutput(jobId);

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
          <div>
            <h2 className="text-lg font-semibold text-foreground">Generate Mode</h2>
            {!isRunning && missingCount !== null && (
              <p className="text-sm text-muted-foreground mt-1">
                {missingCount} generation{missingCount !== 1 ? 's' : ''} needed
              </p>
            )}
          </div>
          <div className="flex gap-2 items-center">
            {!isRunning && (
              <>
                <div className="flex items-center gap-2">
                  <label htmlFor="limit-input" className="text-sm text-muted-foreground">
                    Limit:
                  </label>
                  <input
                    id="limit-input"
                    type="number"
                    min="1"
                    placeholder="All"
                    value={limit}
                    onChange={(e) => setLimit(e.target.value)}
                    className="w-20 px-2 py-1 text-sm border border-border rounded bg-background text-foreground"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label htmlFor="threads-input" className="text-sm text-muted-foreground">
                    Threads:
                  </label>
                  <input
                    id="threads-input"
                    type="number"
                    min="1"
                    max="20"
                    placeholder="7"
                    value={maxWorkers}
                    onChange={(e) => setMaxWorkers(e.target.value)}
                    className="w-20 px-2 py-1 text-sm border border-border rounded bg-background text-foreground"
                  />
                </div>
              </>
            )}
            {isRunning ? (
              <Button onClick={stopGeneration} variant="destructive">
                Stop
              </Button>
            ) : (
              <Button onClick={startGeneration} variant="default" disabled={missingCount === 0}>
                Start Generation
              </Button>
            )}
          </div>
        </div>

        {/* Stats */}
        <div className="flex gap-6 text-sm">
          <div>
            <span className="text-muted-foreground">Total:</span>{' '}
            <span className="font-mono font-semibold text-foreground">{stats.total}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Remaining:</span>{' '}
            <span className="font-mono font-semibold text-foreground">{stats.remaining}</span>
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
            {output || 'No output yet. Click "Start Generation" to begin.'}
          </pre>
        </ScrollArea>
      </div>
    </div>
  );
}
