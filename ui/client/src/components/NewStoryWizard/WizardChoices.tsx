/**
 * WizardChoices - Structured choices plus an always-present freeform input
 * for the new-story wizard, mirroring the narrative reader's interaction
 * pattern (numbered choice buttons + freeform slot 0). The wizard composes
 * its own markup; reader-owned files are untouched.
 */
import {
    useCallback,
    useEffect,
    useRef,
    useState,
    type KeyboardEvent,
} from "react";
import { cn } from "@/lib/utils";
import { InlineMarkdown } from "@/components/nexus/ProseMarkdown";
import { Textarea } from "@/components/ui/textarea";

/**
 * Normalize backend choice payloads into display strings.
 *
 * The wizard turn contract returns `choices: string[]`, but older cached
 * turns may carry structured `{label, description}` objects.
 */
export function normalizeChoices(choices: unknown): string[] {
    if (!Array.isArray(choices)) {
        return [];
    }
    return choices
        .map((choice) => {
            if (typeof choice === "string") {
                return choice.trim();
            }
            if (
                choice !== null &&
                typeof choice === "object" &&
                "label" in choice &&
                "description" in choice
            ) {
                const { label, description } = choice as {
                    label: unknown;
                    description: unknown;
                };
                return `${String(label)}: ${String(description)}`.trim();
            }
            return String(choice ?? "").trim();
        })
        .filter(Boolean);
}

interface WizardChoicesProps {
    /** Structured choices from the wizard turn contract (may be empty). */
    choices: string[];
    /** Called with the chosen or typed text; the parent sends it as the turn. */
    onSubmit: (text: string) => void;
    /** Disable interaction while a turn is in flight or an artifact is pending. */
    disabled?: boolean;
}

export function WizardChoices({
    choices,
    onSubmit,
    disabled = false,
}: WizardChoicesProps) {
    const [freeform, setFreeform] = useState("");
    const freeformRef = useRef<HTMLTextAreaElement>(null);

    // Choice selection clears any freeform draft so it cannot leak into the
    // next turn's input.
    const submitChoice = useCallback(
        (text: string) => {
            if (disabled) return;
            setFreeform("");
            onSubmit(text);
        },
        [disabled, onSubmit],
    );

    const submitFreeform = useCallback(() => {
        const text = freeform.trim();
        if (!text || disabled) return;
        setFreeform("");
        onSubmit(text);
    }, [freeform, disabled, onSubmit]);

    const handleFreeformKeyDown = useCallback(
        (e: KeyboardEvent<HTMLTextAreaElement>) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submitFreeform();
            }
        },
        [submitFreeform],
    );

    // Number keys 1-N select choices when focus is outside any text field.
    useEffect(() => {
        const onKey = (e: globalThis.KeyboardEvent) => {
            if (disabled) return;
            const active = document.activeElement;
            if (
                active instanceof HTMLElement &&
                (active.tagName === "TEXTAREA" ||
                    active.tagName === "INPUT" ||
                    active.isContentEditable)
            ) {
                return;
            }
            const n = parseInt(e.key, 10);
            if (!isNaN(n) && n >= 1 && n <= choices.length) {
                submitChoice(choices[n - 1]);
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [choices, disabled, submitChoice]);

    return (
        <div className="space-y-1.5" data-testid="wizard-choices">
            {choices.map((text, i) => (
                <button
                    key={`${i}-${text}`}
                    type="button"
                    onClick={() => submitChoice(text)}
                    disabled={disabled}
                    data-testid={`wizard-choice-${i + 1}`}
                    className={cn(
                        "flex w-full items-start gap-3 px-4 py-3 text-left",
                        "border border-border/30 transition-colors duration-150",
                        "hover:border-primary/40 hover:bg-primary/5",
                        "disabled:pointer-events-none disabled:opacity-50",
                    )}
                >
                    <span className="min-w-[1.5rem] text-sm font-semibold text-primary">
                        {i + 1}.
                    </span>
                    <span className="flex-1 font-serif text-sm leading-relaxed text-muted-foreground">
                        <InlineMarkdown text={text} />
                    </span>
                </button>
            ))}
            {/* Freeform slot 0: unboxed italic input indented to the
                choice-text line, always present. */}
            <div className="flex items-start gap-3 px-4 py-3">
                <span className="min-w-[1.5rem]" aria-hidden="true" />
                <Textarea
                    ref={freeformRef}
                    rows={1}
                    value={freeform}
                    placeholder="…or something else"
                    onChange={(e) => setFreeform(e.target.value)}
                    onKeyDown={handleFreeformKeyDown}
                    disabled={disabled}
                    data-testid="wizard-freeform"
                    className={cn(
                        "min-h-0 flex-1 resize-none border-0 bg-transparent p-0",
                        "font-serif text-sm italic leading-relaxed shadow-none",
                        "placeholder:text-muted-foreground/60",
                        "focus-visible:ring-0 focus-visible:ring-offset-0",
                    )}
                />
            </div>
        </div>
    );
}
