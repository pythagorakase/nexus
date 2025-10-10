/**
 * Dialog showing detailed breakdown of missing generations.
 */
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { MissingGeneration } from '@/lib/audition-api';

interface MissingGenerationsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  missing: MissingGeneration[];
}

export function MissingGenerationsDialog({
  open,
  onOpenChange,
  missing,
}: MissingGenerationsDialogProps) {
  // Group by condition
  const byCondition = missing.reduce((acc, item) => {
    if (!acc[item.condition_slug]) {
      acc[item.condition_slug] = {
        label: item.condition_label || item.condition_slug,
        provider: item.provider,
        model: item.model_name,
        prompts: [],
      };
    }
    acc[item.condition_slug].prompts.push({
      chunk_id: item.chunk_id,
      label: item.prompt_label,
      category: item.prompt_category,
    });
    return acc;
  }, {} as Record<string, { label: string; provider: string; model: string; prompts: Array<{ chunk_id: number; label: string | null; category: string | null }> }>);

  const conditions = Object.entries(byCondition).sort((a, b) =>
    a[0].localeCompare(b[0])
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle>Missing Generations</DialogTitle>
          <DialogDescription>
            {missing.length} prompt×condition combination{missing.length !== 1 ? 's' : ''} need{missing.length === 1 ? 's' : ''} generation
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="h-[60vh] pr-4">
          <div className="space-y-6">
            {conditions.map(([slug, { label, provider, model, prompts }]) => (
              <div key={slug} className="space-y-2">
                <div className="sticky top-0 bg-background pb-2 border-b">
                  <h3 className="font-semibold text-foreground">
                    {label || slug}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {provider}/{model} • {prompts.length} prompt{prompts.length !== 1 ? 's' : ''}
                  </p>
                </div>
                <ul className="space-y-1 pl-4">
                  {prompts.map((prompt, idx) => (
                    <li key={idx} className="text-sm text-muted-foreground">
                      <span className="text-foreground">Chunk {prompt.chunk_id}</span>
                      {prompt.category && (
                        <span className="text-muted-foreground"> • {prompt.category}</span>
                      )}
                      {prompt.label && (
                        <span>: {prompt.label}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
