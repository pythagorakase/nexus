/**
 * Hook for recording comparison judgments.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { auditionAPI, ComparisonCreate } from '@/lib/audition-api';

export function useJudgment() {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (comparison: ComparisonCreate) => auditionAPI.createComparison(comparison),
    onSuccess: () => {
      // Invalidate comparison query to fetch next one
      queryClient.invalidateQueries({ queryKey: ['comparison', 'next'] });
      // Invalidate leaderboard to show updated ELO
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] });
    },
  });

  return {
    recordJudgment: mutation.mutate,
    recordJudgmentAsync: mutation.mutateAsync,
    isRecording: mutation.isPending,
    isError: mutation.isError,
    error: mutation.error,
    data: mutation.data,
  };
}
