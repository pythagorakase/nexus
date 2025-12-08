import { useState, useEffect, useCallback } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface TraitInfo {
  id: string;
  name: string;
  desc: string[];
  ex: string[];
}

interface TraitSelectorProps {
  onConfirm: (selected: string[]) => void;
  onInvalidConfirm?: (selected: string[], count: number) => void;
  disabled?: boolean;
  suggestedTraits?: string[]; // Used for initial selection state only
}

interface TooltipState {
  trait: TraitInfo | null;
  position: { x: number; y: number } | null;
  side: "left" | "right";
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

// ─────────────────────────────────────────────────────────────────────────────
// Internal Components
// ─────────────────────────────────────────────────────────────────────────────

function IndicatorLights({ count }: { count: number }) {
  const isComplete = count === REQUIRED;
  const isOver = count > REQUIRED;

  return (
    <div className="flex justify-between w-full">
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
        "inline-block px-3 py-1.5 m-0.5 rounded-xl text-[13px] leading-snug border",
        isExample
          ? "bg-secondary text-muted-foreground border-border/60 italic"
          : "bg-primary/20 text-foreground border-primary/40"
      )}
    >
      {children}
    </span>
  );
}

function Tooltip({ trait, position, side }: TooltipState) {
  if (!trait || !position) return null;

  const isLeft = side === "left";

  // Clamp vertical position to stay within viewport (with padding)
  const tooltipHeight = 180; // Approximate max height
  const padding = 16;
  const maxTop = window.innerHeight - tooltipHeight - padding;
  const clampedTop = Math.max(padding, Math.min(position.y, maxTop));

  // Build style object with transform-based positioning for cleaner alignment
  const style: React.CSSProperties = {
    top: clampedTop,
    boxShadow: "0 4px 24px rgba(0,0,0,0.6), 0 0 20px hsl(var(--primary) / 0.1)",
    textAlign: isLeft ? "right" : "left",
    position: "fixed",
    zIndex: 1000,
  };

  if (isLeft) {
    style.left = position.x;
    style.transform = "translateX(-100%)";
  } else {
    style.left = position.x;
  }

  return (
    <div
      className="max-w-[280px] p-3 rounded-md border border-primary/60 bg-background pointer-events-none"
      style={style}
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

interface TraitCardProps {
  trait: TraitInfo;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onHoverStart: (trait: TraitInfo, position: { x: number; y: number }, side: "left" | "right") => void;
  onHoverEnd: () => void;
  column: number;
  disabled?: boolean;
}

function TraitCard({ trait, isSelected, onSelect, onHoverStart, onHoverEnd, column, disabled }: TraitCardProps) {
  const handleMouseEnter = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    // Always show tooltip on left since panel is on right side of screen
    const x = rect.left - 10;
    onHoverStart(trait, { x, y: rect.top }, "left");
  }, [trait, onHoverStart]);

  return (
    <button
      onClick={() => !disabled && onSelect(trait.id)}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={onHoverEnd}
      disabled={disabled}
      className={cn(
        "w-[110px] h-9 font-mono font-normal text-sm tracking-wide rounded border",
        "flex items-center justify-center cursor-pointer transition-all duration-150",
        "small-caps",
        isSelected
          ? "bg-gradient-to-b from-muted/95 to-secondary/60 border-primary/80 text-foreground"
          : "bg-gradient-to-b from-primary/15 to-primary/5 border-border/50 text-muted-foreground hover:border-border",
        disabled && "opacity-50 cursor-not-allowed"
      )}
      style={{
        boxShadow: isSelected
          ? "inset 0 1px 0 rgba(255,255,255,0.08), inset 0 -1px 0 rgba(0,0,0,0.25), 0 0 8px hsl(var(--primary) / 0.4), 0 1px 3px rgba(0,0,0,0.3)"
          : "inset 0 1px 0 hsl(var(--primary) / 0.1), inset 0 -1px 0 rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.1)",
        textShadow: isSelected ? "0 0 6px hsl(var(--primary) / 0.6)" : "none",
      }}
    >
      {trait.name}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────

export function TraitSelector({
  onConfirm,
  onInvalidConfirm,
  disabled = false,
  suggestedTraits = [],
}: TraitSelectorProps) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set(suggestedTraits));
  const [tooltip, setTooltip] = useState<TooltipState>({ trait: null, position: null, side: "right" });

  // Sync selection when suggestedTraits prop changes
  useEffect(() => {
    setSelected(new Set(suggestedTraits));
  }, [suggestedTraits]);

  const count = selected.size;
  const isComplete = count === REQUIRED;

  const toggle = useCallback((id: string) => {
    if (disabled) return;
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, [disabled]);

  const showTooltip = useCallback((trait: TraitInfo, position: { x: number; y: number }, side: "left" | "right") => {
    setTooltip({ trait, position, side });
  }, []);

  const hideTooltip = useCallback(() => {
    setTooltip({ trait: null, position: null, side: "right" });
  }, []);

  const handleConfirm = useCallback(() => {
    if (isComplete) {
      onConfirm(Array.from(selected));
    } else if (onInvalidConfirm) {
      onInvalidConfirm(Array.from(selected), selected.size);
    }
  }, [isComplete, onConfirm, onInvalidConfirm, selected]);

  return (
    <div className="flex flex-col items-center py-2 font-serif">
      <Tooltip trait={tooltip.trait} position={tooltip.position} side={tooltip.side} />

      {/* Header */}
      <h2 className="font-mono font-normal text-xl tracking-widest text-teal-400 mb-4 text-center small-caps"
        style={{ textShadow: "0 0 20px rgba(45, 212, 191, 0.4)" }}
      >
        Trait Selection
      </h2>

      {/* Trait grid */}
      {Object.entries(TRAITS).map(([category, traits]) => (
        <div key={category} className="mb-2.5 w-[226px]">
          <h3 className="font-mono font-normal text-base tracking-wide text-primary/80 mb-2 text-center small-caps">
            {category}
          </h3>
          <div className="grid grid-cols-2 gap-1.5 justify-center">
            {traits.map((trait, idx) => (
              <TraitCard
                key={trait.id}
                trait={trait}
                isSelected={selected.has(trait.id)}
                onSelect={toggle}
                onHoverStart={showTooltip}
                onHoverEnd={hideTooltip}
                column={idx % 2}
                disabled={disabled}
              />
            ))}
          </div>
        </div>
      ))}

      {/* Indicator lights */}
      <div className="py-3 w-[226px]">
        <IndicatorLights count={count} />
      </div>

      {/* Confirm button - shows spinner when disabled after valid selection */}
      <button
        onClick={handleConfirm}
        disabled={disabled || count === 0}
        className={cn(
          "w-[226px] py-2.5 rounded font-mono font-normal text-sm tracking-[0.2em] small-caps",
          "border cursor-pointer transition-all duration-300",
          "flex items-center justify-center gap-2",
          isComplete && !disabled
            ? "bg-gradient-to-b from-emerald-500/95 via-emerald-500/60 to-emerald-500/75 text-background border-emerald-500/90"
            : "bg-gradient-to-b from-secondary/95 via-muted/80 to-secondary/90 text-muted-foreground border-border/50",
          (disabled || count === 0) && "opacity-70 cursor-not-allowed"
        )}
        style={{
          borderTopColor: isComplete && !disabled ? "rgba(16, 185, 129, 0.8)" : "rgba(166, 138, 106, 0.3)",
          borderBottomColor: isComplete && !disabled ? "rgba(16, 185, 129, 0.6)" : "rgba(0, 0, 0, 0.3)",
          boxShadow: isComplete && !disabled
            ? "inset 0 1px 0 rgba(255,255,255,0.25), inset 0 -1px 2px rgba(0,0,0,0.15), 0 0 16px rgba(16, 185, 129, 0.5), 0 2px 4px rgba(0,0,0,0.3)"
            : "inset 0 1px 0 rgba(255,255,255,0.06), inset 0 -1px 2px rgba(0,0,0,0.2), 0 2px 4px rgba(0,0,0,0.25)",
        }}
      >
        {disabled && isComplete ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>Confirming...</span>
          </>
        ) : (
          "Confirm"
        )}
      </button>

      {/* Helper text for invalid confirm */}
      {!isComplete && count > 0 && onInvalidConfirm && (
        <p className="text-[10px] text-muted-foreground text-center mt-1.5">
          Click to discuss selection with Skald
        </p>
      )}
    </div>
  );
}
