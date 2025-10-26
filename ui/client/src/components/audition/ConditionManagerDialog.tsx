/**
 * Condition Manager Dialog - manage condition active/visible state
 */
import { useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { auditionAPI, Condition } from '@/lib/audition-api';

interface ConditionManagerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ConditionManagerDialog({
  open,
  onOpenChange,
}: ConditionManagerDialogProps) {
  const queryClient = useQueryClient();

  // Fetch all conditions
  const { data: conditions = [], isLoading, error } = useQuery({
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

  // Group by provider for better organization
  const groupedConditions = useMemo(() => {
    const groups: { [provider: string]: Condition[] } = {};

    conditions.forEach((condition) => {
      if (!groups[condition.provider]) {
        groups[condition.provider] = [];
      }
      groups[condition.provider].push(condition);
    });

    return groups;
  }, [conditions]);

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
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader className="pb-2">
          <DialogTitle>Manage Contenders</DialogTitle>
          <DialogDescription className="text-xs">
            Control which conditions are active and visible. Active conditions can run
            generations, visible conditions appear in leaderboards and comparisons.
          </DialogDescription>
        </DialogHeader>

        {/* Conditions table */}
        <ScrollArea className="h-[500px] -mx-6">
          <div className="px-6">
            {isLoading ? (
              <div className="text-center py-8 text-muted-foreground">
                Loading conditions...
              </div>
            ) : error ? (
              <div className="text-center py-8 text-destructive">
                Error loading conditions. Please make sure the API server is running.
              </div>
            ) : conditions.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No conditions found
              </div>
            ) : (
              Object.entries(groupedConditions).map(([provider, providerConditions]) => (
                <div key={provider} className="mb-3">
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase mb-1 px-1">
                    {provider}
                  </h3>
                  <Table>
                    <TableHeader>
                      <TableRow className="hover:bg-transparent border-b">
                        <TableHead className="h-8 text-xs">Slug</TableHead>
                        <TableHead className="h-8 text-xs">Label</TableHead>
                        <TableHead className="h-8 w-20 text-center text-xs">Active</TableHead>
                        <TableHead className="h-8 w-20 text-center text-xs">Visible</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {providerConditions.map((condition) => (
                        <TableRow key={condition.id} className="border-b hover:bg-muted/50">
                          <TableCell className="font-mono text-xs py-1.5">
                            {condition.slug}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground py-1.5">
                            {condition.label || '—'}
                          </TableCell>
                          <TableCell className="text-center py-1.5">
                            <div className="flex justify-center">
                              <Checkbox
                                checked={condition.is_active}
                                onCheckedChange={() =>
                                  handleToggleActive(condition.id, condition.is_active)
                                }
                                disabled={updateConditionMutation.isPending}
                                className="h-4 w-4"
                              />
                            </div>
                          </TableCell>
                          <TableCell className="text-center py-1.5">
                            <div className="flex justify-center">
                              <Checkbox
                                checked={condition.is_visible}
                                onCheckedChange={() =>
                                  handleToggleVisible(condition.id, condition.is_visible)
                                }
                                disabled={updateConditionMutation.isPending}
                                className="h-4 w-4"
                              />
                            </div>
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
        {conditions.length > 0 && (
          <div className="text-xs text-muted-foreground border-t pt-2">
            {conditions.length} condition(s) •{' '}
            {conditions.filter((c) => c.is_active).length} active •{' '}
            {conditions.filter((c) => c.is_visible).length} visible
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
