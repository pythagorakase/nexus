import { useState, useRef, useCallback, type KeyboardEvent } from "react";
import { Check, Pencil, X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Selection data structure matching backend SelectChoiceRequest
 */
export interface ChoiceSelection {
  label: number | "freeform";
  text: string;
  edited: boolean;
}

interface StoryChoicesProps {
  /** Array of choice strings from the storyteller */
  choices: string[];
  /** Previous selection for regeneration UX (highlights what was chosen before) */
  previousSelection?: ChoiceSelection;
  /** Callback when user selects a choice */
  onSelect: (selection: ChoiceSelection) => void;
  /** Disable interaction during generation */
  disabled?: boolean;
}

interface ChoiceItemProps {
  number: number;
  text: string;
  onSelect: (text: string, edited: boolean) => void;
  isPreviousSelection?: boolean;
  disabled?: boolean;
}

function ChoiceItem({
  number,
  text,
  onSelect,
  isPreviousSelection = false,
  disabled = false,
}: ChoiceItemProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editedText, setEditedText] = useState(text);
  const textRef = useRef<HTMLSpanElement>(null);

  const handleEdit = useCallback(() => {
    setIsEditing(true);
    setEditedText(text);
    setTimeout(() => {
      if (textRef.current) {
        textRef.current.focus();
        // Place cursor at end
        const range = document.createRange();
        range.selectNodeContents(textRef.current);
        range.collapse(false);
        const sel = window.getSelection();
        if (sel) {
          sel.removeAllRanges();
          sel.addRange(range);
        }
      }
    }, 0);
  }, [text]);

  const handleSend = useCallback(() => {
    const finalText = editedText.trim() || text;
    const wasEdited = finalText !== text;
    onSelect(finalText, wasEdited);
    setIsEditing(false);
  }, [editedText, text, onSelect]);

  const handleCancel = useCallback(() => {
    setEditedText(text);
    setIsEditing(false);
    if (textRef.current) {
      textRef.current.textContent = text;
    }
  }, [text]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      } else if (e.key === "Escape") {
        handleCancel();
      }
    },
    [handleSend, handleCancel]
  );

  const isActive = isHovered || isEditing;

  return (
    <div
      onMouseEnter={() => !disabled && setIsHovered(true)}
      onMouseLeave={() => !isEditing && setIsHovered(false)}
      className={cn(
        "flex items-start gap-3 w-full px-4 py-3 transition-all duration-150",
        "border border-border/30",
        isEditing && "bg-primary/10 border-primary",
        isActive && !isEditing && "bg-primary/5 border-primary/40",
        isPreviousSelection && !isActive && "border-l-2 border-l-accent",
        disabled && "opacity-50 cursor-not-allowed"
      )}
    >
      {/* Choice number */}
      <span className="text-sm font-semibold text-primary min-w-[1.5rem]">
        {number}.
      </span>

      {/* Choice text (contentEditable when editing) */}
      <span
        ref={textRef}
        contentEditable={isEditing}
        suppressContentEditableWarning
        onClick={() => isHovered && !isEditing && !disabled && handleEdit()}
        onInput={(e) => setEditedText(e.currentTarget.textContent || "")}
        onKeyDown={handleKeyDown}
        onPaste={(e) => {
          // P2: Strip HTML on paste to prevent XSS
          e.preventDefault();
          const text = e.clipboardData.getData('text/plain');
          document.execCommand('insertText', false, text);
        }}
        className={cn(
          "flex-1 text-sm leading-relaxed outline-none min-h-[1.6em]",
          "transition-colors duration-150",
          isActive ? "text-foreground" : "text-muted-foreground",
          isEditing && "cursor-text",
          isHovered && !isEditing && "cursor-text"
        )}
      >
        {text}
      </span>

      {/* Action buttons */}
      <div className="flex gap-1.5 items-center min-w-[52px] justify-end">
        {isEditing ? (
          <>
            <button
              onClick={handleCancel}
              className={cn(
                "w-6 h-6 flex items-center justify-center",
                "bg-transparent border border-muted-foreground/30",
                "hover:border-primary hover:text-foreground",
                "transition-all duration-150",
                "text-muted-foreground"
              )}
              title="Cancel (Esc)"
            >
              <X className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleSend}
              className={cn(
                "w-6 h-6 flex items-center justify-center",
                "bg-primary text-primary-foreground",
                "hover:bg-accent transition-all duration-150"
              )}
              title="Send (Enter)"
            >
              <Check className="w-3.5 h-3.5" />
            </button>
          </>
        ) : (
          isHovered &&
          !disabled && (
            <>
              <button
                onClick={handleEdit}
                className={cn(
                  "w-6 h-6 flex items-center justify-center",
                  "bg-transparent border border-muted-foreground/30",
                  "hover:border-primary hover:bg-primary/10",
                  "transition-all duration-150"
                )}
                title="Edit before sending"
              >
                <Pencil className="w-3 h-3 text-muted-foreground" />
              </button>
              <button
                onClick={() => onSelect(text, false)}
                className={cn(
                  "w-6 h-6 flex items-center justify-center",
                  "bg-primary text-primary-foreground",
                  "hover:bg-accent transition-all duration-150"
                )}
                title="Send as-is"
              >
                <Check className="w-3.5 h-3.5" />
              </button>
            </>
          )
        )}
      </div>
    </div>
  );
}

