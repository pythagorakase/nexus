import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Users, Brain, Loader2, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Character, CharacterRelationship, CharacterPsychology } from "@shared/schema";
import alexPortrait from "@assets/Alex - Art Nouveau Choker Frame - Portrait_1759207751777.png";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

export function CharactersTab() {
  const [selectedCharacterId, setSelectedCharacterId] = useState<number | null>(null);

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

  const getPortrait = (character: Character) => {
    return character.id === 1 ? alexPortrait : null;
  };

  const characterNameById = (id: number) => {
    return characters.find((character) => character.id === id)?.name ?? `Character ${id}`;
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
              Failed to load characters: {charactersErrorData instanceof Error ? charactersErrorData.message : 'Unknown error'}
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
                <div className="w-20 h-20 rounded-md overflow-hidden border border-border bg-muted/40 flex-shrink-0">
                  {getPortrait(selectedCharacter) ? (
                    <img
                      src={getPortrait(selectedCharacter)!}
                      alt={selectedCharacter.name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-muted-foreground/60">
                      <Users className="h-6 w-6" />
                    </div>
                  )}
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
                    <p className="text-foreground/90 leading-relaxed">{selectedCharacter.summary}</p>
                  </section>
                )}
                {selectedCharacter.background && (
                  <section>
                    <h3 className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Background</h3>
                    <p className="text-foreground/90 leading-relaxed">{selectedCharacter.background}</p>
                  </section>
                )}
                {selectedCharacter.personality && (
                  <section>
                    <h3 className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Personality</h3>
                    <p className="text-foreground/90 leading-relaxed">{selectedCharacter.personality}</p>
                  </section>
                )}
                {selectedCharacter.currentActivity && (
                  <section>
                    <h3 className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Current Activity</h3>
                    <p className="text-foreground/90 leading-relaxed">{selectedCharacter.currentActivity}</p>
                  </section>
                )}
                {selectedCharacter.currentLocation && (
                  <section>
                    <h3 className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Current Location</h3>
                    <p className="text-foreground/90 leading-relaxed">{selectedCharacter.currentLocation}</p>
                  </section>
                )}
              </CardContent>
            </Card>

            <Card className="bg-card/60 border-border">
              <CardHeader className="flex flex-row items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-mono text-primary">
                  <Users className="h-4 w-4" />
                  Relationships
                </div>
              </CardHeader>
              <CardContent>
                {relationshipsLoading ? (
                  <div className="flex items-center justify-center h-16 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" />
                  </div>
                ) : relationshipsError ? (
                  <p className="text-xs text-destructive">
                    Failed to load relationships: {relationshipsErrorData instanceof Error ? relationshipsErrorData.message : 'Unknown error'}
                  </p>
                ) : relationships.length > 0 ? (
                  <div className="space-y-3 text-sm">
                    {relationships.map((rel, index) => {
                      const fromApi = rel as CharacterRelationship & {
                        character1_id?: number;
                        character2_id?: number;
                        relationship_type?: string;
                        recent_events?: string;
                      };
                      const character1Id = fromApi.character1Id ?? fromApi.character1_id ?? 0;
                      const character2Id = fromApi.character2Id ?? fromApi.character2_id ?? 0;
                      const relationshipType = fromApi.relationshipType ?? fromApi.relationship_type ?? "unknown";
                      const recentEvents = fromApi.recentEvents ?? fromApi.recent_events ?? null;
                      const counterpartId = character1Id === selectedCharacter.id ? character2Id : character1Id;

                      return (
                        <Collapsible key={`${character1Id}-${character2Id}-${index}`}>
                          <CollapsibleTrigger asChild>
                            <Button
                              variant="ghost"
                              className="w-full justify-between px-3 py-2 text-xs font-mono text-foreground border border-border/40 hover:bg-card/70"
                            >
                              <span className="truncate text-left">{characterNameById(counterpartId)}</span>
                              <span className="text-muted-foreground ml-3">{relationshipType}</span>
                            </Button>
                          </CollapsibleTrigger>
                          <CollapsibleContent className="border border-border/40 bg-background/70 rounded-md p-3 text-xs space-y-2 mt-2">
                            <div className="text-muted-foreground/90 leading-relaxed whitespace-pre-wrap">{rel.dynamic}</div>
                            {recentEvents && (
                              <div className="text-muted-foreground/80 leading-relaxed whitespace-pre-wrap">
                                <span className="font-semibold text-primary">Recent:</span> {recentEvents}
                              </div>
                            )}
                            {('history' in rel) && rel.history && (
                              <div className="text-muted-foreground/70 leading-relaxed whitespace-pre-wrap">
                                <span className="font-semibold text-primary">History:</span> {rel.history}
                              </div>
                            )}
                          </CollapsibleContent>
                        </Collapsible>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">No relationships documented.</p>
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
                    Failed to load psychology: {psychologyErrorData instanceof Error ? psychologyErrorData.message : 'Unknown error'}
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
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground font-mono">
            Select a character to view details.
          </div>
        )}
      </main>
    </div>
  );
}
