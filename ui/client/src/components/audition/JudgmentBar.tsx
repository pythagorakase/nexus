/**
 * Judgment control bar with keyboard shortcuts.
 *
 * Handles: 1 (left), 2 (right), 3 (tie), ESC (exit), 0 (skip), N (notes), E (export)
 */
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface JudgmentBarProps {
  onChooseLeft: () => void;
  onChooseRight: () => void;
  onTie: () => void;
  onExit: () => void;
  onNote: (leftNote: string, rightNote: string) => void;
  onExport: () => void;
  onSkip?: () => void;
  disabled?: boolean;
}

export function JudgmentBar({
  onChooseLeft,
  onChooseRight,
  onTie,
  onExit,
  onNote,
  onExport,
  onSkip,
  disabled = false,
}: JudgmentBarProps) {
  const [noteDialogOpen, setNoteDialogOpen] = useState(false);
  const [leftNote, setLeftNote] = useState('');
  const [rightNote, setRightNote] = useState('');

  useEffect(() => {
    const handleKeyPress = (event: KeyboardEvent) => {
      if (disabled) return;

      // Block all shortcuts when note dialog is open
      if (noteDialogOpen) {
        if (event.key === 'Escape') {
          event.preventDefault();
          setNoteDialogOpen(false);
        }
        // Stop propagation to prevent parent handlers from firing
        event.stopPropagation();
        return;
      }

      switch (event.key) {
        case '1':
          event.preventDefault();
          onChooseLeft();
          break;
        case '2':
          event.preventDefault();
          onChooseRight();
          break;
        case '3':
          event.preventDefault();
          onTie();
          break;
        case '0':
          if (onSkip) {
            event.preventDefault();
            onSkip();
          }
          break;
        case 'Escape':
          event.preventDefault();
          onExit();
          break;
        default: {
          const key = event.key.toLowerCase();
          if (key === 'n') {
            event.preventDefault();
            setNoteDialogOpen(true);
          } else if (key === 'e') {
            event.preventDefault();
            onExport();
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyPress, { capture: true });
    return () => window.removeEventListener('keydown', handleKeyPress, { capture: true });
  }, [disabled, noteDialogOpen, onChooseLeft, onChooseRight, onTie, onExit, onExport, onSkip]);

  const handleSubmitNote = () => {
    if (leftNote.trim() || rightNote.trim()) {
      onNote(leftNote, rightNote);
      setLeftNote('');
      setRightNote('');
    }
    setNoteDialogOpen(false);
  };

  return (
    <>
      <div className="border-t border-border bg-card/90 p-4">
        <div className="flex flex-wrap gap-3 justify-center items-center font-mono text-xs sm:text-sm">
          <Button
            variant="outline"
            size="sm"
            onClick={onChooseLeft}
            disabled={disabled}
            className="min-w-28 text-foreground"
          >
            [1] Left passage
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onChooseRight}
            disabled={disabled}
            className="min-w-28 text-foreground"
          >
            [2] Right passage
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onTie}
            disabled={disabled}
            className="min-w-28 text-foreground"
          >
            [3] Tie
          </Button>
          {onSkip && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onSkip}
              disabled={disabled}
              className="min-w-24 text-foreground"
            >
              [0] Skip
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setNoteDialogOpen(true)}
            disabled={disabled}
            className="min-w-24 text-foreground"
          >
            [N] Add Note
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onExport}
            disabled={disabled}
            className="min-w-24 text-foreground"
          >
            [E] Export
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onExit}
            disabled={disabled}
            className="min-w-24 text-foreground"
          >
            [Esc] Exit
          </Button>
        </div>
      </div>

      <Dialog open={noteDialogOpen} onOpenChange={setNoteDialogOpen}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Add Condition Notes</DialogTitle>
            <DialogDescription>
              Add notes to each condition (optional). These will be attached to the condition for future reference.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="left-note">Left Passage</Label>
                <Textarea
                  id="left-note"
                  value={leftNote}
                  onChange={(e) => setLeftNote(e.target.value)}
                  placeholder="e.g., 'good comedic timing'"
                  rows={3}
                  className="resize-none"
                  autoFocus
                />
              </div>
              <div>
                <Label htmlFor="right-note">Right Passage</Label>
                <Textarea
                  id="right-note"
                  value={rightNote}
                  onChange={(e) => setRightNote(e.target.value)}
                  placeholder="e.g., 'introduced unexpected moral dilemma'"
                  rows={3}
                  className="resize-none"
                />
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setNoteDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleSubmitNote}>
                Save Notes
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
