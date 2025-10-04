/**
 * Judgment control bar with keyboard shortcuts.
 *
 * Handles: 1 (left), 2 (right), 3 (tie), ESC (exit), 0 (skip), N (notes)
 */
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
  onNote: (note: string) => void;
  onSkip?: () => void;
  disabled?: boolean;
}

export function JudgmentBar({
  onChooseLeft,
  onChooseRight,
  onTie,
  onExit,
  onNote,
  onSkip,
  disabled = false,
}: JudgmentBarProps) {
  const [noteDialogOpen, setNoteDialogOpen] = useState(false);
  const [noteText, setNoteText] = useState('');

  useEffect(() => {
    const handleKeyPress = (event: KeyboardEvent) => {
      if (disabled) return;
      if (noteDialogOpen) {
        if (event.key === 'Escape') {
          event.preventDefault();
          setNoteDialogOpen(false);
        }
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
          if (event.key.toLowerCase() === 'n') {
            event.preventDefault();
            setNoteDialogOpen(true);
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [disabled, noteDialogOpen, onChooseLeft, onChooseRight, onTie, onExit, onSkip]);

  const handleSubmitNote = () => {
    if (noteText.trim()) {
      onNote(noteText);
      setNoteText('');
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
            onClick={onExit}
            disabled={disabled}
            className="min-w-24 text-foreground"
          >
            [Esc] Exit
          </Button>
        </div>
      </div>

      <Dialog open={noteDialogOpen} onOpenChange={setNoteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Note</DialogTitle>
            <DialogDescription>
              Add a note about this comparison (optional).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="note">Note</Label>
              <Input
                id="note"
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                placeholder="e.g., 'Generation 2 loses coherency'"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleSubmitNote();
                  }
                }}
                autoFocus
              />
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setNoteDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleSubmitNote}>
                Save Note
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
