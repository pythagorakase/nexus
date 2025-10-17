import { useEffect, useMemo, useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Users, Brain, Loader2, ChevronRight, ChevronDown, Upload, Image as ImageIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Character, CharacterRelationship, CharacterPsychology } from "@shared/schema";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ImageGalleryModal, type ImageData } from "@/components/ImageGalleryModal";

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

const renderPsychologyField = (label: string, field: unknown) => {
  if (!field) return null;
  const renderValue = (value: any) => {
    if (Array.isArray(value)) {
      return value.join(", ");
    }
    if (typeof value === "object" && value !== null) {
      return Object.entries(value)
        .map(([key, nested]) => `${key}: ${Array.isArray(nested) ? nested.join(", ") : String(nested)}`)
        .join("\n");
    }
    return String(value);
  };

  return (
    <div className="space-y-1">
      <h4 className="text-xs font-mono text-primary terminal-glow uppercase">{label}</h4>
      <pre className="whitespace-pre-wrap text-xs text-foreground/90 leading-relaxed">
        {renderValue(field)}
      </pre>
    </div>
  );
};

export function CharactersTab() {
  const [selectedCharacterId, setSelectedCharacterId] = useState<number | null>(null);
  const [relationshipsOpen, setRelationshipsOpen] = useState(false);
  const [galleryOpen, setGalleryOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const {
    data: characters = [],
    isLoading: charactersLoading,
    isError: charactersError,
    error: charactersErrorData,
  } = useQuery<Character[]>({
    queryKey: ["/api/characters"],
    select: (data) => [...data].sort((a, b) => a.id - b.id),
  });

  useEffect(() => {
    if (!selectedCharacterId && characters.length > 0) {
      setSelectedCharacterId(characters[0].id);
    }
  }, [characters, selectedCharacterId]);

  const selectedCharacter = useMemo(() => {
    return characters.find((character) => character.id === selectedCharacterId) ?? null;
  }, [characters, selectedCharacterId]);

  useEffect(() => {
    setRelationshipsOpen(false);
  }, [selectedCharacterId]);

  const {
    data: relationships = [],
    isLoading: relationshipsLoading,
    isError: relationshipsError,
    error: relationshipsErrorData,
  } = useQuery<CharacterRelationship[]>({
    queryKey: ["/api/characters", selectedCharacter?.id, "relationships"],
    queryFn: async () => {
      if (!selectedCharacter) return [];
      const response = await fetch(`/api/characters/${selectedCharacter.id}/relationships`);
      if (response.status === 404) {
        return [];
      }
      if (!response.ok) {
        throw new Error("Failed to load relationships");
      }
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

  const {
    data: psychologyRecord,
    isLoading: psychologyLoading,
    isError: psychologyError,
    error: psychologyErrorData,
  } = useQuery<CharacterPsychology | null>({
    queryKey: ["/api/characters", selectedCharacter?.id, "psychology"],
    queryFn: async () => {
      if (!selectedCharacter) return null;
      const response = await fetch(`/api/characters/${selectedCharacter.id}/psychology`);
      if (response.status === 404) {
        return null;
      }
      if (!response.ok) {
        throw new Error("Failed to load psychology");
      }
      return response.json();
    },
    enabled: !!selectedCharacter,
  });

  const {
    data: characterImages = [],
    isLoading: imagesLoading,
  } = useQuery<ImageData[]>({
    queryKey: ["/api/characters", selectedCharacter?.id, "images"],
    queryFn: async () => {
      if (!selectedCharacter) return [];
      const response = await fetch(`/api/characters/${selectedCharacter.id}/images`);
      if (!response.ok) {
        throw new Error("Failed to load images");
      }
      return response.json();
    },
    enabled: !!selectedCharacter,
  });

  const uploadImagesMutation = useMutation({
    mutationFn: async (files: FileList) => {
      if (!selectedCharacter) throw new Error("No character selected");
      const formData = new FormData();
      Array.from(files).forEach((file) => formData.append("images", file));

      const response = await fetch(`/api/characters/${selectedCharacter.id}/images`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to upload images");
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/characters", selectedCharacter?.id, "images"] });
    },
  });

  const setMainImageMutation = useMutation({
    mutationFn: async (imageId: number) => {
      if (!selectedCharacter) throw new Error("No character selected");
      const response = await fetch(`/api/characters/${selectedCharacter.id}/images/${imageId}/main`, {
        method: "PUT",
      });
      if (!response.ok) {
        throw new Error("Failed to set main image");
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/characters", selectedCharacter?.id, "images"] });
    },
  });

  const deleteImageMutation = useMutation({
    mutationFn: async (imageId: number) => {
      if (!selectedCharacter) throw new Error("No character selected");
      const response = await fetch(`/api/characters/${selectedCharacter.id}/images/${imageId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error("Failed to delete image");
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/characters", selectedCharacter?.id, "images"] });
    },
  });

  const getPortrait = (_character: Character) => {
    const mainImage = characterImages.find((img) => img.isMain === 1);
    return mainImage?.filePath || null;
  };

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

  const renderRelationshipPerspective = (
    heading: string,
    rel: NormalizedRelationship | undefined,
  ) => {
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
        <div className="space-y-2 text-xs text-foreground/90">
          <div className="flex items-start gap-2">
            <span className="w-24 text-muted-foreground uppercase tracking-wide">Type</span>
            <span className="flex-1">{rel.relationshipType}</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="w-24 text-muted-foreground uppercase tracking-wide">Valence</span>
            <span className="flex-1">{formatValence(rel.emotionalValence)}</span>
          </div>
          {rel.dynamic && (
            <div>
              <div className="text-[11px] text-muted-foreground uppercase tracking-wide mb-1">Dynamic</div>
              <p className="whitespace-pre-wrap leading-relaxed">{rel.dynamic}</p>
            </div>
          )}
          {rel.recentEvents && (
            <div>
              <div className="text-[11px] text-muted-foreground uppercase tracking-wide mb-1">Recent Events</div>
              <p className="whitespace-pre-wrap leading-relaxed">{rel.recentEvents}</p>
            </div>
          )}
          {rel.history && (
            <div>
              <div className="text-[11px] text-muted-foreground uppercase tracking-wide mb-1">History</div>
              <p className="whitespace-pre-wrap leading-relaxed text-foreground">{rel.history}</p>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="flex h-full bg-background">
      <aside className="w-72 border-r border-border bg-card/40 flex flex-col">
        <div className="px-4 py-3 border-b border-border">
          <h2 className="text-sm font-mono text-primary terminal-glow">[CHARACTER INDEX]</h2>
          <p className="text-xs text-muted-foreground">Sorted by ID</p>
        </div>
        <ScrollArea className="flex-1">
          {charactersLoading ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : charactersError ? (
            <div className="p-4 text-xs text-destructive font-mono">
              Failed to load characters: {charactersErrorData instanceof Error ? charactersErrorData.message : "Unknown error"}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {characters.map((character) => {
                const isActive = character.id === selectedCharacterId;
                return (
                  <button
                    key={character.id}
                    type="button"
                    className={`w-full text-left px-4 py-3 flex items-center gap-3 font-mono text-xs transition-colors ${
                      isActive ? "bg-primary/10 text-primary" : "hover:bg-card/70 text-foreground"
                    }`}
                    onClick={() => {
                      setSelectedCharacterId(character.id);
                    }}
                  >
                    <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-primary/20 text-primary">
                      {character.id}
                    </span>
                    <span className="truncate flex-1">{character.name}</span>
                    {isActive && <ChevronRight className="h-3 w-3" />}
                  </button>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </aside>

      <main className="flex-1 overflow-hidden">
        {selectedCharacter ? (
          <div className="h-full overflow-auto p-6 space-y-6">
            <Card className="bg-card/70 border-border">
              <CardHeader className="flex flex-row items-start gap-4">
                <div className="flex-shrink-0">
                  <button
                    onClick={() => setGalleryOpen(true)}
                    className="w-32 max-h-40 rounded-md overflow-hidden border border-border bg-muted/40 flex items-center justify-center hover:border-primary/50 transition-colors cursor-pointer group"
                  >
                    {getPortrait(selectedCharacter) ? (
                      <img
                        src={getPortrait(selectedCharacter)!}
                        alt={selectedCharacter.name}
                        className="max-w-full max-h-40 object-contain group-hover:opacity-80 transition-opacity"
                      />
                    ) : (
                      <div className="w-32 h-32 flex items-center justify-center text-muted-foreground/60 group-hover:text-muted-foreground">
                        <Users className="h-8 w-8" />
                      </div>
                    )}
                  </button>
                  <div className="mt-2 flex gap-1">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploading}
                      className="font-mono text-xs px-2 py-1 h-auto"
                    >
                      {uploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Upload className="h-3 w-3" />}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setGalleryOpen(true)}
                      className="font-mono text-xs px-2 py-1 h-auto"
                    >
                      <ImageIcon className="h-3 w-3" />
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
                <div className="flex-1 min-w-0">
                  <CardTitle className="text-lg font-mono text-primary terminal-glow">
                    {selectedCharacter.name}
                  </CardTitle>
                  <p className="text-xs text-muted-foreground mt-1">ID: {selectedCharacter.id}</p>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm font-mono">
                {selectedCharacter.summary && (
                  <section>
                    <h3 className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Summary</h3>
                    <p className="text-foreground/90 leading-relaxed whitespace-pre-wrap">{selectedCharacter.summary}</p>
                  </section>
                )}
                {selectedCharacter.background && (
                  <section>
                    <h3 className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Background</h3>
                    <p className="text-foreground/90 leading-relaxed whitespace-pre-wrap">{selectedCharacter.background}</p>
                  </section>
                )}
                {selectedCharacter.personality && (
                  <section>
                    <h3 className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Personality</h3>
                    <p className="text-foreground/90 leading-relaxed whitespace-pre-wrap">{selectedCharacter.personality}</p>
                  </section>
                )}
                {selectedCharacter.currentActivity && (
                  <section>
                    <h3 className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Current Activity</h3>
                    <p className="text-foreground/90 leading-relaxed whitespace-pre-wrap">{selectedCharacter.currentActivity}</p>
                  </section>
                )}
                {selectedCharacter.currentLocation && (
                  <section>
                    <h3 className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Current Location</h3>
                    <p className="text-foreground/90 leading-relaxed whitespace-pre-wrap">{selectedCharacter.currentLocation}</p>
                  </section>
                )}
              </CardContent>
            </Card>

            {psychologyLoading ? (
              <Card className="bg-card/60 border-border">
                <CardHeader className="flex flex-row items-center gap-2 text-sm font-mono text-primary">
                  <Brain className="h-4 w-4" />
                  Psychology
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-center h-16 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" />
                  </div>
                </CardContent>
              </Card>
            ) : psychologyError ? (
              <Card className="bg-card/60 border-border">
                <CardHeader className="flex flex-row items-center gap-2 text-sm font-mono text-primary">
                  <Brain className="h-4 w-4" />
                  Psychology
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-destructive">
                    Failed to load psychology: {psychologyErrorData instanceof Error ? psychologyErrorData.message : "Unknown error"}
                  </p>
                </CardContent>
              </Card>
            ) : psychologyRecord ? (
              <Card className="bg-card/60 border-border">
                <CardHeader className="flex flex-row items-center gap-2 text-sm font-mono text-primary">
                  <Brain className="h-4 w-4" />
                  Psychology
                </CardHeader>
                <CardContent className="space-y-4">
                  {renderPsychologyField("Self Concept", psychologyRecord.selfConcept)}
                  {renderPsychologyField("Behavior", psychologyRecord.behavior)}
                  {renderPsychologyField("Cognitive Framework", psychologyRecord.cognitiveFramework)}
                  {renderPsychologyField("Temperament", psychologyRecord.temperament)}
                  {renderPsychologyField("Relational Style", psychologyRecord.relationalStyle)}
                  {renderPsychologyField("Defense Mechanisms", psychologyRecord.defenseMechanisms)}
                  {renderPsychologyField("Character Arc", psychologyRecord.characterArc)}
                  {renderPsychologyField("Secrets", psychologyRecord.secrets)}
                </CardContent>
              </Card>
            ) : null}

            <Card className="bg-card/60 border-border">
              <CardHeader className="flex flex-row items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-mono text-primary">
                  <Users className="h-4 w-4" />
                  Relationships
                </div>
                {normalizedRelationships.length > 0 && (
                  <span className="text-xs text-muted-foreground">
                    {normalizedRelationships.length} records
                  </span>
                )}
              </CardHeader>
              <CardContent className="space-y-3">
                {relationshipsLoading ? (
                  <div className="flex items-center justify-center h-16 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" />
                  </div>
                ) : relationshipsError ? (
                  <p className="text-xs text-destructive">
                    Failed to load relationships: {relationshipsErrorData instanceof Error ? relationshipsErrorData.message : "Unknown error"}
                  </p>
                ) : relationshipPairs.length > 0 ? (
                  <Collapsible open={relationshipsOpen} onOpenChange={setRelationshipsOpen}>
                    <CollapsibleTrigger asChild>
                      <Button
                        variant="ghost"
                        className="w-full justify-between px-3 py-2 text-xs font-mono hover:bg-card/70"
                      >
                        <span className="flex items-center gap-2">
                          {relationshipsOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                          {relationshipsOpen ? "Hide relationship matrix" : "Show relationship matrix"}
                        </span>
                        <span className="text-[11px] text-muted-foreground">
                          {relationshipPairs.length} counterpart{relationshipPairs.length === 1 ? "" : "s"}
                        </span>
                      </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="space-y-3 pt-3">
                      {relationshipPairs.map((pair) => {
                        const counterpartName = characterNameById(pair.counterpartId);
                        return (
                          <div
                            key={pair.counterpartId}
                            className="border border-border/40 rounded-md bg-background/70 p-4 space-y-4"
                          >
                            <div className="flex items-center justify-between text-sm font-mono text-primary terminal-glow">
                              <span>{counterpartName}</span>
                              <span className="text-[11px] text-muted-foreground uppercase tracking-wide">
                                ID {pair.counterpartId}
                              </span>
                            </div>
                            <div className="grid gap-4 md:grid-cols-2">
                              {renderRelationshipPerspective(selectedCharacter.name, pair.fromSelected)}
                              {renderRelationshipPerspective(counterpartName, pair.toSelected)}
                            </div>
                          </div>
                        );
                      })}
                    </CollapsibleContent>
                  </Collapsible>
                ) : (
                  <p className="text-xs text-muted-foreground">No relationships documented.</p>
                )}
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground font-mono">
            Select a character to view details.
          </div>
        )}
      </main>

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
