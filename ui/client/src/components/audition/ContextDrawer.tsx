/**
 * Collapsible drawer showing prompt context.
 */
import { useState } from 'react';
import { Prompt } from '@/lib/audition-api';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';

interface ContextDrawerProps {
  prompt: Prompt;
}

export function ContextDrawer({ prompt }: ContextDrawerProps) {
  const [isOpen, setIsOpen] = useState(false);

  const userInput = prompt.context?.user_input || 'N/A';
  const chunkId = prompt.chunk_id;
  const category = prompt.category || 'Uncategorized';
  const label = prompt.label || `Chunk ${chunkId}`;

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="border-t border-border">
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          className="w-full flex justify-between items-center px-4 py-3 font-mono text-sm hover:bg-accent"
        >
          <span>
            Context: {label} ({category})
          </span>
          {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="px-4 pb-4">
        <ScrollArea className="h-48 border border-border rounded-md p-3">
          <div className="space-y-3 font-mono text-sm">
            <div>
              <div className="text-muted-foreground mb-1">Chunk ID:</div>
              <div className="text-foreground">{chunkId}</div>
            </div>
            <div>
              <div className="text-muted-foreground mb-1">User Input:</div>
              <div className="text-primary">{userInput}</div>
            </div>
            {prompt.metadata?.authorial_directives && (
              <div>
                <div className="text-muted-foreground mb-1">Authorial Directives:</div>
                <ul className="list-disc list-inside text-muted-foreground">
                  {prompt.metadata.authorial_directives.map((directive: string, i: number) => (
                    <li key={i}>{directive}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </ScrollArea>
      </CollapsibleContent>
    </Collapsible>
  );
}
