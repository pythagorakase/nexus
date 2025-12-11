/**
 * TraitSelectorGrid - Trait selection/display component for the artifact drawer
 *
 * Two modes:
 * - select: Two columns of toggle buttons with indicator dots and tooltips
 * - display: Expandable list of selected traits with descriptions and rationales
 */

import { useState, useEffect, useCallback } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface TraitInfo {
  id: string;
  name: string;
  desc: string[];
  ex: string[];
}

interface TraitSelectorGridProps {
  mode: "select" | "display";
  suggestedTraits: string[];
  selectedTraits: string[];
  onSelectionChange?: (traits: string[]) => void;
  traitRationales?: Record<string, string>;
  maxTraits: number;
}

interface TooltipState {
  trait: TraitInfo | null;
  position: { x: number; y: number } | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const REQUIRED = 3;
const TOTAL_TRAITS = 10;

const TRAITS: Record<string, TraitInfo[]> = {
  "Social Network": [
    { id: "allies", name: "Allies", desc: ["will help you when it matters", "will take risks for you", "highly-aligned goals"], ex: ["family ties", "resistance cells", "fellow veteran"] },
    { id: "contacts", name: "Contacts", desc: ["can be tapped for information, favors, or access", "limited willingness to take risks for you", "relationship may be transactional or arms-length"], ex: ["bartender", "information broker", "journalist"] },
    { id: "patron", name: "Patron", desc: ["powerful figure who mentors, sponsors, protects, or guides you", "has own position to protect", "may have own agenda"], ex: ["noble patron", "archmage mentor", "Sith master"] },
    { id: "dependents", name: "Dependents", desc: ["very high willingness to do what you want", "lower status/power relative to you", "may be capable, but limited ability to act effectively without guidance"], ex: ["child", "employee", "subordinate"] },
  ],
  "Power & Position": [
    { id: "status", name: "Status", desc: ["formal standing", "recognized by specific institution or social structure"], ex: ["military officer commission", "guild journeyman", "corporate board seat"] },
    { id: "reputation", name: "Reputation", desc: ["how widely you're known, for better or worse", "may or may not confer influence"], ex: ["celebrity", "local legend", "pariah"] },
  ],
  "Assets & Territory": [
    { id: "resources", name: "Resources", desc: ["material wealth, equipment, supplies", "may represent access or availability rather than literal possession"], ex: ["liquid assets", "excellent credit", "harvest tithes from a village"] },
    { id: "domain", name: "Domain", desc: ["structure or area", "controlled or claimed by you"], ex: ["condominium", "uncontested turf", "wizard's tower"] },
  ],
  "Liabilities": [
    { id: "enemies", name: "Enemies", desc: ["actively opposed to you", "will expend energy and take risks to thwart you", "goals may be limited or unlimited"], ex: ["jealous colleague who wants to humiliate you", "kin of slain enemy sworn to mortal vengeance"] },
    { id: "obligations", name: "Obligations", desc: ["can be to individuals, groups, concepts", "may be static or dischargeable"], ex: ["retainer to a house", "on parole", "filial piety"] },
  ],
};

// Flat list for lookup
const ALL_TRAITS: TraitInfo[] = Object.values(TRAITS).flat();

function getTraitInfo(id: string): TraitInfo | undefined {
  return ALL_TRAITS.find(t => t.id === id);
}

// ─────────────────────────────────────────────────────────────────────────────
// Select Mode Components
// ─────────────────────────────────────────────────────────────────────────────

function IndicatorDots({ count }: { count: number }) {
  const isComplete = count === REQUIRED;
  const isOver = count > REQUIRED;

  return (
    <div className="flex justify-between w-full px-1">
      {[...Array(TOTAL_TRAITS)].map((_, i) => {
        const isFilled = i < count;

        let colorClasses = "bg-muted border-muted-foreground/30";
        let glowStyle = {};

        if (isComplete && isFilled) {
          colorClasses = "bg-emerald-500 border-transparent";
          glowStyle = { boxShadow: "0 0 8px rgba(16, 185, 129, 0.7), 0 0 16px rgba(16, 185, 129, 0.4)" };
        } else if (isFilled) {
          const color = isOver ? "accent" : "primary";
          colorClasses = `bg-${color} border-transparent`;
          glowStyle = isOver
            ? { boxShadow: "0 0 6px rgba(232, 106, 74, 0.6), 0 0 12px rgba(232, 106, 74, 0.3)" }
            : { boxShadow: "0 0 6px hsl(var(--primary) / 0.6), 0 0 12px hsl(var(--primary) / 0.3)" };
        }

        return (
          <div
            key={i}
            className={cn("w-2.5 h-2.5 rounded-full border transition-all duration-250", colorClasses)}
            style={glowStyle}
          />
        );
      })}
    </div>
  );
}

function Chip({ children, variant = "desc" }: { children: React.ReactNode; variant?: "desc" | "example" }) {
  const isExample = variant === "example";
  return (
    <span
      className={cn(
        "inline-block px-2 py-1 m-0.5 rounded-lg text-xs leading-snug border",
        isExample
          ? "bg-secondary text-muted-foreground border-border/60 italic"
          : "bg-primary/20 text-foreground border-primary/40"
      )}
    >
      {children}
    </span>
  );
}

function Tooltip({ trait, position }: TooltipState) {
  if (!trait || !position) return null;

  // Clamp vertical position to keep tooltip within viewport
  // tooltipHeight: estimated max height of tooltip content (desc chips + divider + example chips)
  // padding: minimum distance from viewport edges to prevent clipping
  const tooltipHeight = 160;
  const padding = 16;
  const maxTop = window.innerHeight - tooltipHeight - padding;
  const clampedTop = Math.max(padding, Math.min(position.y, maxTop));

  return (
    <div
      className="fixed max-w-[260px] p-3 rounded-md border border-primary/60 bg-background pointer-events-none z-[100]"
      style={{
        top: clampedTop,
        left: position.x,
        transform: "translateX(-100%)",
        boxShadow: "0 4px 24px rgba(0,0,0,0.6), 0 0 20px hsl(var(--primary) / 0.1)",
        textAlign: "right",
      }}
    >
      {/* Description chips */}
      <div className="mb-2">
        {trait.desc.map((d, i) => (
          <Chip key={i} variant="desc">{d}</Chip>
        ))}
      </div>

      {/* Divider */}
      <div className="h-px bg-border/50 my-2" />

      {/* Example chips */}
      <div>
        {trait.ex.map((e, i) => (
          <Chip key={i} variant="example">{e}</Chip>
        ))}
      </div>
    </div>
  );
}

interface TraitButtonProps {
  trait: TraitInfo;
  isSelected: boolean;
  isSuggested: boolean;
  onSelect: (id: string) => void;
  onHoverStart: (trait: TraitInfo, position: { x: number; y: number }) => void;
  onHoverEnd: () => void;
}

function TraitButton({ trait, isSelected, isSuggested, onSelect, onHoverStart, onHoverEnd }: TraitButtonProps) {
  const handleMouseEnter = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    // Tooltip appears to the left (flush against drawer border)
    onHoverStart(trait, { x: rect.left - 8, y: rect.top });
  }, [trait, onHoverStart]);

  return (
    <button
      onClick={() => onSelect(trait.id)}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={onHoverEnd}
      className={cn(
        "w-full h-9 font-mono text-sm tracking-wide rounded border",
        "flex items-center justify-center cursor-pointer transition-all duration-150",
        isSelected
          ? "bg-gradient-to-b from-muted/95 to-secondary/60 border-primary/80 text-foreground"
          : "bg-gradient-to-b from-primary/15 to-primary/5 border-border/50 text-muted-foreground hover:border-border",
        isSuggested && !isSelected && "ring-1 ring-primary/30"
      )}
      style={{
        boxShadow: isSelected
          ? "inset 0 1px 0 rgba(255,255,255,0.08), inset 0 -1px 0 rgba(0,0,0,0.25), 0 0 8px hsl(var(--primary) / 0.4)"
          : "inset 0 1px 0 hsl(var(--primary) / 0.1), inset 0 -1px 0 rgba(0,0,0,0.1)",
        textShadow: isSelected ? "0 0 6px hsl(var(--primary) / 0.6)" : "none",
      }}
    >
      {trait.name}
    </button>
  );
}

