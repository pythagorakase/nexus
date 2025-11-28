import {
  useState,
  useEffect,
  useCallback,
  useRef,
  type MutableRefObject,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { StatusBar } from "./StatusBar";
import { NarrativeTab, type ChunkWithMetadata } from "./NarrativeTab";
import { MapTab } from "./MapTab";
import { CharactersTab } from "./CharactersTab";
import AuditionTab from "@/pages/AuditionTab";
import { SettingsTab } from "@/pages/SettingsTab";
import { FontProvider } from "@/contexts/FontContext";
import { useTheme } from "@/contexts/ThemeContext";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Book, Map, Users, Settings } from "lucide-react";
import { toast } from "@/hooks/use-toast";
import { useNarrativeGeneration } from "@/hooks/useNarrativeGeneration";
import type { EntityChanges } from "@/types/narrative";

// Timing constants for APEX status transitions and UI updates
const TIMEOUTS = {
  READY_TRANSITION: 1200,           // Delay before transitioning to READY status
  GENERATING_DEBOUNCE: 300,         // Debounce for GENERATING status during LLM call
  TRANSMITTING_FALLBACK: 600,       // Fallback to GENERATING from TRANSMITTING
  ELAPSED_DISPLAY_THRESHOLD: 5000,  // Show elapsed time after 5 seconds
  ELAPSED_UPDATE_INTERVAL: 500,     // Update elapsed time every 500ms
  MODEL_STATUS_POLL: 5000,          // Poll model status every 5 seconds
  APEX_CONNECTIVITY_POLL: 10000,    // Poll APEX connectivity every 10 seconds
  SETTINGS_REFETCH: 60000,          // Refetch settings every 60 seconds (optimized - settings rarely change)
  LATEST_CHUNK_REFETCH: 30000,      // Refetch latest chunk every 30 seconds (optimized - use WebSocket for real-time updates)
} as const;

interface SettingsPayload {
  ["Agent Settings"]?: {
    global?: {
      model?: {
        default_model?: string;
      };
      llm?: {
        api_base?: string;
      };
      narrative?: {
        test_mode?: boolean;
      };
    };
  };
}