interface FreeformChoiceProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

function FreeformChoice({ onSend, disabled = false }: FreeformChoiceProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [inputText, setInputText] = useState("");
  const textRef = useRef<HTMLDivElement>(null);

  const handleClick = useCallback(() => {
    if (disabled) return;
    setIsEditing(true);
    setTimeout(() => textRef.current?.focus(), 0);
  }, [disabled]);

  const handleSend = useCallback(() => {
    if (inputText.trim()) {
      onSend(inputText.trim());
      setIsEditing(false);
      setInputText("");
    }
  }, [inputText, onSend]);

  const handleCancel = useCallback(() => {
    setIsEditing(false);
    setInputText("");
  }, []);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      } else if (e.key === "Escape") {
        handleCancel();
      }
    },
    [handleSend, handleCancel]
  );

  if (isEditing) {
    return (
      <div
        className={cn(
          "px-4 py-3 bg-secondary/30 border-l-2 border-l-accent",
          "border border-accent"
        )}
      >
        <div
          ref={textRef}
          contentEditable
          onInput={(e) => setInputText(e.currentTarget.textContent || "")}
          onKeyDown={handleKeyDown}
          onPaste={(e) => {
            // P2: Strip HTML on paste to prevent XSS
            e.preventDefault();
            const text = e.clipboardData.getData('text/plain');
            document.execCommand('insertText', false, text);
          }}
          data-placeholder="Describe your action..."
          className={cn(
            "text-sm leading-relaxed text-foreground outline-none min-h-[1.6em] mb-2",
            "empty:before:content-[attr(data-placeholder)] empty:before:text-muted-foreground"
          )}
        />
        <div className="flex justify-end gap-1.5">
          <button
            onClick={handleCancel}
            className={cn(
              "w-6 h-6 flex items-center justify-center",
              "bg-transparent border border-muted-foreground/30",
              "hover:border-primary hover:text-foreground",
              "transition-all duration-150 text-muted-foreground"
            )}
            title="Cancel (Esc)"
          >
            <X className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleSend}
            disabled={!inputText.trim()}
            className={cn(
              "w-6 h-6 flex items-center justify-center",
              "border-none transition-all duration-150",
              inputText.trim()
                ? "bg-primary text-primary-foreground cursor-pointer"
                : "bg-muted-foreground text-muted cursor-default"
            )}
            title="Send (Enter)"
          >
            <Check className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <button
      onClick={handleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      disabled={disabled}
      className={cn(
        "block w-full px-4 py-2.5 text-left transition-all duration-150",
        "bg-transparent border border-dashed",
        "text-[13px] italic",
        isHovered
          ? "border-muted-foreground/60 text-muted-foreground"
          : "border-muted-foreground/30 text-muted-foreground/70",
        disabled && "opacity-50 cursor-not-allowed"
      )}
    >
      Or something else?
    </button>
  );
}

/**
 * StoryChoices - Presents narrative choices to the player
 *
 * Features:
 * - 2-4 choices displayed as selectable items with hover reveal
 * - Edit-before-send: click to edit, Enter to send, Escape to cancel
 * - Freeform option always available
 * - Previous selection highlighted for regeneration UX
 *
 * @example
 * <StoryChoices
 *   choices={["Accept the invitation", "Find the Nosferatu", "Approach the Prince"]}
 *   onSelect={(selection) => handleSelection(selection)}
 * />
 */
export function StoryChoices({
  choices,
  previousSelection,
  onSelect,
  disabled = false,
}: StoryChoicesProps) {
  const handleChoiceSelect = useCallback(
    (index: number, text: string, edited: boolean) => {
      onSelect({
        label: index + 1, // 1-indexed labels
        text,
        edited,
      });
    },
    [onSelect]
  );

  const handleFreeformSelect = useCallback(
    (text: string) => {
      onSelect({
        label: "freeform",
        text,
        edited: false, // Freeform is never "edited" - it's always custom
      });
    },
    [onSelect]
  );

  if (!choices || choices.length < 2) {
    return null; // Don't render if no valid choices
  }

  return (
    <div className="space-y-1.5 mt-6">
      {choices.map((choice, index) => (
        <ChoiceItem
          key={index}
          number={index + 1}
          text={choice}
          onSelect={(text, edited) => handleChoiceSelect(index, text, edited)}
          isPreviousSelection={
            previousSelection?.label === index + 1 ||
            (previousSelection?.label === "freeform" && false)
          }
          disabled={disabled}
        />
      ))}
      <FreeformChoice onSend={handleFreeformSelect} disabled={disabled} />
    </div>
  );
}
