/**
 * ELO leaderboard display.
 */
import { useState } from 'react';
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
import { Loader2, Mail } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

export function LeaderboardView() {
  const [notesDialogOpen, setNotesDialogOpen] = useState(false);
  const [selectedNotes, setSelectedNotes] = useState<Array<{ text: string; timestamp: string }>>([]);

  const { data: rankings, isLoading } = useQuery({
    queryKey: ['leaderboard'],
    queryFn: () => auditionAPI.getLeaderboard(20),
    refetchInterval: 5000, // Refresh every 5 seconds
  });

  const handleViewNotes = (notes: Array<{ text: string; timestamp: string }>) => {
    setSelectedNotes(notes);
    setNotesDialogOpen(true);
  };

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

  const formatOptionalNumber = (value: number | null | undefined) => {
    return value !== null && value !== undefined ? value.toString() : '-';
  };

  const formatReasoning = (reasoningEffort: string | null | undefined, thinkingEnabled: boolean | null | undefined) => {
    // Check for reasoning_effort (OpenAI reasoning models)
    if (reasoningEffort) return reasoningEffort;

    // Check for thinking_enabled (Anthropic extended thinking)
    if (thinkingEnabled === true) return 'enabled';
    if (thinkingEnabled === false) return 'disabled';

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
    return provider;
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="font-mono text-lg">ELO Leaderboard</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
            <TableHeader>
              <TableRow className="font-mono text-xs">
                <TableHead className="w-12">Rank</TableHead>
                <TableHead className="text-right w-20">ELO</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Model</TableHead>
                <TableHead className="text-center">Temperature</TableHead>
                <TableHead className="text-center">Top P</TableHead>
                <TableHead className="text-center">Min P</TableHead>
                <TableHead className="text-center">Freq Pen</TableHead>
                <TableHead className="text-center">Pres Pen</TableHead>
                <TableHead className="text-center">Repeat Pen</TableHead>
                <TableHead className="text-center">Reasoning</TableHead>
                <TableHead className="text-right">Ratings</TableHead>
                <TableHead className="text-center w-16">Notes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rankings.map((entry, index) => (
                <TableRow key={entry.condition_id} className="font-mono">
                  <TableCell className="font-semibold py-1">
                    {index + 1}
                  </TableCell>
                  <TableCell className="text-right font-semibold text-primary text-base py-1">
                    {entry.rating.toFixed(0)}
                  </TableCell>
                  <TableCell className="py-1">
                    {formatProvider(entry.condition.provider)}
                  </TableCell>
                  <TableCell className="font-medium py-1">
                    {formatModelName(entry.condition.model_name)}
                  </TableCell>
                  <TableCell className="text-center text-muted-foreground py-1">
                    {formatOptionalNumber(entry.condition.temperature)}
                  </TableCell>
                  <TableCell className="text-center text-muted-foreground py-1">
                    {formatOptionalNumber(entry.condition.top_p)}
                  </TableCell>
                  <TableCell className="text-center text-muted-foreground py-1">
                    {formatOptionalNumber(entry.condition.min_p)}
                  </TableCell>
                  <TableCell className="text-center text-muted-foreground py-1">
                    {formatOptionalNumber(entry.condition.frequency_penalty)}
                  </TableCell>
                  <TableCell className="text-center text-muted-foreground py-1">
                    {formatOptionalNumber(entry.condition.presence_penalty)}
                  </TableCell>
                  <TableCell className="text-center text-muted-foreground py-1">
                    {formatOptionalNumber(entry.condition.repetition_penalty)}
                  </TableCell>
                  <TableCell className="text-center text-muted-foreground py-1">
                    {formatReasoning(entry.condition.reasoning_effort, entry.condition.thinking_enabled)}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground py-1">
                    {entry.games_played}
                  </TableCell>
                  <TableCell className="text-center py-1">
                    {entry.condition.notes && entry.condition.notes.length > 0 ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0"
                        onClick={() => handleViewNotes(entry.condition.notes!)}
                      >
                        <Mail className="h-4 w-4 text-muted-foreground" />
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={notesDialogOpen} onOpenChange={setNotesDialogOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Condition Notes</DialogTitle>
            <DialogDescription>
              Notes recorded during judging for this condition.
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[60vh] overflow-y-auto">
            {selectedNotes.length > 0 ? (
              <div className="space-y-3">
                {selectedNotes.map((note, index) => (
                  <div key={index} className="border-b border-border pb-3 last:border-b-0">
                    <div className="text-xs text-muted-foreground mb-1">
                      {new Date(note.timestamp).toLocaleString()}
                    </div>
                    <div className="text-sm">
                      {note.text}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No notes available.</p>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
