import React, { useState, useRef, useEffect } from "react";
import { Send, Sparkles, Loader2, CheckCircle, FileText, MapPin, User, Globe, ChevronDown, ChevronRight, Wand2, Scroll, Languages, Swords, Crown, Tag, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { useToast } from "@/hooks/use-toast";
import ReactMarkdown from "react-markdown";
import { StoryChoices, ChoiceSelection } from "@/components/StoryChoices";
import { TraitSelector } from "./TraitSelector";

interface Message {
    id: string;
    role: "user" | "assistant" | "system";
    content: string;
    timestamp: number;
    artifactType?: string;    // e.g., "submit_character_concept"
    artifactData?: any;       // The tool submission data (viewable via modal)
}

interface InteractiveWizardProps {
    slot: number;
    onComplete: () => void;
    onCancel: () => void;
    onPhaseChange: (phase: Phase) => void;
    onArtifactConfirmed?: (type: "setting" | "character" | "seed", data: any) => void;
    wizardData: any;
    setWizardData: (data: any) => void;
    resumeThreadId?: string | null;
    initialPhase?: Phase;
}

type Phase = "setting" | "character" | "seed";

// Trait introduction text from storyteller_new.md YAML frontmatter
// Used for client-side message when transitioning from 2.1 → 2.2 (skips API call)
const TRAIT_INTRODUCTION = `Now we give your character weight.

Traits are the parts of their life that demand narrative attention—the relationships that complicate, the positions that pressure, the secrets that fester. You'll choose three from the menu, plus one wildcard that's entirely yours to define.

A trait isn't a bonus. It's a promise that this aspect of your character will matter—for better or worse. Not choosing a trait doesn't mean your character lacks it; it just won't be a guaranteed source of story.

Based on what we've built so far, here's where I think the interesting tensions live:`;

const buildTraitIntroMessage = (concept: {
    suggested_traits?: string[];
    trait_rationales?: Record<string, string>;
}): string => {
    const traits = concept.suggested_traits || [];
    const rationales = concept.trait_rationales || {};

    if (traits.length === 0) {
        return `${TRAIT_INTRODUCTION}

I'll let you explore the trait menu and choose what feels right for your character.`;
    }

    const traitLines = traits.map(trait => {
        const rationale = rationales[trait] || "";
        const displayName = trait.charAt(0).toUpperCase() + trait.slice(1);
        return rationale
            ? `**${displayName}** — ${rationale}`
            : `**${displayName}**`;
    });

    return `${TRAIT_INTRODUCTION}

${traitLines.join("\n\n")}`;
};

interface CollapsibleSectionProps {
    title: string;
    children: React.ReactNode;
    defaultOpen?: boolean;
    icon?: React.ReactNode;
}

function CollapsibleSection({ title, children, defaultOpen = false, icon }: CollapsibleSectionProps) {
    const [isOpen, setIsOpen] = useState(defaultOpen);

    return (
        <div className="border border-primary/20 rounded-md overflow-hidden bg-background/40">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full flex items-center justify-between p-3 bg-primary/10 hover:bg-primary/20 transition-colors"
            >
                <div className="flex items-center gap-2">
                    {icon}
                    <span className="text-primary font-mono text-sm uppercase tracking-wider">{title}</span>
                </div>
                {isOpen ? <ChevronDown className="w-4 h-4 text-primary" /> : <ChevronRight className="w-4 h-4 text-primary" />}
            </button>
            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                    >
                        <div className="p-4 border-t border-primary/20">
                            {children}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

export function InteractiveWizard({
    slot,
    onComplete,
    onCancel,
    onPhaseChange,
    onArtifactConfirmed,
    wizardData,
    setWizardData,
    resumeThreadId,
    initialPhase,
}: InteractiveWizardProps) {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [threadId, setThreadId] = useState<string | null>(null);
    const [currentPhase, setCurrentPhase] = useState<Phase>(initialPhase || "setting");
    const [pendingArtifact, setPendingArtifact] = useState<any>(null);
    const [displayChoices, setDisplayChoices] = useState<string[] | null>(null);
    const [showTraitSelector, setShowTraitSelector] = useState(false);
    const [suggestedTraits, setSuggestedTraits] = useState<string[]>([]);
    const [viewingArtifact, setViewingArtifact] = useState<{ type: string; data: any } | null>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    const { toast } = useToast();

    const updatePhase = (newPhase: Phase) => {
        setCurrentPhase(newPhase);
        onPhaseChange(newPhase);
    };

    // Initialize chat
    useEffect(() => {
        const initChat = async () => {
            try {
                setIsLoading(true);

                // Reset local UI state when starting/resuming a session
                setMessages([]);
                setDisplayChoices(null);
                setPendingArtifact(null);
                setShowTraitSelector(false);

                if (resumeThreadId) {
                    setThreadId(resumeThreadId);
                    return;
                }

                const startRes = await fetch("/api/story/new/setup/start", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ slot }),
                });

                if (!startRes.ok) throw new Error("Failed to start setup");
                const { thread_id, welcome_message, welcome_choices } = await startRes.json();
                setThreadId(thread_id);

                if (welcome_message) {
                    addMessage("assistant", welcome_message);
                }
                if (welcome_choices && welcome_choices.length > 0) {
                    setDisplayChoices(welcome_choices);
                }
            } catch (error) {
                console.error("Failed to init chat:", error);
                toast({
                    title: "Initialization Error",
                    description: "Failed to initialize new story wizard. Please try again.",
                    variant: "destructive",
                });
            } finally {
                setIsLoading(false);
            }
        };

        initChat();
    }, [slot, toast, resumeThreadId]);

    useEffect(() => {
        setCurrentPhase(initialPhase || "setting");
    }, [initialPhase]);

    // Auto-scroll
    useEffect(() => {
        if (scrollRef.current) {
            // Use a small timeout to ensure DOM is updated and animations start
            setTimeout(() => {
                const scrollElement = scrollRef.current;
                if (scrollElement) {
                    const scrollContainer = scrollElement.querySelector('[data-radix-scroll-area-viewport]');
                    if (scrollContainer) {
                        scrollContainer.scrollTop = scrollContainer.scrollHeight;
                    }
                }
            }, 150);
        }
    }, [messages, isLoading, pendingArtifact, displayChoices]);

    const addMessage = (
        role: Message["role"],
        content: string,
        artifact?: { type: string; data: any }
    ) => {
        setMessages((prev) => [
            ...prev,
            {
                id: Math.random().toString(36).substring(7),
                role,
                content,
                timestamp: Date.now(),
                ...(artifact && { artifactType: artifact.type, artifactData: artifact.data }),
            },
        ]);
    };

    const triggerSubphaseContinuation = async (artifactType: string, contextData: any) => {
        setIsLoading(true);
        setDisplayChoices(null);  // Clear stale choices immediately to prevent flash
        try {
            const res = await fetch("/api/story/new/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slot,
                    thread_id: threadId,
                    message: `[SYSTEM] Artifact ${artifactType} confirmed. Proceed to next step.`,
                    current_phase: currentPhase,
                    context_data: contextData
                }),
            });

            if (!res.ok) throw new Error("Failed to trigger continuation");
            const data = await res.json();

            if (data.phase_complete) {
                setPendingArtifact({ type: data.artifact_type, data: data.data });
                setDisplayChoices(null);
            } else if (data.subphase_complete) {
                handleSubphaseCompletion(data.artifact_type, data.data);
            } else {
                addMessage("assistant", data.message);
                setDisplayChoices(data.choices ? normalizeChoices(data.choices) : null);
                if (currentPhase === "character" && shouldShowTraitSelector(data.message)) {
                    setShowTraitSelector(true);
                    extractSuggestedTraits(data.message);
                }
            }
        } catch (error) {
            console.error("Continuation error:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleSubphaseCompletion = (artifactType: string, artifactData: any) => {
        // Calculate new state synchronously to pass to continuation
        let updatedWizardData = { ...wizardData };

        setWizardData((prev: any) => {
            const charState = prev.character_state || {};
            let newState = prev;

            if (artifactType === "submit_character_concept") {
                newState = { ...prev, character_state: { ...charState, concept: artifactData } };
            } else if (artifactType === "submit_trait_selection") {
                setShowTraitSelector(false); // Close trait selector after confirmation
                newState = { ...prev, character_state: { ...charState, trait_selection: artifactData } };
            } else if (artifactType === "submit_wildcard_trait") {
                newState = { ...prev, character_state: { ...charState, wildcard: artifactData } };
            }

            updatedWizardData = newState;
            return newState;
        });

        // Show trait selector after concept is submitted
        if (artifactType === "submit_character_concept") {
            // Pre-select LLM's suggested traits from schema-validated data
            if (artifactData.suggested_traits && Array.isArray(artifactData.suggested_traits)) {
                setSuggestedTraits(artifactData.suggested_traits);
            }
            setShowTraitSelector(true);

            // Add clickable system message to view concept data
            addMessage("system", `[${artifactType} confirmed]`, { type: artifactType, data: artifactData });

            // Build client-side intro message with rationales (SKIP API CALL)
            // This eliminates latency and ensures message is synced with pre-selection
            const introMessage = buildTraitIntroMessage(artifactData);
            addMessage("assistant", introMessage);
            setDisplayChoices(null);  // No structured choices - TraitSelector handles it
            return;  // Early return - no API call needed
        }

        // For other subphases, continue with API call
        addMessage("system", `[${artifactType} confirmed]`, { type: artifactType, data: artifactData });
        triggerSubphaseContinuation(artifactType, updatedWizardData);
    };

    const normalizeChoices = (choices: any): string[] | null => {
        if (!choices || !Array.isArray(choices) || choices.length === 0) {
            return null;
        }
        // Already string array
        if (typeof choices[0] === "string") {
            return (choices as string[]).map((c) => c.trim()).filter(Boolean);
        }
        // Handle structured {label, description}
        if (choices[0]?.label && choices[0]?.description) {
            return (choices as Array<{ label: string; description: string }>).map(
                (c) => `${c.label}: ${c.description}`
            );
        }
        // Fallback: coerce to strings
        return (choices as Array<any>).map((c) => String(c).trim()).filter(Boolean);
    };

    const handleSend = async () => {
        if (!input.trim() || isLoading || !threadId) return;

        const userMsg = input.trim();
        setInput("");
        addMessage("user", userMsg);
        setDisplayChoices(null);  // Clear choices while loading
        setIsLoading(true);

        try {
            const res = await fetch("/api/story/new/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slot,
                    thread_id: threadId,
                    message: userMsg,
                    current_phase: currentPhase,
                    context_data: wizardData
                }),
            });

            if (!res.ok) throw new Error("Failed to send message");

            const data = await res.json();

            if (data.phase_complete) {
                setPendingArtifact({ type: data.artifact_type, data: data.data });
                setDisplayChoices(null);
            } else if (data.subphase_complete) {
                handleSubphaseCompletion(data.artifact_type, data.data);
            } else {
                addMessage("assistant", data.message);
                // Set choices if returned by backend
                setDisplayChoices(data.choices ? normalizeChoices(data.choices) : null);
                // Check if LLM is prompting for trait selection
                if (currentPhase === "character" && shouldShowTraitSelector(data.message)) {
                    setShowTraitSelector(true);
                    // Try to extract suggested traits from message
                    extractSuggestedTraits(data.message);
                }
            }

        } catch (error) {
            console.error("Chat error:", error);
            toast({
                title: "Transmission Error",
                description: "Failed to send message. Please try again.",
                variant: "destructive",
            });
        } finally {
            setIsLoading(false);
        }
    };

    const handleChoiceSelect = (selection: ChoiceSelection) => {
        // Clear choices while loading
        setDisplayChoices(null);
        const inputToSend = selection.text;
        addMessage("user", inputToSend);
        setIsLoading(true);

        fetch("/api/story/new/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                slot,
                thread_id: threadId,
                message: inputToSend,
                current_phase: currentPhase,
                context_data: wizardData
            }),
        })
            .then(async (res) => {
                if (!res.ok) throw new Error("Failed to send message");
                const data = await res.json();
                if (data.phase_complete) {
                    setPendingArtifact({ type: data.artifact_type, data: data.data });
                    setDisplayChoices(null);
                } else if (data.subphase_complete) {
                    handleSubphaseCompletion(data.artifact_type, data.data);
                } else {
                    addMessage("assistant", data.message);
                    // Set choices if returned by backend
                    setDisplayChoices(data.choices ? normalizeChoices(data.choices) : null);
                    // Check if LLM is prompting for trait selection
                    if (currentPhase === "character" && shouldShowTraitSelector(data.message)) {
                        setShowTraitSelector(true);
                    }
                }
            })
            .catch((error) => {
                console.error("Chat error:", error);
                toast({
                    title: "Transmission Error",
                    description: "Failed to send message. Please try again.",
                    variant: "destructive",
                });
            })
            .finally(() => {
                setIsLoading(false);
            });
    };

    // Detect if LLM message is prompting for trait selection
    const shouldShowTraitSelector = (message: string): boolean => {
        const lowerMessage = message.toLowerCase();
        const traitKeywords = ["select", "choose", "pick"];
        const traitMentions = ["trait", "traits"];
        return traitKeywords.some(k => lowerMessage.includes(k)) &&
            traitMentions.some(t => lowerMessage.includes(t));
    };

    // Extract suggested traits from LLM message
    const extractSuggestedTraits = (message: string): void => {
        const lowerMessage = message.toLowerCase();
        const traitNames = [
            "allies", "contacts", "patron", "dependents",
            "status", "reputation", "resources", "domain",
            "enemies", "obligations"
        ];

        const suggested: string[] = [];

        // Look for bolded traits or traits mentioned with positive context
        for (const trait of traitNames) {
            if (!suggested.includes(trait)) {
                // Check for bold formatting
                const boldPattern = new RegExp(`\\*\\*${trait}\\*\\*`, 'i');
                // Check for suggestion context
                const suggestionPattern = new RegExp(`(suggest|recommend|interesting|compelling|fitting|suits|matches)[^.]*${trait}`, 'i');
                if (boldPattern.test(message) || suggestionPattern.test(message)) {
                    suggested.push(trait);
                }
            }
        }

        if (suggested.length > 0) {
            setSuggestedTraits(suggested.slice(0, 3)); // Max 3 suggestions
        }
    };

    const handleTraitConfirm = (traits: string[]) => {
        setShowTraitSelector(false);
        const traitMessage = `I'll take: ${traits.join(", ")}`;
        setInput("");
        addMessage("user", traitMessage);
        setDisplayChoices(null);  // Clear choices while loading
        setIsLoading(true);

        fetch("/api/story/new/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                slot,
                thread_id: threadId,
                message: traitMessage,
                current_phase: currentPhase,
                context_data: wizardData
            }),
        })
            .then(async (res) => {
                if (!res.ok) throw new Error("Failed to send message");
                const data = await res.json();
                if (data.phase_complete) {
                    setPendingArtifact({ type: data.artifact_type, data: data.data });
                    setDisplayChoices(null);
                } else if (data.subphase_complete) {
                    handleSubphaseCompletion(data.artifact_type, data.data);
                } else {
                    addMessage("assistant", data.message);
                    setDisplayChoices(data.choices ? normalizeChoices(data.choices) : null);
                }
            })
            .catch((error) => {
                console.error("Chat error:", error);
                toast({
                    title: "Transmission Error",
                    description: "Failed to send message. Please try again.",
                    variant: "destructive",
                });
            })
            .finally(() => {
                setIsLoading(false);
            });
    };

    // Handle invalid trait selection (≠3 traits) - sends to LLM for dialog, UI stays open
    const handleInvalidTraitConfirm = (traits: string[], count: number) => {
        // UI stays open for continued adjustment
        const direction = count < 3 ? "add more" : "narrow down";
        const traitMessage = `I've selected ${count} trait${count !== 1 ? "s" : ""}: ${traits.join(", ")}. I need to ${direction} my selection.`;
        addMessage("user", traitMessage);
        setIsLoading(true);

        fetch("/api/story/new/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                slot,
                thread_id: threadId,
                message: traitMessage,
                current_phase: currentPhase,
                context_data: wizardData
            }),
        })
            .then(async (res) => {
                if (!res.ok) throw new Error("Failed to send message");
                const data = await res.json();
                addMessage("assistant", data.message);
            })
            .catch((error) => {
                console.error("Chat error:", error);
                toast({
                    title: "Transmission Error",
                    description: "Failed to send message. Please try again.",
                    variant: "destructive",
                });
            })
            .finally(() => {
                setIsLoading(false);
            });
    };

    const handleArtifactConfirm = async () => {
        // Determine next phase or completion
        if (currentPhase === "setting") {
            setWizardData((prev: any) => ({ ...prev, setting: pendingArtifact.data }));
            onArtifactConfirmed?.("setting", pendingArtifact.data);
            updatePhase("character");
            setPendingArtifact(null);
            // Trigger next phase prompt
            triggerNextPhase("character");
        } else if (currentPhase === "character") {
            setWizardData((prev: any) => ({ ...prev, character: pendingArtifact.data }));
            onArtifactConfirmed?.("character", pendingArtifact.data);
            updatePhase("seed");
            setPendingArtifact(null);
            // Trigger next phase prompt
            triggerNextPhase("seed");
        } else if (currentPhase === "seed") {
            setWizardData((prev: any) => ({ ...prev, seed: pendingArtifact.data }));
            onArtifactConfirmed?.("seed", pendingArtifact.data);
            setPendingArtifact(null);
            setIsLoading(true);

            // Call transition endpoint to finalize and populate database
            try {
                const res = await fetch("/api/story/new/transition", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ slot }),
                });

                if (!res.ok) {
                    const error = await res.json();
                    throw new Error(error.detail || "Transition failed");
                }

                const result = await res.json();

                toast({
                    title: "Initialization Complete",
                    description: result.message || "Entering simulation...",
                });

                // Navigate to game after successful transition
                setTimeout(() => {
                    localStorage.setItem("activeSlot", slot.toString());
                    onComplete();
                }, 1000);
            } catch (e: any) {
                console.error("Transition error:", e);
                toast({
                    title: "Transition Error",
                    description: e.message || "Failed to initialize story. Please try again.",
                    variant: "destructive",
                });
                setIsLoading(false);
                // Don't navigate - stay on wizard for retry
            }
        }
    };

    const triggerNextPhase = async (nextPhase: Phase) => {
        setIsLoading(true);
        try {
            const res = await fetch("/api/story/new/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slot,
                    thread_id: threadId,
                    message: `[SYSTEM] Phase ${currentPhase} complete. Proceeding to ${nextPhase}. Please introduce the next phase.`,
                    current_phase: nextPhase,
                    context_data: wizardData
                }),
            });

            if (!res.ok) throw new Error("Failed to trigger next phase");
            const data = await res.json();
            addMessage("assistant", data.message);

            // Set new choices (or clear if none)
            setDisplayChoices(data.choices ? normalizeChoices(data.choices) : null);
        } catch (error) {
            console.error("Next phase trigger error:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const renderArtifactConfirmation = () => {
        if (!pendingArtifact) return null;

        const { type, data } = pendingArtifact;

        return (
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="absolute inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-6"
            >

                <Card className="w-full max-w-2xl bg-card border border-primary/50 p-6 space-y-6 shadow-lg">
                    <div className="flex items-center gap-3 border-b border-primary/30 pb-4">
                        <CheckCircle className="w-6 h-6 text-primary" />
                        <h3 className="text-xl font-mono text-primary uppercase tracking-widest">
                            Confirm {currentPhase}
                        </h3>
                    </div>

                    <ScrollArea className="h-[400px] pr-4">
                        <div className="space-y-4 font-mono text-sm text-muted-foreground">
                            {type === "submit_world_document" && (
                                <div className="space-y-4">
                                    {/* Header */}
                                    <div className="border-l-2 border-primary pl-4 mb-6">
                                        <div className="flex items-baseline gap-2 mb-1">
                                            <span className="text-primary text-xs uppercase">World</span>
                                            <h4 className="text-xl text-white font-bold">{data.world_name}</h4>
                                        </div>
                                    </div>

                                    {/* Quick Reference Grid */}
                                    <div className="grid grid-cols-2 gap-3 text-xs">
                                        <div className="bg-primary/5 border border-primary/20 p-2 rounded">
                                            <span className="text-primary block uppercase mb-1">Genre</span>
                                            <span className="text-white capitalize">{data.genre}{data.secondary_genres?.length > 0 && ` (+${data.secondary_genres.join(", ")})`}</span>
                                        </div>
                                        <div className="bg-primary/5 border border-primary/20 p-2 rounded">
                                            <span className="text-primary block uppercase mb-1">Era</span>
                                            <span className="text-white">{data.time_period}</span>
                                        </div>
                                        <div className="bg-primary/5 border border-primary/20 p-2 rounded">
                                            <span className="text-primary block uppercase mb-1">Tone</span>
                                            <span className="text-white capitalize">{data.tone}</span>
                                        </div>
                                        <div className="bg-primary/5 border border-primary/20 p-2 rounded">
                                            <span className="text-primary block uppercase mb-1">Tech Level</span>
                                            <span className="text-white capitalize">{data.tech_level?.replace(/_/g, " ")}</span>
                                        </div>
                                        <div className="bg-primary/5 border border-primary/20 p-2 rounded">
                                            <span className="text-primary block uppercase mb-1">Scope</span>
                                            <span className="text-white capitalize">{data.geographic_scope}</span>
                                        </div>
                                        <div className="bg-primary/5 border border-primary/20 p-2 rounded">
                                            <span className="text-primary block uppercase mb-1">Magic</span>
                                            <span className="text-white">{data.magic_exists ? "Present" : "None"}</span>
                                        </div>
                                    </div>

                                    {/* Magic Description (if exists) */}
                                    {data.magic_exists && data.magic_description && (
                                        <CollapsibleSection title="Magic System" defaultOpen={true} icon={<Wand2 className="w-4 h-4 text-primary" />}>
                                            <p className="text-sm text-white/80 leading-relaxed">{data.magic_description}</p>
                                        </CollapsibleSection>
                                    )}

                                    {/* Narrative Elements */}
                                    <CollapsibleSection title="World Context" defaultOpen={true} icon={<Globe className="w-4 h-4 text-primary" />}>
                                        <div className="space-y-3">
                                            <div>
                                                <span className="text-primary block text-xs uppercase mb-1">Political Structure</span>
                                                <p className="text-sm text-white/80">{data.political_structure}</p>
                                            </div>
                                            <div>
                                                <span className="text-primary block text-xs uppercase mb-1">Major Conflict</span>
                                                <p className="text-sm text-white/80">{data.major_conflict}</p>
                                            </div>
                                            {data.themes?.length > 0 && (
                                                <div>
                                                    <span className="text-primary block text-xs uppercase mb-1">Themes</span>
                                                    <div className="flex flex-wrap gap-1">
                                                        {data.themes.map((theme: string, i: number) => (
                                                            <span key={i} className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded">{theme}</span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </CollapsibleSection>

                                    {/* Cultural Notes */}
                                    {data.cultural_notes && (
                                        <CollapsibleSection title="Cultural Notes" icon={<Scroll className="w-4 h-4 text-primary" />}>
                                            <p className="text-sm text-white/80 leading-relaxed whitespace-pre-wrap">{data.cultural_notes}</p>
                                        </CollapsibleSection>
                                    )}

                                    {/* Language Notes (if present) */}
                                    {data.language_notes && (
                                        <CollapsibleSection title="Language & Naming" icon={<Languages className="w-4 h-4 text-primary" />}>
                                            <p className="text-sm text-white/80 leading-relaxed">{data.language_notes}</p>
                                        </CollapsibleSection>
                                    )}

                                    {/* Diegetic Artifact - collapsed by default */}
                                    {data.diegetic_artifact && (
                                        <CollapsibleSection title="In-World Document" icon={<FileText className="w-4 h-4 text-primary" />}>
                                            <div className="prose prose-invert prose-sm max-w-none">
                                                <p className="whitespace-pre-wrap text-muted-foreground italic leading-relaxed">
                                                    {data.diegetic_artifact}
                                                </p>
                                            </div>
                                        </CollapsibleSection>
                                    )}
                                </div>
                            )}

                            {type === "submit_character_sheet" && (
                                <div className="space-y-4">
                                    <div className="flex items-center gap-4 mb-6">
                                        <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center border border-primary/30 shrink-0">
                                            <User className="w-8 h-8 text-primary" />
                                        </div>
                                        <div>
                                            <h4 className="text-2xl text-white font-bold">{data.name}</h4>
                                            <p className="text-primary text-sm">{data.summary}</p>
                                        </div>
                                    </div>

                                    <CollapsibleSection title="Narrative Portrait" defaultOpen={true} icon={<FileText className="w-4 h-4 text-primary" />}>
                                        <p className="whitespace-pre-wrap text-muted-foreground italic leading-relaxed text-sm">
                                            {data.diegetic_artifact}
                                        </p>
                                    </CollapsibleSection>

                                    <CollapsibleSection title="Wildcard" defaultOpen={true} icon={<Sparkles className="w-4 h-4 text-primary" />}>
                                        <div>
                                            <span className="text-primary block text-xs uppercase mb-1">{data.wildcard_name}</span>
                                            <p className="text-sm text-white/90">{data.wildcard_description}</p>
                                        </div>
                                    </CollapsibleSection>

                                    <CollapsibleSection title="Attributes & Traits" icon={<User className="w-4 h-4 text-primary" />}>
                                        <div className="space-y-4">
                                            <div className="grid grid-cols-2 gap-4">
                                                <div>
                                                    <span className="text-primary block text-xs uppercase mb-1">Appearance</span>
                                                    <p className="text-sm text-white/80">{data.appearance}</p>
                                                </div>
                                                <div>
                                                    <span className="text-primary block text-xs uppercase mb-1">Personality</span>
                                                    <p className="text-sm text-white/80">{data.personality}</p>
                                                </div>
                                            </div>

                                            <div>
                                                <span className="text-primary block text-xs uppercase mb-2">Traits</span>
                                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                                    {[
                                                        "allies", "contacts", "patron", "dependents",
                                                        "status", "reputation", "resources", "domain",
                                                        "enemies", "obligations"
                                                    ].map(trait => {
                                                        if (data[trait]) {
                                                            return (
                                                                <div key={trait} className="bg-primary/5 border border-primary/20 p-2 rounded">
                                                                    <span className="text-primary text-xs uppercase block mb-1">{trait}</span>
                                                                    <p className="text-xs text-white/80">{data[trait]}</p>
                                                                </div>
                                                            );
                                                        }
                                                        return null;
                                                    })}
                                                </div>
                                            </div>
                                        </div>
                                    </CollapsibleSection>
                                </div>
                            )}

                            {type === "submit_starting_scenario" && (
                                <div className="space-y-4">
                                    <div className="border-l-2 border-primary pl-4 mb-6">
                                        <span className="text-primary block text-xs uppercase mb-1">Starting Scenario</span>
                                        <h4 className="text-xl text-white font-bold mb-2">{data.seed.title}</h4>
                                        <p className="italic text-muted-foreground/60">{data.seed.hook}</p>
                                    </div>

                                    <CollapsibleSection title="Location Details" defaultOpen={true} icon={<MapPin className="w-4 h-4 text-primary" />}>
                                        <div className="space-y-2">
                                            <div className="flex justify-between border-b border-white/10 py-2">
                                                <span className="text-primary">Region (Layer)</span>
                                                <span className="text-white text-right">{data.layer.name}</span>
                                            </div>
                                            <div className="flex justify-between border-b border-white/10 py-2">
                                                <span className="text-primary">Zone</span>
                                                <span className="text-white text-right">{data.zone.name}</span>
                                            </div>
                                            <div className="flex justify-between border-b border-white/10 py-2">
                                                <span className="text-primary">Specific Location</span>
                                                <span className="text-white text-right">{data.location.name}</span>
                                            </div>
                                            <div className="pt-2">
                                                <span className="text-primary block text-xs uppercase mb-1">Description</span>
                                                <p className="text-sm text-white/80">{(data.location.description || "").substring(0, 200)}...</p>
                                            </div>
                                        </div>
                                    </CollapsibleSection>
                                </div>
                            )}
                        </div>
                    </ScrollArea>

                    <div className="flex justify-end gap-3 pt-4 border-t border-primary/30">
                        <Button
                            variant="outline"
                            onClick={() => setPendingArtifact(null)}
                            className="border-destructive/50 text-destructive hover:bg-destructive/10"
                        >
                            REVISE
                        </Button>
                        <Button
                            onClick={handleArtifactConfirm}
                            className="bg-primary/20 border border-primary text-primary hover:bg-primary/30"
                        >
                            CONFIRM & PROCEED
                        </Button>
                    </div>
                </Card>
            </motion.div>
        );
    };

    const renderArtifactViewer = () => {
        if (!viewingArtifact) return null;

        const { type, data } = viewingArtifact;

        // Format artifact type for display
        const formatTypeName = (t: string) => t.replace("submit_", "").replace(/_/g, " ");

        return (
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="absolute inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-6"
                onClick={(e) => e.target === e.currentTarget && setViewingArtifact(null)}
            >
                <Card className="w-full max-w-2xl bg-card border border-primary/50 p-6 space-y-6 shadow-lg">
                    <div className="flex items-center gap-3 border-b border-primary/30 pb-4">
                        <Eye className="w-6 h-6 text-primary" />
                        <h3 className="text-xl font-mono text-primary uppercase tracking-widest">
                            {formatTypeName(type)}
                        </h3>
                    </div>

                    <ScrollArea className="h-[400px] pr-4">
                        <div className="space-y-4 font-mono text-sm text-muted-foreground">
                            {type === "submit_character_concept" && (
                                <div className="space-y-4">
                                    {/* Character Header */}
                                    <div className="border-l-2 border-primary pl-4 mb-6">
                                        <div className="flex items-baseline gap-2 mb-1">
                                            <span className="text-primary text-xs uppercase">Character</span>
                                            <h4 className="text-xl text-white font-bold">{data.name}</h4>
                                        </div>
                                        <p className="text-primary/80 italic">{data.archetype}</p>
                                    </div>

                                    {/* Core Details */}
                                    <div className="space-y-3">
                                        <div>
                                            <span className="text-primary block text-xs uppercase mb-1">Appearance</span>
                                            <p className="text-sm text-white/80">{data.appearance}</p>
                                        </div>
                                        <div>
                                            <span className="text-primary block text-xs uppercase mb-1">Background</span>
                                            <p className="text-sm text-white/80">{data.background}</p>
                                        </div>
                                    </div>

                                    {/* Suggested Traits */}
                                    {data.suggested_traits && data.suggested_traits.length > 0 && (
                                        <CollapsibleSection title="Suggested Traits" defaultOpen={true} icon={<Tag className="w-4 h-4 text-primary" />}>
                                            <div className="space-y-3">
                                                {data.suggested_traits.map((trait: string) => (
                                                    <div key={trait} className="bg-primary/5 border border-primary/20 p-2 rounded">
                                                        <span className="text-primary text-xs uppercase block mb-1 capitalize">{trait}</span>
                                                        {data.trait_rationales?.[trait] && (
                                                            <p className="text-xs text-white/80">{data.trait_rationales[trait]}</p>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </CollapsibleSection>
                                    )}
                                </div>
                            )}

                            {type === "submit_trait_selection" && (
                                <div className="space-y-4">
                                    <div className="border-l-2 border-primary pl-4 mb-6">
                                        <span className="text-primary text-xs uppercase">Selected Traits</span>
                                    </div>
                                    <div className="grid grid-cols-1 gap-3">
                                        {data.traits?.map((trait: string) => (
                                            <div key={trait} className="bg-primary/5 border border-primary/20 p-3 rounded">
                                                <span className="text-primary text-sm uppercase capitalize">{trait}</span>
                                                {data.trait_details?.[trait] && (
                                                    <p className="text-xs text-white/80 mt-1">{data.trait_details[trait]}</p>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {type === "submit_wildcard_trait" && (
                                <div className="space-y-4">
                                    <div className="border-l-2 border-primary pl-4 mb-6">
                                        <div className="flex items-baseline gap-2 mb-1">
                                            <span className="text-primary text-xs uppercase">Wildcard</span>
                                            <h4 className="text-xl text-white font-bold">{data.name}</h4>
                                        </div>
                                    </div>
                                    <div>
                                        <span className="text-primary block text-xs uppercase mb-1">Description</span>
                                        <p className="text-sm text-white/80 leading-relaxed">{data.description}</p>
                                    </div>
                                </div>
                            )}
                        </div>
                    </ScrollArea>

                    <div className="flex justify-end pt-4 border-t border-primary/30">
                        <Button
                            onClick={() => setViewingArtifact(null)}
                            className="bg-primary/20 border border-primary text-primary hover:bg-primary/30"
                        >
                            CLOSE
                        </Button>
                    </div>
                </Card>
            </motion.div>
        );
    };

    return (
        <div className="flex flex-col h-full w-full max-w-5xl mx-auto bg-background/40 border border-primary/30 rounded-lg overflow-hidden backdrop-blur-sm relative">
            {renderArtifactConfirmation()}
            {renderArtifactViewer()}

            {/* Header */}
            <div className="p-4 border-b border-primary/30 bg-background/60 flex justify-between items-center">
                <div className="flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-primary" />
                    <h3 className="font-mono text-foreground">
                        SKALD // {currentPhase.toUpperCase()} PROTOCOL
                    </h3>
                </div>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={async () => {
                        if (!threadId || isLoading) return;
                        // Accept Fate: Backend forces tool call via tool_choice="required"
                        // No user message added to keep conversation clean
                        setIsLoading(true);

                        try {
                            const res = await fetch("/api/story/new/chat", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                    slot,
                                    thread_id: threadId,
                                    message: "",  // No message needed
                                    current_phase: currentPhase,
                                    context_data: wizardData,
                                    accept_fate: true,  // Backend forces tool call
                                }),
                            });

                            if (!res.ok) throw new Error("Failed to send message");
                            const data = await res.json();

                            if (data.phase_complete) {
                                setPendingArtifact({ type: data.artifact_type, data: data.data });
                            } else if (data.subphase_complete) {
                                handleSubphaseCompletion(data.artifact_type, data.data);
                            } else {
                                addMessage("assistant", data.message);
                                setDisplayChoices(data.choices?.length > 0 ? normalizeChoices(data.choices) : null);
                            }
                        } catch (e) {
                            console.error(e);
                            toast({ title: "Transmission Error", variant: "destructive" });
                        } finally {
                            setIsLoading(false);
                        }
                    }}
                    className="text-amber-500/70 hover:text-amber-400 font-mono text-xs uppercase tracking-wider"
                    disabled={isLoading || !threadId}
                >
                    Accept Fate
                </Button>
            </div>

            {/* Main content area with optional sidebar */}
            <div className="flex flex-1 overflow-hidden">
                {/* Chat column */}
                <div className="flex-1 flex flex-col min-w-0">
                    {/* Chat Area */}
                    <ScrollArea className="flex-1 p-4" ref={scrollRef}>
                        <div className="space-y-6">
                            <AnimatePresence initial={false}>
                                {messages.map((msg) => (
                                    <motion.div
                                        key={msg.id}
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        className={cn(
                                            "flex w-full",
                                            msg.role === "user" ? "justify-end" : "justify-start"
                                        )}
                                    >
                                        <div
                                            className={cn(
                                                "max-w-[85%] p-4 rounded-lg font-mono text-sm leading-relaxed shadow-lg",
                                                msg.role === "user"
                                                    ? "bg-primary/20 border border-primary/30 text-foreground"
                                                    : "bg-background/80 border border-border text-foreground"
                                            )}
                                        >
                                            {msg.role === "assistant" ? (
                                                <div>
                                                    <div className="flex items-center gap-1.5 mb-2 pb-1 border-b border-primary/20">
                                                        <Sparkles className="w-3 h-3 text-primary" />
                                                        <span className="text-[10px] font-mono text-primary uppercase tracking-widest">Skald</span>
                                                    </div>
                                                    <div className="prose prose-invert prose-sm max-w-none prose-p:leading-relaxed prose-pre:bg-black/50 prose-pre:border prose-pre:border-white/10">
                                                        <ReactMarkdown>
                                                            {msg.content}
                                                        </ReactMarkdown>
                                                    </div>
                                                </div>
                                            ) : msg.role === "system" && msg.artifactData ? (
                                                <button
                                                    onClick={() => setViewingArtifact({ type: msg.artifactType!, data: msg.artifactData })}
                                                    className="flex items-center gap-2 text-primary/60 hover:text-primary transition-colors group"
                                                >
                                                    <Eye className="w-3 h-3 opacity-60 group-hover:opacity-100" />
                                                    <span className="underline underline-offset-2">{msg.content}</span>
                                                </button>
                                            ) : (
                                                <div className="whitespace-pre-wrap">{msg.content}</div>
                                            )}
                                        </div>
                                    </motion.div>
                                ))}
                            </AnimatePresence>
                            {/* Structured choices */}
                            {displayChoices && displayChoices.length > 0 && !isLoading && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="mt-4"
                                >
                                    <StoryChoices
                                        choices={displayChoices}
                                        onSelect={handleChoiceSelect}
                                        disabled={isLoading}
                                    />
                                </motion.div>
                            )}
                            {isLoading && (
                                <motion.div
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    className="flex justify-start"
                                >
                                    <div className="bg-muted/60 border border-accent/30 p-3 rounded-lg flex items-center gap-2">
                                        <Loader2 className="w-4 h-4 text-accent animate-spin" />
                                        <span className="text-xs text-muted-foreground font-mono">PROCESSING...</span>
                                    </div>
                                </motion.div>
                            )}
                        </div>
                    </ScrollArea>

                    {/* Input Area */}
                    <div className="p-4 border-t border-primary/30 bg-background/60">
                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                handleSend();
                            }}
                            className="flex gap-2 items-end"
                        >
                            <textarea
                                value={input}
                                onChange={(e) => {
                                    setInput(e.target.value);
                                    e.target.style.height = 'auto';
                                    e.target.style.height = e.target.scrollHeight + 'px';
                                }}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && !e.shiftKey) {
                                        e.preventDefault();
                                        handleSend();
                                    }
                                }}
                                placeholder={`Input for ${currentPhase} phase...`}
                                className="flex-1 bg-background/40 border border-primary/30 text-foreground focus:border-primary font-mono min-h-[48px] max-h-[200px] p-3 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-primary"
                                disabled={isLoading || !!pendingArtifact}
                                rows={1}
                            />
                            <Button
                                type="submit"
                                disabled={isLoading || !input.trim() || !!pendingArtifact}
                                className="h-12 px-6 bg-primary/20 border border-primary/50 text-primary hover:bg-primary/30"
                            >
                                <Send className="w-5 h-5" />
                            </Button>
                        </form>
                    </div>
                </div>

                {/* Trait Selection Sidebar */}
                {showTraitSelector && (
                    <motion.div
                        initial={{ width: 0, opacity: 0 }}
                        animate={{ width: 280, opacity: 1 }}
                        exit={{ width: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="border-l border-primary/30 bg-background/80 p-4 overflow-hidden"
                    >
                        <TraitSelector
                            onConfirm={handleTraitConfirm}
                            onInvalidConfirm={handleInvalidTraitConfirm}
                            disabled={isLoading}
                            suggestedTraits={suggestedTraits}
                        />
                    </motion.div>
                )}
            </div>
        </div >
    );
}
