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

  // Check for Anthropic format: raw.content[0].text
  if (payload.raw?.content?.[0]?.text) {
    return payload.raw.content[0].text;
  }

  // Check for OpenAI /v1/responses format with output array
  // Reasoning models (GPT-5, o3) have: [0]=reasoning, [1]=message
  // Standard models (GPT-4o) have: [0]=message
  if (Array.isArray(payload.raw?.output)) {
    // Find the first "message" type output (skip "reasoning" type)
    for (const output of payload.raw.output) {
      if (output?.content?.[0]?.text && output.type !== 'reasoning') {
        return output.content[0].text;
      }
    }
  }

  // Fallback: top-level content field (string)
  if (typeof payload.content === 'string' && payload.content) {
    return payload.content;
  }

  // Legacy OpenAI chat completions format
  if (Array.isArray(payload.choices) && payload.choices.length > 0) {
    const choice = payload.choices[0];
    if (typeof choice?.message?.content === 'string') {
      return choice.message.content;
    }
  }

  // Fallback: top-level output field
  if (typeof payload.output === 'string') {
    return payload.output;
  }

  // Last resort: payload itself is a string
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
        <pre className="font-mono text-sm leading-relaxed whitespace-pre-wrap text-foreground">
          {content}
        </pre>
      </ScrollArea>
    </div>
  );
}
