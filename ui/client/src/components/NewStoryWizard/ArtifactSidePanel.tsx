/**
 * ArtifactSidePanel - Right-side resizable panel for wizard artifacts
 *
 * Uses react-resizable-panels for true drag-to-resize:
 * - Collapsed: Shows phase icons (Setting → Character → Seed) centered with AnimatedBeam
 * - Expanded: Shows full artifact accordion with confirm/revise actions
 */

import { useRef, useState, useEffect } from "react";
import {
  Globe,
  User,
  Sparkles,
  ChevronRight,
  ChevronLeft,
  Lock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { AnimatedBeam } from "@/components/ui/animated-beam";

// ─────────────────────────────────────────────────────────────────────────────
// Type Definitions
// ─────────────────────────────────────────────────────────────────────────────

type Phase = "setting" | "character" | "seed";

interface SettingData {
  world_name?: string;
  genre?: string;
  secondary_genres?: string[];
  time_period?: string;
  tone?: string;
  tech_level?: string;
  political_structure?: string;
  major_conflict?: string;
  themes?: string[];
  cultural_notes?: string;
}

interface CharacterConcept {
  name: string;
  archetype: string;
  background?: string;
  suggested_traits?: string[];
  trait_rationales?: Record<string, string>;
}

interface TraitSelection {
  selected_traits: string[];
  trait_rationales?: Record<string, string>;
}

interface WildcardTrait {
  name: string;
  description: string;
  mechanical_effect?: string;
}

interface CharacterInProgress {
  concept?: CharacterConcept;
  trait_selection?: TraitSelection;
  wildcard?: WildcardTrait;
}

interface CharacterComplete {
  name: string;
  archetype: string;
  summary: string;
  background?: string;
  traits?: string[];
  trait_rationales?: Record<string, string>;
  wildcard_name?: string;
  wildcard_description?: string;
  wildcard_effect?: string;
}

interface SeedData {
  seed?: {
    title?: string;
    hook?: string;
  };
  layer?: {
    name?: string;
  };
  zone?: {
    name?: string;
  };
  location?: {
    name?: string;
    summary?: string;
  };
}

function isCharacterComplete(
  data: CharacterInProgress | CharacterComplete | null | undefined
): data is CharacterComplete {
  return Boolean(data && "summary" in data && data.summary);
}

function getCharacterView(
  data: CharacterInProgress | CharacterComplete | null | undefined
): {
  concept: CharacterConcept | null;
  traitSelection: TraitSelection | null;
  wildcard: WildcardTrait | null;
  isComplete: boolean;
  completeSheet: CharacterComplete | null;
} {
  if (!data) {
    return {
      concept: null,
      traitSelection: null,
      wildcard: null,
      isComplete: false,
      completeSheet: null,
    };
  }

  if (isCharacterComplete(data)) {
    return {
      concept: {
        name: data.name,
        archetype: data.archetype,
        background: data.background,
      },
      traitSelection: data.traits
        ? { selected_traits: data.traits, trait_rationales: data.trait_rationales }
        : null,
      wildcard: data.wildcard_name
        ? {
            name: data.wildcard_name,
            description: data.wildcard_description || "",
            mechanical_effect: data.wildcard_effect,
          }
        : null,
      isComplete: true,
      completeSheet: data,
    };
  }

  const inProgress = data as CharacterInProgress;
  return {
    concept: inProgress.concept || null,
    traitSelection: inProgress.trait_selection || null,
    wildcard: inProgress.wildcard || null,
    isComplete: false,
    completeSheet: null,
  };
}

interface WizardData {
  setting?: SettingData;
  character?: CharacterComplete;
  character_state?: CharacterInProgress;
  seed?: SeedData;
}

interface Artifact {
  type: string;
  data:
    | SettingData
    | CharacterConcept
    | TraitSelection
    | WildcardTrait
    | CharacterComplete
    | SeedData;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component Props
// ─────────────────────────────────────────────────────────────────────────────

interface ArtifactSidePanelProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  mode: "confirm" | "view";
  wizardData: WizardData;
  currentPhase: Phase;
  completedPhases: Set<Phase>;
  pendingArtifact: Artifact | null;
  onPhaseClick: (phase: Phase) => void;
  onConfirm: () => void;
  onRevise: () => void;
  isLoading: boolean;
  // Trait selector props
  showTraitSelector?: boolean;
  suggestedTraits?: string[];
  selectedTraits?: string[];
  onTraitSelectionChange?: (traits: string[]) => void;
  traitRationales?: Record<string, string>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase Configuration
// ─────────────────────────────────────────────────────────────────────────────

const PHASE_CONFIG: { id: Phase; label: string; icon: typeof Globe }[] = [
  { id: "setting", label: "Setting", icon: Globe },
  { id: "character", label: "Character", icon: User },
  { id: "seed", label: "Seed", icon: Sparkles },
];

const BEAM_DURATION = 8;

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

interface AccordionSectionProps {
  title: string;
  icon: React.ReactNode;
  isLocked: boolean;
  isActive: boolean;
  hasContent: boolean;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function AccordionSection({
  title,
  icon,
  isLocked,
  isActive,
  hasContent,
  defaultOpen = false,
  children,
}: AccordionSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen || (isActive && hasContent));

  useEffect(() => {
    if (isActive && hasContent) {
      setIsOpen(true);
    }
  }, [isActive, hasContent]);

  if (isLocked) {
    return (
      <div className="border border-muted/30 rounded-md overflow-hidden opacity-50">
        <div className="flex items-center justify-between p-3 bg-muted/10">
          <div className="flex items-center gap-2">
            {icon}
            <span className="text-muted-foreground font-mono text-sm uppercase tracking-wider">
              {title}
            </span>
          </div>
          <Lock className="w-4 h-4 text-muted-foreground/50" />
        </div>
      </div>
    );
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="border border-primary/20 rounded-md overflow-hidden bg-background/40">
        <CollapsibleTrigger asChild>
          <button className="w-full flex items-center justify-between p-3 bg-primary/10 hover:bg-primary/20 transition-colors">
            <div className="flex items-center gap-2">
              {icon}
              <span className="text-primary font-sans text-sm uppercase tracking-wider">
                {title}
              </span>
            </div>
            <ChevronRight
              className={cn(
                "w-4 h-4 text-primary transition-transform duration-200",
                isOpen && "rotate-90"
              )}
            />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="p-4 border-t border-primary/20 space-y-4">
            {hasContent ? (
              children
            ) : (
              <p className="text-muted-foreground text-sm italic">
                Waiting for data...
              </p>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

function ExpandableText({
  text,
  maxLength = 200,
}: {
  text: string;
  maxLength?: number;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const needsExpansion = text.length > maxLength;

  if (!needsExpansion) {
    return <p className="text-sm text-white/80 font-narrative">{text}</p>;
  }

  return (
    <div>
      <p className="text-sm text-white/80 font-narrative">
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

// ─────────────────────────────────────────────────────────────────────────────
// Content Components
// ─────────────────────────────────────────────────────────────────────────────

function SettingContent({ data }: { data: SettingData | null | undefined }) {
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="border-l-2 border-primary pl-4">
        <div className="flex items-baseline gap-2 mb-1">
          <span className="text-primary text-xs uppercase">World</span>
          <h4 className="text-lg text-white font-bold">{data.world_name}</h4>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-primary/5 border border-primary/20 p-2 rounded">
          <span className="text-primary block uppercase mb-1">Genre</span>
          <span className="text-white capitalize">
            {data.genre}
            {(data.secondary_genres?.length ?? 0) > 0 &&
              ` (+${data.secondary_genres!.join(", ")})`}
          </span>
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
          <span className="text-primary block uppercase mb-1">Tech</span>
          <span className="text-white capitalize">
            {data.tech_level?.replace(/_/g, " ")}
          </span>
        </div>
      </div>

      {data.political_structure && (
        <div>
          <span className="text-primary block text-xs uppercase mb-1">
            Political Structure
          </span>
          <p className="text-sm text-white/80 font-narrative">
            {data.political_structure}
          </p>
        </div>
      )}

      {data.major_conflict && (
        <div>
          <span className="text-primary block text-xs uppercase mb-1">
            Major Conflict
          </span>
          <p className="text-sm text-white/80 font-narrative">
            {data.major_conflict}
          </p>
        </div>
      )}

      {(data.themes?.length ?? 0) > 0 && (
        <div>
          <span className="text-primary block text-xs uppercase mb-1">
            Themes
          </span>
          <div className="flex flex-wrap gap-1">
            {data.themes!.map((theme: string, i: number) => (
              <span
                key={i}
                className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded"
              >
                {theme}
              </span>
            ))}
          </div>
        </div>
      )}

      {data.cultural_notes && (
        <div>
          <span className="text-primary block text-xs uppercase mb-1">
            Cultural Notes
          </span>
          <ExpandableText text={data.cultural_notes} maxLength={150} />
        </div>
      )}
    </div>
  );
}

function CharacterContent({
  data,
  showTraitSelector,
  suggestedTraits,
  selectedTraits,
  onTraitSelectionChange,
  traitRationales,
}: {
  data: CharacterInProgress | CharacterComplete | null | undefined;
  showTraitSelector?: boolean;
  suggestedTraits?: string[];
  selectedTraits?: string[];
  onTraitSelectionChange?: (traits: string[]) => void;
  traitRationales?: Record<string, string>;
}) {
  const charView = getCharacterView(data);
  const { concept, traitSelection, wildcard, isComplete, completeSheet } =
    charView;

  if (!data && !showTraitSelector) return null;

  if (isComplete && completeSheet) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-primary/10 rounded-full flex items-center justify-center border border-primary/30 shrink-0">
            <User className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h4 className="text-lg text-white font-bold">{completeSheet.name}</h4>
            <p className="text-primary text-xs">{completeSheet.archetype}</p>
          </div>
        </div>

        {completeSheet.summary && (
          <div>
            <span className="text-primary block text-xs uppercase mb-1">
              Summary
            </span>
            <ExpandableText text={completeSheet.summary} maxLength={200} />
          </div>
        )}

        {wildcard && (
          <div className="bg-primary/5 border border-primary/20 p-3 rounded">
            <div className="flex items-center gap-2 mb-1">
              <Sparkles className="w-4 h-4 text-primary" />
              <span className="text-primary text-xs uppercase">
                {wildcard.name}
              </span>
            </div>
            <p className="text-sm text-white/80 font-narrative">
              {wildcard.description}
            </p>
          </div>
        )}

        {traitSelection && traitSelection.selected_traits.length > 0 && (
          <div>
            <span className="text-primary block text-xs uppercase mb-1">
              Traits
            </span>
            <div className="flex flex-wrap gap-1">
              {traitSelection.selected_traits.map((trait, i) => (
                <span
                  key={i}
                  className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded"
                >
                  {trait}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {concept && (
        <>
          <div className="border-l-2 border-primary pl-4">
            <div className="flex items-baseline gap-2 mb-1">
              <span className="text-primary text-xs uppercase">Character</span>
              <h4 className="text-lg text-white font-bold">{concept.name}</h4>
            </div>
            {concept.archetype && (
              <p className="text-primary/80 italic text-sm">
                {concept.archetype}
              </p>
            )}
          </div>

          {concept.background && (
            <div>
              <span className="text-primary block text-xs uppercase mb-1">
                Background
              </span>
              <ExpandableText text={concept.background} maxLength={200} />
            </div>
          )}
        </>
      )}

      {showTraitSelector && suggestedTraits && onTraitSelectionChange && (
        <div className="border-t border-primary/20 pt-4 mt-4">
          <span className="text-primary block text-xs uppercase mb-2">
            Select Traits
          </span>
          <div className="flex flex-wrap gap-2">
            {suggestedTraits.map((trait) => {
              const isSelected = selectedTraits?.includes(trait);
              return (
                <button
                  key={trait}
                  onClick={() => {
                    if (isSelected) {
                      onTraitSelectionChange(
                        selectedTraits?.filter((t) => t !== trait) || []
                      );
                    } else {
                      onTraitSelectionChange([...(selectedTraits || []), trait]);
                    }
                  }}
                  className={cn(
                    "text-xs px-3 py-1.5 rounded border transition-colors",
                    isSelected
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-primary/10 text-primary border-primary/30 hover:border-primary"
                  )}
                >
                  {trait}
                </button>
              );
            })}
          </div>
          {traitRationales && (
            <div className="mt-3 text-xs text-muted-foreground">
              <p className="italic">
                {selectedTraits?.length || 0} traits selected
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SeedContent({ data }: { data: SeedData | null | undefined }) {
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="border-l-2 border-primary pl-4">
        <span className="text-primary block text-xs uppercase mb-1">
          Starting Scenario
        </span>
        <h4 className="text-lg text-white font-bold mb-1">{data.seed?.title}</h4>
        {data.seed?.hook && (
          <p className="italic text-muted-foreground/60 text-sm">
            {data.seed.hook}
          </p>
        )}
      </div>

      {(data.layer || data.zone || data.location) && (
        <div className="space-y-2">
          {data.layer?.name && (
            <div className="flex justify-between border-b border-white/10 py-2">
              <span className="text-primary text-xs">Region</span>
              <span className="text-white text-sm text-right">
                {data.layer.name}
              </span>
            </div>
          )}
          {data.zone?.name && (
            <div className="flex justify-between border-b border-white/10 py-2">
              <span className="text-primary text-xs">Zone</span>
              <span className="text-white text-sm text-right">
                {data.zone.name}
              </span>
            </div>
          )}
          {data.location?.name && (
            <div className="flex justify-between border-b border-white/10 py-2">
              <span className="text-primary text-xs">Location</span>
              <span className="text-white text-sm text-right">
                {data.location.name}
              </span>
            </div>
          )}
          {data.location?.summary && (
            <div className="pt-2">
              <span className="text-primary block text-xs uppercase mb-1">
                Description
              </span>
              <ExpandableText text={data.location.summary} maxLength={150} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase Icons (collapsed view)
// ─────────────────────────────────────────────────────────────────────────────

function PhaseIcons({
  currentPhase,
  completedPhases,
  onPhaseClick,
  onExpand,
}: {
  currentPhase: Phase;
  completedPhases: Set<Phase>;
  onPhaseClick: (phase: Phase) => void;
  onExpand: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const phase1Ref = useRef<HTMLButtonElement>(null);
  const phase2Ref = useRef<HTMLButtonElement>(null);
  const phase3Ref = useRef<HTMLButtonElement>(null);
  const phaseRefs = [phase1Ref, phase2Ref, phase3Ref];

  const getPhaseIndex = (phase: Phase): number => {
    return PHASE_CONFIG.findIndex((p) => p.id === phase);
  };

  const currentPhaseIndex = getPhaseIndex(currentPhase);

  const handleClick = (phase: Phase) => {
    if (completedPhases.has(phase) || phase === currentPhase) {
      onExpand();
      onPhaseClick(phase);
    }
  };

  return (
    <TooltipProvider delayDuration={0}>
      <div ref={containerRef} className="relative flex flex-col items-center py-4 gap-4">
        {/* Animated beams connecting phases */}
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

        {PHASE_CONFIG.map((phase, index) => {
          const Icon = phase.icon;
          const completed = completedPhases.has(phase.id);
          const active = phase.id === currentPhase;
          const locked = getPhaseIndex(phase.id) > currentPhaseIndex && !completed;

          return (
            <Tooltip key={phase.id}>
              <TooltipTrigger asChild>
                <button
                  ref={phaseRefs[index]}
                  onClick={() => handleClick(phase.id)}
                  disabled={locked}
                  className={cn(
                    "relative w-10 h-10 rounded-lg flex items-center justify-center transition-all",
                    "hover:bg-primary/20",
                    active && "bg-primary/20 ring-2 ring-primary",
                    locked && "opacity-40 cursor-not-allowed"
                  )}
                >
                  <Icon className="w-5 h-5 text-primary" />
                  {completed && (
                    <div className="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full flex items-center justify-center">
                      <svg
                        className="w-2.5 h-2.5 text-white"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={3}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    </div>
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent side="left">
                {phase.label}
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </TooltipProvider>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────

export function ArtifactSidePanel({
  isCollapsed,
  onToggleCollapse,
  mode,
  wizardData,
  currentPhase,
  completedPhases,
  pendingArtifact,
  onPhaseClick,
  onConfirm,
  onRevise,
  isLoading,
  showTraitSelector,
  suggestedTraits,
  selectedTraits,
  onTraitSelectionChange,
  traitRationales,
}: ArtifactSidePanelProps) {
  const getPhaseIndex = (phase: Phase): number => {
    const phases: Phase[] = ["setting", "character", "seed"];
    return phases.indexOf(phase);
  };

  const currentPhaseIndex = getPhaseIndex(currentPhase);

  const isPhaseCompleted = (phase: Phase) => completedPhases.has(phase);
  const isPhaseActive = (phase: Phase) => phase === currentPhase;
  const isPhaseLocked = (phase: Phase) => {
    const idx = getPhaseIndex(phase);
    return idx > currentPhaseIndex && !isPhaseCompleted(phase);
  };

  const getDisplayData = (phase: Phase) => {
    if (pendingArtifact && isPhaseActive(phase)) {
      return pendingArtifact.data;
    }
    if (phase === "character") {
      return wizardData.character || wizardData.character_state;
    }
    return wizardData[phase];
  };

  const shouldShowFooter =
    mode === "confirm" && (pendingArtifact || showTraitSelector);
  const isConfirmDisabled =
    isLoading || (showTraitSelector ? (selectedTraits?.length ?? 0) === 0 : false);

  // Collapsed view - just show phase icons centered
  if (isCollapsed) {
    return (
      <div className="h-full flex flex-col bg-background/80 backdrop-blur-sm border-l border-primary/30">
        {/* Collapse toggle button */}
        <div className="p-2 border-b border-primary/30 flex justify-center">
          <button
            onClick={onToggleCollapse}
            className="p-2 rounded-md hover:bg-primary/20 text-primary transition-colors"
            title="Expand panel"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        </div>

        {/* Phase icons */}
        <div className="flex-1 flex flex-col items-center justify-center">
          <PhaseIcons
            currentPhase={currentPhase}
            completedPhases={completedPhases}
            onPhaseClick={onPhaseClick}
            onExpand={onToggleCollapse}
          />
        </div>
      </div>
    );
  }

  // Expanded view - full content
  return (
    <div className="h-full flex flex-col bg-background/80 backdrop-blur-sm border-l border-primary/30">
      {/* Header */}
      <div className="p-3 border-b border-primary/30 flex items-center justify-between">
        <h3 className="text-primary font-mono uppercase tracking-wider text-sm">
          Story Elements
        </h3>
        <button
          onClick={onToggleCollapse}
          className="p-2 rounded-md hover:bg-primary/20 text-primary transition-colors"
          title="Collapse panel"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-3">
          <AccordionSection
            title="Setting"
            icon={<Globe className="w-4 h-4 text-primary" />}
            isLocked={isPhaseLocked("setting")}
            isActive={isPhaseActive("setting")}
            hasContent={!!getDisplayData("setting")}
            defaultOpen={currentPhase === "setting" || !!wizardData.setting}
          >
            <SettingContent
              data={getDisplayData("setting") as SettingData | null | undefined}
            />
          </AccordionSection>

          <AccordionSection
            title="Character"
            icon={<User className="w-4 h-4 text-primary" />}
            isLocked={isPhaseLocked("character")}
            isActive={isPhaseActive("character")}
            hasContent={!!getDisplayData("character") || !!showTraitSelector}
            defaultOpen={currentPhase === "character"}
          >
            <CharacterContent
              data={
                getDisplayData("character") as
                  | CharacterInProgress
                  | CharacterComplete
                  | null
                  | undefined
              }
              showTraitSelector={showTraitSelector}
              suggestedTraits={suggestedTraits}
              selectedTraits={selectedTraits}
              onTraitSelectionChange={onTraitSelectionChange}
              traitRationales={traitRationales}
            />
          </AccordionSection>

          <AccordionSection
            title="Seed"
            icon={<Sparkles className="w-4 h-4 text-primary" />}
            isLocked={isPhaseLocked("seed")}
            isActive={isPhaseActive("seed")}
            hasContent={!!getDisplayData("seed")}
            defaultOpen={currentPhase === "seed"}
          >
            <SeedContent
              data={getDisplayData("seed") as SeedData | null | undefined}
            />
          </AccordionSection>
        </div>
      </ScrollArea>

      {/* Footer with action buttons */}
      {shouldShowFooter && (
        <div className="p-4 border-t border-primary/30">
          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={onRevise}
              disabled={isLoading}
              className="flex-1 border-destructive/50 text-destructive hover:bg-destructive/10 font-sans uppercase tracking-wide text-xs"
            >
              Revise
            </Button>
            <Button
              onClick={onConfirm}
              disabled={isConfirmDisabled}
              className="flex-1 bg-primary/20 border border-primary text-primary hover:bg-primary/30 font-sans uppercase tracking-wide text-xs"
            >
              {isLoading ? "Processing..." : "Confirm"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
