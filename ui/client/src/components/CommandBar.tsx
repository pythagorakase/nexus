import { useState, useRef } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface CommandBarProps {
  onCommand: (command: string) => void;
  placeholder?: string;
  userPrefix?: string;
  isAwaitingConfirmation?: boolean;
  showButton?: boolean;
  onButtonClick?: () => void;
}

export function CommandBar({
  onCommand,
  placeholder = "Enter directive or /command...",
  userPrefix = "NEXUS:USER",
  isAwaitingConfirmation = false,
  showButton = false,
  onButtonClick,
}: CommandBarProps) {
  const [command, setCommand] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (command.trim()) {
      onCommand(command);
      setCommand("");
    } else if (isAwaitingConfirmation) {
      onCommand("");
    }
  };

  return (
    <div className="h-12 md:h-14 border-t border-border bg-card terminal-scanlines">
      {showButton ? (
        <div className="h-full flex items-center px-2 md:px-4">
          <Button
            onClick={onButtonClick}
            variant="ghost"
            className="font-mono text-xs md:text-sm text-muted-foreground hover:text-primary hover:bg-transparent transition-colors terminal-glow"
            data-testid="button-continue-story"
          >
            continue the story
          </Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="h-full flex items-center px-2 md:px-4 gap-2 md:gap-3">
          <span
            className="text-xs md:text-sm font-mono text-primary terminal-glow whitespace-nowrap flex-shrink-0"
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
            data-testid="input-command"
            autoFocus
          />
        </form>
      )}
    </div>
  );
}