function SelectMode({
  suggestedTraits,
  selectedTraits,
  onSelectionChange,
}: {
  suggestedTraits: string[];
  selectedTraits: string[];
  onSelectionChange: (traits: string[]) => void;
}) {
  const [tooltip, setTooltip] = useState<TooltipState>({ trait: null, position: null });
  const selectedSet = new Set(selectedTraits);
  const suggestedSet = new Set(suggestedTraits);

  const toggle = useCallback((id: string) => {
    const next = new Set(selectedSet);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    onSelectionChange(Array.from(next));
  }, [selectedSet, onSelectionChange]);

  const showTooltip = useCallback((trait: TraitInfo, position: { x: number; y: number }) => {
    setTooltip({ trait, position });
  }, []);

  const hideTooltip = useCallback(() => {
    setTooltip({ trait: null, position: null });
  }, []);

  return (
    <div className="space-y-4">
      <Tooltip trait={tooltip.trait} position={tooltip.position} />

      {/* Trait grid by category */}
      {Object.entries(TRAITS).map(([category, traits]) => (
        <div key={category}>
          <h4 className="font-mono text-xs tracking-wide text-primary/80 mb-2 text-center uppercase">
            {category}
          </h4>
          <div className="grid grid-cols-2 gap-1.5">
            {traits.map((trait) => (
              <TraitButton
                key={trait.id}
                trait={trait}
                isSelected={selectedSet.has(trait.id)}
                isSuggested={suggestedSet.has(trait.id)}
                onSelect={toggle}
                onHoverStart={showTooltip}
                onHoverEnd={hideTooltip}
              />
            ))}
          </div>
        </div>
      ))}

      {/* Indicator dots */}
      <div className="pt-2">
        <IndicatorDots count={selectedTraits.length} />
        <p className="text-xs text-muted-foreground text-center mt-2">
          Select {REQUIRED} traits (currently {selectedTraits.length})
        </p>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Display Mode Components
// ─────────────────────────────────────────────────────────────────────────────

function TraitDisplay({
  traitId,
  rationale,
}: {
  traitId: string;
  rationale?: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const trait = getTraitInfo(traitId);

  if (!trait) {
    return (
      <div className="bg-primary/5 border border-primary/20 p-2 rounded">
        <span className="text-primary text-sm capitalize">{traitId}</span>
      </div>
    );
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="bg-primary/5 border border-primary/20 rounded overflow-hidden">
        <CollapsibleTrigger asChild>
          <button className="w-full flex items-center justify-between p-2 hover:bg-primary/10 transition-colors">
            <span className="text-primary text-sm font-medium capitalize">{trait.name}</span>
            <ChevronDown
              className={cn(
                "w-4 h-4 text-primary/60 transition-transform duration-200",
                isOpen && "rotate-180"
              )}
            />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="p-3 pt-0 space-y-3 border-t border-primary/10">
            {/* Trait description */}
            <div>
              <span className="text-primary/60 text-xs uppercase block mb-1">Description</span>
              <div className="flex flex-wrap gap-1">
                {trait.desc.map((d, i) => (
                  <Chip key={i} variant="desc">{d}</Chip>
                ))}
              </div>
            </div>

            {/* Examples */}
            <div>
              <span className="text-primary/60 text-xs uppercase block mb-1">Examples</span>
              <div className="flex flex-wrap gap-1">
                {trait.ex.map((e, i) => (
                  <Chip key={i} variant="example">{e}</Chip>
                ))}
              </div>
            </div>

            {/* Rationale (if available) */}
            {rationale && (
              <div>
                <span className="text-primary/60 text-xs uppercase block mb-1">Why this trait?</span>
                <p className="text-sm text-white/80 font-narrative italic">{rationale}</p>
              </div>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

function DisplayMode({
  selectedTraits,
  traitRationales,
}: {
  selectedTraits: string[];
  traitRationales?: Record<string, string>;
}) {
  if (selectedTraits.length === 0) {
    return (
      <p className="text-muted-foreground text-sm italic">No traits selected.</p>
    );
  }

  return (
    <div className="space-y-2">
      <h4 className="font-mono text-xs tracking-wide text-primary/80 uppercase mb-3">
        Selected Traits ({selectedTraits.length})
      </h4>
      {selectedTraits.map((traitId) => (
        <TraitDisplay
          key={traitId}
          traitId={traitId}
          rationale={traitRationales?.[traitId]}
        />
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────

export function TraitSelectorGrid({
  mode,
  suggestedTraits,
  selectedTraits,
  onSelectionChange,
  traitRationales,
  maxTraits,
}: TraitSelectorGridProps) {
  // Initialize selection from suggested traits when switching to select mode
  const [internalSelection, setInternalSelection] = useState<string[]>(
    selectedTraits.length > 0 ? selectedTraits : suggestedTraits
  );

  // Sync with prop changes
  useEffect(() => {
    if (selectedTraits.length > 0) {
      setInternalSelection(selectedTraits);
    } else if (suggestedTraits.length > 0 && mode === "select") {
      setInternalSelection(suggestedTraits);
    }
  }, [selectedTraits, suggestedTraits, mode]);

  const handleSelectionChange = useCallback((traits: string[]) => {
    setInternalSelection(traits);
    onSelectionChange?.(traits);
  }, [onSelectionChange]);

  if (mode === "display") {
    return (
      <DisplayMode
        selectedTraits={selectedTraits}
        traitRationales={traitRationales}
      />
    );
  }

  return (
    <SelectMode
      suggestedTraits={suggestedTraits}
      selectedTraits={internalSelection}
      onSelectionChange={handleSelectionChange}
    />
  );
}
