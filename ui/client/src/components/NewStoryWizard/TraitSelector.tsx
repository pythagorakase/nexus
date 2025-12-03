import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";

interface TraitInfo {
    name: string;
    description: string[];
    examples: string[];
}

interface TraitSelectorProps {
    onConfirm: (selected: string[]) => void;
    onInvalidConfirm?: (selected: string[], count: number) => void;
    disabled?: boolean;
    suggestedTraits?: string[]; // LLM's pre-selected recommendations
}

// Exactly 3 traits required
const REQUIRED_TRAIT_COUNT = 3;

// Canonical trait data baked from traits.json
const TRAIT_DATA: Record<string, Record<string, TraitInfo>> = {
    "Social Network": {
        allies: {
            name: "Allies",
            description: [
                "will help you when it matters",
                "will take risks for you",
                "highly-aligned goals",
            ],
            examples: ["family ties", "resistance cells", "fellow veteran"],
        },
        contacts: {
            name: "Contacts",
            description: [
                "can be tapped for information, favors, or access",
                "limited willingness to take risks for you",
                "relationship may be transactional or arms-length",
            ],
            examples: ["bartender", "information broker", "journalist"],
        },
        patron: {
            name: "Patron",
            description: [
                "powerful figure who mentors, sponsors, protects, or guides you",
                "has own position to protect",
                "may have own agenda",
            ],
            examples: ["noble patron", "archmage mentor", "Sith master"],
        },
        dependents: {
            name: "Dependents",
            description: [
                "very high willingness to do what you want",
                "lower status/power relative to you",
                "may be capable, but limited ability to act effectively without guidance",
            ],
            examples: ["child", "employee", "subordinate"],
        },
    },
    "Power & Position": {
        status: {
            name: "Status",
            description: [
                "formal standing",
                "recognized by specific institution or social structure",
            ],
            examples: [
                "military officer commission",
                "guild journeyman",
                "corporate board seat",
            ],
        },
        reputation: {
            name: "Reputation",
            description: [
                "how widely you're known, for better or worse",
                "may or may not confer influence",
            ],
            examples: ["celebrity", "local legend", "pariah"],
        },
    },
    "Assets & Territory": {
        resources: {
            name: "Resources",
            description: [
                "material wealth, equipment, supplies",
                "may represent access or availability rather than literal possession",
            ],
            examples: [
                "liquid assets",
                "excellent credit",
                "harvest tithes from a village",
            ],
        },
        domain: {
            name: "Domain",
            description: ["structure or area", "controlled or claimed by you"],
            examples: ["condominium", "uncontested turf", "wizard's tower"],
        },
    },
    Liabilities: {
        enemies: {
            name: "Enemies",
            description: [
                "actively opposed to you",
                "will expend energy and take risks to thwart you",
                "goals may be limited or unlimited",
            ],
            examples: [
                "jealous colleague who wants to humiliate you",
                "kin of slain enemy sworn to mortal vengeance",
            ],
        },
        obligations: {
            name: "Obligations",
            description: [
                "can be to individuals, groups, concepts",
                "may be static or dischargeable",
            ],
            examples: ["retainer to a house", "on parole", "filial piety"],
        },
    },
};

type TraitName = string;

