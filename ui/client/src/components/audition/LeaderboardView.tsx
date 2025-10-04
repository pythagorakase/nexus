/**
 * ELO leaderboard display.
 */
import { useQuery } from '@tanstack/react-query';
import { auditionAPI } from '@/lib/audition-api';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2 } from 'lucide-react';

export function LeaderboardView() {
  const { data: rankings, isLoading } = useQuery({
    queryKey: ['leaderboard'],
    queryFn: () => auditionAPI.getLeaderboard(20),
    refetchInterval: 5000, // Refresh every 5 seconds
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!rankings || rankings.length === 0) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-center text-muted-foreground">
            No rankings available yet. Complete some comparisons to see the leaderboard!
          </p>
        </CardContent>
      </Card>
    );
  }

  const formatTemperature = (params: Record<string, any>) => {
    return params?.temperature !== undefined ? params.temperature.toString() : '-';
  };

  const formatReasoning = (params: Record<string, any>) => {
    if (!params) return '-';

    // Check for reasoning_effort (OpenAI reasoning models)
    if (params.reasoning_effort) return params.reasoning_effort;

    // Check for thinking_enabled (Anthropic extended thinking)
    if (params.thinking_enabled === true) return 'enabled';
    if (params.thinking_enabled === false) return 'disabled';

    return '-';
  };

  const formatModelName = (modelName: string) => {
    // Simplify model names for display
    const simplifications: Record<string, string> = {
      'claude-sonnet-4-5': 'Sonnet 4.5',
      'claude-opus-4-1': 'Opus 4.1',
      'gpt-4o': '4o',
      'gpt-5': 'GPT-5',
      'o3': 'o3',
    };
    return simplifications[modelName] || modelName;
  };

  const formatProvider = (provider: string) => {
    return provider.charAt(0).toUpperCase() + provider.slice(1);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-mono text-lg">ELO Leaderboard</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow className="font-mono text-xs">
              <TableHead className="w-12">Rank</TableHead>
              <TableHead className="text-right w-20">ELO</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>Model</TableHead>
              <TableHead className="text-center">Temperature</TableHead>
              <TableHead className="text-center">Reasoning</TableHead>
              <TableHead className="text-right">Ratings</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rankings.map((entry, index) => (
              <TableRow key={entry.condition_id} className="font-mono">
                <TableCell className="font-semibold">
                  {index + 1}
                </TableCell>
                <TableCell className="text-right font-semibold text-primary text-base">
                  {entry.rating.toFixed(0)}
                </TableCell>
                <TableCell>
                  {formatProvider(entry.condition.provider)}
                </TableCell>
                <TableCell className="font-medium">
                  {formatModelName(entry.condition.model_name)}
                </TableCell>
                <TableCell className="text-center text-muted-foreground">
                  {formatTemperature(entry.condition.parameters)}
                </TableCell>
                <TableCell className="text-center text-muted-foreground">
                  {formatReasoning(entry.condition.parameters)}
                </TableCell>
                <TableCell className="text-right text-muted-foreground">
                  {entry.games_played}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
