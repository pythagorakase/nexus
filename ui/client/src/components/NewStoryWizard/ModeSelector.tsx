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
                <h2 className="text-3xl font-mono text-cyan-400 tracking-wider glow-text">
                    INITIALIZATION PROTOCOL
                </h2>
                <p className="text-cyan-400/60 font-mono">
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
                        className="h-full p-6 bg-black/40 border-cyan-500/30 hover:border-cyan-400 cursor-pointer group transition-all duration-300 relative overflow-hidden"
                        onClick={() => onSelectMode("express")}
                    >
                        <div className="absolute inset-0 bg-cyan-500/5 opacity-0 group-hover:opacity-100 transition-opacity" />

                        <div className="relative z-10 flex flex-col h-full space-y-4">
                            <div className="flex items-center justify-between">
                                <div className="p-3 rounded-full bg-cyan-500/10 border border-cyan-500/30 group-hover:border-cyan-400 group-hover:shadow-[0_0_15px_rgba(6,182,212,0.3)] transition-all">
                                    <MessageSquare className="w-8 h-8 text-cyan-400" />
                                </div>
                                <div className="px-2 py-1 rounded bg-cyan-500/20 border border-cyan-500/30 text-xs font-mono text-cyan-300">
                                    RECOMMENDED
                                </div>
                            </div>

                            <div>
                                <h3 className="text-xl font-mono text-cyan-100 mb-2 group-hover:text-cyan-400 transition-colors">
                                    EXPRESS MODE
                                </h3>
                                <p className="text-sm text-cyan-400/60 font-mono leading-relaxed">
                                    Conversational initialization. Chat with the system to organically build your world, character, and story seed. Best for fluid, creative exploration.
                                </p>
                            </div>

                            <div className="mt-auto pt-4">
                                <ul className="space-y-2 text-xs font-mono text-cyan-400/50">
                                    <li className="flex items-center gap-2">
                                        <Zap className="w-3 h-3" /> Natural language interface
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <Zap className="w-3 h-3" /> Dynamic suggestions
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <Zap className="w-3 h-3" /> Rapid iteration
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
                        className="h-full p-6 bg-black/40 border-cyan-500/30 hover:border-purple-400 cursor-pointer group transition-all duration-300 relative overflow-hidden"
                        onClick={() => onSelectMode("advanced")}
                    >
                        <div className="absolute inset-0 bg-purple-500/5 opacity-0 group-hover:opacity-100 transition-opacity" />

                        <div className="relative z-10 flex flex-col h-full space-y-4">
                            <div className="flex items-center justify-between">
                                <div className="p-3 rounded-full bg-purple-500/10 border border-purple-500/30 group-hover:border-purple-400 group-hover:shadow-[0_0_15px_rgba(168,85,247,0.3)] transition-all">
                                    <Settings className="w-8 h-8 text-purple-400" />
                                </div>
                            </div>

                            <div>
                                <h3 className="text-xl font-mono text-purple-100 mb-2 group-hover:text-purple-400 transition-colors">
                                    ADVANCED MODE
                                </h3>
                                <p className="text-sm text-purple-400/60 font-mono leading-relaxed">
                                    Structured initialization. Manually configure every aspect of your simulation parameters using detailed forms. Best for specific, pre-planned scenarios.
                                </p>
                            </div>

                            <div className="mt-auto pt-4">
                                <ul className="space-y-2 text-xs font-mono text-purple-400/50">
                                    <li className="flex items-center gap-2">
                                        <FileText className="w-3 h-3" /> Granular control
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <FileText className="w-3 h-3" /> Parameter validation
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <FileText className="w-3 h-3" /> Direct input
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
