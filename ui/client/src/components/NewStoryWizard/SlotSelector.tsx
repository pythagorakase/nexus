import { useState } from "react";
import { AlertTriangle, Loader2, Lock, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { getSlotVisuals, readBoundSlot } from "./slotVisualState";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/hooks/use-toast";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface SlotData {
    slot: number;
    thread_id?: string;
    setting_draft?: any;
    character_draft?: any;
    selected_seed?: any;
    initial_location?: any;
    base_timestamp?: string;
    target_slot?: number;
    is_active?: boolean;
    is_locked?: boolean;
    last_updated?: string;
    // Wizard resume state
    wizard_in_progress?: boolean;
    wizard_thread_id?: string;
    wizard_phase?: "setting" | "character" | "seed";
}

// Subtle corner accent for Art Deco framing
const SlotFrameCorner = ({ position }: { position: 'tl' | 'tr' | 'bl' | 'br' }) => (
    <div
        className="absolute w-4 h-4 pointer-events-none"
        style={{
            top: position.includes('t') ? 0 : undefined,
            bottom: position.includes('b') ? 0 : undefined,
            left: position.includes('l') ? 0 : undefined,
            right: position.includes('r') ? 0 : undefined,
            borderTop: position.includes('t') ? '1px solid hsl(var(--primary) / 0.4)' : undefined,
            borderBottom: position.includes('b') ? '1px solid hsl(var(--primary) / 0.4)' : undefined,
            borderLeft: position.includes('l') ? '1px solid hsl(var(--primary) / 0.4)' : undefined,
            borderRight: position.includes('r') ? '1px solid hsl(var(--primary) / 0.4)' : undefined,
        }}
    />
);

interface SlotSelectorProps {
    onSlotSelected: (slot: number) => void;
    onSlotResumed: (slotData: SlotData) => void;
}