export function NexusLayout() {
  const [currentModel, setCurrentModel] = useState("LOADING");
  const [currentModelId, setCurrentModelId] = useState("");
  type ModelStatus = "unloaded" | "loading" | "loaded" | "generating";
  type StableModelStatus = Exclude<ModelStatus, "generating">;
  const [modelStatus, internalSetModelStatus] = useState<ModelStatus>("unloaded");
  const stableModelStatusRef = useRef<StableModelStatus>("unloaded");
  const setModelStatus = useCallback((status: ModelStatus) => {
    if (status !== "generating") {
      stableModelStatusRef.current = status as StableModelStatus;
    }
    internalSetModelStatus(status);
  }, []);
  const [isStoryMode, setIsStoryMode] = useState(true);
  const [isTestModeEnabled, setIsTestModeEnabled] = useState(false);
  const [apexStatus, setApexStatus] = useState<
    "OFFLINE" | "READY" | "TRANSMITTING" | "GENERATING" | "RECEIVING"
  >("READY");
  const apexStatusRef = useRef(apexStatus);
  const generatingTimeoutRef = useRef<number | null>(null);
  const readyTimeoutRef = useRef<number | null>(null);
  const isMountedRef = useRef(true);
  const { isCyberpunk, isGilded } = useTheme();
  const glowClass = isGilded ? "deco-glow" : "terminal-glow";
  // Read initial tab from URL query param (e.g., /nexus?tab=settings)
  const [activeTab, setActiveTab] = useState(() => {
    const searchParams = new URLSearchParams(window.location.search);
    return searchParams.get('tab') || 'narrative';
  });
  const [selectedChunk, setSelectedChunk] = useState<ChunkWithMetadata | null>(null);
  const [currentChunkLocation, setCurrentChunkLocation] = useState<string | null>("Night City Center");
  const [isInputExpanded, setIsInputExpanded] = useState(false);
  const [activeSlot, setActiveSlot] = useState<number | null>(() => {
    const storedSlot = localStorage.getItem("activeSlot");
    return storedSlot ? parseInt(storedSlot, 10) : null;
  });

  useEffect(() => {
    apexStatusRef.current = apexStatus;
  }, [apexStatus]);

  const handleChunkSelection = useCallback((chunk: ChunkWithMetadata | null) => {
    setSelectedChunk(chunk);
    if (chunk?.metadata?.slug) {
      setCurrentChunkLocation(chunk.metadata.slug);
    }
  }, []);

  // Fetch settings to get model name
  const {
    data: settings,
    isSuccess: settingsLoaded,
    isError: settingsError,
  } = useQuery<SettingsPayload>({
    queryKey: ["/api/settings"],
    refetchInterval: TIMEOUTS.SETTINGS_REFETCH,
  });

  const clearTimeoutRef = useCallback((ref: MutableRefObject<number | null>) => {
    if (ref.current !== null) {
      window.clearTimeout(ref.current);
      ref.current = null;
    }
  }, []);

  const handleCompleteEvent = useCallback(() => {
    clearTimeoutRef(generatingTimeoutRef);
    clearTimeoutRef(readyTimeoutRef);
    setApexStatus("RECEIVING");
    readyTimeoutRef.current = window.setTimeout(() => {
      if (!isMountedRef.current) {
        return;
      }
      setApexStatus("READY");
    }, TIMEOUTS.READY_TRANSITION);
  }, [clearTimeoutRef, setApexStatus]);

  const handlePhaseEvent = useCallback(
    (phase: string | null | undefined) => {
      clearTimeoutRef(generatingTimeoutRef);
      clearTimeoutRef(readyTimeoutRef);

      if (!phase) {
        setApexStatus("READY");
        return;
      }

      if (phase === "complete") {
        handleCompleteEvent();
        return;
      }

      if (phase === "error") {
        setApexStatus("OFFLINE");
        return;
      }

      if (phase === "calling_llm" || phase === "processing_response") {
        setApexStatus("GENERATING");
        generatingTimeoutRef.current = window.setTimeout(() => {
          if (!isMountedRef.current) {
            return;
          }
          setApexStatus("GENERATING");
        }, TIMEOUTS.GENERATING_DEBOUNCE);
        return;
      }

      if (phase === "initiated" || phase === "loading_chunk" || phase === "building_context") {
        setApexStatus("TRANSMITTING");
        generatingTimeoutRef.current = window.setTimeout(() => {
          if (!isMountedRef.current) {
            return;
          }
          setApexStatus("GENERATING");
        }, TIMEOUTS.TRANSMITTING_FALLBACK);
        return;
      }

      setApexStatus("READY");
    },
    [clearTimeoutRef, handleCompleteEvent, setApexStatus],
  );

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      clearTimeoutRef(generatingTimeoutRef);
      clearTimeoutRef(readyTimeoutRef);
    };
  }, [clearTimeoutRef]);

  // Fetch latest chunk for chapter info
  const { data: latestChunk } = useQuery<{
    id: number;
    rawText: string;
    createdAt: string;
    metadata?: {
      season: number | null;
      episode: number | null;
      scene: number | null;
    };
  }>({
    queryKey: ["/api/narrative/latest-chunk", activeSlot],
    queryFn: async () => {
      if (!activeSlot) return null;
      const res = await fetch(`/api/narrative/latest-chunk?slot=${activeSlot}`);
      if (!res.ok) throw new Error("Failed to fetch latest chunk");
      return res.json();
    },
    enabled: !!activeSlot,
    refetchInterval: TIMEOUTS.LATEST_CHUNK_REFETCH,
  });

  // Narrative generation hook - encapsulates WebSocket, state management, and approval flow
  const narrative = useNarrativeGeneration({
    allowedChunkId: latestChunk?.id ?? null,
    slot: activeSlot,
    onPhaseChange: (phase) => {
      handlePhaseEvent(phase);
    },
    onComplete: () => {
      handleCompleteEvent();
    },
    onError: () => {
      setApexStatus("OFFLINE");
    },
  });

  // Parse model name from settings
  useEffect(() => {
    if (settingsLoaded) {
      const defaultModel = settings?.["Agent Settings"]?.global?.model?.default_model;

      if (defaultModel) {
        const modelName = defaultModel.includes("/")
          ? defaultModel.split("/").pop()!.toUpperCase()
          : defaultModel.toUpperCase();
        setCurrentModel(modelName);
        setCurrentModelId(defaultModel); // Store full ID for API calls
      } else {
        setCurrentModel("UNCONFIGURED");
        setCurrentModelId("");
      }
      const testMode = Boolean(settings?.["Agent Settings"]?.global?.narrative?.test_mode);
      setIsTestModeEnabled(testMode);
    } else if (settingsError) {
      setCurrentModel("UNAVAILABLE");
      setCurrentModelId("");
      setIsTestModeEnabled(false);
    }
  }, [settings, settingsError, settingsLoaded]);

  const refreshModelStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/models/status");
      if (response.ok) {
        const data = await response.json();
        const loadedModels = Array.isArray(data.loaded_models) ? data.loaded_models : [];
        setModelStatus(loadedModels.length > 0 ? "loaded" : "unloaded");
      } else {
        setModelStatus("unloaded");
      }
    } catch {
      setModelStatus("unloaded");
    }
  }, [setModelStatus]);


  // Check if LLM server is running and has model loaded
  useEffect(() => {
    refreshModelStatus();
    const interval = setInterval(refreshModelStatus, TIMEOUTS.MODEL_STATUS_POLL);
    return () => clearInterval(interval);
  }, [refreshModelStatus]);

  useEffect(() => {
    if (apexStatus === "GENERATING" && stableModelStatusRef.current === "loaded") {
      internalSetModelStatus("generating");
    } else if (apexStatus !== "GENERATING" && modelStatus === "generating") {
      internalSetModelStatus(stableModelStatusRef.current);
    }
  }, [apexStatus, modelStatus]);

  // Check APEX connectivity
  useEffect(() => {
    const checkApexConnectivity = async () => {
      try {
        // Check if backend is reachable
        const response = await fetch("/api/settings", { method: "HEAD" });
        if (response.ok) {
          // Backend is reachable, set to READY if not in other states
          if (apexStatus === "OFFLINE") {
            setApexStatus("READY");
          }
        } else {
          setApexStatus("OFFLINE");
        }
      } catch {
        // No connectivity
        setApexStatus("OFFLINE");
      }
    };

    checkApexConnectivity();
    const interval = setInterval(checkApexConnectivity, TIMEOUTS.APEX_CONNECTIVITY_POLL);
    return () => clearInterval(interval);
  }, [apexStatus]);


  const handleCommand = (command: string) => {
    console.log("Command:", command);

    if (command.startsWith("/")) {
      const [cmd, ...args] = command.slice(1).split(" ");

      switch (cmd.toLowerCase()) {
        case "tab":
          const tabArg = args.join(" ").trim().toLowerCase();
          if (["narrative", "map", "characters", "audition", "settings"].includes(tabArg)) {
            setActiveTab(tabArg);
          }
          break;
        case "story":
          setIsStoryMode(true);
          setApexStatus("READY");
          break;
        case "model":
          const modelArg = args.join(" ").trim();
          if (modelArg) {
            setCurrentModel(modelArg);
          }
          break;
        case "help":
          console.log(
            "Available commands: /tab <narrative|map|characters>, /story, /model <name>, /help"
          );
          break;
        default:
          console.log("Unknown command:", cmd);
      }
    } else if (isStoryMode) {
      narrative.triggerNarrativeTurn(selectedChunk, command);
      setIsInputExpanded(false);
    }
  };


  const phaseLabels: Record<string, string> = {
    initiated: "Request received...",
    loading_chunk: "Loading parent chunk...",
    building_context: "Assembling context package...",
    calling_llm: "Calling LORE / LOGON...",
    processing_response: "Processing response...",
    complete: "Awaiting approval",
    error: "Generation failed",
  };

  const latestChunkId = latestChunk?.id ?? null;
  const progressLabel = narrative.narrativePhase ? phaseLabels[narrative.narrativePhase] ?? narrative.narrativePhase : null;
  const showElapsed = narrative.elapsedMs > TIMEOUTS.ELAPSED_DISPLAY_THRESHOLD;
  const canContinue = latestChunkId !== null && selectedChunk?.id === latestChunkId;
  const continueDisabled = !canContinue || (narrative.narrativePhase !== null && narrative.narrativePhase !== "error");
  const approvalOpen = narrative.showApprovalModal && !!narrative.incubatorData;
  const entityChanges: EntityChanges = narrative.incubatorData?.entity_changes || {};
  const referenceChanges = narrative.incubatorData?.references || [];
  const characterChanges = Array.isArray(entityChanges?.characters) ? entityChanges.characters : [];
  const locationChanges = Array.isArray(entityChanges?.locations) ? entityChanges.locations : [];
  const factionChanges = Array.isArray(entityChanges?.factions) ? entityChanges.factions : [];
  const referencedCharacters = Array.isArray(referenceChanges) ? referenceChanges.filter((r) => r.entityType === 'character') : [];
  const referencedPlaces = Array.isArray(referenceChanges) ? referenceChanges.filter((r) => r.entityType === 'place') : [];
  const referencedFactions = Array.isArray(referenceChanges) ? referenceChanges.filter((r) => r.entityType === 'faction') : [];
  const tabContentClass = "flex-1 min-h-0 overflow-hidden flex flex-col data-[state=inactive]:hidden";
  const chunkLabel =
    narrative.generationParentChunk?.metadata?.season !== null &&
      narrative.generationParentChunk?.metadata?.season !== undefined &&
      narrative.generationParentChunk?.metadata?.episode !== null &&
      narrative.generationParentChunk?.metadata?.episode !== undefined
      ? `S${String(narrative.generationParentChunk.metadata.season).padStart(2, "0")}E${String(
        narrative.generationParentChunk.metadata.episode,
      ).padStart(2, "0")}`
      : narrative.incubatorData?.parent_chunk_id
        ? `Chunk ${narrative.incubatorData.parent_chunk_id}`
        : "Narrative turn";
  const subtitle = narrative.generationParentChunk?.metadata?.slug || "Awaiting metadata";

  return (
    <FontProvider>
      <div className="h-screen w-full bg-background flex flex-col font-mono overflow-hidden dark animate-fade-in">
        <StatusBar
          model={currentModel}
          modelId={currentModelId}
          season={latestChunk?.metadata?.season ?? 1}
          episode={latestChunk?.metadata?.episode ?? 1}
          scene={latestChunk?.metadata?.scene ?? 1}
          apexStatus={apexStatus}
          isStoryMode={isStoryMode}
          isTestModeEnabled={isTestModeEnabled}
          modelStatus={modelStatus}
          onModelStatusChange={setModelStatus}
          onRefreshModelStatus={refreshModelStatus}
          onNavigate={setActiveTab}
          onHamburgerClick={() => {
            // Can be used for mobile menu in the future
          }}
        />

        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className={`flex-1 flex flex-col min-h-0 overflow-hidden bg-background ${isCyberpunk ? "terminal-scanlines" : ""}`}
        >
          <div className="border-b border-border bg-card/50 overflow-x-auto flex-shrink-0">
            <TabsList className="h-10 bg-transparent border-0 rounded-none p-0 inline-flex min-w-full">
              <TabsTrigger
                value="narrative"
                className={`data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-10 px-3 md:px-4 font-mono text-xs text-primary/70 ${isCyberpunk ? "terminal-glow" : "deco-glow"} flex items-center gap-1 md:gap-2 flex-1 md:flex-initial`}
                data-testid="tab-narrative"
              >
                <Book className="h-3 w-3" />
                <span className="hidden sm:inline">NARRATIVE</span>
                <span className="sm:hidden">NAR</span>
              </TabsTrigger>
              <TabsTrigger
                value="map"
                className={`data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-10 px-3 md:px-4 font-mono text-xs text-primary/70 ${isCyberpunk ? "terminal-glow" : "deco-glow"} flex items-center gap-1 md:gap-2 flex-1 md:flex-initial`}
                data-testid="tab-map"
              >
                <Map className="h-3 w-3" />
                MAP
              </TabsTrigger>
              <TabsTrigger
                value="characters"
                className={`data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-10 px-3 md:px-4 font-mono text-xs text-primary/70 ${isCyberpunk ? "terminal-glow" : "deco-glow"} flex items-center gap-1 md:gap-2 flex-1 md:flex-initial`}
                data-testid="tab-characters"
              >
                <Users className="h-3 w-3" />
                <span className="hidden sm:inline">CHARACTERS</span>
                <span className="sm:hidden">CHAR</span>
              </TabsTrigger>
              <TabsTrigger
                value="settings"
                className={`data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-10 px-3 md:px-4 font-mono text-xs text-primary/70 ${isCyberpunk ? "terminal-glow" : "deco-glow"} flex items-center gap-1 md:gap-2 flex-1 md:flex-initial`}
                data-testid="tab-settings"
              >
                <Settings className="h-3 w-3" />
                <span className="hidden sm:inline">SETTINGS</span>
                <span className="sm:hidden">SET</span>
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="narrative" className={tabContentClass}>
            <NarrativeTab
              onChunkSelected={handleChunkSelection}
              sessionId={narrative.activeNarrativeSession ?? undefined}
              slot={activeSlot}
            />
          </TabsContent>

          <TabsContent value="map" className={tabContentClass}>
            <MapTab currentChunkLocation={currentChunkLocation} slot={activeSlot} />
          </TabsContent>

          <TabsContent value="characters" className={tabContentClass}>
            <CharactersTab slot={activeSlot} />
          </TabsContent>

          <TabsContent value="audition" className={tabContentClass}>
            <AuditionTab />
          </TabsContent>

          <TabsContent value="settings" className={tabContentClass}>
            <SettingsTab />
          </TabsContent>
        </Tabs>

        {activeTab === "narrative" && narrative.narrativePhase && (
          <div className="border-t border-border bg-card/80 text-xs font-mono px-3 py-2 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className={narrative.narrativePhase === "error" ? "text-destructive" : `text-primary ${glowClass}`}>
                {narrative.narrativePhase === "error" ? "!" : ">>"}
              </span>
              <span className={narrative.narrativePhase === "error" ? "text-destructive" : "text-foreground"}>
                {progressLabel}
              </span>
              {narrative.narrativePhase === "error" && narrative.generationError && (
                <span className="text-destructive/80 truncate max-w-[42ch]">{narrative.generationError}</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {showElapsed && (
                <span className="text-muted-foreground">
                  {Math.round(narrative.elapsedMs / 1000)}s elapsed
                </span>
              )}
            </div>
          </div>
        )}
        {activeTab === "narrative" && !narrative.narrativePhase && narrative.generationError && (
          <div className="border-t border-destructive/40 bg-destructive/10 text-destructive font-mono text-xs px-3 py-2 flex items-center justify-between">
            <span>{narrative.generationError}</span>
          </div>
        )}
      </div>

      <Dialog open={approvalOpen} onOpenChange={(open) => !open && narrative.handleCancel()}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span>Review generated narrative</span>
              <div className="flex items-center gap-2">
                {isTestModeEnabled && <Badge variant="destructive">TEST MODE</Badge>}
                {narrative.activeNarrativeSession && (
                  <Badge variant="outline">Session {narrative.activeNarrativeSession.slice(0, 8)}</Badge>
                )}
              </div>
            </DialogTitle>
            <DialogDescription className="font-mono text-xs">
              {chunkLabel} {'->'} proposed chunk {narrative.incubatorData?.chunk_id ?? "pending"}
            </DialogDescription>
          </DialogHeader>

          {narrative.incubatorData && (
            <div className="grid gap-4 md:grid-cols-3 text-sm">
              <div className="md:col-span-2 space-y-3">
                <div className="space-y-1">
                  <div className={`text-primary ${glowClass} font-mono text-sm`}>{chunkLabel}</div>
                  <div className="text-muted-foreground italic text-xs">{subtitle}</div>
                  <div className="text-muted-foreground text-xs">
                    {narrative.incubatorData.time_delta || "Time delta pending"}
                  </div>
                </div>
                <ScrollArea className="h-72 rounded border border-border bg-card/70 p-4">
                  <div className="whitespace-pre-wrap leading-relaxed text-foreground">
                    {narrative.incubatorData.storyteller_text || "No narrative captured"}
                  </div>
                </ScrollArea>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-muted-foreground">Entity changes</span>
                  <Badge variant="outline">{narrative.incubatorData.entity_update_count ?? 0}</Badge>
                </div>
                <div className="rounded border border-border bg-card/60 p-3 space-y-3 text-xs text-foreground">
                  {characterChanges.length > 0 ? (
                    <div>
                      <div className="font-mono text-[11px] text-muted-foreground mb-1">Characters</div>
                      <ul className="space-y-1 list-disc list-inside">
                        {characterChanges.map((change: any, idx: number) => (
                          <li key={`char-${idx}`} className="leading-relaxed">
                            #{change.character_id ?? "?"}: {change.character_name ?? "Unknown"}
                            {change.emotional_state ? ` - ${change.emotional_state}` : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <div className="text-muted-foreground">No character updates</div>
                  )}

                  {locationChanges.length > 0 && (
                    <div>
                      <div className="font-mono text-[11px] text-muted-foreground mb-1">Locations</div>
                      <ul className="space-y-1 list-disc list-inside">
                        {locationChanges.map((change: any, idx: number) => (
                          <li key={`loc-${idx}`} className="leading-relaxed">
                            #{change.place_id ?? "?"}: {change.place_name ?? "Unknown"}
                            {change.current_status ? ` - ${change.current_status}` : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {factionChanges.length > 0 && (
                    <div>
                      <div className="font-mono text-[11px] text-muted-foreground mb-1">Factions</div>
                      <ul className="space-y-1 list-disc list-inside">
                        {factionChanges.map((change: any, idx: number) => (
                          <li key={`faction-${idx}`} className="leading-relaxed">
                            #{change.faction_id ?? "?"}: {change.faction_name ?? "Unknown"}
                            {change.current_activity ? ` - ${change.current_activity}` : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {(referencedCharacters.length > 0 ||
                    referencedPlaces.length > 0 ||
                    referencedFactions.length > 0) && (
                      <div>
                        <div className="font-mono text-[11px] text-muted-foreground mb-1">References</div>
                        <ul className="space-y-1 list-disc list-inside">
                          {referencedCharacters.map((ref: any, idx: number) => (
                            <li key={`ref-char-${idx}`}>
                              #{ref.character_id ?? "?"}: {ref.character_name ?? "Unknown"}{" "}
                              {ref.reference_type ? `(${ref.reference_type})` : ""}
                            </li>
                          ))}
                          {referencedPlaces.map((ref: any, idx: number) => (
                            <li key={`ref-place-${idx}`}>
                              #{ref.place_id ?? "?"}: {ref.place_name ?? "Unknown"}{" "}
                              {ref.reference_type ? `(${ref.reference_type})` : ""}
                            </li>
                          ))}
                          {referencedFactions.map((ref: any, idx: number) => (
                            <li key={`ref-faction-${idx}`}>
                              #{ref.faction_id ?? "?"}: {ref.faction_name ?? "Unknown"}{" "}
                              {ref.reference_type ? `(${ref.reference_type})` : ""}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                </div>
              </div>
            </div>
          )}

          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={narrative.handleCancel}>
              Cancel
            </Button>
            <Button variant="outline" onClick={narrative.handleRegenerate} disabled={narrative.isMidGeneration}>
              Regenerate
            </Button>
            <Button onClick={narrative.handleApprove} disabled={!narrative.activeNarrativeSession}>
              Approve &amp; Commit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </FontProvider>
  );
}
