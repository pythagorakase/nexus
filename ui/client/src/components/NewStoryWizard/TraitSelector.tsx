import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface TraitSelectorProps {
    onConfirm: (selected: string[]) => void;
    disabled?: boolean;
}

// P3: Extract magic numbers as named constants
const MIN_TRAIT_SELECTION = 1;
const MAX_TRAIT_SELECTION = 5;

const TRAIT_CATEGORIES = {
    "Social Network": ["allies", "contacts", "patron", "dependents"],
    "Power & Position": ["status", "reputation"],
    "Assets & Territory": ["resources", "domain"],
    "Liabilities": ["enemies", "obligations"],
} as const;

type TraitName = typeof TRAIT_CATEGORIES[keyof typeof TRAIT_CATEGORIES][number];

export function TraitSelector({ onConfirm, disabled = false }: TraitSelectorProps) {
    const [selected, setSelected] = useState<Set<TraitName>>(new Set());

    const toggleTrait = (trait: TraitName) => {
        if (disabled) return;

        setSelected(prev => {
            const next = new Set(prev);
            if (next.has(trait)) {
                next.delete(trait);
            } else if (next.size < MAX_TRAIT_SELECTION) {
                next.add(trait);
            }
            return next;
        });
    };

    const canConfirm = selected.size >= MIN_TRAIT_SELECTION && selected.size <= MAX_TRAIT_SELECTION;

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="border-b border-primary/30 pb-3 mb-4">
                <h3 className="font-mono text-primary text-sm uppercase tracking-wider">
                    Trait Selection ({selected.size}/{MAX_TRAIT_SELECTION})
                </h3>
                <p className="text-xs text-muted-foreground mt-1">
                    Select {MIN_TRAIT_SELECTION}-{MAX_TRAIT_SELECTION} traits
                </p>
            </div>

            {/* Categories */}
            <div className="flex-1 space-y-4 overflow-y-auto">
                {Object.entries(TRAIT_CATEGORIES).map(([category, traits]) => (
                    <div key={category}>
                        <h4 className="font-mono text-xs text-primary/80 uppercase tracking-wider mb-2">
                            {category}
                        </h4>
                        <div className="space-y-1">
                            {traits.map((trait) => {
                                const isSelected = selected.has(trait);
                                const isDisabled = disabled || (!isSelected && selected.size >= MAX_TRAIT_SELECTION);

                                return (
                                    <button
                                        key={trait}
                                        type="button"
                                        onClick={() => toggleTrait(trait)}
                                        disabled={isDisabled}
                                        className={cn(
                                            "w-full flex items-center justify-between px-3 py-2 rounded text-left transition-colors",
                                            "border font-mono text-sm",
                                            isSelected
                                                ? "bg-primary/20 border-primary text-primary"
                                                : "bg-background/40 border-primary/20 text-foreground/80 hover:border-primary/40",
                                            isDisabled && !isSelected && "opacity-50 cursor-not-allowed"
                                        )}
                                    >
                                        <span className="flex items-center gap-2">
                                            <span className={cn(
                                                "w-4 h-4 border rounded-sm flex items-center justify-center",
                                                isSelected ? "border-primary bg-primary" : "border-primary/40"
                                            )}>
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
                                            {trait}
                                        </span>
                                        {isSelected && (
                                            <span className="text-xs uppercase tracking-wider text-primary/80">
                                                Selected
                                            </span>
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </div>

            {/* Confirm Button */}
            <div className="pt-4 mt-4 border-t border-primary/30">
                <Button
                    onClick={() => onConfirm(Array.from(selected))}
                    disabled={!canConfirm || disabled}
                    className="w-full bg-primary/20 border border-primary text-primary hover:bg-primary/30 font-mono uppercase tracking-wider"
                >
                    Confirm Traits
                </Button>
            </div>
        </div>
    );
}
