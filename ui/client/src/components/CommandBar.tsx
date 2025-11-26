import { useState, useRef } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";

interface CommandBarProps {
  onCommand: (command: string) => void;
  placeholder?: string;
  userPrefix?: string;
  isAwaitingConfirmation?: boolean;
  showButton?: boolean;
  onButtonClick?: () => void;
  onExpandInput?: () => void;
  isGenerating?: boolean;
  continueDisabled?: boolean;
}

export function CommandBar({
  onCommand,
  placeholder = "Enter directive or /command...",
  userPrefix = "NEXUS:USER",
  isAwaitingConfirmation = false,
  showButton = false,
  onButtonClick,
  onExpandInput,
  isGenerating = false,
  continueDisabled = false,
}: CommandBarProps) {
  const [command, setCommand] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const { isCyberpunk } = useTheme();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (command.trim()) {
      onCommand(command);
      setCommand("");
    } else if (isAwaitingConfirmation) {
      onCommand("");
    }
  };

  const glowClass = isCyberpunk ? "terminal-glow" : "deco-glow";
  const scanlineClass = isCyberpunk ? "terminal-scanlines" : "";

  return (
    <div className={`h-12 md:h-14 border-t border-border bg-card ${scanlineClass}`}>
      {showButton ? (
        <div className="h-full flex items-center px-2 md:px-4 gap-2">
          <Button
            onClick={onButtonClick}
            variant="ghost"
            disabled={continueDisabled || isGenerating}
            className={`font-mono text-xs md:text-sm text-muted-foreground hover:text-primary hover:bg-transparent transition-colors ${glowClass}`}
            data-testid="button-continue-story"
          >
            {isGenerating ? (
              <>
                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                generating...
              </>
            ) : (
              "continue the story"
            )}
          </Button>
          {onExpandInput && (
            <Button
              onClick={onExpandInput}
              variant="ghost"
              size="sm"
              className="font-mono text-[10px] md:text-xs text-muted-foreground hover:text-primary hover:bg-transparent transition-colors"
            >
              custom input
            </Button>
          )}
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="h-full flex items-center px-2 md:px-4 gap-2 md:gap-3">
          <span
            className={`text-xs md:text-sm font-mono text-primary ${glowClass} whitespace-nowrap flex-shrink-0`}
            data-testid="text-command-prefix"
          >
            {userPrefix}
          </span>
          <Input
            ref={inputRef}
            type="text"
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder={placeholder}
            className="flex-1 bg-transparent border-0 text-foreground font-mono text-xs md:text-sm focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-muted-foreground/50 min-w-0"
            disabled={isGenerating}
            data-testid="input-command"
            autoFocus
          />
        </form>
      )}
    </div>
  );
}
