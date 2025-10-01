/**
 * Hook for fetching and managing comparisons.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { auditionAPI, ComparisonQueueItem } from '@/lib/audition-api';

export interface UseComparisonOptions {
  run_id?: string;
  condition_a_id?: number;
  condition_b_id?: number;
  enabled?: boolean;
}

export function useComparison(options: UseComparisonOptions = {}) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['comparison', 'next', options],
    queryFn: () => auditionAPI.getNextComparison(options),
    enabled: options.enabled !== false,
    staleTime: 0, // Always fetch fresh comparison
    gcTime: 0, // Don't cache
  });

  const refetch = () => {
    queryClient.invalidateQueries({ queryKey: ['comparison', 'next'] });
  };

  return {
    comparison: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch,
  };
}