export function SlotSelector({ onSlotSelected, onSlotResumed }: SlotSelectorProps) {
    const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
    // Currently-bound story slot (localStorage 'activeSlot') — gets the beacon.
    const [boundSlot] = useState<number | null>(readBoundSlot);
    const queryClient = useQueryClient();

    // Fetch status of all 5 slots
    const { data: slots = [], isLoading } = useQuery<SlotData[]>({
        queryKey: ["/api/story/new/slots"],
        queryFn: async () => {
            const res = await fetch("/api/story/new/slots");
            if (!res.ok) throw new Error("Failed to fetch slots");
            const data = await res.json();

            // Map response to expected format
            return data.map((slot: any) => ({
                slot: slot.slot_number,
                is_active: slot.is_active,
                is_locked: slot.is_locked,
                // Wizard resume state
                wizard_in_progress: slot.wizard_in_progress,
                wizard_thread_id: slot.wizard_thread_id,
                wizard_phase: slot.wizard_phase,
            }));
        },
    });

    const resetMutation = useMutation({
        mutationFn: async (slot: number) => {
            const res = await fetch("/api/story/new/setup/reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ slot }),
            });
            if (!res.ok) throw new Error("Failed to reset slot");
            return res.json();
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["/api/story/new/slots"] });
            toast({ title: "Slot cleared" });
        },
    });

    // Occupied slot awaiting overwrite confirmation (tenet 9: wiping an
    // occupied slot earns explicit friction; empty slots stay single-click).
    const [slotToOverwrite, setSlotToOverwrite] = useState<number | null>(null);

    const proceedToWizard = (slot: number) => {
        setSelectedSlot(slot);
        onSlotSelected(slot);
    };

    const handleSelect = (slot: number, slotData: SlotData) => {
        if (slotData.is_locked) {
            toast({ title: "Slot locked", variant: "destructive" });
            return;
        }
        if (slotData.is_active) {
            // Initializing an occupied slot destroys its story; gate it
            // behind an explicit confirmation. Mouse and keyboard activation
            // both route through here, so both paths are gated.
            setSlotToOverwrite(slot);
            return;
        }
        proceedToWizard(slot);
    };

    const confirmOverwrite = () => {
        if (slotToOverwrite !== null) {
            const slot = slotToOverwrite;
            setSlotToOverwrite(null);
            proceedToWizard(slot);
        }
    };

    const handleResume = (e: React.MouseEvent, slotData: SlotData) => {
        e.stopPropagation();
        onSlotResumed(slotData);
    };

    const [slotToDelete, setSlotToDelete] = useState<number | null>(null);

    const handleReset = (e: React.MouseEvent, slotData: SlotData) => {
        e.stopPropagation();
        if (slotData.is_locked) return;
        setSlotToDelete(slotData.slot);
    };

    const confirmReset = () => {
        if (slotToDelete) {
            resetMutation.mutate(slotToDelete);
            setSlotToDelete(null);
        }
    };

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-64">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        );
    }

    return (
        <div className="space-y-6 max-w-4xl mx-auto p-6">
            {/* Deco frame wrapper with corner accents */}
            <div className="relative p-4">
                <SlotFrameCorner position="tl" />
                <SlotFrameCorner position="tr" />
                <SlotFrameCorner position="bl" />
                <SlotFrameCorner position="br" />

                <div className="grid gap-4 md:grid-cols-1">
                    {slots.map((slotData) => {
                        const visuals = getSlotVisuals(slotData, {
                            selected: selectedSlot === slotData.slot,
                            boundSlot,
                        });
                        return (
                        <Card
                            key={slotData.slot}
                            onClick={() => handleSelect(slotData.slot, slotData)}
                            onKeyDown={(e) => {
                                if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
                                    e.preventDefault();
                                    handleSelect(slotData.slot, slotData);
                                }
                            }}
                            tabIndex={0}
                            role="group"
                            aria-label={visuals.ariaLabel}
                            title={visuals.ariaLabel}
                            data-occupancy={visuals.occupancy}
                            className={visuals.card}
                        >
                            {/* Scanline effect */}
                            <div className="absolute inset-0 pointer-events-none bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] z-0 bg-[length:100%_2px,3px_100%] opacity-20" />

                            {/* Currently-bound story: glowing left edge-marker (same
                                vocabulary as the nexus current-chunk marker) */}
                            {visuals.bound && (
                                <div
                                    aria-hidden="true"
                                    className="absolute left-0 top-0 bottom-0 w-[3px] bg-primary shadow-[0_0_10px_2px_hsl(var(--primary)/0.6)]"
                                />
                            )}

                            <div className={cn("relative z-10 flex items-center justify-between", visuals.content)}>
                                <div className="flex items-center gap-4">
                                    <div className={visuals.tile}>
                                        {slotData.slot}
                                        {/* Wizard-in-progress: pulsing corner mote */}
                                        {visuals.occupancy === "wizard" && (
                                            <span
                                                aria-hidden="true"
                                                className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-primary animate-pulse motion-reduce:animate-none shadow-[0_0_6px_1px_hsl(var(--primary)/0.8)]"
                                            />
                                        )}
                                    </div>

                                    <div className="flex items-center gap-2">
                                        <span className={cn(
                                            "font-mono text-sm font-bold",
                                            slotData.is_locked
                                                ? "text-destructive"
                                                : visuals.occupancy === "empty"
                                                    ? "text-muted-foreground"
                                                    : "text-foreground"
                                        )}>
                                            MEMORY SLOT {slotData.slot}
                                        </span>
                                    </div>
                                </div>

                                <div className="flex items-center gap-2 ml-auto">
                                    {slotData.is_locked ? (
                                        <div
                                            className="flex items-center text-destructive px-3 py-1.5 border border-destructive/30 bg-destructive/5 rounded"
                                            role="img"
                                            aria-label="Locked"
                                        >
                                            <Lock className="h-3 w-3" />
                                        </div>
                                    ) : slotData.is_active ? (
                                        <>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                aria-label={`Clear Memory Slot ${slotData.slot}`}
                                                onClick={(e) => handleReset(e, slotData)}
                                                className="text-muted-foreground hover:text-destructive hover:bg-destructive/10 font-mono text-xs"
                                            >
                                                <Trash2 className="h-3 w-3 mr-2" />
                                                CLEAR
                                            </Button>
                                            <Button
                                                variant="default"
                                                aria-label={`Resume story in Memory Slot ${slotData.slot}`}
                                                className="font-mono text-xs bg-primary text-primary-foreground hover:bg-primary/90 terminal-glow"
                                                onClick={(e) => handleResume(e, slotData)}
                                            >
                                                RESUME
                                            </Button>
                                        </>
                                    ) : (
                                        <Button
                                            variant="ghost"
                                            aria-label={`Initialize empty Memory Slot ${slotData.slot}`}
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                handleSelect(slotData.slot, slotData);
                                            }}
                                            className={cn(
                                                "font-mono text-xs border border-transparent group-hover:border-primary/30",
                                                selectedSlot === slotData.slot && "bg-primary text-primary-foreground hover:bg-primary/90"
                                            )}
                                        >
                                            INITIALIZE
                                        </Button>
                                    )}
                                </div>
                            </div>
                        </Card>
                        );
                    })}
                </div>
            </div>

            <AlertDialog open={!!slotToDelete} onOpenChange={(open) => !open && setSlotToDelete(null)}>
                <AlertDialogContent className="border-destructive/50 bg-background/95 backdrop-blur-xl">
                    <AlertDialogHeader>
                        <AlertDialogTitle className="text-destructive font-mono uppercase tracking-wider flex items-center gap-2">
                            <AlertTriangle className="h-5 w-5" />
                            Clear Slot {slotToDelete}
                        </AlertDialogTitle>
                        <AlertDialogDescription className="text-muted-foreground font-mono">
                            The story in this slot will be erased.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel className="font-mono">CANCEL</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={confirmReset}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90 font-mono"
                        >
                            ERASE
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            {/* Overwrite confirmation: shown only when initialization targets
                an occupied slot (the destructive path). */}
            <AlertDialog
                open={slotToOverwrite !== null}
                onOpenChange={(open) => !open && setSlotToOverwrite(null)}
            >
                <AlertDialogContent
                    className="border-destructive/50 bg-background/95 backdrop-blur-xl"
                    data-testid="overwrite-confirm"
                >
                    <AlertDialogHeader>
                        <AlertDialogTitle className="text-destructive font-mono uppercase tracking-wider flex items-center gap-2">
                            <AlertTriangle className="h-5 w-5" />
                            Overwrite Slot {slotToOverwrite}
                        </AlertDialogTitle>
                        <AlertDialogDescription className="text-muted-foreground font-mono">
                            Starting a new story here erases the existing one.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel className="font-mono" data-testid="overwrite-cancel">
                            CANCEL
                        </AlertDialogCancel>
                        <AlertDialogAction
                            onClick={confirmOverwrite}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90 font-mono"
                            data-testid="overwrite-confirm-action"
                        >
                            OVERWRITE
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}


