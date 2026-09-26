/**
 * WaitScreen - Full-screen loading state for long-running API operations.
 *
 * Displays a timer counting up, a segmented stage track (one pip per stage:
 * done lit, active glowing, pending dim, failed in the danger colour), and
 * retry/cancel buttons. Used while the story's world is generated, which can
 * take many minutes.
 */
import { useTheme } from '@/contexts/ThemeContext';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { RotateCcw, X } from 'lucide-react';

interface WaitScreenProps<S extends string> {
  /** Status message displayed above the timer */
  statusText: string;
  /** Elapsed time in seconds */
  elapsedSeconds: number;
  /** Ordered stages of the operation; each renders as one pip */
  stages: readonly S[];
  /**
   * The stage in progress, or the stage that failed when hasError is set.
   * Null before the first stage reports.
   */
  currentStage: S | null;
  /** Called when user clicks Retry button */
  onRetry: () => void;
  /** Called when user clicks Cancel button */
  onCancel: () => void;
  /** Whether an error occurred (shows retry button more prominently) */
  hasError?: boolean;
  /** Error message to display */
  errorMessage?: string;
}

type StageState = 'done' | 'active' | 'pending' | 'failed';

/**
 * Format seconds as MM:SS
 */
function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

/** Each stage's state: every stage before the current one is done. */
function stageStates<S extends string>(
  stages: readonly S[],
  currentStage: S | null,
  hasError: boolean,
): StageState[] {
  const current = currentStage === null ? -1 : stages.indexOf(currentStage);
  if (currentStage !== null && current < 0) {
    throw new Error(`Wait stage ${currentStage} is not one of ${stages.join(', ')}`);
  }
  return stages.map((_, index) =>
    index < current
      ? 'done'
      : index > current
      ? 'pending'
      : hasError
      ? 'failed'
      : 'active',
  );
}

export function WaitScreen<S extends string>({
  statusText,
  elapsedSeconds,
  stages,
  currentStage,
  onRetry,
  onCancel,
  hasError = false,
  errorMessage,
}: WaitScreenProps<S>) {
  const { glowClass, generatingClass, isGilded, isVeil } = useTheme();
  const states = stageStates(stages, currentStage, hasError);

  // Theme-specific accent shared by the timer and the lit pips
  const timerColor = isGilded
    ? 'text-primary'
    : isVeil
    ? 'text-accent'
    : 'text-chart-1';
  const pipLit = isGilded
    ? 'bg-primary'
    : isVeil
    ? 'bg-accent'
    : 'bg-chart-1';
  const pipGlow = isGilded
    ? 'shadow-[0_0_6px_1px_hsl(var(--primary)/0.8)]'
    : isVeil
    ? 'shadow-[0_0_6px_1px_hsl(var(--accent)/0.8)]'
    : 'shadow-[0_0_6px_1px_hsl(var(--chart-1)/0.8)]';
  const pipClass: Record<StageState, string> = {
    done: pipLit,
    active: cn(pipLit, pipGlow, 'animate-pulse motion-reduce:animate-none'),
    pending: 'bg-muted',
    failed: 'bg-destructive shadow-[0_0_6px_1px_hsl(var(--destructive)/0.8)]',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/95 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-8 p-8 max-w-md w-full">
        {/* Status text with generating animation */}
        <div className={`text-center ${hasError ? '' : generatingClass}`}>
          <h2 className="text-2xl font-medium tracking-wide text-foreground mb-2">
            {hasError ? 'Generation Failed' : statusText}
          </h2>
        </div>

        {/* Error message if present */}
        {hasError && errorMessage && (
          <div className="text-destructive/80 text-sm text-center px-4 py-2 rounded-lg bg-destructive/10 border border-destructive/20">
            {errorMessage}
          </div>
        )}

        {/* Timer display */}
        <div className={`text-6xl font-mono ${timerColor} ${glowClass}`}>
          {formatTime(elapsedSeconds)}
        </div>

        {/* Stage track: one uncaptioned pip per stage */}
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={stages.length}
          aria-valuenow={states.filter((state) => state === 'done').length}
          className="flex w-full max-w-xs gap-1.5"
        >
          {states.map((state, index) => (
            <span
              key={stages[index]}
              data-testid="wait-stage"
              data-state={state}
              className={cn('h-1.5 flex-1 rounded-full transition-colors', pipClass[state])}
            />
          ))}
        </div>

        {/* Action buttons */}
        <div className="flex gap-4 mt-4">
          <Button
            variant="outline"
            onClick={onCancel}
            className="gap-2"
          >
            <X className="h-4 w-4" />
            Cancel
          </Button>
          <Button
            onClick={onRetry}
            className={`gap-2 ${hasError ? 'animate-pulse' : ''}`}
            variant={hasError ? 'default' : 'outline'}
          >
            <RotateCcw className="h-4 w-4" />
            Retry
          </Button>
        </div>
      </div>
    </div>
  );
}
