import React, { useState, useRef, useEffect } from "react";
import { Send, Sparkles, Loader2, CheckCircle, FileText, MapPin, User, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { useToast } from "@/hooks/use-toast";
import ReactMarkdown from "react-markdown";

interface Message {
    id: string;
    role: "user" | "assistant" | "system";
    content: string;
    timestamp: number;
}

interface InteractiveWizardProps {
    slot: number;
    onComplete: () => void;
    onCancel: () => void;
    onPhaseChange: (phase: Phase) => void;
    wizardData: any;
    setWizardData: (data: any) => void;
}

type Phase = "setting" | "character" | "seed";

export function InteractiveWizard({ slot, onComplete, onCancel, onPhaseChange, wizardData, setWizardData }: InteractiveWizardProps) {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [threadId, setThreadId] = useState<string | null>(null);
    const [currentPhase, setCurrentPhase] = useState<Phase>("setting");
    const [pendingArtifact, setPendingArtifact] = useState<any>(null);
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
                const startRes = await fetch("/api/story/new/setup/start", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ slot }),
                });

                if (!startRes.ok) throw new Error("Failed to start setup");
                const { thread_id } = await startRes.json();
                setThreadId(thread_id);

                const initialRes = await fetch("/api/story/new/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        slot,
                        thread_id,
                        message: "INIT_GREETING",
                        is_init: true,
                        current_phase: "setting"
                    }),
                });

                if (initialRes.ok) {
                    const data = await initialRes.json();
                    addMessage("assistant", data.message);
                }
            } catch (error) {
                console.error("Failed to init chat:", error);
                toast({
                    title: "Connection Error",
                    description: "Failed to connect to the narrative core.",
                    variant: "destructive",
                });
            } finally {
                setIsLoading(false);
            }
        };

        initChat();
    }, [slot, toast]);

    // Auto-scroll
    useEffect(() => {
        if (scrollRef.current) {
            // Use a small timeout to ensure DOM is updated
            setTimeout(() => {
                const scrollElement = scrollRef.current;
                if (scrollElement) {
                    const scrollContainer = scrollElement.querySelector('[data-radix-scroll-area-viewport]');
                    if (scrollContainer) {
                        scrollContainer.scrollTop = scrollContainer.scrollHeight;
                    }
                }
            }, 100);
        }
    }, [messages, isLoading, pendingArtifact]);

    const addMessage = (role: Message["role"], content: string) => {
        setMessages((prev) => [
            ...prev,
            {
                id: Math.random().toString(36).substring(7),
                role,
                content,
                timestamp: Date.now(),
            },
        ]);
    };

    const handleSend = async () => {
        if (!input.trim() || isLoading || !threadId) return;

        const userMsg = input.trim();
        setInput("");
        addMessage("user", userMsg);
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
            } else {
                addMessage("assistant", data.message);
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

    const handleArtifactConfirm = async () => {
        // Determine next phase or completion
        if (currentPhase === "setting") {
            setWizardData((prev: any) => ({ ...prev, setting: pendingArtifact.data }));
            updatePhase("character");
            setPendingArtifact(null);
            // Trigger next phase prompt
            triggerNextPhase("character");
        } else if (currentPhase === "character") {
            setWizardData((prev: any) => ({ ...prev, character: pendingArtifact.data }));
            updatePhase("seed");
            setPendingArtifact(null);
            // Trigger next phase prompt
            triggerNextPhase("seed");
        } else if (currentPhase === "seed") {
            setWizardData((prev: any) => ({ ...prev, seed: pendingArtifact.data }));
            // Finalize
            toast({
                title: "Initialization Complete",
                description: "Entering simulation...",
            });
            setTimeout(onComplete, 2000);
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
                <Card className="w-full max-w-2xl bg-black border border-cyan-500/50 p-6 space-y-6 shadow-[0_0_50px_rgba(6,182,212,0.2)]">
                    <div className="flex items-center gap-3 border-b border-cyan-500/30 pb-4">
                        <CheckCircle className="w-6 h-6 text-cyan-400" />
                        <h3 className="text-xl font-mono text-cyan-100 uppercase tracking-widest">
                            Confirm {currentPhase}
                        </h3>
                    </div>

                    <ScrollArea className="h-[400px] pr-4">
                        <div className="space-y-4 font-mono text-sm text-cyan-100/80">
                            {type === "submit_world_document" && (
                                <div className="space-y-6">
                                    <div className="border-l-2 border-cyan-500 pl-4">
                                        <h4 className="text-xl text-white font-bold mb-2">{data.world_name}</h4>
                                        <p className="text-cyan-400 text-sm uppercase tracking-wider mb-4">{data.genre} // {data.time_period}</p>
                                        <div className="prose prose-invert prose-sm max-w-none">
                                            <p className="whitespace-pre-wrap text-cyan-100/90 italic leading-relaxed">
                                                {data.diegetic_artifact || data.cultural_notes}
                                            </p>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-4 text-xs">
                                        <div>
                                            <span className="text-cyan-500 block uppercase">Tone</span>
                                            <span className="text-white">{data.tone}</span>
                                        </div>
                                        <div>
                                            <span className="text-cyan-500 block uppercase">Tech Level</span>
                                            <span className="text-white">{data.tech_level}</span>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {type === "submit_character_sheet" && (
                                <div className="space-y-6">
                                    <div className="flex items-center gap-4">
                                        <div className="w-16 h-16 bg-cyan-900/30 rounded-full flex items-center justify-center border border-cyan-500/30">
                                            <User className="w-8 h-8 text-cyan-400" />
                                        </div>
                                        <div>
                                            <h4 className="text-2xl text-white font-bold">{data.name}</h4>
                                            <p className="text-cyan-400">{data.age} y/o {data.background} {data.occupation}</p>
                                        </div>
                                    </div>

                                    <div className="bg-black/40 border border-cyan-500/20 p-4 rounded-md">
                                        <span className="text-cyan-500 block text-xs uppercase mb-2">Dossier</span>
                                        <p className="whitespace-pre-wrap text-cyan-100/90 italic leading-relaxed text-sm">
                                            {data.diegetic_artifact || data.backstory}
                                        </p>
                                    </div>

                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <span className="text-cyan-500 block text-xs uppercase">Appearance</span>
                                            <p className="text-sm">{data.appearance}</p>
                                        </div>
                                        <div>
                                            <span className="text-cyan-500 block text-xs uppercase">Personality</span>
                                            <p className="text-sm">{data.personality}</p>
                                        </div>
                                    </div>
                                    <div>
                                        <span className="text-cyan-500 block text-xs uppercase">Skills</span>
                                        <div className="flex flex-wrap gap-2 mt-1">
                                            {data.skills.map((s: string, i: number) => (
                                                <span key={i} className="px-2 py-1 bg-cyan-500/10 border border-cyan-500/30 rounded text-xs">
                                                    {s}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            )}

                            {type === "submit_starting_scenario" && (
                                <div className="space-y-6">
                                    <div className="border-l-2 border-cyan-500 pl-4">
                                        <span className="text-cyan-500 block text-xs uppercase mb-1">Starting Scenario</span>
                                        <h4 className="text-xl text-white font-bold mb-2">{data.seed.title}</h4>
                                        <p className="italic text-cyan-100/60">{data.seed.hook}</p>
                                    </div>

                                    <div className="space-y-2">
                                        <div className="flex justify-between border-b border-white/10 py-2">
                                            <span className="text-cyan-500">assets.selected_seed</span>
                                            <span className="text-white text-right">{data.seed.title}</span>
                                        </div>
                                        <div className="flex justify-between border-b border-white/10 py-2">
                                            <span className="text-cyan-500">public.layers.name</span>
                                            <span className="text-white text-right">{data.layer.name}</span>
                                        </div>
                                        <div className="flex justify-between border-b border-white/10 py-2">
                                            <span className="text-cyan-500">public.zones.name</span>
                                            <span className="text-white text-right">{data.zone.name}</span>
                                        </div>
                                        <div className="flex justify-between border-b border-white/10 py-2">
                                            <span className="text-cyan-500">public.places.name</span>
                                            <span className="text-white text-right">{data.location.name}</span>
                                        </div>
                                        <div className="pt-2">
                                            <span className="text-cyan-500 block text-xs uppercase mb-1">public.places.summary</span>
                                            <p className="text-sm text-white/80">{data.location.description.substring(0, 200)}...</p>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </ScrollArea>

                    <div className="flex justify-end gap-3 pt-4 border-t border-cyan-500/30">
                        <Button
                            variant="outline"
                            onClick={() => setPendingArtifact(null)}
                            className="border-red-500/50 text-red-400 hover:bg-red-500/10"
                        >
                            REVISE
                        </Button>
                        <Button
                            onClick={handleArtifactConfirm}
                            className="bg-cyan-500/20 border border-cyan-500 text-cyan-400 hover:bg-cyan-500/30"
                        >
                            CONFIRM & PROCEED
                        </Button>
                    </div>
                </Card>
            </motion.div>
        );
    };

    return (
        <div className="flex flex-col h-full w-full max-w-5xl mx-auto bg-black/40 border border-cyan-500/30 rounded-lg overflow-hidden backdrop-blur-sm relative">
            {renderArtifactConfirmation()}

            {/* Header */}
            <div className="p-4 border-b border-cyan-500/30 bg-black/60 flex justify-between items-center">
                <div className="flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-cyan-400" />
                    <h3 className="font-mono text-cyan-100">
                        NEXUS // {currentPhase.toUpperCase()} PROTOCOL
                    </h3>
                </div>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={onCancel}
                    className="text-cyan-400/60 hover:text-cyan-400"
                >
                    ABORT
                </Button>
            </div>

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
                                            ? "bg-cyan-900/20 border border-cyan-500/30 text-cyan-100"
                                            : "bg-black/80 border border-purple-500/30 text-gray-100"
                                    )}
                                >
                                    {msg.role === "assistant" ? (
                                        <div className="prose prose-invert prose-sm max-w-none prose-p:leading-relaxed prose-pre:bg-black/50 prose-pre:border prose-pre:border-white/10">
                                            <ReactMarkdown>
                                                {msg.content}
                                            </ReactMarkdown>
                                        </div>
                                    ) : (
                                        <div className="whitespace-pre-wrap">{msg.content}</div>
                                    )}
                                </div>
                            </motion.div>
                        ))}
                    </AnimatePresence>
                    {isLoading && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="flex justify-start"
                        >
                            <div className="bg-black/60 border border-purple-500/30 p-3 rounded-lg flex items-center gap-2">
                                <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />
                                <span className="text-xs text-purple-400/60 font-mono">PROCESSING...</span>
                            </div>
                        </motion.div>
                    )}
                </div>
            </ScrollArea>

            {/* Input Area */}
            <div className="p-4 border-t border-cyan-500/30 bg-black/60">
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
                        className="flex-1 bg-black/40 border border-cyan-500/30 text-cyan-100 focus:border-cyan-400 font-mono min-h-[48px] max-h-[200px] p-3 rounded-md resize-none focus:outline-none focus:ring-1 focus:ring-cyan-400"
                        disabled={isLoading || !!pendingArtifact}
                        rows={1}
                    />
                    <Button
                        type="submit"
                        disabled={isLoading || !input.trim() || !!pendingArtifact}
                        className="h-12 px-6 bg-cyan-500/20 border border-cyan-500/50 text-cyan-400 hover:bg-cyan-500/30"
                    >
                        <Send className="w-5 h-5" />
                    </Button>
                </form>
            </div>
        </div>
    );
}
