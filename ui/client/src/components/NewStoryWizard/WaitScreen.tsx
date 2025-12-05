/**
 * WaitScreen - Full-screen loading state for long-running API operations.
 *
 * Displays a timer counting up, progress bar, and retry/cancel buttons.
 * Used during story generation when API calls may take up to 10 minutes.
 */
import { useTheme } from '@/contexts/ThemeContext';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import { RotateCcw, X } from 'lucide-react';

interface WaitScreenProps {
  /** Status message displayed above the timer */
  statusText: string;
  /** Elapsed time in seconds */
  elapsedSeconds: number;
  /** Maximum expected time in seconds (default: 600 = 10 minutes) */
  maxSeconds?: number;
  /** Called when user clicks Retry button */
  onRetry: () => void;
  /** Called when user clicks Cancel button */
  onCancel: () => void;
  /** Whether an error occurred (shows retry button more prominently) */
  hasError?: boolean;
  /** Error message to display */
  errorMessage?: string;
}

/**
 * Format seconds as MM:SS
 */
function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export function WaitScreen({
  statusText,
  elapsedSeconds,
  maxSeconds = 600,
  onRetry,
  onCancel,
  hasError = false,
  errorMessage,
}: WaitScreenProps) {
  const { glowClass, generatingClass, isGilded, isVector, isVeil } = useTheme();

  // Calculate progress percentage (cap at 100%)
  const progressPercent = Math.min((elapsedSeconds / maxSeconds) * 100, 100);

  // Theme-specific accent color for the timer
  const timerColor = isGilded
    ? 'text-primary'
    : isVeil
    ? 'text-accent'
    : 'text-chart-1';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/95 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-8 p-8 max-w-md w-full">
        {/* Status text with generating animation */}
        <div className={`text-center ${hasError ? '' : generatingClass}`}>
          <h2 className="text-2xl font-medium tracking-wide text-foreground mb-2">
            {hasError ? 'Generation Failed' : statusText}
          </h2>
          {!hasError && (
            <p className="text-muted-foreground text-sm">
              This may take several minutes for complex scenarios
            </p>
          )}
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

        {/* Progress bar */}
        <div className="w-full max-w-xs">
          <Progress
            value={progressPercent}
            className="h-2 bg-muted"
          />
          <p className="text-center text-muted-foreground text-xs mt-2">
            {hasError ? 'Ready to retry' : `${Math.round(progressPercent)}% of expected time`}
          </p>
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
            {hasError ? 'Retry' : 'Retry Now'}
          </Button>
        </div>

        {/* Hint text */}
        {!hasError && (
          <p className="text-muted-foreground/60 text-xs text-center max-w-xs">
            Reasoning models like GPT-5.1 may need extra time for complex world-building.
            You can retry if the request seems stuck.
          </p>
        )}
      </div>
    </div>
  );
}
