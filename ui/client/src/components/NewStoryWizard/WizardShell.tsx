import { useState } from "react";
import { Check, Menu, Home, Settings, Sparkles, Monitor, Wand2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { SlotSelector } from "./SlotSelector";
import { InteractiveWizard } from "./InteractiveWizard";
import { useLocation, Link } from "wouter";
import { useTheme } from "@/contexts/ThemeContext";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CornerSunburst } from "@/components/deco";
import { useToast } from "@/hooks/use-toast";

type WizardPhase = "slot" | "setting" | "character" | "seed";

const PHASES: { id: WizardPhase; label: string }[] = [
    { id: "setting", label: "Setting" },
    { id: "character", label: "Character" },
    { id: "seed", label: "Introduction" },
];

export function NewStoryWizard() {
    const [currentPhase, setCurrentPhase] = useState<WizardPhase>("slot");
    const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
    const [resumeThreadId, setResumeThreadId] = useState<string | null>(null);
    const [_, setLocation] = useLocation();
    const { isGilded, isVector, theme, setTheme, glowClass } = useTheme();
    const { toast } = useToast();

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
        setResumeThreadId(null);
        setWizardData({
            slot,
            setting: null,
            character: null,
            seed: null,
            location: null,
        });
    };

    const handleInteractivePhaseChange = (phase: "setting" | "character" | "seed") => {
        setCurrentPhase(phase);
    };

    const handleSlotResumed = async (slotData: {
        slot: number;
        wizard_in_progress?: boolean;
        wizard_thread_id?: string;
        wizard_phase?: "setting" | "character" | "seed";
    }) => {
        localStorage.setItem("activeSlot", slotData.slot.toString());

        if (slotData.wizard_in_progress && slotData.wizard_thread_id) {
            try {
                const resumeRes = await fetch(`/api/story/new/setup/resume?slot=${slotData.slot}`);
                if (!resumeRes.ok) {
                    throw new Error("Failed to resume wizard session");
                }

                const resumeData = await resumeRes.json();
                const inferredPhase: WizardPhase =
                    slotData.wizard_phase || resumeData.current_phase ||
                    (resumeData.selected_seed ? "seed" : resumeData.character_draft ? "character" : "setting");

                setResumeThreadId(resumeData.thread_id ?? null);
                setWizardData({
                    slot: slotData.slot,
                    setting: resumeData.setting_draft ?? null,
                    character: resumeData.character_draft ?? null,
                    seed: resumeData.selected_seed ?? null,
                    location: resumeData.initial_location ?? null,
                });

                setSelectedSlot(slotData.slot);
                setCurrentPhase(inferredPhase);
            } catch (error) {
                console.error("Failed to resume wizard:", error);
                toast({
                    title: "Resume Failed",
                    description: "Could not resume your in-progress wizard. Please try again.",
                    variant: "destructive",
                });
            }
        } else {
            // Story complete - go to NexusLayout
            window.location.href = "/nexus";
        }
    };

    const handleComplete = () => {
        if (selectedSlot) {
            localStorage.setItem("activeSlot", selectedSlot.toString());
        }
        window.location.href = "/nexus";
    };

    const handleAbort = () => {
        window.location.href = "/";
    };

    const currentPhaseIndex = PHASES.findIndex(p => p.id === currentPhase);

    return (
        <div className={cn(
            "h-screen bg-background flex flex-col font-mono overflow-hidden dark animate-fade-in",
            isVector && "terminal-scanlines"
        )}>
            {/* Status Bar with Hamburger Menu */}
            <div className="relative h-10 md:h-12 border-b border-border bg-card flex items-center px-2 md:px-4 gap-2 md:gap-4 overflow-hidden">
                {/* Art Deco corner sunbursts */}
                {isGilded && (
                    <>
                        <CornerSunburst position="tl" size={60} rays={8} opacity={0.08} />
                        <CornerSunburst position="tr" size={60} rays={8} opacity={0.08} />
                    </>
                )}

                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7 md:h-8 md:w-8 flex-shrink-0 z-10"
                        >
                            <Menu className="h-3 w-3 md:h-4 md:w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start">
                        <DropdownMenuItem asChild>
                            <Link href="/">
                                <div className="flex items-center gap-2 cursor-pointer">
                                    <Home className="h-4 w-4" />
                                    <span>Home</span>
                                </div>
                            </Link>
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem asChild>
                            <Link href="/nexus">
                                <div className="flex items-center gap-2 cursor-pointer">
                                    <Settings className="h-4 w-4" />
                                    <span>Settings</span>
                                </div>
                            </Link>
                        </DropdownMenuItem>
                        <DropdownMenuItem asChild>
                            <Link href="/nexus">
                                <div className="flex items-center gap-2 cursor-pointer">
                                    <Sparkles className="h-4 w-4" />
                                    <span>Audition</span>
                                </div>
                            </Link>
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuLabel className="text-xs text-muted-foreground">
                            Theme
                        </DropdownMenuLabel>
                        <DropdownMenuItem onClick={() => setTheme('gilded')}>
                            <div className="flex items-center gap-2 cursor-pointer">
                                <Sparkles className="h-4 w-4" />
                                <span>Gilded{theme === 'gilded' ? ' ✓' : ''}</span>
                            </div>
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setTheme('vector')}>
                            <div className="flex items-center gap-2 cursor-pointer">
                                <Monitor className="h-4 w-4" />
                                <span>Vector{theme === 'vector' ? ' ✓' : ''}</span>
                            </div>
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setTheme('veil')}>
                            <div className="flex items-center gap-2 cursor-pointer">
                                <Wand2 className="h-4 w-4" />
                                <span>Veil{theme === 'veil' ? ' ✓' : ''}</span>
                            </div>
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>

                <div className="flex-1 flex items-center justify-center">
                    <span className={`font-display text-2xl md:text-4xl text-primary ${glowClass} tracking-wider`}>
                        NEXUS
                    </span>
                </div>

                <Button
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground hover:text-foreground text-xs md:text-sm"
                    onClick={handleAbort}
                >
                    {isGilded ? "EXIT" : "[ABORT]"}
                </Button>
            </div>

            {/* Stepper Header - Only show when not in slot selection phase */}
            {currentPhase !== "slot" && (
                <div className="border-b border-border bg-card/50 p-4 shrink-0 z-10">
                    <div className="max-w-5xl mx-auto">

                        <div className="flex items-start justify-between relative">
                            {/* Progress Bar Background */}
                            <div className="absolute left-0 top-4 w-full h-0.5 bg-border -z-10" />

                            {/* Progress Bar Fill */}
                            <div
                                className="absolute left-0 top-4 h-0.5 bg-primary transition-all duration-500 -z-10"
                                style={{ width: `${(currentPhaseIndex / (PHASES.length - 1)) * 100}%` }}
                            />

                            {PHASES.map((phase, index) => {
                                const isActive = index === currentPhaseIndex;
                                const isCompleted = index < currentPhaseIndex;

                                return (
                                    <div key={phase.id} className="flex flex-col items-center gap-2">
                                        <div className={cn(
                                            "w-8 h-8 rounded-full flex items-center justify-center border-2 transition-all duration-300",
                                            isActive && `border-primary bg-background text-primary ${glowClass} scale-110`,
                                            isCompleted && "border-primary bg-primary text-primary-foreground",
                                            !isActive && !isCompleted && "border-muted text-muted-foreground bg-card"
                                        )}>
                                            {isCompleted ? <Check className="w-4 h-4" /> : <span className="text-xs">{index + 1}</span>}
                                        </div>
                                        <span className={cn(
                                            "text-[10px] font-bold tracking-wider transition-colors duration-300",
                                            isActive ? `text-primary ${glowClass}` : "text-muted-foreground"
                                        )}>
                                            {phase.label}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            )}

            {/* Main Content */}
            <div className="flex-1 overflow-hidden relative">
                {currentPhase === "slot" ? (
                    <div className="h-full overflow-auto py-8">
                        <div className="max-w-5xl mx-auto">
                            <SlotSelector
                                onSlotSelected={handleSlotSelected}
                                onSlotResumed={handleSlotResumed}
                            />
                        </div>
                    </div>
                ) : (
                    <div className="absolute inset-0 p-4 md:p-8">
                        <InteractiveWizard
                            slot={selectedSlot!}
                            onComplete={handleComplete}
                            onCancel={handleAbort}
                            onPhaseChange={handleInteractivePhaseChange}
                            wizardData={wizardData}
                            setWizardData={setWizardData}
                            resumeThreadId={resumeThreadId}
                            initialPhase={currentPhase as "setting" | "character" | "seed"}
                        />
                    </div>
                )}
            </div>
        </div>
    );
}
