/**
 * ArtifactDrawer - Right-side drawer for viewing and confirming wizard artifacts
 *
 * Features:
 * - Nested accordion: Setting → Character → Seed
 * - Progressive disclosure: sections locked until phase completes
 * - Two modes: 'confirm' (with buttons) and 'view' (read-only)
 * - Auto-opens on new artifact, can be manually toggled via PhaseDock
 */

import { useState, useEffect } from "react";
import { X, Globe, User, Sparkles, ChevronRight, Lock, Wand2, FileText, MapPin, Scroll, Languages, Tag } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerFooter,
  DrawerClose,
} from "@/components/ui/drawer";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { TraitSelectorGrid } from "./TraitSelectorGrid";

// ─────────────────────────────────────────────────────────────────────────────
// Type Definitions
// ─────────────────────────────────────────────────────────────────────────────

type Phase = "setting" | "character" | "seed";

/** Setting artifact data from submit_world_document */
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

/** Character concept from submit_character_concept (subphase 1) */
interface CharacterConcept {
  name: string;
  archetype: string;
  background?: string;
  suggested_traits?: string[];
  trait_rationales?: Record<string, string>;
}

/** Trait selection from submit_trait_selection (subphase 2) */
interface TraitSelection {
  selected_traits: string[];
  trait_rationales?: Record<string, string>;
}

/** Wildcard from submit_wildcard_trait (subphase 3) */
interface WildcardTrait {
  name: string;
  description: string;
  mechanical_effect?: string;
}

/** Character data during subphase creation (nested structure) */
interface CharacterInProgress {
  concept?: CharacterConcept;
  trait_selection?: TraitSelection;
  wildcard?: WildcardTrait;
}

/** Complete character sheet from submit_character_sheet (flat structure) */
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

/** Seed artifact data from submit_starting_scenario */
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

/** Type guard to check if character data is complete (has summary) */
function isCharacterComplete(data: CharacterInProgress | CharacterComplete | null | undefined): data is CharacterComplete {
  return Boolean(data && 'summary' in data && data.summary);
}

/** Normalize character data to extract viewable parts */
function getCharacterView(data: CharacterInProgress | CharacterComplete | null | undefined): {
  concept: CharacterConcept | null;
  traitSelection: TraitSelection | null;
  wildcard: WildcardTrait | null;
  isComplete: boolean;
  completeSheet: CharacterComplete | null;
} {
  if (!data) {
    return { concept: null, traitSelection: null, wildcard: null, isComplete: false, completeSheet: null };
  }

  if (isCharacterComplete(data)) {
    // Complete sheet - extract concept-like data for display
    return {
      concept: { name: data.name, archetype: data.archetype, background: data.background },
      traitSelection: data.traits ? { selected_traits: data.traits, trait_rationales: data.trait_rationales } : null,
      wildcard: data.wildcard_name ? { name: data.wildcard_name, description: data.wildcard_description || '', mechanical_effect: data.wildcard_effect } : null,
      isComplete: true,
      completeSheet: data,
    };
  }

  // In-progress structure
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
  data: SettingData | CharacterConcept | TraitSelection | WildcardTrait | CharacterComplete | SeedData;
}

