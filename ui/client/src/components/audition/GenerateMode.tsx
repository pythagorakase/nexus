import {useEffect, useRef, useState} from 'react';
import {Button} from '@/components/ui/button';
import {auditionAPI, MissingGeneration} from '@/lib/audition-api';
import {MissingGenerationsDialog} from './MissingGenerationsDialog';

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
  const [asyncOpenAI, setAsyncOpenAI] = useState<boolean>(() => {
    const saved = localStorage.getItem('audition_async_openai');
    return saved === 'true';
  });
  const [asyncAnthropic, setAsyncAnthropic] = useState<boolean>(() => {
    const saved = localStorage.getItem('audition_async_anthropic');
    return saved === 'true';
  });
  const [showMissingDialog, setShowMissingDialog] = useState(false);
  const [missingGenerations, setMissingGenerations] = useState<MissingGeneration[]>([]);
  const [initialRemaining, setInitialRemaining] = useState<number>(0);
  const [initialCompleted, setInitialCompleted] = useState<number>(0);
  const [initialFailed, setInitialFailed] = useState<number>(0);
  const [taskCount, setTaskCount] = useState<number | null>(null);
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

  // Save async preferences to localStorage
  useEffect(() => {
    localStorage.setItem('audition_async_openai', asyncOpenAI.toString());
  }, [asyncOpenAI]);

  useEffect(() => {
    localStorage.setItem('audition_async_anthropic', asyncAnthropic.toString());
  }, [asyncAnthropic]);

  // Fetch task count when limit or async settings change
  useEffect(() => {
    const fetchTaskCount = async () => {
      try {
        const limitValue = limit ? parseInt(limit, 10) : undefined;
        const asyncProviders: string[] = [];
        if (asyncOpenAI) asyncProviders.push('openai');
        if (asyncAnthropic) asyncProviders.push('anthropic');

        const data = await auditionAPI.getTaskCount(limitValue, asyncProviders);
        setTaskCount(data.task_count);
      } catch (err) {
        console.error('Error fetching task count:', err);
        setTaskCount(null);
      }
    };

    if (!isRunning) {
      fetchTaskCount();
    }
  }, [limit, asyncOpenAI, asyncAnthropic, isRunning]);

  // Start generation job
  const startGeneration = async () => {
    setError(null);
    try {
      const limitValue = limit ? parseInt(limit, 10) : undefined;
      const maxWorkersValue = maxWorkers ? parseInt(maxWorkers, 10) : undefined;

      // Build async providers array
      const asyncProviders: string[] = [];
      if (asyncOpenAI) asyncProviders.push('openai');
      if (asyncAnthropic) asyncProviders.push('anthropic');

      const data = await auditionAPI.startGeneration(limitValue, maxWorkersValue, asyncProviders);
      setJobId(data.job_id);
      setIsRunning(true);
      setOutput('');
      setStats({total: 0, remaining: 0, completed: 0, failed: 0});
      setInitialRemaining(missingCount || 0); // Capture the queue size at start
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

  // Show missing generations breakdown
  const showMissingBreakdown = async () => {
    try {
      const data = await auditionAPI.getMissingGenerations();
      setMissingGenerations(data);
      setShowMissingDialog(true);
    } catch (err) {
      console.error('Error fetching missing generations:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  // Poll for output and stats
  useEffect(() => {
    if (!jobId || !isRunning) return;

    let isFirstPoll = true;

    const interval = setInterval(async () => {
      try {
        const data = await auditionAPI.getGenerationOutput(jobId);

        setOutput(data.output || '');
        if (data.stats) {
          // Capture initial stats on first poll
          if (isFirstPoll) {
            setInitialCompleted(data.stats.completed || 0);
            setInitialFailed(data.stats.failed || 0);
            isFirstPoll = false;
          }
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

  // Calculate progress percentages for current queue
  const queueTotal = isRunning && initialRemaining > 0 ? initialRemaining : (stats.total || 0);
  const completedInQueue = isRunning ? Math.max(0, (stats.completed || 0) - initialCompleted) : 0;
  const failedInQueue = isRunning ? Math.max(0, (stats.failed || 0) - initialFailed) : 0;
  const completedPercent = queueTotal > 0 ? (completedInQueue / queueTotal) * 100 : 0;
  const failedPercent = queueTotal > 0 ? (failedInQueue / queueTotal) * 100 : 0;

  return (
    <div className="flex flex-col h-full">
      {/* Status Bar */}
      <div className="border-b border-border bg-card p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Generate Mode</h2>
            {!isRunning && missingCount !== null && (
              <p
                className="text-sm text-muted-foreground mt-1 cursor-pointer hover:text-foreground underline decoration-dotted"
                onClick={showMissingBreakdown}
              >
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
                <div className="h-4 w-px bg-border" />
                <div className="flex flex-col gap-1">
                  <div className="text-sm text-muted-foreground">Asynchronous:</div>
                  <div className="flex flex-col gap-1">
                    <label htmlFor="async-openai" className="text-sm text-muted-foreground flex items-center gap-1 cursor-pointer">
                      <input
                        id="async-openai"
                        type="checkbox"
                        checked={asyncOpenAI}
                        onChange={(e) => setAsyncOpenAI(e.target.checked)}
                        className="cursor-pointer"
                      />
                      OpenAI
                    </label>
                    <label htmlFor="async-anthropic" className="text-sm text-muted-foreground flex items-center gap-1 cursor-pointer">
                      <input
                        id="async-anthropic"
                        type="checkbox"
                        checked={asyncAnthropic}
                        onChange={(e) => setAsyncAnthropic(e.target.checked)}
                        className="cursor-pointer"
                      />
                      Anthropic
                    </label>
                  </div>
                </div>
              </>
            )}
            <div className="flex flex-col items-end gap-1">
              {isRunning ? (
                <Button onClick={stopGeneration} variant="destructive">
                  Stop
                </Button>
              ) : (
                <>
                  <Button onClick={startGeneration} variant="default" disabled={missingCount === 0}>
                    Start Generation
                  </Button>
                  {taskCount !== null && taskCount > 0 && (
                    <div className="text-xs text-muted-foreground">
                      tasks: {taskCount}
                    </div>
                  )}
                </>
              )}
            </div>
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
        <div
          ref={scrollRef}
          className="flex-1 rounded border border-border bg-muted/30 overflow-auto"
        >
          <pre className="p-4 text-xs font-mono text-foreground whitespace-pre-wrap">
            {output || 'No output yet. Click "Start Generation" to begin.'}
          </pre>
        </div>
      </div>

      {/* Missing Generations Dialog */}
      <MissingGenerationsDialog
        open={showMissingDialog}
        onOpenChange={setShowMissingDialog}
        missing={missingGenerations}
      />
    </div>
  );
}
