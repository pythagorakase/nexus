import React from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MessageSquare, FileText, Zap, Settings } from "lucide-react";
import { motion } from "framer-motion";

interface ModeSelectorProps {
    onSelectMode: (mode: "express" | "advanced") => void;
}

export function ModeSelector({ onSelectMode }: ModeSelectorProps) {
    return (
        <div className="max-w-4xl mx-auto space-y-8 p-6">
            <div className="text-center space-y-4">
                <h2 className="text-3xl font-mono text-primary tracking-wider glow-text">
                    INITIALIZATION PROTOCOL
                </h2>
                <p className="text-muted-foreground font-mono">
                    Select your preferred narrative initialization method.
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Express Mode Card */}
                <motion.div
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                >
                    <Card
                        className="h-full p-6 bg-card border-primary/30 hover:border-primary cursor-pointer group transition-all duration-300 relative overflow-hidden"
                        onClick={() => onSelectMode("express")}
                    >
                        <div className="absolute inset-0 bg-primary/5 opacity-0 group-hover:opacity-100 transition-opacity" />

                        <div className="relative z-10 flex flex-col h-full space-y-4">
                            <div className="flex items-center justify-between">
                                <div className="p-3 rounded-full bg-primary/10 border border-primary/30 group-hover:border-primary group-hover:shadow-[0_0_15px_rgba(var(--primary),0.3)] transition-all">
                                    <MessageSquare className="w-8 h-8 text-primary" />
                                </div>
                                <div className="px-2 py-1 rounded bg-primary/20 border border-primary/30 text-xs font-mono text-primary">
                                    RECOMMENDED
                                </div>
                            </div>

                            <div>
                                <h3 className="text-xl font-mono text-foreground mb-2 group-hover:text-primary transition-colors">
                                    EXPRESS MODE
                                </h3>
                                <p className="text-sm text-muted-foreground font-mono leading-relaxed">
                                    Conversational initialization. Chat with the system to organically build your world, character, and story seed. Best for fluid, creative exploration.
                                </p>
                            </div>

                            <div className="mt-auto pt-4">
                                <ul className="space-y-2 text-xs font-mono text-muted-foreground">
                                    <li className="flex items-center gap-2">
                                        <Zap className="w-3 h-3 text-primary" /> Natural language interface
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <Zap className="w-3 h-3 text-primary" /> Dynamic suggestions
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <Zap className="w-3 h-3 text-primary" /> Rapid iteration
                                    </li>
                                </ul>
                            </div>
                        </div>
                    </Card>
                </motion.div>

                {/* Advanced Mode Card */}
                <motion.div
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                >
                    <Card
                        className="h-full p-6 bg-card border-primary/30 hover:border-accent cursor-pointer group transition-all duration-300 relative overflow-hidden"
                        onClick={() => onSelectMode("advanced")}
                    >
                        <div className="absolute inset-0 bg-accent/5 opacity-0 group-hover:opacity-100 transition-opacity" />

                        <div className="relative z-10 flex flex-col h-full space-y-4">
                            <div className="flex items-center justify-between">
                                <div className="p-3 rounded-full bg-accent/10 border border-accent/30 group-hover:border-accent group-hover:shadow-[0_0_15px_rgba(var(--accent),0.3)] transition-all">
                                    <Settings className="w-8 h-8 text-accent" />
                                </div>
                            </div>

                            <div>
                                <h3 className="text-xl font-mono text-foreground mb-2 group-hover:text-accent transition-colors">
                                    ADVANCED MODE
                                </h3>
                                <p className="text-sm text-muted-foreground font-mono leading-relaxed">
                                    Structured initialization. Manually configure every aspect of your simulation parameters using detailed forms. Best for specific, pre-planned scenarios.
                                </p>
                            </div>

                            <div className="mt-auto pt-4">
                                <ul className="space-y-2 text-xs font-mono text-muted-foreground">
                                    <li className="flex items-center gap-2">
                                        <FileText className="w-3 h-3 text-accent" /> Granular control
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <FileText className="w-3 h-3 text-accent" /> Parameter validation
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <FileText className="w-3 h-3 text-accent" /> Direct input
                                    </li>
                                </ul>
                            </div>
                        </div>
                    </Card>
                </motion.div>
            </div>
        </div>
    );
}
