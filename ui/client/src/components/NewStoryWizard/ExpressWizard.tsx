import React, { useState, useRef, useEffect } from "react";
import { Send, Sparkles, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { useToast } from "@/hooks/use-toast";

interface Message {
    id: string;
    role: "user" | "assistant" | "system";
    content: string;
    timestamp: number;
}

interface ExpressWizardProps {
    slot: number;
    onComplete: () => void;
    onCancel: () => void;
}

export function ExpressWizard({ slot, onComplete, onCancel }: ExpressWizardProps) {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [threadId, setThreadId] = useState<string | null>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    const { toast } = useToast();

    // Initialize chat
    useEffect(() => {
        const initChat = async () => {
            try {
                setIsLoading(true);
                // Start setup to get thread ID
                const startRes = await fetch("/api/story/new/setup/start", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ slot }),
                });

                if (!startRes.ok) throw new Error("Failed to start setup");
                const { thread_id } = await startRes.json();
                setThreadId(thread_id);

                // Send initial greeting (triggered by backend or simulated)
                // For now, we'll simulate the system initiating
                const initialRes = await fetch("/api/story/new/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        slot,
                        thread_id,
                        message: "INIT_GREETING", // Special signal to backend to start the flow
                        is_init: true
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
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

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
                    message: userMsg
                }),
            });

            if (!res.ok) throw new Error("Failed to send message");

            const data = await res.json();
            addMessage("assistant", data.message);

            // Check if setup is complete
            if (data.is_complete) {
                toast({
                    title: "Setup Complete",
                    description: "Transitioning to simulation...",
                });
                setTimeout(onComplete, 2000);
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

    return (
        <div className="flex flex-col h-[600px] max-w-4xl mx-auto bg-black/40 border border-cyan-500/30 rounded-lg overflow-hidden backdrop-blur-sm">
            {/* Header */}
            <div className="p-4 border-b border-cyan-500/30 bg-black/60 flex justify-between items-center">
                <div className="flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-cyan-400" />
                    <h3 className="font-mono text-cyan-100">NARRATIVE INITIALIZATION</h3>
                </div>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={onCancel}
                    className="text-cyan-400/60 hover:text-cyan-400"
                >
                    CANCEL
                </Button>
            </div>

            {/* Chat Area */}
            <ScrollArea className="flex-1 p-4" ref={scrollRef}>
                <div className="space-y-4">
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
                                        "max-w-[80%] p-3 rounded-lg font-mono text-sm leading-relaxed",
                                        msg.role === "user"
                                            ? "bg-cyan-500/20 border border-cyan-500/30 text-cyan-100"
                                            : "bg-black/60 border border-purple-500/30 text-purple-100"
                                    )}
                                >
                                    {msg.content}
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
                            <div className="bg-black/60 border border-purple-500/30 p-3 rounded-lg">
                                <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />
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
                    className="flex gap-2"
                >
                    <Input
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Describe your world or answer the prompt..."
                        className="bg-black/40 border-cyan-500/30 text-cyan-100 focus:border-cyan-400 font-mono"
                        disabled={isLoading}
                    />
                    <Button
                        type="submit"
                        disabled={isLoading || !input.trim()}
                        className="bg-cyan-500/20 border border-cyan-500/50 text-cyan-400 hover:bg-cyan-500/30"
                    >
                        <Send className="w-4 h-4" />
                    </Button>
                </form>
            </div>
        </div>
    );
}
