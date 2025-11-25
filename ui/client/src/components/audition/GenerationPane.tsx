/**
 * Display panel for a single generation.
 */
import { Generation } from '@/lib/audition-api';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useFonts } from '@/contexts/FontContext';
import ReactMarkdown from 'react-markdown';

interface GenerationPaneProps {
  generation: Generation;
  label: '1' | '2';
  highlighted?: boolean;
}

export function resolveGenerationContent(generation: Generation): string {
  const payload = generation.response_payload as any;

  if (!payload) {
    return '[No content generated]';
  }

  // Priority 1: Top-level content field (most reliable for recent generations)
  if (typeof payload.content === 'string' && payload.content) {
    return payload.content;
  }

  // Priority 2: Anthropic format: raw.content[0].text (legacy sync generations)
  if (payload.raw?.content?.[0]?.text) {
    return payload.raw.content[0].text;
  }

  // Priority 3: OpenAI /v1/responses format with output array
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

  // Priority 4: Legacy OpenAI chat completions format
  if (Array.isArray(payload.choices) && payload.choices.length > 0) {
    const choice = payload.choices[0];
    if (typeof choice?.message?.content === 'string') {
      return choice.message.content;
    }
  }

  // Priority 5: top-level output field
  if (typeof payload.output === 'string') {
    return payload.output;
  }

  // Last resort: payload itself is a string
  if (typeof payload === 'string') {
    return payload;
  }

  return `[Unsupported response payload format - generation.id: ${generation.id}]`;
}

export function GenerationPane({
  generation,
  label,
  highlighted = false,
}: GenerationPaneProps) {
  const content = resolveGenerationContent(generation);
  const { currentBodyFont } = useFonts();

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
      <ScrollArea className="flex-1 p-4" style={{ transform: 'translateZ(0)', contain: 'layout style' }}>
        <div
          className="text-sm leading-relaxed text-foreground"
          style={{ fontFamily: currentBodyFont }}
        >
          <ReactMarkdown
            components={{
              p: ({node, ...props}) => <p className="mb-3 last:mb-0" {...props} />,
              strong: ({node, ...props}) => <strong className="font-bold" {...props} />,
              em: ({node, ...props}) => <em className="italic" {...props} />,
              ol: ({node, ...props}) => (
                <ol className="pl-10 list-decimal space-y-1 my-3" style={{ listStylePosition: 'outside' }} {...props} />
              ),
              ul: ({node, ...props}) => (
                <ul className="pl-6 list-disc space-y-1 my-3" style={{ listStylePosition: 'outside' }} {...props} />
              ),
              li: ({node, ...props}) => <li className="leading-relaxed pl-1" {...props} />,
              h1: ({node, ...props}) => <h1 className="text-lg font-bold mb-2 mt-4 first:mt-0" {...props} />,
              h2: ({node, ...props}) => <h2 className="text-base font-bold mb-2 mt-3 first:mt-0" {...props} />,
              h3: ({node, ...props}) => <h3 className="font-bold mb-1 mt-2 first:mt-0" {...props} />,
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      </ScrollArea>
    </div>
  );
}