interface ArtifactDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "confirm" | "view";
  wizardData: WizardData;
  currentPhase: Phase;
  pendingArtifact: Artifact | null;
  onConfirm: () => void;
  onRevise: () => void;
  isLoading: boolean;
  // Trait selector props (for character phase 2.2)
  showTraitSelector?: boolean;
  suggestedTraits?: string[];
  selectedTraits?: string[];
  onTraitSelectionChange?: (traits: string[]) => void;
  traitRationales?: Record<string, string>;
}

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

  // Auto-open when phase becomes active and has content
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
            {hasContent ? children : (
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

// Expandable text component for long content
function ExpandableText({ text, maxLength = 200 }: { text: string; maxLength?: number }) {
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

// Setting section content
function SettingContent({ data }: { data: SettingData | null | undefined }) {
  if (!data) return null;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="border-l-2 border-primary pl-4">
        <div className="flex items-baseline gap-2 mb-1">
          <span className="text-primary text-xs uppercase">World</span>
          <h4 className="text-lg text-white font-bold">{data.world_name}</h4>
        </div>
      </div>

      {/* Quick Reference Grid */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-primary/5 border border-primary/20 p-2 rounded">
          <span className="text-primary block uppercase mb-1">Genre</span>
          <span className="text-white capitalize">
            {data.genre}
            {(data.secondary_genres?.length ?? 0) > 0 && ` (+${data.secondary_genres!.join(", ")})`}
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
          <span className="text-white capitalize">{data.tech_level?.replace(/_/g, " ")}</span>
        </div>
      </div>

      {/* Political Structure */}
      {data.political_structure && (
        <div>
          <span className="text-primary block text-xs uppercase mb-1">Political Structure</span>
          <p className="text-sm text-white/80 font-narrative">{data.political_structure}</p>
        </div>
      )}

      {/* Major Conflict */}
      {data.major_conflict && (
        <div>
          <span className="text-primary block text-xs uppercase mb-1">Major Conflict</span>
          <p className="text-sm text-white/80 font-narrative">{data.major_conflict}</p>
        </div>
      )}

      {/* Themes */}
      {(data.themes?.length ?? 0) > 0 && (
        <div>
          <span className="text-primary block text-xs uppercase mb-1">Themes</span>
          <div className="flex flex-wrap gap-1">
            {data.themes!.map((theme: string, i: number) => (
              <span key={i} className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded">
                {theme}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Cultural Notes (collapsed) */}
      {data.cultural_notes && (
        <div>
          <span className="text-primary block text-xs uppercase mb-1">Cultural Notes</span>
          <ExpandableText text={data.cultural_notes} maxLength={150} />
        </div>
      )}
    </div>
  );
}

// Character section content
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
  // Use normalization helper to handle both in-progress and complete data structures
  const charView = getCharacterView(data);
  const { concept, traitSelection, wildcard, isComplete, completeSheet } = charView;

  if (!data && !showTraitSelector) return null;

  // If we have a complete character sheet (has summary)
  if (isComplete && completeSheet) {
    return (
      <div className="space-y-4">
        {/* Character Header */}
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 bg-primary/10 rounded-full flex items-center justify-center border border-primary/30 shrink-0">
            <User className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h4 className="text-lg text-white font-bold">{completeSheet.name}</h4>
            <p className="text-primary text-xs">{completeSheet.archetype}</p>
          </div>
        </div>

        {/* Summary */}
        {completeSheet.summary && (
          <div>
            <span className="text-primary block text-xs uppercase mb-1">Summary</span>
            <ExpandableText text={completeSheet.summary} maxLength={200} />
          </div>
        )}

        {/* Wildcard */}
        {wildcard && (
          <div className="bg-primary/5 border border-primary/20 p-3 rounded">
            <div className="flex items-center gap-2 mb-1">
              <Sparkles className="w-4 h-4 text-primary" />
              <span className="text-primary text-xs uppercase">{wildcard.name}</span>
            </div>
            <p className="text-sm text-white/80 font-narrative">{wildcard.description}</p>
          </div>
        )}

        {/* Selected Traits (display mode) */}
        {traitSelection && traitSelection.selected_traits.length > 0 && (
          <TraitSelectorGrid
            mode="display"
            suggestedTraits={[]}
            selectedTraits={traitSelection.selected_traits}
            traitRationales={traitSelection.trait_rationales || traitRationales}
            maxTraits={10}
          />
        )}
      </div>
    );
  }

  // Show concept data first if available, then trait selector below (in-progress state)
  return (
    <div className="space-y-4">
      {/* Concept data */}
      {concept && (
        <>
          <div className="border-l-2 border-primary pl-4">
            <div className="flex items-baseline gap-2 mb-1">
              <span className="text-primary text-xs uppercase">Character</span>
              <h4 className="text-lg text-white font-bold">{concept.name}</h4>
            </div>
            {concept.archetype && (
              <p className="text-primary/80 italic text-sm">{concept.archetype}</p>
            )}
          </div>

          {concept.background && (
            <div>
              <span className="text-primary block text-xs uppercase mb-1">Background</span>
              <ExpandableText text={concept.background} maxLength={200} />
            </div>
          )}
        </>
      )}

      {/* Trait selector (below concept when in selection mode) */}
      {showTraitSelector && suggestedTraits && onTraitSelectionChange && (
        <div className="border-t border-primary/20 pt-4 mt-4">
          <TraitSelectorGrid
            mode="select"
            suggestedTraits={suggestedTraits}
            selectedTraits={selectedTraits || []}
            onSelectionChange={onTraitSelectionChange}
            traitRationales={traitRationales || concept?.trait_rationales}
            maxTraits={10}
          />
        </div>
      )}
    </div>
  );
}

// Seed section content
function SeedContent({ data }: { data: SeedData | null | undefined }) {
  if (!data) return null;

  return (
    <div className="space-y-4">
      {/* Scenario Header */}
      <div className="border-l-2 border-primary pl-4">
        <span className="text-primary block text-xs uppercase mb-1">Starting Scenario</span>
        <h4 className="text-lg text-white font-bold mb-1">{data.seed?.title}</h4>
        {data.seed?.hook && (
          <p className="italic text-muted-foreground/60 text-sm">{data.seed.hook}</p>
        )}
      </div>

      {/* Location Details */}
      {(data.layer || data.zone || data.location) && (
        <div className="space-y-2">
          {data.layer?.name && (
            <div className="flex justify-between border-b border-white/10 py-2">
              <span className="text-primary text-xs">Region</span>
              <span className="text-white text-sm text-right">{data.layer.name}</span>
            </div>
          )}
          {data.zone?.name && (
            <div className="flex justify-between border-b border-white/10 py-2">
              <span className="text-primary text-xs">Zone</span>
              <span className="text-white text-sm text-right">{data.zone.name}</span>
            </div>
          )}
          {data.location?.name && (
            <div className="flex justify-between border-b border-white/10 py-2">
              <span className="text-primary text-xs">Location</span>
              <span className="text-white text-sm text-right">{data.location.name}</span>
            </div>
          )}
          {data.location?.summary && (
            <div className="pt-2">
              <span className="text-primary block text-xs uppercase mb-1">Description</span>
              <ExpandableText text={data.location.summary} maxLength={150} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ArtifactDrawer({
  open,
  onOpenChange,
  mode,
  wizardData,
  currentPhase,
  pendingArtifact,
  onConfirm,
  onRevise,
  isLoading,
  showTraitSelector,
  suggestedTraits,
  selectedTraits,
  onTraitSelectionChange,
  traitRationales,
}: ArtifactDrawerProps) {
  const getPhaseIndex = (phase: Phase): number => {
    const phases: Phase[] = ["setting", "character", "seed"];
    return phases.indexOf(phase);
  };

  const currentPhaseIndex = getPhaseIndex(currentPhase);

  const isPhaseCompleted = (phase: Phase) => {
    const idx = getPhaseIndex(phase);
    return idx < currentPhaseIndex || (idx === currentPhaseIndex && !!wizardData[phase]);
  };

  const isPhaseActive = (phase: Phase) => phase === currentPhase;

  const isPhaseLocked = (phase: Phase) => {
    const idx = getPhaseIndex(phase);
    return idx > currentPhaseIndex;
  };

  // Determine what data to show for the pending artifact
  const getDisplayData = (phase: Phase) => {
    // If there's a pending artifact for this phase, show that
    if (pendingArtifact && isPhaseActive(phase)) {
      return pendingArtifact.data;
    }
    // Character phase uses character_state during creation, character when finalized
    if (phase === "character") {
      // Check for finalized character first, then in-progress character_state
      return wizardData.character || wizardData.character_state;
    }
    // Otherwise show confirmed data
    return wizardData[phase];
  };

  const shouldShowFooter = mode === "confirm" && (pendingArtifact || showTraitSelector);
  const isConfirmDisabled =
    isLoading || (showTraitSelector ? (selectedTraits?.length ?? 0) === 0 : false);

  return (
    <Drawer open={open} onOpenChange={onOpenChange} direction="right">
      <DrawerContent direction="right" className="w-[420px]">
        {/* Header with close button */}
        <DrawerHeader className="flex flex-row items-center justify-between border-b border-primary/30">
          <DrawerTitle className="text-primary font-mono uppercase tracking-wider">
            Story Elements
          </DrawerTitle>
          <DrawerClose asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <X className="h-4 w-4" />
              <span className="sr-only">Close</span>
            </Button>
          </DrawerClose>
        </DrawerHeader>

        {/* Scrollable content area */}
        <ScrollArea className="flex-1 px-4 py-4">
          <div className="space-y-3">
            {/* Setting Section */}
            <AccordionSection
              title="Setting"
              icon={<Globe className="w-4 h-4 text-primary" />}
              isLocked={isPhaseLocked("setting")}
              isActive={isPhaseActive("setting")}
              hasContent={!!getDisplayData("setting")}
              defaultOpen={currentPhase === "setting" || !!wizardData.setting}
            >
              <SettingContent data={getDisplayData("setting") as SettingData | null | undefined} />
            </AccordionSection>

            {/* Character Section */}
            <AccordionSection
              title="Character"
              icon={<User className="w-4 h-4 text-primary" />}
              isLocked={isPhaseLocked("character")}
              isActive={isPhaseActive("character")}
              hasContent={!!getDisplayData("character") || !!showTraitSelector}
              defaultOpen={currentPhase === "character"}
            >
              <CharacterContent
                data={getDisplayData("character") as CharacterInProgress | CharacterComplete | null | undefined}
                showTraitSelector={showTraitSelector}
                suggestedTraits={suggestedTraits}
                selectedTraits={selectedTraits}
                onTraitSelectionChange={onTraitSelectionChange}
                traitRationales={traitRationales}
              />
            </AccordionSection>

            {/* Seed Section */}
            <AccordionSection
              title="Seed"
              icon={<Sparkles className="w-4 h-4 text-primary" />}
              isLocked={isPhaseLocked("seed")}
              isActive={isPhaseActive("seed")}
              hasContent={!!getDisplayData("seed")}
              defaultOpen={currentPhase === "seed"}
            >
              <SeedContent data={getDisplayData("seed") as SeedData | null | undefined} />
            </AccordionSection>
          </div>
        </ScrollArea>

        {/* Footer with action buttons (only in confirm mode) */}
        {shouldShowFooter && (
          <DrawerFooter className="border-t border-primary/30">
            <div className="flex gap-3">
              <Button
                variant="outline"
                onClick={onRevise}
                disabled={isLoading}
                className="flex-1 border-destructive/50 text-destructive hover:bg-destructive/10 font-sans uppercase tracking-wide"
              >
                Revise
              </Button>
              <Button
                onClick={onConfirm}
                disabled={isConfirmDisabled}
                className="flex-1 bg-primary/20 border border-primary text-primary hover:bg-primary/30 font-sans uppercase tracking-wide"
              >
                {isLoading ? "Processing..." : "Confirm"}
              </Button>
            </div>
          </DrawerFooter>
        )}
      </DrawerContent>
    </Drawer>
  );
}
