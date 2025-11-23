import { Check, X, RefreshCw, Edit } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface AcceptRejectButtonsProps {
    onAccept: () => void;
    onReject: (action: "regenerate" | "edit_previous") => void;
    isProcessing: boolean;
    className?: string;
}

export function AcceptRejectButtons({
    onAccept,
    onReject,
    isProcessing,
    className,
}: AcceptRejectButtonsProps) {
    return (
        <div className={cn("flex items-center gap-4 p-4 border-t border-border bg-card/50", className)}>
            <div className="flex-1 flex gap-2">
                <Button
                    onClick={() => onReject("regenerate")}
                    disabled={isProcessing}
                    variant="outline"
                    className="flex-1 border-destructive/50 text-destructive hover:bg-destructive/10 hover:text-destructive hover:border-destructive font-mono text-xs uppercase tracking-wider"
                >
                    <RefreshCw className={cn("mr-2 h-3 w-3", isProcessing && "animate-spin")} />
                    [REJECT & RETRY]
                </Button>

                <Button
                    onClick={() => onReject("edit_previous")}
                    disabled={isProcessing}
                    variant="outline"
                    className="flex-1 border-warning/50 text-warning hover:bg-warning/10 hover:text-warning hover:border-warning font-mono text-xs uppercase tracking-wider"
                >
                    <Edit className="mr-2 h-3 w-3" />
                    [EDIT INPUT]
                </Button>
            </div>

            <Button
                onClick={onAccept}
                disabled={isProcessing}
                className="flex-[2] bg-primary/10 text-primary border border-primary/50 hover:bg-primary/20 hover:border-primary font-mono text-xs uppercase tracking-wider terminal-glow"
            >
                <Check className="mr-2 h-4 w-4" />
                [ACCEPT CHUNK]
            </Button>
        </div>
    );
}
