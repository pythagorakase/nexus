import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface EditPreviousDialogProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (newInput: string) => void;
    initialInput: string;
    isSubmitting: boolean;
}

export function EditPreviousDialog({
    isOpen,
    onClose,
    onSubmit,
    initialInput,
    isSubmitting,
}: EditPreviousDialogProps) {
    const [input, setInput] = useState(initialInput);

    useEffect(() => {
        if (isOpen) {
            setInput(initialInput);
        }
    }, [isOpen, initialInput]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (input.trim()) {
            onSubmit(input);
        }
    };

    return (
        <Dialog open={isOpen} onOpenChange={(open) => !isSubmitting && !open && onClose()}>
            <DialogContent className="sm:max-w-[500px] bg-card border-border terminal-scanlines">
                <DialogHeader>
                    <DialogTitle className="font-mono text-primary terminal-glow">
                        [EDIT PREVIOUS INPUT]
                    </DialogTitle>
                    <DialogDescription className="font-mono text-xs text-muted-foreground">
                        Modify your previous instruction. This will regenerate the current chunk.
                    </DialogDescription>
                </DialogHeader>

                <form onSubmit={handleSubmit} className="space-y-4 py-4">
                    <Textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        className="font-mono text-sm bg-background/50 border-primary/20 focus-visible:ring-primary/50 min-h-[100px]"
                        placeholder="Enter your instruction..."
                        disabled={isSubmitting}
                    />

                    <DialogFooter>
                        <Button
                            type="button"
                            variant="ghost"
                            onClick={onClose}
                            disabled={isSubmitting}
                            className="font-mono text-xs"
                        >
                            CANCEL
                        </Button>
                        <Button
                            type="submit"
                            disabled={isSubmitting || !input.trim()}
                            className="font-mono text-xs bg-primary/20 text-primary hover:bg-primary/30 border border-primary/50 terminal-glow"
                        >
                            {isSubmitting ? (
                                <>
                                    <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                                    REGENERATING...
                                </>
                            ) : (
                                "[CONFIRM & REGENERATE]"
                            )}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}
