/**
 * Display panel for a single generation.
 *
 * Shows the generated narrative content with condition metadata.
 */
import { Condition, Generation } from '@/lib/audition-api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';

interface GenerationPaneProps {
  condition: Condition;
  generation: Generation;
  label: 'A' | 'B';
  highlighted?: boolean;
}

export function GenerationPane({
  condition,
  generation,
  label,
  highlighted = false
}: GenerationPaneProps) {
  const content = generation.response_payload?.content || '[No content generated]';
  const tokenCount = generation.output_tokens || 0;
  const costUSD = generation.cost_usd || 0;

  // Extract temperature from parameters if available
  const temp = condition.parameters?.temperature || 'N/A';

  return (
    <Card className={`h-full flex flex-col ${highlighted ? 'ring-2 ring-primary' : ''}`}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-mono">
            [{label}] {condition.model}
          </CardTitle>
          <div className="flex gap-2">
            <Badge variant="outline">{condition.provider}</Badge>
            <Badge variant="secondary">temp: {temp}</Badge>
          </div>
        </div>
        <div className="flex gap-3 text-sm text-muted-foreground font-mono">
          <span>{tokenCount}t</span>
          <span>${costUSD.toFixed(4)}</span>
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="prose prose-sm prose-invert max-w-none">
            <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed">
              {content}
            </pre>
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
