import { useEffect, useMemo, useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Users, Brain, Loader2, ChevronRight, ChevronDown, Upload, Image as ImageIcon, Circle, CircleDot, MapPin, Activity, User, ScrollText, Heart, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Character, CharacterRelationship, CharacterPsychology } from "@shared/schema";
import { ImageGalleryModal, type ImageData } from "@/components/ImageGalleryModal";
import { useTheme } from "@/contexts/ThemeContext";
import { cn } from "@/lib/utils";

interface NormalizedRelationship {
  character1Id: number;
  character2Id: number;
  relationshipType: string;
  emotionalValence: string | null;
  dynamic: string | null;
  recentEvents: string | null;
  history: string | null;
}

interface RelationshipPair {
  counterpartId: number;
  fromSelected?: NormalizedRelationship;
  toSelected?: NormalizedRelationship;
}

interface Place {
  id: number;
  name: string;
}

// Section definitions for the outline column
type SectionId = "summary" | "background" | "personality" | "currentActivity" | "currentLocation" | "psychology" | "relationships";

interface SectionDef {
  id: SectionId;
  label: string;
  icon: React.ReactNode;
  collapsible?: boolean;
}

const SECTIONS: SectionDef[] = [
  { id: "summary", label: "Summary", icon: <ScrollText className="h-3 w-3" /> },
  { id: "background", label: "Background", icon: <User className="h-3 w-3" /> },
  { id: "personality", label: "Personality", icon: <Sparkles className="h-3 w-3" /> },
  { id: "currentActivity", label: "Current Activity", icon: <Activity className="h-3 w-3" /> },
  { id: "currentLocation", label: "Current Location", icon: <MapPin className="h-3 w-3" /> },
  { id: "psychology", label: "Psychology", icon: <Brain className="h-3 w-3" />, collapsible: true },
  { id: "relationships", label: "Relationships", icon: <Heart className="h-3 w-3" />, collapsible: true },
];

// Psychology field definitions for nested subsections
type PsychologyFieldId = "selfConcept" | "behavior" | "cognitiveFramework" | "temperament" | "relationalStyle" | "defenseMechanisms" | "characterArc" | "secrets";

const PSYCHOLOGY_FIELDS: { id: PsychologyFieldId; label: string }[] = [
  { id: "selfConcept", label: "Self Concept" },
  { id: "behavior", label: "Behavior" },
  { id: "cognitiveFramework", label: "Cognitive Framework" },
  { id: "temperament", label: "Temperament" },
  { id: "relationalStyle", label: "Relational Style" },
  { id: "defenseMechanisms", label: "Defense Mechanisms" },
  { id: "characterArc", label: "Character Arc" },
  { id: "secrets", label: "Secrets" },
];

