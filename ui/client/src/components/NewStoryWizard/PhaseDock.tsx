/**
 * PhaseDock - Vertical phase progress indicator for the wizard
 *
 * Displays three phases (Setting, Character, Seed) as a vertical dock
 * anchored to the right margin. AnimatedBeam connects phases and shows
 * the current trajectory. Clicking a completed phase opens the artifact drawer.
 */

import { useRef } from "react";
import { cn } from "@/lib/utils";
import { AnimatedBeam } from "@/components/ui/animated-beam";
import { Globe, User, Sparkles } from "lucide-react";

type Phase = "setting" | "character" | "seed";

interface PhaseDockProps {
  currentPhase: Phase;
  completedPhases: Set<Phase>;
  onPhaseClick: (phase: Phase) => void;
  className?: string;
}

const PHASE_CONFIG: { id: Phase; label: string; icon: typeof Globe }[] = [
  { id: "setting", label: "Setting", icon: Globe },
  { id: "character", label: "Character", icon: User },
  { id: "seed", label: "Seed", icon: Sparkles },
];

// Animation timing constants (in seconds)
const BEAM_DURATION = 8; // How long the gradient takes to traverse the beam
const PULSE_DURATION = 4; // Active phase indicator pulse cycle

export function PhaseDock({
  currentPhase,
  completedPhases,
  onPhaseClick,
  className,
}: PhaseDockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const phase1Ref = useRef<HTMLButtonElement>(null);
  const phase2Ref = useRef<HTMLButtonElement>(null);
  const phase3Ref = useRef<HTMLButtonElement>(null);

  const phaseRefs = [phase1Ref, phase2Ref, phase3Ref];

  const getPhaseIndex = (phase: Phase): number => {
    return PHASE_CONFIG.findIndex((p) => p.id === phase);
  };

  const currentPhaseIndex = getPhaseIndex(currentPhase);

  const isPhaseCompleted = (phase: Phase) => completedPhases.has(phase);
  const isPhaseActive = (phase: Phase) => phase === currentPhase;
  const isPhaseLocked = (phase: Phase) => {
    const idx = getPhaseIndex(phase);
    return idx > currentPhaseIndex && !isPhaseCompleted(phase);
  };

  const handleClick = (phase: Phase) => {
    // Only allow clicking completed phases
    if (isPhaseCompleted(phase)) {
      onPhaseClick(phase);
    }
  };

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative flex flex-col justify-between h-full py-4 px-2",
        className
      )}
    >
      {/* Animated beams connecting phases */}
      {/* Beam 1→2: animated when in phase 1 (working toward 2) */}
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={phase1Ref}
        toRef={phase2Ref}
        animated={currentPhaseIndex === 0}
        pathColor="hsl(var(--primary) / 0.3)"
        pathWidth={2}
        pathOpacity={0.4}
        gradientStartColor="hsl(var(--primary))"
        gradientStopColor="hsl(var(--primary) / 0.5)"
        duration={BEAM_DURATION}
        curvature={0}
        startYOffset={16}
        endYOffset={-16}
      />

      {/* Beam 2→3: animated when in phase 2 (working toward 3) */}
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={phase2Ref}
        toRef={phase3Ref}
        animated={currentPhaseIndex === 1}
        pathColor="hsl(var(--primary) / 0.3)"
        pathWidth={2}
        pathOpacity={0.4}
        gradientStartColor="hsl(var(--primary))"
        gradientStopColor="hsl(var(--primary) / 0.5)"
        duration={BEAM_DURATION}
        curvature={0}
        startYOffset={16}
        endYOffset={-16}
      />

      {/* Phase indicators */}
      {PHASE_CONFIG.map((phase, index) => {
        const Icon = phase.icon;
        const completed = isPhaseCompleted(phase.id);
        const active = isPhaseActive(phase.id);
        const locked = isPhaseLocked(phase.id);

        return (
          <button
            key={phase.id}
            ref={phaseRefs[index]}
            onClick={() => handleClick(phase.id)}
            disabled={locked}
            className={cn(
              "flex flex-col items-center gap-1 transition-all duration-200",
              "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded-lg p-2",
              completed && "cursor-pointer hover:scale-105",
              active && "scale-105",
              locked && "opacity-40 cursor-not-allowed"
            )}
            title={
              completed
                ? `View ${phase.label}`
                : active
                  ? `Current: ${phase.label}`
                  : phase.label
            }
          >
            {/* Phase circle */}
            <div
              className={cn(
                "relative w-10 h-10 rounded-full border-2 flex items-center justify-center transition-all duration-300",
                completed && "bg-primary border-primary text-primary-foreground",
                active && !completed && "border-primary bg-primary/20 text-primary",
                locked && "border-muted-foreground/30 bg-muted/20 text-muted-foreground/50"
              )}
              style={active && !completed ? {
                animation: `slow-pulse ${PULSE_DURATION}s ease-in-out infinite`
              } : undefined}
            >
              <Icon className="w-5 h-5" />

              {/* Completion checkmark overlay */}
              {completed && (
                <div className="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full flex items-center justify-center">
                  <svg
                    className="w-2.5 h-2.5 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={3}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              )}
            </div>

            {/* Phase label */}
            <span
              className={cn(
                "text-xs font-medium font-sans uppercase tracking-wide",
                completed && "text-primary",
                active && !completed && "text-primary",
                locked && "text-muted-foreground/50"
              )}
            >
              {phase.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
