import { useState } from "react";
import { Check, Menu, Home, Settings, Sparkles, Monitor, Wand2, X, Globe, User, MapPin } from "lucide-react";
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
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { motion, AnimatePresence } from "framer-motion";

// Types for confirmed artifacts
type ArtifactType = "setting" | "character" | "seed";
interface ConfirmedArtifacts {
    setting?: any;
    character?: any;
    seed?: any;
}

// Simple expandable text component for long descriptions
function ExpandableText({ text, maxLength = 200, className = "" }: { text: string; maxLength?: number; className?: string }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const needsExpansion = text && text.length > maxLength;

    if (!text) return null;
    if (!needsExpansion) return <p className={className}>{text}</p>;

    return (
        <div>
            <p className={className}>
                {isExpanded ? text : `${text.substring(0, maxLength)}...`}
            </p>
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="text-primary text-xs mt-1 hover:underline focus:outline-none"
            >
                {isExpanded ? "show less" : "show more"}
            </button>
        </div>
    );
}

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

    // Confirmed artifacts for phase breadcrumb access
    const [confirmedArtifacts, setConfirmedArtifacts] = useState<ConfirmedArtifacts>({});
    const [viewingArtifact, setViewingArtifact] = useState<ArtifactType | null>(null);

    const handleArtifactConfirmed = (type: ArtifactType, data: any) => {
        setConfirmedArtifacts(prev => ({ ...prev, [type]: data }));
    };

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
        setConfirmedArtifacts({});
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

                // Restore confirmed artifacts from resumed data
                setConfirmedArtifacts({
                    setting: resumeData.setting_draft ?? undefined,
                    character: resumeData.character_draft ?? undefined,
                    seed: resumeData.selected_seed ?? undefined,
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

                {/* Centered NEXUS title - absolutely positioned for true window centering */}
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
                    <span className={`font-display text-2xl md:text-4xl text-primary ${glowClass} tracking-wider`}>
                        NEXUS
                    </span>
                </div>

                {/* Spacer to push abort button to right */}
                <div className="flex-1" />

                <Button
                    variant="ghost"
                    size="sm"
                    className="z-10 text-muted-foreground hover:text-foreground text-xs md:text-sm"
                    onClick={handleAbort}
                >
                    {isGilded ? "EXIT" : "[ABORT]"}
                </Button>
            </div>

            {/* Stepper Header - Only show when not in slot selection phase */}
            {currentPhase !== "slot" && (
                <div className="border-b border-border bg-card/50 py-4 shrink-0 z-10">
                    {/* Grid with 3 equal columns ensures middle item is truly centered */}
                    <div className="grid grid-cols-3 place-items-center relative px-8 max-w-2xl mx-auto">
                        {/* Progress Bar Background - proportional positioning to align with circle centers */}
                        <div className="absolute left-[16.667%] right-[16.667%] top-4 h-0.5 bg-border -z-10" />

                        {/* Progress Bar Fill */}
                        <div
                            className="absolute top-4 h-0.5 bg-primary transition-all duration-500 -z-10"
                            style={{
                              left: '16.667%',
                              width: `calc(66.666% * ${currentPhaseIndex / (PHASES.length - 1)})`,
                            }}
                        />

                        {PHASES.map((phase, index) => {
                            const isActive = index === currentPhaseIndex;
                            const isCompleted = index < currentPhaseIndex;
                                const artifactKey = phase.id as ArtifactType;
                                const hasArtifact = isCompleted && confirmedArtifacts[artifactKey];

                                return (
                                    <div key={phase.id} className="flex flex-col items-center gap-2">
                                        <button
                                            onClick={() => hasArtifact && setViewingArtifact(artifactKey)}
                                            disabled={!hasArtifact}
                                            className={cn(
                                                "w-8 h-8 rounded-full flex items-center justify-center border-2 transition-all duration-300",
                                                isActive && `border-primary bg-background text-primary ${glowClass} scale-110`,
                                                isCompleted && "border-primary bg-primary text-primary-foreground",
                                                !isActive && !isCompleted && "border-muted text-muted-foreground bg-card",
                                                hasArtifact && "cursor-pointer hover:scale-110 hover:shadow-lg hover:shadow-primary/30"
                                            )}
                                            title={hasArtifact ? `View ${phase.label} details` : undefined}
                                        >
                                            {isCompleted ? <Check className="w-4 h-4" /> : <span className="text-xs">{index + 1}</span>}
                                        </button>
                                        <span className={cn(
                                            "text-xs font-bold tracking-wider transition-colors duration-300",
                                            isActive ? `text-primary ${glowClass}` : "text-muted-foreground"
                                        )}>
                                            {phase.label}
                                        </span>
                                    </div>
                                );
                            })}
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
                            onArtifactConfirmed={handleArtifactConfirmed}
                            wizardData={wizardData}
                            setWizardData={setWizardData}
                            resumeThreadId={resumeThreadId}
                            initialPhase={currentPhase as "setting" | "character" | "seed"}
                        />
                    </div>
                )}
            </div>

            {/* Artifact View Modal */}
            <AnimatePresence>
                {viewingArtifact && confirmedArtifacts[viewingArtifact] && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-6"
                        onClick={() => setViewingArtifact(null)}
                    >
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.95 }}
                            onClick={(e) => e.stopPropagation()}
                        >
                            <Card className="w-full max-w-2xl bg-card border border-primary/50 p-6 space-y-4 shadow-lg">
                                <div className="flex items-center justify-between border-b border-primary/30 pb-4">
                                    <div className="flex items-center gap-3">
                                        {viewingArtifact === "setting" && <Globe className="w-6 h-6 text-primary" />}
                                        {viewingArtifact === "character" && <User className="w-6 h-6 text-primary" />}
                                        {viewingArtifact === "seed" && <MapPin className="w-6 h-6 text-primary" />}
                                        <h3 className="text-xl font-mono text-primary uppercase tracking-widest">
                                            {viewingArtifact === "setting" && "World Setting"}
                                            {viewingArtifact === "character" && "Character"}
                                            {viewingArtifact === "seed" && "Introduction"}
                                        </h3>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => setViewingArtifact(null)}
                                        className="text-muted-foreground hover:text-foreground"
                                    >
                                        <X className="w-5 h-5" />
                                    </Button>
                                </div>

                                <ScrollArea className="h-[400px] pr-4">
                                    {/* Setting Artifact */}
                                    {viewingArtifact === "setting" && (
                                        <div className="space-y-4 font-mono text-sm">
                                            <div className="border-l-2 border-primary pl-4">
                                                <div className="flex items-baseline gap-2 mb-1">
                                                    <span className="text-primary text-xs uppercase">World</span>
                                                    <h4 className="text-xl text-white font-bold">{confirmedArtifacts.setting?.world_name}</h4>
                                                </div>
                                            </div>
                                            <div className="grid grid-cols-2 gap-3 text-xs">
                                                <div className="bg-primary/5 border border-primary/20 p-2 rounded">
                                                    <span className="text-primary block uppercase mb-1">Genre</span>
                                                    <span className="text-white capitalize">{confirmedArtifacts.setting?.genre}</span>
                                                </div>
                                                <div className="bg-primary/5 border border-primary/20 p-2 rounded">
                                                    <span className="text-primary block uppercase mb-1">Era</span>
                                                    <span className="text-white">{confirmedArtifacts.setting?.time_period}</span>
                                                </div>
                                                <div className="bg-primary/5 border border-primary/20 p-2 rounded">
                                                    <span className="text-primary block uppercase mb-1">Tone</span>
                                                    <span className="text-white capitalize">{confirmedArtifacts.setting?.tone}</span>
                                                </div>
                                                <div className="bg-primary/5 border border-primary/20 p-2 rounded">
                                                    <span className="text-primary block uppercase mb-1">Tech Level</span>
                                                    <span className="text-white capitalize">{confirmedArtifacts.setting?.tech_level?.replace(/_/g, " ")}</span>
                                                </div>
                                            </div>
                                            {confirmedArtifacts.setting?.diegetic_artifact && (
                                                <div className="pt-4 border-t border-primary/20">
                                                    <span className="text-primary block text-xs uppercase mb-2">In-World Document</span>
                                                    <p className="text-muted-foreground italic leading-relaxed whitespace-pre-wrap text-xs font-narrative">
                                                        {confirmedArtifacts.setting.diegetic_artifact}
                                                    </p>
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Character Artifact */}
                                    {viewingArtifact === "character" && (
                                        <div className="space-y-4 font-mono text-sm">
                                            <div className="flex items-center gap-4 mb-4">
                                                <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center border border-primary/30 shrink-0">
                                                    <User className="w-8 h-8 text-primary" />
                                                </div>
                                                <div>
                                                    <h4 className="text-2xl text-white font-bold">{confirmedArtifacts.character?.name}</h4>
                                                    <p className="text-primary text-sm">{confirmedArtifacts.character?.summary}</p>
                                                </div>
                                            </div>
                                            {confirmedArtifacts.character?.diegetic_artifact && (
                                                <div>
                                                    <span className="text-primary block text-xs uppercase mb-2">Narrative Portrait</span>
                                                    <p className="text-muted-foreground italic leading-relaxed text-xs whitespace-pre-wrap font-narrative">
                                                        {confirmedArtifacts.character.diegetic_artifact}
                                                    </p>
                                                </div>
                                            )}
                                            {confirmedArtifacts.character?.wildcard_name && (
                                                <div className="pt-4 border-t border-primary/20">
                                                    <span className="text-primary block text-xs uppercase mb-1">{confirmedArtifacts.character.wildcard_name}</span>
                                                    <p className="text-sm text-white/90 font-narrative">{confirmedArtifacts.character.wildcard_description}</p>
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Seed/Introduction Artifact */}
                                    {viewingArtifact === "seed" && (
                                        <div className="space-y-4 font-mono text-sm">
                                            <div className="border-l-2 border-primary pl-4">
                                                <span className="text-primary block text-xs uppercase mb-1">Starting Scenario</span>
                                                <h4 className="text-xl text-white font-bold mb-2">{confirmedArtifacts.seed?.seed?.title}</h4>
                                                <p className="italic text-muted-foreground/60 font-narrative">{confirmedArtifacts.seed?.seed?.hook}</p>
                                            </div>
                                            {confirmedArtifacts.seed?.location && (
                                                <div className="pt-4">
                                                    <span className="text-primary block text-xs uppercase mb-2">Location</span>
                                                    <p className="text-white">{confirmedArtifacts.seed.location.name}</p>
                                                    <ExpandableText
                                                        text={confirmedArtifacts.seed.location.summary || ""}
                                                        maxLength={200}
                                                        className="text-muted-foreground text-xs mt-1"
                                                    />
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </ScrollArea>
                            </Card>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