// Convert camelCase or snake_case to Chicago Title Case
const toChicagoTitle = (str: string): string => {
  // Replace underscores with spaces first, then insert space before capitals
  const withSpaces = str.replace(/_/g, " ");
  const words = withSpaces.replace(/([A-Z])/g, " $1").trim().split(/\s+/);
  const minorWords = new Set(["a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "nor", "of", "on", "or", "so", "the", "to", "up", "with", "yet"]);

  return words.map((word, i) => {
    const lower = word.toLowerCase();
    // Capitalize first word, last word, and major words
    if (i === 0 || i === words.length - 1 || !minorWords.has(lower)) {
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    }
    return lower;
  }).join(" ");
};

const normalizeRelationship = (
  rel: CharacterRelationship & {
    character1_id?: number;
    character2_id?: number;
    relationship_type?: string;
    emotional_valence?: string;
    recent_events?: string;
  },
): NormalizedRelationship => ({
  character1Id: rel.character1Id ?? rel.character1_id ?? 0,
  character2Id: rel.character2Id ?? rel.character2_id ?? 0,
  relationshipType: rel.relationshipType ?? rel.relationship_type ?? "unknown",
  emotionalValence: rel.emotionalValence ?? rel.emotional_valence ?? null,
  dynamic: rel.dynamic ?? null,
  recentEvents: rel.recentEvents ?? rel.recent_events ?? null,
  history: rel.history ?? null,
});

const formatValence = (value: string | null | undefined): string => {
  if (!value) return "—";
  return value.includes("|") ? value.replace("|", " | ") : value;
};

export function CharactersTab({ slot = null }: { slot?: number | null }) {
  const { glowClass } = useTheme();
  const [selectedCharacterId, setSelectedCharacterId] = useState<number | null>(null);
  const [selectedSection, setSelectedSection] = useState<SectionId | null>(null);
  const [psychologyExpanded, setPsychologyExpanded] = useState(false);
  const [relationshipsExpanded, setRelationshipsExpanded] = useState(false);
  const [selectedPsychologyField, setSelectedPsychologyField] = useState<PsychologyFieldId | null>(null);
  const [selectedRelationshipId, setSelectedRelationshipId] = useState<number | null>(null);
  const [galleryOpen, setGalleryOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  // Fetch characters
  const {
    data: characters = [],
    isLoading: charactersLoading,
    isError: charactersError,
    error: charactersErrorData,
  } = useQuery<Character[]>({
    queryKey: ["/api/characters", slot],
    queryFn: async () => {
      const res = await fetch(`/api/characters${slot ? `?slot=${slot}` : ""}`);
      if (!res.ok) throw new Error("Failed to fetch characters");
      return res.json();
    },
    select: (data) => [...data].sort((a, b) => a.id - b.id),
  });

  // Fetch places for location name lookup
  const { data: places = [] } = useQuery<Place[]>({
    queryKey: ["/api/places", slot],
    queryFn: async () => {
      const res = await fetch(`/api/places${slot ? `?slot=${slot}` : ""}`);
      if (!res.ok) return [];
      return res.json();
    },
  });

  const placeNameById = useMemo(() => {
    const lookup = new Map<number, string>();
    places.forEach(p => lookup.set(p.id, p.name));
    return lookup;
  }, [places]);

  useEffect(() => {
    if (!selectedCharacterId && characters.length > 0) {
      setSelectedCharacterId(characters[0].id);
    }
  }, [characters, selectedCharacterId]);

  const selectedCharacter = useMemo(() => {
    return characters.find((character) => character.id === selectedCharacterId) ?? null;
  }, [characters, selectedCharacterId]);

  // Reset section when character changes - start with portrait-only view
  useEffect(() => {
    setSelectedSection(null);
    setPsychologyExpanded(false);
    setRelationshipsExpanded(false);
    setSelectedPsychologyField(null);
    setSelectedRelationshipId(null);
  }, [selectedCharacterId]);

  // Fetch relationships
  const {
    data: relationships = [],
    isLoading: relationshipsLoading,
    isError: relationshipsError,
    error: relationshipsErrorData,
  } = useQuery<CharacterRelationship[]>({
    queryKey: ["/api/characters", selectedCharacter?.id, "relationships", slot],
    queryFn: async () => {
      if (!selectedCharacter) return [];
      const response = await fetch(`/api/characters/${selectedCharacter.id}/relationships${slot ? `?slot=${slot}` : ""}`);
      if (response.status === 404) return [];
      if (!response.ok) throw new Error("Failed to load relationships");
      return response.json();
    },
    enabled: !!selectedCharacter,
  });

  const normalizedRelationships = useMemo(() => {
    return relationships.map((rel) => normalizeRelationship(rel));
  }, [relationships]);

  const relationshipPairs: RelationshipPair[] = useMemo(() => {
    if (!selectedCharacter) return [];
    const grouped = new Map<number, { fromSelected?: NormalizedRelationship; toSelected?: NormalizedRelationship }>();

    for (const rel of normalizedRelationships) {
      const fromSelected = rel.character1Id === selectedCharacter.id;
      const counterpartId = fromSelected ? rel.character2Id : rel.character1Id;
      const entry = grouped.get(counterpartId) ?? {};
      if (fromSelected) {
        entry.fromSelected = rel;
      } else {
        entry.toSelected = rel;
      }
      grouped.set(counterpartId, entry);
    }

    return Array.from(grouped.entries())
      .map(([counterpartId, pair]) => ({ counterpartId, ...pair }))
      .sort((a, b) => a.counterpartId - b.counterpartId);
  }, [normalizedRelationships, selectedCharacter]);

  // Fetch psychology
  const {
    data: psychologyRecord,
    isLoading: psychologyLoading,
    isError: psychologyError,
    error: psychologyErrorData,
  } = useQuery<CharacterPsychology | null>({
    queryKey: ["/api/characters", selectedCharacter?.id, "psychology", slot],
    queryFn: async () => {
      if (!selectedCharacter) return null;
      const response = await fetch(`/api/characters/${selectedCharacter.id}/psychology${slot ? `?slot=${slot}` : ""}`);
      if (response.status === 404) return null;
      if (!response.ok) throw new Error("Failed to load psychology");
      return response.json();
    },
    enabled: !!selectedCharacter,
  });

  // Fetch character images
  const {
    data: characterImages = [],
  } = useQuery<ImageData[]>({
    queryKey: ["/api/characters", selectedCharacter?.id, "images", slot],
    queryFn: async () => {
      if (!selectedCharacter) return [];
      const response = await fetch(`/api/characters/${selectedCharacter.id}/images${slot ? `?slot=${slot}` : ""}`);
      if (!response.ok) throw new Error("Failed to load images");
      return response.json();
    },
    enabled: !!selectedCharacter,
  });

  const uploadImagesMutation = useMutation({
    mutationFn: async (files: FileList) => {
      if (!selectedCharacter) throw new Error("No character selected");
      const formData = new FormData();
      Array.from(files).forEach((file) => formData.append("images", file));

      const response = await fetch(`/api/characters/${selectedCharacter.id}/images${slot ? `?slot=${slot}` : ""}`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error("Failed to upload images");
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/characters", selectedCharacter?.id, "images", slot] });
    },
  });

  const setMainImageMutation = useMutation({
    mutationFn: async (imageId: number) => {
      if (!selectedCharacter) throw new Error("No character selected");
      const response = await fetch(`/api/characters/${selectedCharacter.id}/images/${imageId}/main${slot ? `?slot=${slot}` : ""}`, {
        method: "PUT",
      });
      if (!response.ok) throw new Error("Failed to set main image");
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/characters", selectedCharacter?.id, "images", slot] });
    },
  });

  const deleteImageMutation = useMutation({
    mutationFn: async (imageId: number) => {
      if (!selectedCharacter) throw new Error("No character selected");
      const response = await fetch(`/api/characters/${selectedCharacter.id}/images/${imageId}${slot ? `?slot=${slot}` : ""}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Failed to delete image");
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/characters", selectedCharacter?.id, "images", slot] });
    },
  });

  const mainImage = useMemo(() => {
    return characterImages.find((img) => img.isMain === 1) || characterImages[0] || null;
  }, [characterImages]);

  const handleQuickUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    try {
      await uploadImagesMutation.mutateAsync(files);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } finally {
      setUploading(false);
    }
  };

  const characterNameById = (id: number) => {
    return characters.find((character) => character.id === id)?.name ?? `Character ${id}`;
  };

  // Check if section has content
  const sectionHasContent = (sectionId: SectionId): boolean => {
    if (!selectedCharacter) return false;
    switch (sectionId) {
      case "summary": return !!selectedCharacter.summary;
      case "background": return !!selectedCharacter.background;
      case "personality": return !!selectedCharacter.personality;
      case "currentActivity": return !!selectedCharacter.currentActivity;
      case "currentLocation": return selectedCharacter.currentLocation !== null && selectedCharacter.currentLocation !== undefined;
      case "psychology": return !!psychologyRecord;
      case "relationships": return relationshipPairs.length > 0;
      default: return false;
    }
  };

  // Render psychology field with Chicago title case
  const renderPsychologyField = (key: string, value: unknown) => {
    if (!value) return null;
    const label = toChicagoTitle(key);

    const renderValue = (val: any): string => {
      if (Array.isArray(val)) {
        return val.join(", ");
      }
      if (typeof val === "object" && val !== null) {
        return Object.entries(val)
          .map(([k, nested]) => `${toChicagoTitle(k)}: ${Array.isArray(nested) ? nested.join(", ") : String(nested)}`)
          .join("\n");
      }
      return String(val);
    };

    return (
      <div key={key} className="space-y-1">
        <h4 className={`text-xs font-mono text-primary ${glowClass} uppercase`}>{label}</h4>
        <pre className="whitespace-pre-wrap font-serif text-sm text-foreground/90 leading-relaxed">
          {renderValue(value)}
        </pre>
      </div>
    );
  };

  // Render relationship perspective
  const renderRelationshipPerspective = (heading: string, rel: NormalizedRelationship | undefined) => {
    if (!rel) {
      return (
        <div className="space-y-2">
          <h4 className="text-xs font-mono text-primary uppercase tracking-wide">{heading}</h4>
          <p className="text-xs text-muted-foreground italic">No perspective recorded.</p>
        </div>
      );
    }

    return (
      <div className="space-y-2">
        <h4 className="text-xs font-mono text-primary uppercase tracking-wide">{heading}</h4>
        <div className="space-y-2 text-sm text-foreground/90">
          <div className="flex items-start gap-2">
            <span className="w-24 text-xs text-muted-foreground uppercase tracking-wide">Type</span>
            <span className="flex-1 font-serif">{rel.relationshipType}</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="w-24 text-xs text-muted-foreground uppercase tracking-wide">Valence</span>
            <span className="flex-1 font-serif">{formatValence(rel.emotionalValence)}</span>
          </div>
          {rel.dynamic && (
            <div>
              <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Dynamic</div>
              <p className="whitespace-pre-wrap leading-relaxed font-serif">{rel.dynamic}</p>
            </div>
          )}
          {rel.recentEvents && (
            <div>
              <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Recent Events</div>
              <p className="whitespace-pre-wrap leading-relaxed font-serif">{rel.recentEvents}</p>
            </div>
          )}
          {rel.history && (
            <div>
              <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">History</div>
              <p className="whitespace-pre-wrap leading-relaxed font-serif">{rel.history}</p>
            </div>
          )}
        </div>
      </div>
    );
  };

  // Render section content
  const renderSectionContent = () => {
    if (!selectedCharacter) return null;
    if (!selectedSection) return null; // Portrait-only view

    switch (selectedSection) {
      case "summary":
        return selectedCharacter.summary ? (
          <p className="font-serif text-foreground/90 leading-relaxed whitespace-pre-wrap">{selectedCharacter.summary}</p>
        ) : (
          <p className="text-muted-foreground italic text-sm">No summary recorded.</p>
        );

      case "background":
        return selectedCharacter.background ? (
          <p className="font-serif text-foreground/90 leading-relaxed whitespace-pre-wrap">{selectedCharacter.background}</p>
        ) : (
          <p className="text-muted-foreground italic text-sm">No background recorded.</p>
        );

      case "personality":
        return selectedCharacter.personality ? (
          <p className="font-serif text-foreground/90 leading-relaxed whitespace-pre-wrap">{selectedCharacter.personality}</p>
        ) : (
          <p className="text-muted-foreground italic text-sm">No personality recorded.</p>
        );

      case "currentActivity":
        return selectedCharacter.currentActivity ? (
          <p className="font-serif text-foreground/90 leading-relaxed whitespace-pre-wrap">{selectedCharacter.currentActivity}</p>
        ) : (
          <p className="text-muted-foreground italic text-sm">No current activity recorded.</p>
        );

      case "currentLocation":
        const locationId = selectedCharacter.currentLocation;
        if (locationId === null || locationId === undefined) {
          return <p className="text-muted-foreground italic text-sm">No current location set.</p>;
        }
        const locationName = placeNameById.get(Number(locationId)) || `Unknown location (ID: ${locationId})`;
        return (
          <div className="space-y-2">
            <p className={`font-serif text-lg text-primary ${glowClass}`}>{locationName}</p>
          </div>
        );

      case "psychology":
        if (psychologyLoading) {
          return (
            <div className="flex items-center justify-center h-32 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          );
        }
        if (psychologyError) {
          return (
            <p className="text-xs text-destructive">
              Failed to load psychology: {psychologyErrorData instanceof Error ? psychologyErrorData.message : "Unknown error"}
            </p>
          );
        }
        if (!psychologyRecord) {
          return <p className="text-muted-foreground italic text-sm">No psychology profile recorded.</p>;
        }
        // If a specific field is selected, show only that field
        if (selectedPsychologyField) {
          return (
            <div className="space-y-4">
              {renderPsychologyField(selectedPsychologyField, psychologyRecord[selectedPsychologyField])}
            </div>
          );
        }
        // Otherwise show all fields
        return (
          <div className="space-y-4">
            {renderPsychologyField("selfConcept", psychologyRecord.selfConcept)}
            {renderPsychologyField("behavior", psychologyRecord.behavior)}
            {renderPsychologyField("cognitiveFramework", psychologyRecord.cognitiveFramework)}
            {renderPsychologyField("temperament", psychologyRecord.temperament)}
            {renderPsychologyField("relationalStyle", psychologyRecord.relationalStyle)}
            {renderPsychologyField("defenseMechanisms", psychologyRecord.defenseMechanisms)}
            {renderPsychologyField("characterArc", psychologyRecord.characterArc)}
            {renderPsychologyField("secrets", psychologyRecord.secrets)}
          </div>
        );

      case "relationships":
        if (relationshipsLoading) {
          return (
            <div className="flex items-center justify-center h-32 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          );
        }
        if (relationshipsError) {
          return (
            <p className="text-xs text-destructive">
              Failed to load relationships: {relationshipsErrorData instanceof Error ? relationshipsErrorData.message : "Unknown error"}
            </p>
          );
        }
        if (relationshipPairs.length === 0) {
          return <p className="text-muted-foreground italic text-sm">No relationships documented.</p>;
        }
        // If a specific relationship is selected, show only that one
        const pairsToShow = selectedRelationshipId
          ? relationshipPairs.filter((p) => p.counterpartId === selectedRelationshipId)
          : relationshipPairs;
        return (
          <div className="space-y-4">
            {pairsToShow.map((pair) => {
              const counterpartName = characterNameById(pair.counterpartId);
              return (
                <div
                  key={pair.counterpartId}
                  className="border border-border/40 rounded-md bg-background/70 p-4 space-y-4"
                >
                  <div className={`text-sm font-mono text-primary ${glowClass}`}>
                    {counterpartName}
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    {renderRelationshipPerspective(selectedCharacter.name, pair.fromSelected)}
                    {renderRelationshipPerspective(counterpartName, pair.toSelected)}
                  </div>
                </div>
              );
            })}
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="flex h-full min-h-0 w-full bg-background">
      {/* Column 1: Character Index */}
      <aside className="w-48 border-r border-border bg-card/40 flex flex-col flex-shrink-0">
        <div className="px-3 py-3 border-b border-border">
          <h2 className={`text-sm font-mono text-primary ${glowClass}`}>[INDEX]</h2>
        </div>
        <ScrollArea className="flex-1">
          {charactersLoading ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : charactersError ? (
            <div className="p-3 text-xs text-destructive font-mono">
              {charactersErrorData instanceof Error ? charactersErrorData.message : "Error"}
            </div>
          ) : (
            <div className="py-1">
              {characters.map((character) => {
                const isActive = character.id === selectedCharacterId;
                return (
                  <button
                    key={character.id}
                    type="button"
                    className={cn(
                      "w-full text-left px-3 py-2 font-mono text-sm transition-colors",
                      isActive
                        ? `bg-primary/10 text-primary ${glowClass}`
                        : "hover:bg-card/70 text-foreground/80"
                    )}
                    onClick={() => setSelectedCharacterId(character.id)}
                  >
                    <span className="truncate block">{character.name}</span>
                  </button>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </aside>

      {/* Column 2: Section Outline */}
      {selectedCharacter && (
        <aside className="w-52 border-r border-border bg-card/20 flex flex-col flex-shrink-0">
          <div className="px-3 py-3 border-b border-border">
            <h2 className={`text-sm font-mono text-primary ${glowClass} truncate`}>{selectedCharacter.name}</h2>
          </div>
          <ScrollArea className="flex-1">
            <div className="py-1">
              {SECTIONS.map((section) => {
                const hasContent = sectionHasContent(section.id);
                const isSelected = selectedSection === section.id;
                const isCollapsible = section.collapsible;
                const isExpanded = section.id === "psychology" ? psychologyExpanded :
                                   section.id === "relationships" ? relationshipsExpanded : true;

                if (isCollapsible) {
                  return (
                    <div key={section.id}>
                      <button
                        type="button"
                        className={cn(
                          "w-full text-left px-3 py-2 flex items-center gap-2 font-mono text-xs transition-colors",
                          isSelected && !selectedPsychologyField && !selectedRelationshipId
                            ? `bg-primary/10 text-primary ${glowClass}`
                            : hasContent
                              ? "hover:bg-card/70 text-foreground/80"
                              : "text-muted-foreground/50"
                        )}
                        onClick={() => {
                          if (section.id === "psychology") {
                            setPsychologyExpanded(!psychologyExpanded);
                            if (!psychologyExpanded) {
                              setSelectedSection("psychology");
                              setSelectedPsychologyField(null);
                            }
                          } else if (section.id === "relationships") {
                            setRelationshipsExpanded(!relationshipsExpanded);
                            if (!relationshipsExpanded) {
                              setSelectedSection("relationships");
                              setSelectedRelationshipId(null);
                            }
                          }
                        }}
                      >
                        {isExpanded ? <ChevronDown className="h-3 w-3 flex-shrink-0" /> : <ChevronRight className="h-3 w-3 flex-shrink-0" />}
                        {section.icon}
                        <span className="flex-1 truncate">{section.label}</span>
                        {isSelected && !selectedPsychologyField && !selectedRelationshipId && (
                          <CircleDot className="h-3 w-3 text-primary flex-shrink-0" />
                        )}
                      </button>

                      {/* Nested Psychology subsections */}
                      {section.id === "psychology" && isExpanded && psychologyRecord && (
                        <div className="ml-4 border-l border-border/30">
                          {PSYCHOLOGY_FIELDS.map((field) => {
                            const fieldValue = psychologyRecord[field.id];
                            if (!fieldValue) return null;
                            const isFieldSelected = selectedSection === "psychology" && selectedPsychologyField === field.id;
                            return (
                              <button
                                key={field.id}
                                type="button"
                                className={cn(
                                  "w-full text-left px-3 py-1.5 flex items-center gap-2 font-mono text-[11px] transition-colors",
                                  isFieldSelected
                                    ? `bg-primary/10 text-primary ${glowClass}`
                                    : "hover:bg-card/70 text-foreground/60"
                                )}
                                onClick={() => {
                                  setSelectedSection("psychology");
                                  setSelectedPsychologyField(field.id);
                                }}
                              >
                                <Circle className="h-2 w-2 flex-shrink-0" />
                                <span className="truncate">{field.label}</span>
                                {isFieldSelected && <CircleDot className="h-2.5 w-2.5 text-primary flex-shrink-0 ml-auto" />}
                              </button>
                            );
                          })}
                        </div>
                      )}

                      {/* Nested Relationships subsections */}
                      {section.id === "relationships" && isExpanded && relationshipPairs.length > 0 && (
                        <div className="ml-4 border-l border-border/30">
                          {relationshipPairs.map((pair) => {
                            const counterpartName = characterNameById(pair.counterpartId);
                            const isRelSelected = selectedSection === "relationships" && selectedRelationshipId === pair.counterpartId;
                            return (
                              <button
                                key={pair.counterpartId}
                                type="button"
                                className={cn(
                                  "w-full text-left px-3 py-1.5 flex items-center gap-2 font-mono text-[11px] transition-colors",
                                  isRelSelected
                                    ? `bg-primary/10 text-primary ${glowClass}`
                                    : "hover:bg-card/70 text-foreground/60"
                                )}
                                onClick={() => {
                                  setSelectedSection("relationships");
                                  setSelectedRelationshipId(pair.counterpartId);
                                }}
                              >
                                <Circle className="h-2 w-2 flex-shrink-0" />
                                <span className="truncate">{counterpartName}</span>
                                {isRelSelected && <CircleDot className="h-2.5 w-2.5 text-primary flex-shrink-0 ml-auto" />}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                }

                return (
                  <button
                    key={section.id}
                    type="button"
                    className={cn(
                      "w-full text-left px-3 py-2 flex items-center gap-2 font-mono text-xs transition-colors",
                      isSelected
                        ? `bg-primary/10 text-primary ${glowClass}`
                        : hasContent
                          ? "hover:bg-card/70 text-foreground/80"
                          : "text-muted-foreground/50"
                    )}
                    onClick={() => setSelectedSection(section.id)}
                    disabled={!hasContent}
                  >
                    <span className="w-3 flex-shrink-0" /> {/* Spacer for alignment */}
                    {section.icon}
                    <span className="flex-1 truncate">{section.label}</span>
                    {isSelected && <CircleDot className="h-3 w-3 text-primary flex-shrink-0" />}
                  </button>
                );
              })}
            </div>
          </ScrollArea>
        </aside>
      )}

      {/* Column 3: Content - Portrait as background element */}
      <main className="flex-1 min-h-0 overflow-hidden flex flex-col relative">
        {selectedCharacter ? (
          <>
            {/* Portrait background - fills container, minimal gradient for text readability
                Uses object-contain to preserve full image including ornamental borders */}
            <div className="absolute inset-0 pointer-events-none z-0 flex items-start justify-end">
              {mainImage ? (
                <img
                  src={mainImage.filePath}
                  alt={selectedCharacter.name}
                  className="max-w-full max-h-full object-contain object-right-top"
                  style={{
                    maskImage: "linear-gradient(to left, black 85%, transparent 100%)",
                    WebkitMaskImage: "linear-gradient(to left, black 85%, transparent 100%)",
                  }}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-muted/20">
                  <Users className="h-24 w-24 text-muted-foreground/30" />
                </div>
              )}
            </div>

            {/* Portrait-only view: just character name and upload controls */}
            {!selectedSection ? (
              <div className="flex-1 flex flex-col items-center justify-center relative z-10">
                <h1 className={`text-3xl font-mono text-primary ${glowClass} mb-4`}>{selectedCharacter.name}</h1>
                <p className="text-sm text-muted-foreground font-mono mb-6">Select a section to view details</p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                    className="font-mono text-xs"
                  >
                    {uploading ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Upload className="h-3 w-3 mr-1" />}
                    Upload Portrait
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setGalleryOpen(true)}
                    className="font-mono text-xs"
                  >
                    <ImageIcon className="h-3 w-3 mr-1" />
                    Gallery
                  </Button>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/jpg"
                  multiple
                  onChange={handleQuickUpload}
                  className="hidden"
                />
              </div>
            ) : (
              /* Content overlay view */
              <ScrollArea className="flex-1 relative z-10">
                <div className="p-6 pr-24">
                  {/* Gradient overlay for readability over portrait */}
                  <div
                    className="absolute inset-0 pointer-events-none z-0"
                    style={{
                      background: "linear-gradient(to right, hsl(var(--background)) 60%, transparent 100%)",
                    }}
                  />
                  <div className="relative z-10">
                    <div className="mb-4">
                      <h1 className={`text-xl font-mono text-primary ${glowClass}`}>{selectedCharacter.name}</h1>
                      <p className="text-xs text-muted-foreground font-mono mt-1">
                        {selectedPsychologyField
                          ? PSYCHOLOGY_FIELDS.find(f => f.id === selectedPsychologyField)?.label
                          : selectedRelationshipId
                            ? characterNameById(selectedRelationshipId)
                            : SECTIONS.find(s => s.id === selectedSection)?.label || ""}
                      </p>
                    </div>
                    <div className="prose prose-sm max-w-2xl">
                      {renderSectionContent()}
                    </div>
                  </div>
                </div>
              </ScrollArea>
            )}
          </>
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground font-mono">
            Select a character to view details.
          </div>
        )}
      </main>

      {/* Image Gallery Modal */}
      {selectedCharacter && (
        <ImageGalleryModal
          open={galleryOpen}
          onOpenChange={setGalleryOpen}
          images={characterImages}
          entityId={selectedCharacter.id}
          entityType="character"
          onUpload={async (files) => {
            await uploadImagesMutation.mutateAsync(files);
          }}
          onSetMain={async (imageId) => {
            await setMainImageMutation.mutateAsync(imageId);
          }}
          onDelete={async (imageId) => {
            await deleteImageMutation.mutateAsync(imageId);
          }}
        />
      )}
    </div>
  );
}
