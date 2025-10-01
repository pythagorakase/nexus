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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-mono">ELO Leaderboard</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow className="font-mono">
              <TableHead className="w-16">Rank</TableHead>
              <TableHead>Model</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead className="text-right">ELO</TableHead>
              <TableHead className="text-right">Games</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rankings.map((entry, index) => (
              <TableRow key={entry.condition_id} className="font-mono">
                <TableCell className="font-semibold">
                  #{index + 1}
                </TableCell>
                <TableCell className="font-medium">
                  {entry.condition.model}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{entry.condition.provider}</Badge>
                </TableCell>
                <TableCell className="text-right font-semibold text-primary">
                  {entry.rating.toFixed(0)}
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
