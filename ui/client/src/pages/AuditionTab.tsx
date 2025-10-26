/**
 * Apex Audition tab for comparing model generations.
 */
import { useMemo, useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useComparison } from '@/hooks/useComparison';
import { ComparisonLayout } from '@/components/audition/ComparisonLayout';
import { ResultsDashboard } from '@/components/audition/ResultsDashboard';
import { GenerateMode } from '@/components/audition/GenerateMode';
import { FilterDialog, FilterItem } from '@/components/audition/FilterDialog';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, Filter, X } from 'lucide-react';
import { auditionAPI } from '@/lib/audition-api';

type AuditionMode = 'judge' | 'results' | 'generate';

export default function AuditionTab() {
  const [evaluator] = useState(() => {
    return localStorage.getItem('audition_evaluator') || 'default';
  });

  const [mode, setMode] = useState<AuditionMode>('judge');
  const [comparisonCount, setComparisonCount] = useState(0);
  const [skippedCount, setSkippedCount] = useState(0);

  // Filter state
  const [conditionIds, setConditionIds] = useState<number[] | undefined>(() => {
    const saved = localStorage.getItem('audition_condition_filters');
    return saved ? JSON.parse(saved) : undefined;
  });
  const [passageMode, setPassageMode] = useState<'all' | 'custom' | number>(() => {
    const saved = localStorage.getItem('audition_passage_mode');
    return saved ? JSON.parse(saved) : 'all';
  });
  const [promptIds, setPromptIds] = useState<number[] | undefined>(() => {
    const saved = localStorage.getItem('audition_prompt_filters');
    return saved ? JSON.parse(saved) : undefined;
  });
  const [contenderDialogOpen, setContenderDialogOpen] = useState(false);
  const [passageDialogOpen, setPassageDialogOpen] = useState(false);

  // Fetch conditions and prompts for filtering
  const { data: conditions } = useQuery({
    queryKey: ['conditions'],
    queryFn: () => auditionAPI.getConditions(),
  });

  const visibleConditions = useMemo(() => {
    return (conditions || []).filter(condition => condition.is_visible !== false);
  }, [conditions]);

  useEffect(() => {
    if (!conditionIds || conditionIds.length === 0) return;
    const visibleIds = new Set(visibleConditions.map(condition => condition.id));
    const filtered = conditionIds.filter(id => visibleIds.has(id));
    if (filtered.length !== conditionIds.length) {
      setConditionIds(filtered.length > 0 ? filtered : undefined);
    }
  }, [conditionIds, visibleConditions]);

  const { data: prompts } = useQuery({
    queryKey: ['prompts'],
    queryFn: () => auditionAPI.getPrompts(),
  });

  // Save filters to localStorage
  useEffect(() => {
    if (conditionIds) {
      localStorage.setItem('audition_condition_filters', JSON.stringify(conditionIds));
    } else {
      localStorage.removeItem('audition_condition_filters');
    }
  }, [conditionIds]);

  useEffect(() => {
    localStorage.setItem('audition_passage_mode', JSON.stringify(passageMode));
  }, [passageMode]);

  useEffect(() => {
    if (promptIds) {
      localStorage.setItem('audition_prompt_filters', JSON.stringify(promptIds));
    } else {
      localStorage.removeItem('audition_prompt_filters');
    }
  }, [promptIds]);

  // Build filter params for useComparison
  const filterParams = useMemo(() => {
    const params: any = {};

    if (conditionIds && conditionIds.length > 0) {
      params.condition_ids = conditionIds;
    }

    if (passageMode === 'custom' && promptIds && promptIds.length > 0) {
      params.prompt_ids = promptIds;
    } else if (typeof passageMode === 'number') {
      params.prompt_id = passageMode;
    }

    return params;
  }, [conditionIds, passageMode, promptIds]);

  const { comparison, isLoading, isError, error, refetch } = useComparison({
    enabled: mode === 'judge',
    ...filterParams,
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

  // Filter UI handlers
  const conditionFilterItems: FilterItem[] = useMemo(() => {
    return visibleConditions.map(c => ({
      id: c.id,
      label: c.slug,
    }));
  }, [visibleConditions]);

  const promptFilterItems: FilterItem[] = useMemo(() => {
    return (prompts || []).map(p => ({
      id: p.id,
      label: p.label || `Chunk ${p.chunk_id}`,
    }));
  }, [prompts]);

  const hasConditionFilters = conditionIds && conditionIds.length > 0 &&
    conditionIds.length !== visibleConditions.length;
  const hasPassageFilters = passageMode !== 'all';

  const handleApplyConditionFilters = (ids: number[]) => {
    setConditionIds(ids.length === visibleConditions.length ? undefined : ids);
    refetch();
  };

  const handleApplyPassageFilters = (ids: number[]) => {
    setPromptIds(ids.length === prompts?.length ? undefined : ids);
    refetch();
  };

  const handlePassageModeChange = (value: string) => {
    if (value === 'ALL') {
      setPassageMode('all');
    } else if (value === 'CUSTOM') {
      setPassageMode('custom');
      setPassageDialogOpen(true);
    } else {
      setPassageMode(parseInt(value));
    }
    refetch();
  };

  const clearConditionFilters = () => {
    setConditionIds(undefined);
    refetch();
  };

  const clearPassageFilters = () => {
    setPassageMode('all');
    setPromptIds(undefined);
    refetch();
  };

  const clearAllFilters = () => {
    setConditionIds(undefined);
    setPassageMode('all');
    setPromptIds(undefined);
    refetch();
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
            className={mode === 'judge' ? '' : 'text-foreground'}
          >
            Arena
          </Button>
          <Button
            variant={mode === 'results' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setMode('results')}
            className={mode === 'results' ? '' : 'text-foreground'}
          >
            Results
          </Button>
          <Button
            variant={mode === 'generate' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => setMode('generate')}
            className={mode === 'generate' ? '' : 'text-foreground'}
          >
            Commission
          </Button>

          {mode === 'judge' && (
            <>
              <div className="h-4 w-px bg-border" />
              <Button
                variant="outline"
                size="sm"
                onClick={() => setContenderDialogOpen(true)}
              >
                <Filter className="h-3 w-3 mr-1" />
                [C] Contenders
              </Button>
              <Select value={passageMode === 'all' ? 'ALL' : passageMode === 'custom' ? 'CUSTOM' : String(passageMode)} onValueChange={handlePassageModeChange}>
                <SelectTrigger className="w-[140px] h-8 text-xs">
                  <SelectValue placeholder="Passages" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">ALL</SelectItem>
                  <SelectItem value="CUSTOM">CUSTOM</SelectItem>
                  {prompts && prompts.length > 0 && (
                    <>
                      <div className="h-px bg-border my-1" />
                      {prompts.map(p => (
                        <SelectItem key={p.id} value={String(p.id)} className="text-xs">
                          {p.label || `Chunk ${p.chunk_id}`}
                        </SelectItem>
                      ))}
                    </>
                  )}
                </SelectContent>
              </Select>
              {(hasConditionFilters || hasPassageFilters) && (
                <>
                  {hasConditionFilters && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={clearConditionFilters}
                      className="h-7 px-2"
                    >
                      <X className="h-3 w-3 mr-1" />
                      Clear Contenders
                    </Button>
                  )}
                  {hasPassageFilters && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={clearPassageFilters}
                      className="h-7 px-2"
                    >
                      <X className="h-3 w-3 mr-1" />
                      Clear Passages
                    </Button>
                  )}
                  {hasConditionFilters && hasPassageFilters && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={clearAllFilters}
                      className="h-7 px-2"
                    >
                      <X className="h-3 w-3 mr-1" />
                      Clear All
                    </Button>
                  )}
                </>
              )}
            </>
          )}
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

      {/* Filter dialogs */}
      <FilterDialog
        open={contenderDialogOpen}
        onOpenChange={setContenderDialogOpen}
        title="Filter Contenders"
        description="Select which conditions to include in comparisons."
        items={conditionFilterItems}
        initialIncluded={conditionIds}
        onApply={handleApplyConditionFilters}
      />

      <FilterDialog
        open={passageDialogOpen}
        onOpenChange={setPassageDialogOpen}
        title="Filter Passages"
        description="Select which passages to include in comparisons."
        items={promptFilterItems}
        initialIncluded={promptIds}
        onApply={handleApplyPassageFilters}
      />
    </div>
  );
}
