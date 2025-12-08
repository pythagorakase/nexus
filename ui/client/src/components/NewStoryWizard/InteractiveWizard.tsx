import React, { useState, useRef, useEffect, useCallback } from "react";
import { Sparkles, CheckCircle, FileText, MapPin, User, Globe, ChevronDown, ChevronRight, Wand2, Scroll, Languages, Crown, Tag, Eye, Cpu, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area"; // Still used for artifact confirmation modals
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { useToast } from "@/hooks/use-toast";
import { StoryChoices, ChoiceSelection } from "@/components/StoryChoices";
import { TraitSelector } from "./TraitSelector";
import { WaitScreen } from "./WaitScreen";
import { useModel } from "@/contexts/ModelContext";
import {
    Conversation,
    ConversationContent,
    ConversationScrollButton,
    PromptInput,
    PromptInputTextarea,
    PromptInputToolbar,
    PromptInputTools,
    PromptInputSubmit,
    PromptInputModelSelect,
    PromptInputModelSelectTrigger,
    PromptInputModelSelectContent,
    PromptInputModelSelectItem,
    PromptInputModelSelectValue,
    Loader,
    Response,
} from "@/components/ai";

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

interface ExpandableTextProps {
    text: string;
    maxLength?: number;
    className?: string;
}

function ExpandableText({ text, maxLength = 200, className = "" }: ExpandableTextProps) {
    const [isExpanded, setIsExpanded] = useState(false);
    const needsExpansion = text.length > maxLength;

    if (!needsExpansion) {
        return <p className={className}>{text}</p>;
    }

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
    const { toast } = useToast();
    const { model, setModel, availableModels, isTestMode } = useModel();

    // Ref-based guard for synchronous double-click prevention
    // React state updates are async, so fast double-clicks can slip through state-based guards
    const processingRef = useRef(false);

    // Wait screen state for long-running transition + bootstrap
    const [waitScreenActive, setWaitScreenActive] = useState(false);
    const [waitScreenElapsed, setWaitScreenElapsed] = useState(0);
    const [waitScreenError, setWaitScreenError] = useState<string | null>(null);
    const [waitScreenStatusText, setWaitScreenStatusText] = useState("Initializing your world...");
    const transitionAbortRef = useRef<AbortController | null>(null);

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
                    body: JSON.stringify({ slot, model }),  // Include model for TEST mode support
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

    // Note: Auto-scroll is now handled by the Conversation component (use-stick-to-bottom)

    // Timer for wait screen - counts up every second while active
    useEffect(() => {
        if (!waitScreenActive) {
            return;
        }
        const interval = setInterval(() => {
            setWaitScreenElapsed((prev) => prev + 1);
        }, 1000);
        return () => clearInterval(interval);
    }, [waitScreenActive]);

    // Transition handler - performs transition + triggers bootstrap, then navigates
    // NexusLayout handles detecting incubator data and showing approval modal
    const performTransition = useCallback(async () => {
        // Reset state on start/retry
        setWaitScreenError(null);
        setWaitScreenElapsed(0);
        setWaitScreenStatusText("Initializing your world...");
        setWaitScreenActive(true);

        // Create abort controller for cancellation
        const abortController = new AbortController();
        transitionAbortRef.current = abortController;

        try {
            // Step 1: Transition (write entities to database)
            const transitionRes = await fetch("/api/story/new/transition", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ slot }),
                signal: abortController.signal,
            });

            if (!transitionRes.ok) {
                const error = await transitionRes.json();
                throw new Error(error.detail || "Transition failed");
            }

            await transitionRes.json(); // consume response

            // Step 2: Trigger bootstrap (generate first narrative chunk)
            setWaitScreenStatusText("Starting narrative generation...");

            const bootstrapRes = await fetch("/api/narrative/continue", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    chunk_id: 0,  // Bootstrap signal
                    slot,
                    user_text: "Begin the story.",
                }),
                signal: abortController.signal,
            });

            if (!bootstrapRes.ok) {
                const error = await bootstrapRes.json();
                throw new Error(error.detail || error.error || "Bootstrap failed");
            }

            const bootstrapData = await bootstrapRes.json();
            console.log("[Wizard] Bootstrap triggered, session:", bootstrapData.session_id);

            localStorage.setItem(
                "pendingBootstrapSession",
                JSON.stringify({ slot, sessionId: bootstrapData.session_id, createdAt: Date.now() }),
            );

            // Step 3: Navigate to NexusLayout immediately
            // NexusLayout will:
            // - Connect to WebSocket for real-time updates
            // - Detect incubator data when generation completes
            // - Show approval modal automatically
            setWaitScreenActive(false);
            toast({
                title: "Generation Started",
                description: "Your story is being created...",
            });
            localStorage.setItem("activeSlot", slot.toString());
            onComplete();

        } catch (e: any) {
            if (e.name === "AbortError") {
                // User cancelled via handleWaitScreenCancel - reset state for retry
                // Note: processingRef is also reset in handleWaitScreenCancel, but we reset here too
                // for the edge case where abort happens before cancel handler runs
                processingRef.current = false;
                setWaitScreenActive(false);
                setIsLoading(false);
                toast({
                    title: "Operation cancelled",
                    description: "You can restart when ready.",
                });
                return;
            }
            console.error("Transition/bootstrap error:", e);
            // Reset guard to allow retry after error
            processingRef.current = false;
            setWaitScreenError(e.message || "Failed to initialize story");
            // Keep wait screen active with error state for retry
        }
    }, [slot, toast, onComplete]);

    // Cancel wait screen and return to artifact review
    const handleWaitScreenCancel = useCallback(() => {
        // Abort any in-flight request
        if (transitionAbortRef.current) {
            transitionAbortRef.current.abort();
        }
        // Reset guard to allow re-confirming after cancel
        processingRef.current = false;
        setWaitScreenActive(false);
        setWaitScreenError(null);
        setWaitScreenElapsed(0);
        setWaitScreenStatusText("Initializing your world...");
        setIsLoading(false);
        // Re-show the pending artifact for editing
        // (pendingArtifact is still set from before)
    }, []);

    // Retry transition from wait screen
    const handleWaitScreenRetry = useCallback(() => {
        performTransition();
    }, [performTransition]);

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

    // Normalize artifact data for confirmation modal
    // When character phase completes, extract character_sheet from nested response
    const normalizePendingArtifact = (phase: string, artifactType: string, responseData: any) => {
        if (phase === "character" && responseData.character_sheet) {
            return { type: "submit_character_sheet", data: responseData.character_sheet };
        }
        return { type: artifactType, data: responseData };
    };

    const triggerSubphaseContinuation = async (artifactType: string, contextData: any) => {
        if (isLoading) return;
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
                    model,
                    current_phase: currentPhase,
                    context_data: contextData
                }),
            });

            if (!res.ok) throw new Error("Failed to trigger continuation");
            const data = await res.json();

            if (data.phase_complete) {
                setPendingArtifact(normalizePendingArtifact(data.phase, data.artifact_type, data.data));
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
            processingRef.current = false;
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
                // Extract from wrapper - backend returns {"character_state": {...}}
                const concept = artifactData.character_state?.concept || artifactData;
                newState = { ...prev, character_state: { ...charState, concept } };
            } else if (artifactType === "submit_trait_selection") {
                setShowTraitSelector(false); // Close trait selector after confirmation
                const traitSelection = artifactData.character_state?.trait_selection || artifactData;
                newState = { ...prev, character_state: { ...charState, trait_selection: traitSelection } };
            } else if (artifactType === "submit_wildcard_trait") {
                const wildcard = artifactData.character_state?.wildcard || artifactData;
                newState = { ...prev, character_state: { ...charState, wildcard } };
            }

            updatedWizardData = newState;
            return newState;
        });

        // Show trait selector after concept is submitted
        if (artifactType === "submit_character_concept") {
            // Extract concept from character_state wrapper (backend returns nested structure)
            const conceptData = artifactData.character_state?.concept || artifactData;

            // Pre-select LLM's suggested traits from schema-validated data
            if (conceptData.suggested_traits && Array.isArray(conceptData.suggested_traits)) {
                setSuggestedTraits(conceptData.suggested_traits);
            }
            setShowTraitSelector(true);

            // Add clickable system message to view concept data
            addMessage("system", `[${artifactType} confirmed]`, { type: artifactType, data: conceptData });

            // Build client-side intro message with rationales (SKIP API CALL)
            // This eliminates latency and ensures message is synced with pre-selection
            try {
                const introMessage = buildTraitIntroMessage(conceptData);
                addMessage("assistant", introMessage);
            } catch (error) {
                console.error("Failed to build trait intro message:", error);
                addMessage("assistant", TRAIT_INTRODUCTION + "\n\nPlease select your traits from the menu.");
            }
            setDisplayChoices(null);  // No structured choices - TraitSelector handles it
            return;  // Early return - no API call needed
        }

        // For other subphases, continue with API call
        // Unwrap nested data for trait artifacts so modal displays correctly
        const displayData = artifactType === "submit_trait_selection"
            ? (artifactData.character_state?.trait_selection || artifactData)
            : artifactType === "submit_wildcard_trait"
            ? (artifactData.character_state?.wildcard || artifactData)
            : artifactData;
        addMessage("system", `[${artifactType} confirmed]`, { type: artifactType, data: displayData });
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
        // Synchronous ref-based guard for double-click prevention
        if (processingRef.current || !input.trim() || isLoading || !threadId) return;
        processingRef.current = true;

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
                    model,
                    current_phase: currentPhase,
                    context_data: wizardData
                }),
            });

            if (!res.ok) throw new Error("Failed to send message");

            const data = await res.json();

            if (data.phase_complete) {
                setPendingArtifact(normalizePendingArtifact(data.phase, data.artifact_type, data.data));
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
            processingRef.current = false;
            setIsLoading(false);
        }
    };

    const handleChoiceSelect = (selection: ChoiceSelection) => {
        // Synchronous ref-based guard for double-click prevention
        if (processingRef.current || isLoading) return;
        processingRef.current = true;

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
                model,
                current_phase: currentPhase,
                context_data: wizardData
            }),
        })
            .then(async (res) => {
                if (!res.ok) throw new Error("Failed to send message");
                const data = await res.json();
                if (data.phase_complete) {
                    setPendingArtifact(normalizePendingArtifact(data.phase, data.artifact_type, data.data));
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
                processingRef.current = false;
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
        // Synchronous ref-based guard for double-click prevention
        if (processingRef.current || isLoading) return;
        processingRef.current = true;

        // Don't close selector yet - keep it open with spinner while processing
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
                model,
                current_phase: currentPhase,
                context_data: wizardData
            }),
        })
            .then(async (res) => {
                if (!res.ok) throw new Error("Failed to send message");
                const data = await res.json();
                // Close selector AFTER successful response
                setShowTraitSelector(false);
                if (data.phase_complete) {
                    setPendingArtifact(normalizePendingArtifact(data.phase, data.artifact_type, data.data));
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
                // Also close on error so user can retry
                setShowTraitSelector(false);
                toast({
                    title: "Transmission Error",
                    description: "Failed to send message. Please try again.",
                    variant: "destructive",
                });
            })
            .finally(() => {
                processingRef.current = false;
                setIsLoading(false);
            });
    };

    // Handle invalid trait selection (≠3 traits) - sends to LLM for dialog, UI stays open
    const handleInvalidTraitConfirm = (traits: string[], count: number) => {
        // Synchronous ref-based guard for double-click prevention
        if (processingRef.current || isLoading) return;
        processingRef.current = true;

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
                model,
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
                processingRef.current = false;
                setIsLoading(false);
            });
    };

    const handleArtifactConfirm = async () => {
        // Synchronous ref-based guard for double-click prevention
        if (processingRef.current || !pendingArtifact || isLoading) return;
        processingRef.current = true;

        // Validate artifact matches expected phase to prevent race condition issues
        const expectedArtifactTypes: Record<Phase, string> = {
            setting: "submit_world_document",
            character: "submit_character_sheet",
            seed: "submit_starting_scenario",
        };

        const expectedType = expectedArtifactTypes[currentPhase];
        if (expectedType && pendingArtifact.type !== expectedType) {
            console.warn(`Phase mismatch: expected ${expectedType} for ${currentPhase} phase, got ${pendingArtifact.type}`);
            processingRef.current = false;
            setPendingArtifact(null);
            return;
        }

        // Determine next phase or completion
        if (currentPhase === "setting") {
            setIsLoading(true);
            try {
                setWizardData((prev: any) => ({ ...prev, setting: pendingArtifact.data }));
                onArtifactConfirmed?.("setting", pendingArtifact.data);
                updatePhase("character");
                // Await next phase to ensure proper sequencing
                await triggerNextPhase("character");
            } catch (error) {
                console.error("Error transitioning to character phase:", error);
                toast({
                    title: "Transition Error",
                    description: "Failed to proceed. Please try again.",
                    variant: "destructive",
                });
            } finally {
                setPendingArtifact(null);
                processingRef.current = false;
                setIsLoading(false);
            }
        } else if (currentPhase === "character") {
            // Issue #6: Close trait selector when leaving character phase
            setShowTraitSelector(false);
            // Issue #8: Show loading indicator during transition
            setIsLoading(true);
            try {
                setWizardData((prev: any) => ({ ...prev, character: pendingArtifact.data }));
                onArtifactConfirmed?.("character", pendingArtifact.data);
                updatePhase("seed");
                // Await next phase to keep modal visible with "Processing..." state
                await triggerNextPhase("seed");
            } catch (error) {
                console.error("Error transitioning to seed phase:", error);
                toast({
                    title: "Transition Error",
                    description: "Failed to proceed. Please try again.",
                    variant: "destructive",
                });
            } finally {
                setPendingArtifact(null);
                processingRef.current = false;
                setIsLoading(false);
            }
        } else if (currentPhase === "seed") {
            setWizardData((prev: any) => ({ ...prev, seed: pendingArtifact.data }));
            onArtifactConfirmed?.("seed", pendingArtifact.data);
            // Keep pendingArtifact set so cancel can return to editing
            setIsLoading(true);

            // Show wait screen and start transition
            // This can take up to 10 minutes with reasoning models
            performTransition();
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
                    model,
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
            processingRef.current = false;
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
                                            <p className="text-sm text-white/80 leading-relaxed font-narrative">{data.magic_description}</p>
                                        </CollapsibleSection>
                                    )}

                                    {/* Narrative Elements */}
                                    <CollapsibleSection title="World Context" defaultOpen={true} icon={<Globe className="w-4 h-4 text-primary" />}>
                                        <div className="space-y-3">
                                            <div>
                                                <span className="text-primary block text-xs uppercase mb-1">Political Structure</span>
                                                <p className="text-sm text-white/80 font-narrative">{data.political_structure}</p>
                                            </div>
                                            <div>
                                                <span className="text-primary block text-xs uppercase mb-1">Major Conflict</span>
                                                <p className="text-sm text-white/80 font-narrative">{data.major_conflict}</p>
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
                                            <p className="text-sm text-white/80 leading-relaxed whitespace-pre-wrap font-narrative">{data.cultural_notes}</p>
                                        </CollapsibleSection>
                                    )}

                                    {/* Language Notes (if present) */}
                                    {data.language_notes && (
                                        <CollapsibleSection title="Language & Naming" icon={<Languages className="w-4 h-4 text-primary" />}>
                                            <p className="text-sm text-white/80 leading-relaxed font-narrative">{data.language_notes}</p>
                                        </CollapsibleSection>
                                    )}

                                    {/* Diegetic Artifact - collapsed by default */}
                                    {data.diegetic_artifact && (
                                        <CollapsibleSection title="In-World Document" icon={<FileText className="w-4 h-4 text-primary" />}>
                                            <div className="prose prose-invert prose-sm max-w-none">
                                                <p className="whitespace-pre-wrap text-muted-foreground italic leading-relaxed font-narrative">
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
                                        <p className="whitespace-pre-wrap text-muted-foreground italic leading-relaxed text-sm font-narrative">
                                            {data.summary}
                                        </p>
                                    </CollapsibleSection>

                                    <CollapsibleSection title="Wildcard" defaultOpen={true} icon={<Sparkles className="w-4 h-4 text-primary" />}>
                                        <div>
                                            <span className="text-primary block text-xs uppercase mb-1">{data.wildcard_name}</span>
                                            <p className="text-sm text-white/90 font-narrative">{data.wildcard_description}</p>
                                        </div>
                                    </CollapsibleSection>

                                    <CollapsibleSection title="Attributes & Traits" icon={<User className="w-4 h-4 text-primary" />}>
                                        <div className="space-y-4">
                                            <div className="grid grid-cols-2 gap-4">
                                                <div>
                                                    <span className="text-primary block text-xs uppercase mb-1">Appearance</span>
                                                    <p className="text-sm text-white/80 font-narrative">{data.appearance}</p>
                                                </div>
                                                {data.personality && (
                                                    <div>
                                                        <span className="text-primary block text-xs uppercase mb-1">Personality</span>
                                                        <p className="text-sm text-white/80 font-narrative">{data.personality}</p>
                                                    </div>
                                                )}
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
                                                                    <p className="text-xs text-white/80 font-narrative">{data[trait]}</p>
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
                                                <ExpandableText
                                                    text={data.location.summary || ""}
                                                    maxLength={200}
                                                    className="text-sm text-white/80"
                                                />
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
                            disabled={isLoading}
                            className="border-destructive/50 text-destructive hover:bg-destructive/10 disabled:opacity-50"
                        >
                            REVISE
                        </Button>
                        <Button
                            onClick={handleArtifactConfirm}
                            disabled={isLoading}
                            className="bg-primary/20 border border-primary text-primary hover:bg-primary/30 disabled:opacity-50"
                        >
                            {isLoading ? "Processing..." : "CONFIRM & PROCEED"}
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

            {/* Wait screen for long-running transition + bootstrap operations */}
            {waitScreenActive && (
                <WaitScreen
                    statusText={waitScreenStatusText}
                    elapsedSeconds={waitScreenElapsed}
                    maxSeconds={600}
                    onRetry={handleWaitScreenRetry}
                    onCancel={handleWaitScreenCancel}
                    hasError={!!waitScreenError}
                    errorMessage={waitScreenError || undefined}
                />
            )}

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
                                    model,
                                    current_phase: currentPhase,
                                    context_data: wizardData,
                                    accept_fate: true,  // Backend forces tool call
                                }),
                            });

                            if (!res.ok) throw new Error("Failed to send message");
                            const data = await res.json();

                            if (data.phase_complete) {
                                setPendingArtifact(normalizePendingArtifact(data.phase, data.artifact_type, data.data));
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
                    {/* Chat Area - shadcn AI Conversation with auto-scroll */}
                    <Conversation className="flex-1">
                        <ConversationContent className="p-4 space-y-6">
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
                                                "max-w-[85%] p-4 rounded-lg font-serif text-sm leading-relaxed shadow-lg",
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
                                                    <div className="prose prose-invert max-w-none prose-p:leading-relaxed">
                                                        <Response>{msg.content}</Response>
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
                                        <Loader size={16} className="text-accent" />
                                        <span className="text-xs text-muted-foreground font-mono">PROCESSING...</span>
                                    </div>
                                </motion.div>
                            )}
                        </ConversationContent>
                        <ConversationScrollButton />
                    </Conversation>

                    {/* Input Area - shadcn AI PromptInput */}
                    <div className="p-4 border-t border-primary/30 bg-background/60">
                        <PromptInput
                            onSubmit={(e) => {
                                e.preventDefault();
                                handleSend();
                            }}
                            className="border-primary/30 bg-background/40"
                        >
                            <PromptInputTextarea
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder={displayChoices && displayChoices.length > 0 ? "or something else?" : `Input for ${currentPhase} phase...`}
                                disabled={isLoading || !!pendingArtifact}
                                className="font-mono bg-transparent"
                            />
                            <PromptInputToolbar>
                                <PromptInputTools>
                                    {/* Model Picker */}
                                    <PromptInputModelSelect value={model} onValueChange={(value) => setModel(value as any)}>
                                        <PromptInputModelSelectTrigger className="w-auto font-mono text-xs">
                                            <div className="flex items-center gap-1.5">
                                                <Cpu className="w-3 h-3 shrink-0" />
                                                <PromptInputModelSelectValue />
                                            </div>
                                        </PromptInputModelSelectTrigger>
                                        <PromptInputModelSelectContent>
                                            {availableModels.map((m) => (
                                                <PromptInputModelSelectItem key={m.id} value={m.id} className="font-mono text-xs">
                                                    {m.label}
                                                </PromptInputModelSelectItem>
                                            ))}
                                        </PromptInputModelSelectContent>
                                    </PromptInputModelSelect>
                                </PromptInputTools>
                                <PromptInputSubmit
                                    disabled={isLoading || !input.trim() || !!pendingArtifact}
                                    status={isLoading ? "submitted" : "ready"}
                                    className="bg-primary/20 border border-primary/50 text-primary hover:bg-primary/30"
                                />
                            </PromptInputToolbar>
                        </PromptInput>
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
