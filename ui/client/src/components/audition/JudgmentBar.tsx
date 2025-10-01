/**
 * Judgment control bar with keyboard shortcuts.
 *
 * Handles: A (choose A), B (choose B), T (tie), S (skip), N (notes)
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
  onChooseA: () => void;
  onChooseB: () => void;
  onTie: () => void;
  onSkip: () => void;
  onNote: (note: string) => void;
  disabled?: boolean;
}

export function JudgmentBar({
  onChooseA,
  onChooseB,
  onTie,
  onSkip,
  onNote,
  disabled = false
}: JudgmentBarProps) {
  const [noteDialogOpen, setNoteDialogOpen] = useState(false);
  const [noteText, setNoteText] = useState('');

  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (disabled) return;
      if (noteDialogOpen) return; // Don't handle shortcuts when note dialog is open

      const key = e.key.toLowerCase();

      switch (key) {
        case 'a':
          e.preventDefault();
          onChooseA();
          break;
        case 'b':
          e.preventDefault();
          onChooseB();
          break;
        case 't':
          e.preventDefault();
          onTie();
          break;
        case 's':
          e.preventDefault();
          onSkip();
          break;
        case 'n':
          e.preventDefault();
          setNoteDialogOpen(true);
          break;
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [disabled, noteDialogOpen, onChooseA, onChooseB, onTie, onSkip]);

  const handleSubmitNote = () => {
    if (noteText.trim()) {
      onNote(noteText);
      setNoteText('');
    }
    setNoteDialogOpen(false);
  };

  return (
    <>
      <div className="border-t border-border bg-card p-4">
        <div className="flex gap-3 justify-center items-center font-mono text-sm">
          <Button
            variant="outline"
            size="sm"
            onClick={onChooseA}
            disabled={disabled}
            className="min-w-24"
          >
            [A] Choose A
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onChooseB}
            disabled={disabled}
            className="min-w-24"
          >
            [B] Choose B
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onTie}
            disabled={disabled}
            className="min-w-24"
          >
            [T] Tie
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onSkip}
            disabled={disabled}
            className="min-w-24"
          >
            [S] Skip
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setNoteDialogOpen(true)}
            disabled={disabled}
            className="min-w-24"
          >
            [N] Add Note
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
                placeholder="e.g., 'Generation B has stilted dialog'"
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
