import { useState } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { SlotSelector } from "./SlotSelector";
import { InteractiveWizard } from "./InteractiveWizard";
import { useLocation } from "wouter";

type WizardPhase = "slot" | "setting" | "character" | "seed";

const PHASES: { id: WizardPhase; label: string }[] = [
    { id: "slot", label: "MEMORY SLOT" },
    { id: "setting", label: "WORLD GEN" },
    { id: "character", label: "PROTAGONIST" },
    { id: "seed", label: "INITIALIZATION" },
];

export function NewStoryWizard() {
    const [currentPhase, setCurrentPhase] = useState<WizardPhase>("slot");
    const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
    const [_, setLocation] = useLocation();

    // State for data collected across phases
    const [wizardData, setWizardData] = useState({
        slot: null as number | null,
        setting: null,
        character: null,
        seed: null,
        location: null,
    });

    const handleSlotSelected = (slot: number) => {
        setSelectedSlot(slot);
        setCurrentPhase("setting");
    };

    const handleInteractivePhaseChange = (phase: "setting" | "character" | "seed") => {
        setCurrentPhase(phase);
    };

    const handleComplete = () => {
        setLocation("/");
    };

    const currentPhaseIndex = PHASES.findIndex(p => p.id === currentPhase);

    return (
        <div className="h-screen bg-background flex flex-col font-mono terminal-scanlines overflow-hidden">
            {/* Header / Stepper */}
            <div className="border-b border-border bg-card/50 p-4 shrink-0 z-10">
                <div className="max-w-5xl mx-auto">
                    <div className="flex items-center justify-between mb-6">
                        <h1 className="text-xl font-bold text-primary terminal-glow">
                            NEXUS // INITIALIZATION_SEQUENCE
                        </h1>
                        <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-foreground">
                            [ABORT SEQUENCE]
                        </Button>
                    </div>

                    <div className="flex items-center justify-between relative">
                        {/* Progress Bar Background */}
                        <div className="absolute left-0 top-1/2 w-full h-0.5 bg-border -z-10" />

                        {/* Progress Bar Fill */}
                        <div
                            className="absolute left-0 top-1/2 h-0.5 bg-primary transition-all duration-500 -z-10"
                            style={{ width: `${(currentPhaseIndex / (PHASES.length - 1)) * 100}%` }}
                        />

                        {PHASES.map((phase, index) => {
                            const isActive = index === currentPhaseIndex;
                            const isCompleted = index < currentPhaseIndex;

                            return (
                                <div key={phase.id} className="flex flex-col items-center gap-2 bg-background px-2">
                                    <div className={cn(
                                        "w-8 h-8 rounded-full flex items-center justify-center border-2 transition-all duration-300",
                                        isActive && "border-primary bg-background text-primary terminal-glow scale-110",
                                        isCompleted && "border-primary bg-primary text-primary-foreground",
                                        !isActive && !isCompleted && "border-muted text-muted-foreground bg-card"
                                    )}>
                                        {isCompleted ? <Check className="w-4 h-4" /> : <span className="text-xs">{index + 1}</span>}
                                    </div>
                                    <span className={cn(
                                        "text-[10px] font-bold tracking-wider transition-colors duration-300",
                                        isActive ? "text-primary terminal-glow" : "text-muted-foreground"
                                    )}>
                                        {phase.label}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 overflow-hidden relative">
                {currentPhase === "slot" ? (
                    <div className="h-full overflow-auto py-8">
                        <div className="max-w-5xl mx-auto">
                            <SlotSelector onSlotSelected={handleSlotSelected} />
                        </div>
                    </div>
                ) : (
                    <div className="absolute inset-0 p-4 md:p-8">
                        <InteractiveWizard
                            slot={selectedSlot!}
                            onComplete={handleComplete}
                            onCancel={() => setCurrentPhase("slot")}
                            onPhaseChange={handleInteractivePhaseChange}
                            wizardData={wizardData}
                            setWizardData={setWizardData}
                        />
                    </div>
                )}
            </div>
        </div>
    );
}
