/**
 * Display panel for a single generation.
 */
import { Generation } from '@/lib/audition-api';
import { ScrollArea } from '@/components/ui/scroll-area';

interface GenerationPaneProps {
  generation: Generation;
  label: '1' | '2';
  highlighted?: boolean;
}

function resolveContent(generation: Generation): string {
  const payload = generation.response_payload as any;

  if (!payload) {
    return '[No content generated]';
  }

  if (typeof payload.content === 'string') {
    return payload.content;
  }

  if (Array.isArray(payload.choices) && payload.choices.length > 0) {
    const choice = payload.choices[0];
    if (typeof choice?.message?.content === 'string') {
      return choice.message.content;
    }
  }

  if (typeof payload.output === 'string') {
    return payload.output;
  }

  if (typeof payload === 'string') {
    return payload;
  }

  return '[Unsupported response payload format]';
}

export function GenerationPane({
  generation,
  label,
  highlighted = false,
}: GenerationPaneProps) {
  const content = resolveContent(generation);

  return (
    <div
      className={`relative h-full flex flex-col border border-border/70 rounded-lg bg-background/80 transition-shadow ${
        highlighted ? 'ring-2 ring-primary shadow-lg' : 'shadow-sm'
      }`}
    >
      <div className="px-4 py-2 border-b border-border/60">
        <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-primary/20 text-primary font-semibold text-sm">
          {label}
        </span>
      </div>
      <ScrollArea className="flex-1 p-4">
        <pre className="font-mono text-sm leading-relaxed whitespace-pre-wrap">
          {content}
        </pre>
      </ScrollArea>
    </div>
  );
}
