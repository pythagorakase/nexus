import { useState, useEffect } from "react";
import { Save, AlertTriangle, Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/hooks/use-toast";

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
                character_name: slot.character_name,
                last_played: slot.last_played,
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
            toast({
                title: "Slot Reset",
                description: "Save slot has been cleared.",
            });
        },
    });

    const handleSelect = (slot: number) => {
        if (slot === 1) {
            toast({
                title: "Slot Locked",
                description: "Save Slot 1 is protected and cannot be overwritten.",
                variant: "destructive",
            });
            return;
        }
        setSelectedSlot(slot);
        onSlotSelected(slot);
    };

    const handleResume = (e: React.MouseEvent, slotData: SlotData) => {
        e.stopPropagation();
        onSlotResumed(slotData);
    };

    const handleReset = (e: React.MouseEvent, slot: number) => {
        e.stopPropagation();
        if (slot === 1) return;

        if (confirm(`Are you sure you want to clear Slot ${slot}? This cannot be undone.`)) {
            resetMutation.mutate(slot);
        }
    };

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 space-y-4">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="font-mono text-sm text-muted-foreground">Scanning memory banks...</p>
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
                    {slots.map((slotData) => (
                        <Card
                            key={slotData.slot}
                            onClick={() => handleSelect(slotData.slot)}
                            className={cn(
                                "p-4 cursor-pointer transition-all duration-300 border-border bg-card/50 hover:bg-card hover:border-primary/50 group relative overflow-hidden",
                                selectedSlot === slotData.slot && "border-primary bg-primary/5 ring-1 ring-primary",
                                slotData.slot === 1 && "opacity-80 cursor-not-allowed hover:border-destructive/50 hover:bg-destructive/5"
                            )}
                        >
                        {/* Scanline effect */}
                        <div className="absolute inset-0 pointer-events-none bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] z-0 bg-[length:100%_2px,3px_100%] opacity-20" />

                        <div className="relative z-10 flex items-center justify-between">
                            <div className="flex items-center gap-4">
                                <div className={cn(
                                    "h-12 w-12 rounded-sm flex items-center justify-center font-mono text-lg font-bold border",
                                    slotData.slot === 1
                                        ? "border-destructive/50 text-destructive bg-destructive/10"
                                        : slotData.is_active
                                            ? "border-primary text-primary bg-primary/10 terminal-glow"
                                            : "border-muted text-muted-foreground bg-muted/10"
                                )}>
                                    {slotData.slot}
                                </div>

                                <div className="flex items-center gap-2">
                                    <span className={cn(
                                        "font-mono text-sm font-bold",
                                        slotData.slot === 1 ? "text-destructive" : "text-foreground"
                                    )}>
                                        {slotData.slot === 1 ? "PROTECTED ARCHIVE" : `MEMORY SLOT ${slotData.slot}`}
                                    </span>
                                    {slotData.is_active && (
                                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/20 text-primary font-mono">
                                            ACTIVE
                                        </span>
                                    )}
                                </div>
                            </div>

                            <div className="flex items-center gap-2 ml-auto">
                                {slotData.slot === 1 ? (
                                    <div className="flex items-center gap-2 text-destructive text-xs font-mono px-3 py-1.5 border border-destructive/30 bg-destructive/5 rounded">
                                        <AlertTriangle className="h-3 w-3" />
                                        LOCKED
                                    </div>
                                ) : slotData.is_active ? (
                                    <>
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={(e) => handleReset(e, slotData.slot)}
                                            className="text-muted-foreground hover:text-destructive hover:bg-destructive/10 font-mono text-xs"
                                        >
                                            <Trash2 className="h-3 w-3 mr-2" />
                                            CLEAR
                                        </Button>
                                        <Button
                                            variant="default"
                                            className="font-mono text-xs bg-primary text-primary-foreground hover:bg-primary/90 terminal-glow"
                                            onClick={(e) => handleResume(e, slotData)}
                                        >
                                            RESUME
                                        </Button>
                                    </>
                                ) : (
                                    <Button
                                        variant="ghost"
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
                    ))}
                </div>
            </div>
        </div>
    );
}