export function TraitSelector({
    onConfirm,
    onInvalidConfirm,
    disabled = false,
    suggestedTraits = [],
}: TraitSelectorProps) {
    const [selected, setSelected] = useState<Set<TraitName>>(
        () => new Set(suggestedTraits)
    );
    const [hoveredTrait, setHoveredTrait] = useState<TraitName | null>(null);

    // Sync selection when suggestedTraits prop changes (component may already be mounted)
    useEffect(() => {
        setSelected(new Set(suggestedTraits));
    }, [suggestedTraits]);

    const toggleTrait = (trait: TraitName) => {
        if (disabled) return;

        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(trait)) {
                next.delete(trait);
            } else {
                // Allow selecting beyond 3 so user can adjust, but warn visually
                next.add(trait);
            }
            return next;
        });
    };

    const isExactlyThree = selected.size === REQUIRED_TRAIT_COUNT;

    const handleConfirm = () => {
        if (isExactlyThree) {
            onConfirm(Array.from(selected));
        } else if (onInvalidConfirm) {
            // Send to LLM for dialog - UI stays open
            onInvalidConfirm(Array.from(selected), selected.size);
        }
    };

    // Get trait info by key
    const getTraitInfo = (traitKey: string): TraitInfo | null => {
        for (const category of Object.values(TRAIT_DATA)) {
            if (traitKey in category) {
                return category[traitKey];
            }
        }
        return null;
    };

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="border-b border-primary/30 pb-3 mb-4">
                <h3 className="font-mono text-primary text-sm uppercase tracking-wider">
                    Trait Selection ({selected.size}/{REQUIRED_TRAIT_COUNT})
                </h3>
                <p className="text-xs text-muted-foreground mt-1">
                    Select exactly {REQUIRED_TRAIT_COUNT} traits
                </p>
            </div>

            {/* Categories */}
            <div className="flex-1 space-y-4 overflow-y-auto">
                {Object.entries(TRAIT_DATA).map(([category, traits]) => (
                    <div key={category}>
                        <h4 className="font-mono text-xs text-primary/80 uppercase tracking-wider mb-2">
                            {category}
                        </h4>
                        <div className="space-y-1">
                            {Object.entries(traits).map(([traitKey, traitInfo]) => {
                                const isSelected = selected.has(traitKey);
                                const isSuggested = suggestedTraits.includes(traitKey);
                                const isHovered = hoveredTrait === traitKey;
                                const showDetails = isSelected || isHovered;

                                return (
                                    <div key={traitKey} className="relative">
                                        <button
                                            type="button"
                                            onClick={() => toggleTrait(traitKey)}
                                            onMouseEnter={() => setHoveredTrait(traitKey)}
                                            onMouseLeave={() => setHoveredTrait(null)}
                                            disabled={disabled}
                                            className={cn(
                                                "w-full flex items-center justify-between px-3 py-2 rounded text-left transition-colors",
                                                "border font-mono text-sm",
                                                isSelected
                                                    ? "bg-primary/20 border-primary text-primary"
                                                    : isSuggested
                                                      ? "bg-amber-500/10 border-amber-500/40 text-foreground/90 hover:border-amber-500/60"
                                                      : "bg-background/40 border-primary/20 text-foreground/80 hover:border-primary/40",
                                                disabled && "opacity-50 cursor-not-allowed"
                                            )}
                                        >
                                            <span className="flex items-center gap-2">
                                                <span
                                                    className={cn(
                                                        "w-4 h-4 border rounded-sm flex items-center justify-center",
                                                        isSelected
                                                            ? "border-primary bg-primary"
                                                            : "border-primary/40"
                                                    )}
                                                >
                                                    {isSelected && (
                                                        <svg
                                                            className="w-3 h-3 text-background"
                                                            fill="none"
                                                            stroke="currentColor"
                                                            viewBox="0 0 24 24"
                                                        >
                                                            <path
                                                                strokeLinecap="round"
                                                                strokeLinejoin="round"
                                                                strokeWidth={3}
                                                                d="M5 13l4 4L19 7"
                                                            />
                                                        </svg>
                                                    )}
                                                </span>
                                                <span className="capitalize">{traitInfo.name}</span>
                                                {isSuggested && !isSelected && (
                                                    <span className="text-[10px] uppercase tracking-wider text-amber-500/80 ml-1">
                                                        suggested
                                                    </span>
                                                )}
                                            </span>
                                            {isSelected && (
                                                <span className="text-xs uppercase tracking-wider text-primary/80">
                                                    Selected
                                                </span>
                                            )}
                                        </button>

                                        {/* Progressive Disclosure - Details on hover/select */}
                                        <AnimatePresence>
                                            {showDetails && (
                                                <motion.div
                                                    initial={{ opacity: 0, height: 0 }}
                                                    animate={{ opacity: 1, height: "auto" }}
                                                    exit={{ opacity: 0, height: 0 }}
                                                    transition={{ duration: 0.15 }}
                                                    className="overflow-hidden"
                                                >
                                                    <div className="px-3 py-2 ml-6 text-xs text-muted-foreground border-l border-primary/20">
                                                        <ul className="list-disc list-inside space-y-0.5">
                                                            {traitInfo.description.map((desc, i) => (
                                                                <li key={i}>{desc}</li>
                                                            ))}
                                                        </ul>
                                                        <div className="mt-1.5 text-primary/60 italic">
                                                            e.g., {traitInfo.examples.join(", ")}
                                                        </div>
                                                    </div>
                                                </motion.div>
                                            )}
                                        </AnimatePresence>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </div>

            {/* Traits Selected Summary Panel */}
            <AnimatePresence>
                {selected.size > 0 && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                    >
                        <div className="pt-3 mt-3 border-t border-primary/20">
                            <h4 className="font-mono text-xs text-primary/80 uppercase tracking-wider mb-2">
                                Selected Traits
                            </h4>
                            <div className="space-y-2 max-h-32 overflow-y-auto">
                                <AnimatePresence mode="popLayout">
                                    {Array.from(selected).map((traitKey) => {
                                        const info = getTraitInfo(traitKey);
                                        if (!info) return null;
                                        return (
                                            <motion.div
                                                key={traitKey}
                                                initial={{ opacity: 0, x: -10 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                exit={{ opacity: 0, x: 10 }}
                                                layout
                                                className="bg-primary/10 rounded px-2 py-1.5 text-xs"
                                            >
                                                <div className="font-mono text-primary capitalize">
                                                    {info.name}
                                                </div>
                                                <div className="text-muted-foreground mt-0.5">
                                                    {info.description[0]}
                                                </div>
                                            </motion.div>
                                        );
                                    })}
                                </AnimatePresence>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Selection Status Warning */}
            {selected.size > 0 && selected.size !== REQUIRED_TRAIT_COUNT && (
                <div className="mt-2 text-xs text-amber-500/80 font-mono">
                    {selected.size < REQUIRED_TRAIT_COUNT
                        ? `Select ${REQUIRED_TRAIT_COUNT - selected.size} more trait${REQUIRED_TRAIT_COUNT - selected.size > 1 ? "s" : ""}`
                        : `Remove ${selected.size - REQUIRED_TRAIT_COUNT} trait${selected.size - REQUIRED_TRAIT_COUNT > 1 ? "s" : ""}`}
                </div>
            )}

            {/* Confirm Button */}
            <div className="pt-4 mt-4 border-t border-primary/30">
                <Button
                    onClick={handleConfirm}
                    disabled={disabled || selected.size === 0}
                    className={cn(
                        "w-full border font-mono uppercase tracking-wider transition-colors",
                        isExactlyThree
                            ? "bg-emerald-600 border-emerald-500 text-white hover:bg-emerald-700"
                            : "bg-primary/20 border-primary/40 text-primary/80 hover:bg-primary/30"
                    )}
                >
                    CONFIRM
                </Button>
                {!isExactlyThree && selected.size > 0 && onInvalidConfirm && (
                    <p className="text-[10px] text-muted-foreground text-center mt-1">
                        Click to discuss selection with Skald
                    </p>
                )}
            </div>
        </div>
    );
}
