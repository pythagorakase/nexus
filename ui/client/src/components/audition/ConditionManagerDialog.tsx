/**
 * Condition Manager Dialog - manage condition active/visible state
 */
import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Search } from 'lucide-react';
import { auditionAPI, Condition } from '@/lib/audition-api';

interface ConditionManagerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ConditionManagerDialog({
  open,
  onOpenChange,
}: ConditionManagerDialogProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const queryClient = useQueryClient();

  // Fetch all conditions
  const { data: conditions = [], isLoading } = useQuery({
    queryKey: ['conditions', 'all'],
    queryFn: () => auditionAPI.getAllConditions(),
    enabled: open,
  });

  // Mutation for updating conditions
  const updateConditionMutation = useMutation({
    mutationFn: ({
      conditionId,
      updates,
    }: {
      conditionId: number;
      updates: { is_active?: boolean; is_visible?: boolean };
    }) => auditionAPI.updateCondition(conditionId, updates),
    onSuccess: () => {
      // Invalidate all condition queries to refetch
      queryClient.invalidateQueries({ queryKey: ['conditions'] });
    },
  });

  // Filter conditions by search query
  const filteredConditions = useMemo(() => {
    if (!searchQuery) return conditions;

    const query = searchQuery.toLowerCase();
    return conditions.filter((condition) => {
      return (
        condition.slug.toLowerCase().includes(query) ||
        condition.provider.toLowerCase().includes(query) ||
        (condition.label && condition.label.toLowerCase().includes(query))
      );
    });
  }, [conditions, searchQuery]);

  // Group by provider for better organization
  const groupedConditions = useMemo(() => {
    const groups: { [provider: string]: Condition[] } = {};

    filteredConditions.forEach((condition) => {
      if (!groups[condition.provider]) {
        groups[condition.provider] = [];
      }
      groups[condition.provider].push(condition);
    });

    return groups;
  }, [filteredConditions]);

  const handleToggleActive = (conditionId: number, currentValue: boolean) => {
    updateConditionMutation.mutate({
      conditionId,
      updates: { is_active: !currentValue },
    });
  };

  const handleToggleVisible = (conditionId: number, currentValue: boolean) => {
    updateConditionMutation.mutate({
      conditionId,
      updates: { is_visible: !currentValue },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-5xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Manage Contenders</DialogTitle>
          <DialogDescription>
            Control which conditions are active and visible. Active conditions can run
            generations, visible conditions appear in leaderboards and comparisons.
          </DialogDescription>
        </DialogHeader>

        {/* Search bar */}
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by slug, provider, or label..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8"
          />
        </div>

        {/* Conditions table */}
        <ScrollArea className="flex-1 -mx-6">
          <div className="px-6">
            {isLoading ? (
              <div className="text-center py-8 text-muted-foreground">
                Loading conditions...
              </div>
            ) : filteredConditions.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                {searchQuery ? 'No conditions match your search' : 'No conditions found'}
              </div>
            ) : (
              Object.entries(groupedConditions).map(([provider, providerConditions]) => (
                <div key={provider} className="mb-6">
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase mb-2">
                    {provider}
                  </h3>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Slug</TableHead>
                        <TableHead>Label</TableHead>
                        <TableHead className="w-24 text-center">Active</TableHead>
                        <TableHead className="w-24 text-center">Visible</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {providerConditions.map((condition) => (
                        <TableRow key={condition.id}>
                          <TableCell className="font-mono text-sm">
                            {condition.slug}
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground">
                            {condition.label || '—'}
                          </TableCell>
                          <TableCell className="text-center">
                            <Checkbox
                              checked={condition.is_active}
                              onCheckedChange={() =>
                                handleToggleActive(condition.id, condition.is_active)
                              }
                              disabled={updateConditionMutation.isPending}
                            />
                          </TableCell>
                          <TableCell className="text-center">
                            <Checkbox
                              checked={condition.is_visible}
                              onCheckedChange={() =>
                                handleToggleVisible(condition.id, condition.is_visible)
                              }
                              disabled={updateConditionMutation.isPending}
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ))
            )}
          </div>
        </ScrollArea>

        {/* Summary footer */}
        <div className="text-sm text-muted-foreground border-t pt-4">
          {filteredConditions.length} condition(s) •{' '}
          {filteredConditions.filter((c) => c.is_active).length} active •{' '}
          {filteredConditions.filter((c) => c.is_visible).length} visible
        </div>
      </DialogContent>
    </Dialog>
  );
}
