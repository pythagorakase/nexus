import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { User, Users, Brain, Heart, Loader2, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { Character, CharacterRelationship, CharacterPsychology } from "@shared/schema";
import alexPortrait from "@assets/Alex - Art Nouveau Choker Frame - Portrait_1759207751777.png";

interface CharacterGroup {
  label: string;
  startId: number;
  endId: number;
}

const characterGroups: CharacterGroup[] = [
  { label: "Main Characters", startId: 1, endId: 10 },
  { label: "Supporting Characters", startId: 11, endId: 20 },
  { label: "Minor Characters (21-30)", startId: 21, endId: 30 },
  { label: "Minor Characters (31-40)", startId: 31, endId: 40 },
  { label: "Background Characters", startId: 41, endId: 1000 },
];

export function CharactersTab() {
  const [selectedCharacter, setSelectedCharacter] = useState<Character | null>(null);
  const [showRelationships, setShowRelationships] = useState(false);
  const [showPsychology, setShowPsychology] = useState(false);
  const [openGroups, setOpenGroups] = useState<string[]>(["Main Characters"]);

  // Fetch all characters
  const { data: allCharacters = [], isLoading: charactersLoading } = useQuery<Character[]>({
    queryKey: ["/api/characters"],
  });

  // Fetch relationships for selected character
  const { data: relationships = [] } = useQuery<CharacterRelationship[]>({
    queryKey: ["/api/characters", selectedCharacter?.id, "relationships"],
    queryFn: () =>
      fetch(`/api/characters/${selectedCharacter?.id}/relationships`).then((r) => r.json()),
    enabled: !!selectedCharacter && showRelationships,
  });

  // Fetch psychology for selected character
  const { data: psychology } = useQuery<CharacterPsychology>({
    queryKey: ["/api/characters", selectedCharacter?.id, "psychology"],
    queryFn: () =>
      fetch(`/api/characters/${selectedCharacter?.id}/psychology`).then((r) => 
        r.ok ? r.json() : null
      ),
    enabled: !!selectedCharacter && showPsychology,
  });

  const toggleGroup = (groupLabel: string) => {
    setOpenGroups((prev) =>
      prev.includes(groupLabel)
        ? prev.filter((g) => g !== groupLabel)
        : [...prev, groupLabel]
    );
  };

  const getCharacterImage = (character: Character) => {
    if (character.id === 1) {
      return alexPortrait;
    }
    return null;
  };

  const renderPsychologyField = (field: any, title: string) => {
    if (!field) return null;

    return (
      <div className="space-y-2">
        <h4 className="text-xs font-mono text-primary terminal-glow">{title}</h4>
        {typeof field === "object" && !Array.isArray(field) ? (
          <div className="space-y-1 text-xs">
            {Object.entries(field).map(([key, value]) => (
              <div key={key}>
                <span className="text-muted-foreground">{key}: </span>
                <span className="text-foreground">
                  {Array.isArray(value) ? value.join(", ") : String(value)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-foreground">{String(field)}</div>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-full bg-background">
      <ScrollArea className="flex-1">
        <div className="p-6 space-y-6">
          {charactersLoading ? (
            <div className="flex items-center justify-center p-16">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : (
            characterGroups.map((group) => {
              const groupCharacters = allCharacters.filter(
                (c) => c.id >= group.startId && c.id <= group.endId
              );

              if (groupCharacters.length === 0) return null;

              const isOpen = openGroups.includes(group.label);

              return (
                <Collapsible
                  key={group.label}
                  open={isOpen}
                  onOpenChange={() => toggleGroup(group.label)}
                >
                  <CollapsibleTrigger asChild>
                    <div className="flex items-center justify-between p-4 bg-card/30 border border-border rounded-md hover-elevate cursor-pointer" data-testid={`button-group-${group.label}`}>
                      <h3 className="text-sm font-mono text-primary terminal-glow">
                        {group.label} ({groupCharacters.length})
                      </h3>
                      <ChevronDown
                        className={`h-4 w-4 text-muted-foreground transition-transform ${
                          isOpen ? "rotate-180" : ""
                        }`}
                      />
                    </div>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {groupCharacters.map((character) => {
                        const image = getCharacterImage(character);

                        return (
                          <Card
                            key={character.id}
                            className="bg-card/50 border-border hover-elevate cursor-pointer"
                            onClick={() => {
                              setSelectedCharacter(character);
                              setShowRelationships(false);
                              setShowPsychology(false);
                            }}
                            data-testid={`card-character-${character.id}`}
                          >
                            <CardHeader className="pb-3">
                              <div className="flex items-start gap-3">
                                <div className="w-16 h-16 rounded-md overflow-hidden bg-muted/20 border border-border flex-shrink-0">
                                  {image ? (
                                    <img
                                      src={image}
                                      alt={character.name}
                                      className="w-full h-full object-cover"
                                    />
                                  ) : (
                                    <div className="w-full h-full flex items-center justify-center bg-gradient-to-b from-muted/10 to-muted/30">
                                      <User className="h-8 w-8 text-muted-foreground/50" />
                                    </div>
                                  )}
                                </div>
                                <div className="flex-1 min-w-0">
                                  <h3 className="text-sm font-mono text-primary terminal-glow truncate">
                                    {character.name}
                                  </h3>
                                  <p className="text-xs text-muted-foreground mt-1">
                                    ID: {character.id}
                                  </p>
                                </div>
                              </div>
                            </CardHeader>
                            <CardContent>
                              <div className="space-y-2 text-xs">
                                {character.summary && (
                                  <p className="text-foreground line-clamp-3">{character.summary}</p>
                                )}
                                {character.currentLocation && (
                                  <p className="text-muted-foreground">
                                    📍 {character.currentLocation}
                                  </p>
                                )}
                              </div>
                            </CardContent>
                          </Card>
                        );
                      })}
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              );
            })
          )}
        </div>
      </ScrollArea>

      {/* Character Details Modal */}
      <Dialog open={!!selectedCharacter} onOpenChange={() => setSelectedCharacter(null)}>
        <DialogContent className="bg-card border-primary/50 max-w-2xl max-h-[80vh] font-mono">
          <DialogHeader>
            <DialogTitle className="text-primary terminal-glow flex items-center gap-2">
              {selectedCharacter?.name}
              <span className="text-xs text-muted-foreground">(ID: {selectedCharacter?.id})</span>
            </DialogTitle>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh]">
            <div className="space-y-4 text-sm">
              {/* Character Portrait */}
              {selectedCharacter && getCharacterImage(selectedCharacter) && (
                <div className="w-32 h-32 rounded-md overflow-hidden bg-muted/20 border border-border mx-auto">
                  <img
                    src={getCharacterImage(selectedCharacter)!}
                    alt={selectedCharacter.name}
                    className="w-full h-full object-cover"
                  />
                </div>
              )}

              {/* Basic Info */}
              {selectedCharacter?.summary && (
                <div>
                  <h4 className="text-xs text-primary terminal-glow mb-1">Summary</h4>
                  <p className="text-foreground">{selectedCharacter.summary}</p>
                </div>
              )}

              {selectedCharacter?.appearance && (
                <div>
                  <h4 className="text-xs text-primary terminal-glow mb-1">Appearance</h4>
                  <p className="text-foreground">{selectedCharacter.appearance}</p>
                </div>
              )}

              {selectedCharacter?.background && (
                <div>
                  <h4 className="text-xs text-primary terminal-glow mb-1">Background</h4>
                  <p className="text-foreground">{selectedCharacter.background}</p>
                </div>
              )}

              {selectedCharacter?.personality && (
                <div>
                  <h4 className="text-xs text-primary terminal-glow mb-1">Personality</h4>
                  <p className="text-foreground">{selectedCharacter.personality}</p>
                </div>
              )}

              {selectedCharacter?.emotionalState && (
                <div>
                  <h4 className="text-xs text-primary terminal-glow mb-1">Emotional State</h4>
                  <p className="text-foreground">{selectedCharacter.emotionalState}</p>
                </div>
              )}

              {selectedCharacter?.currentActivity && (
                <div>
                  <h4 className="text-xs text-primary terminal-glow mb-1">Current Activity</h4>
                  <p className="text-foreground">{selectedCharacter.currentActivity}</p>
                </div>
              )}

              {selectedCharacter?.currentLocation && (
                <div>
                  <h4 className="text-xs text-primary terminal-glow mb-1">Current Location</h4>
                  <p className="text-foreground">{selectedCharacter.currentLocation}</p>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex gap-2 pt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowRelationships(!showRelationships)}
                  className="font-mono text-xs"
                  data-testid="button-relationships"
                >
                  <Users className="h-3 w-3 mr-1" />
                  Relationships
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowPsychology(!showPsychology)}
                  className="font-mono text-xs"
                  data-testid="button-psychology"
                >
                  <Brain className="h-3 w-3 mr-1" />
                  Psychology
                </Button>
              </div>

              {/* Relationships Section */}
              {showRelationships && (
                <div className="border-t border-border pt-4">
                  <h4 className="text-xs text-primary terminal-glow mb-2">Relationships</h4>
                  {relationships.length > 0 ? (
                    <div className="space-y-3">
                      {relationships.map((rel, idx) => (
                        <div key={idx} className="p-3 bg-muted/10 rounded-md">
                          <div className="flex justify-between items-start mb-1">
                            <span className="text-xs text-foreground">
                              Character {rel.character2Id}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {rel.relationshipType}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground">{rel.dynamic}</p>
                          {rel.recentEvents && (
                            <p className="text-xs text-muted-foreground mt-1">
                              Recent: {rel.recentEvents}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">No relationships found</p>
                  )}
                </div>
              )}

              {/* Psychology Section */}
              {showPsychology && psychology && (
                <div className="border-t border-border pt-4 space-y-3">
                  <h4 className="text-xs text-primary terminal-glow">Psychology Profile</h4>
                  {renderPsychologyField(psychology.selfConcept, "Self Concept")}
                  {renderPsychologyField(psychology.behavior, "Behavior")}
                  {renderPsychologyField(psychology.cognitiveFramework, "Cognitive Framework")}
                  {renderPsychologyField(psychology.temperament, "Temperament")}
                  {renderPsychologyField(psychology.relationalStyle, "Relational Style")}
                  {renderPsychologyField(psychology.defenseMechanisms, "Defense Mechanisms")}
                  {renderPsychologyField(psychology.characterArc, "Character Arc")}
                  {renderPsychologyField(psychology.secrets, "Secrets")}
                </div>
              )}
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  );
}