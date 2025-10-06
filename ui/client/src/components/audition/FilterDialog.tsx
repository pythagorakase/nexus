/**
 * Reusable filter dialog with Include/Exclude columns.
 */
import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChevronRight, ChevronLeft } from 'lucide-react';

export interface FilterItem {
  id: number;
  label: string;
}

interface FilterDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  items: FilterItem[];
  initialIncluded?: number[];
  onApply: (includedIds: number[]) => void;
}

export function FilterDialog({
  open,
  onOpenChange,
  title,
  description,
  items,
  initialIncluded,
  onApply,
}: FilterDialogProps) {
  const [includedIds, setIncludedIds] = useState<Set<number>>(new Set());
  const [selectedIncluded, setSelectedIncluded] = useState<Set<number>>(new Set());
  const [selectedExcluded, setSelectedExcluded] = useState<Set<number>>(new Set());

  // Initialize included/excluded on open
  useEffect(() => {
    if (open) {
      if (initialIncluded && initialIncluded.length > 0) {
        setIncludedIds(new Set(initialIncluded));
      } else {
        // Default: all items included
        setIncludedIds(new Set(items.map(i => i.id)));
      }
      setSelectedIncluded(new Set());
      setSelectedExcluded(new Set());
    }
  }, [open, items, initialIncluded]);

  const includedItems = items.filter(item => includedIds.has(item.id));
  const excludedItems = items.filter(item => !includedIds.has(item.id));

  const handleIncludedClick = (id: number, event: React.MouseEvent) => {
    if (event.shiftKey) {
      // Add to selection
      setSelectedIncluded(prev => new Set(prev).add(id));
    } else {
      // Toggle selection
      setSelectedIncluded(prev => {
        const newSet = new Set(prev);
        if (newSet.has(id)) {
          newSet.delete(id);
        } else {
          newSet.clear();
          newSet.add(id);
        }
        return newSet;
      });
    }
    setSelectedExcluded(new Set());
  };

  const handleExcludedClick = (id: number, event: React.MouseEvent) => {
    if (event.shiftKey) {
      // Add to selection
      setSelectedExcluded(prev => new Set(prev).add(id));
    } else {
      // Toggle selection
      setSelectedExcluded(prev => {
        const newSet = new Set(prev);
        if (newSet.has(id)) {
          newSet.delete(id);
        } else {
          newSet.clear();
          newSet.add(id);
        }
        return newSet;
      });
    }
    setSelectedIncluded(new Set());
  };

  const handleIncludedDoubleClick = (id: number) => {
    setIncludedIds(prev => {
      const newSet = new Set(prev);
      newSet.delete(id);
      return newSet;
    });
    setSelectedIncluded(new Set());
  };

  const handleExcludedDoubleClick = (id: number) => {
    setIncludedIds(prev => new Set(prev).add(id));
    setSelectedExcluded(new Set());
  };

  const moveToExcluded = () => {
    if (selectedIncluded.size > 0) {
      setIncludedIds(prev => {
        const newSet = new Set(prev);
        selectedIncluded.forEach(id => newSet.delete(id));
        return newSet;
      });
      setSelectedIncluded(new Set());
    }
  };

  const moveToIncluded = () => {
    if (selectedExcluded.size > 0) {
      setIncludedIds(prev => {
        const newSet = new Set(prev);
        selectedExcluded.forEach(id => newSet.add(id));
        return newSet;
      });
      setSelectedExcluded(new Set());
    }
  };

  const handleApply = () => {
    onApply(Array.from(includedIds));
    onOpenChange(false);
  };

  const handleCancel = () => {
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-[1fr_auto_1fr] gap-4 h-[400px]">
          {/* Include column */}
          <div className="flex flex-col">
            <div className="text-sm font-medium mb-2">Include</div>
            <ScrollArea className="border rounded-md flex-1">
              <div className="p-2 space-y-1">
                {includedItems.map(item => (
                  <div
                    key={item.id}
                    className={`px-2 py-1 text-sm rounded cursor-pointer select-none font-mono ${
                      selectedIncluded.has(item.id)
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-accent'
                    }`}
                    onClick={(e) => handleIncludedClick(item.id, e)}
                    onDoubleClick={() => handleIncludedDoubleClick(item.id)}
                  >
                    {item.label}
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>

          {/* Arrow buttons */}
          <div className="flex flex-col items-center justify-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={moveToExcluded}
              disabled={selectedIncluded.size === 0}
              title="Move to Exclude"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={moveToIncluded}
              disabled={selectedExcluded.size === 0}
              title="Move to Include"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
          </div>

          {/* Exclude column */}
          <div className="flex flex-col">
            <div className="text-sm font-medium mb-2">Exclude</div>
            <ScrollArea className="border rounded-md flex-1">
              <div className="p-2 space-y-1">
                {excludedItems.map(item => (
                  <div
                    key={item.id}
                    className={`px-2 py-1 text-sm rounded cursor-pointer select-none font-mono ${
                      selectedExcluded.has(item.id)
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-accent'
                    }`}
                    onClick={(e) => handleExcludedClick(item.id, e)}
                    onDoubleClick={() => handleExcludedDoubleClick(item.id)}
                  >
                    {item.label}
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleCancel}>
            Cancel
          </Button>
          <Button onClick={handleApply}>
            Apply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
