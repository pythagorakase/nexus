import {
  useState,
  useEffect,
  useCallback,
  useRef,
  type MutableRefObject,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { StatusBar } from "./StatusBar";
import { CommandBar } from "./CommandBar";
import { NarrativeTab, type ChunkWithMetadata } from "./NarrativeTab";
import { MapTab } from "./MapTab";
import { CharactersTab } from "./CharactersTab";
import AuditionTab from "@/pages/AuditionTab";
import { SettingsTab } from "@/pages/SettingsTab";
import { FontProvider } from "@/contexts/FontContext";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Book, Map, Users, Sparkles, Settings } from "lucide-react";
import { toast } from "@/hooks/use-toast";

interface SettingsPayload {
  ["Agent Settings"]?: {
    global?: {
      model?: {
        default_model?: string;
      };
      llm?: {
        api_base?: string;
      };
    };
  };
}

interface IncubatorViewPayload {
  chunk_id: number;
  parent_chunk_id: number;
  parent_chunk_text?: string | null;
  user_text?: string | null;
  storyteller_text?: string | null;
  episode_transition?: string | null;
  time_delta?: string | null;
  world_layer?: string | null;
  pacing?: string | null;
  entity_update_count?: number;
  entity_changes?: any;
  references?: any;
  status?: string;
  session_id?: string;
  created_at?: string;
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
  const narrativeStreamRef = useRef<WebSocket | null>(null);
  const isMountedRef = useRef(true);
  const [activeTab, setActiveTab] = useState("narrative");
  const [selectedChunk, setSelectedChunk] = useState<ChunkWithMetadata | null>(null);
  const [currentChunkLocation, setCurrentChunkLocation] = useState<string | null>("Night City Center");
  const [isInputExpanded, setIsInputExpanded] = useState(false);
  const [activeNarrativeSession, setActiveNarrativeSession] = useState<string | null>(null);
  const activeNarrativeSessionRef = useRef<string | null>(null);
  const [narrativePhase, setNarrativePhase] = useState<string | null>(null);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [lastUserInput, setLastUserInput] = useState<string>("Continue.");
  const [generationParentChunk, setGenerationParentChunk] = useState<ChunkWithMetadata | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const elapsedTimerRef = useRef<number | null>(null);
  const [incubatorData, setIncubatorData] = useState<IncubatorViewPayload | null>(null);
  const [showApprovalModal, setShowApprovalModal] = useState(false);

  useEffect(() => {
    apexStatusRef.current = apexStatus;
  }, [apexStatus]);

  useEffect(() => {
    activeNarrativeSessionRef.current = activeNarrativeSession;
  }, [activeNarrativeSession]);

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
    refetchInterval: 30000, // Refetch every 30 seconds
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
    }, 1200);
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
        }, 300);
        return;
      }

      if (phase === "initiated" || phase === "loading_chunk" || phase === "building_context") {
        setApexStatus("TRANSMITTING");
        generatingTimeoutRef.current = window.setTimeout(() => {
          if (!isMountedRef.current) {
            return;
          }
          setApexStatus("GENERATING");
        }, 600);
        return;
      }

      setApexStatus("READY");
    },
    [clearTimeoutRef, handleCompleteEvent, setApexStatus],
  );

  const stopElapsedTimer = useCallback(() => {
    if (elapsedTimerRef.current !== null) {
      window.clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  }, []);

  const startElapsedTimer = useCallback(
    (startTime: number) => {
      stopElapsedTimer();
      setElapsedMs(0);
      elapsedTimerRef.current = window.setInterval(() => {
        setElapsedMs(Date.now() - startTime);
      }, 500);
    },
    [stopElapsedTimer],
  );

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      if (narrativeStreamRef.current) {
        narrativeStreamRef.current.close();
        narrativeStreamRef.current = null;
      }
      clearTimeoutRef(generatingTimeoutRef);
      clearTimeoutRef(readyTimeoutRef);
      stopElapsedTimer();
    };
  }, [clearTimeoutRef, stopElapsedTimer]);

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
    queryKey: ["/api/narrative/latest-chunk"],
    refetchInterval: 10000, // Refetch every 10 seconds
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

  const fetchIncubatorData = useCallback(async () => {
    try {
      const response = await fetch("/api/narrative/incubator");
      if (!response.ok) {
        const message = (await response.text()) || "Failed to load incubator contents";
        throw new Error(message);
      }
      const payload = await response.json();
      if (payload?.message === "Incubator is empty") {
        setIncubatorData(null);
        return;
      }
      setIncubatorData(payload as IncubatorViewPayload);
      setShowApprovalModal(true);
    } catch (error) {
      console.error("Unable to load incubator data:", error);
      setGenerationError(error instanceof Error ? error.message : "Unable to load incubator");
    }
  }, []);

  const handleNarrativeProgress = useCallback(
    (payload: any) => {
      if (!payload || typeof payload !== "object") {
        return;
      }

      const sessionId = payload.session_id as string | undefined;
      const phase = payload.status as string | undefined;

      if (!sessionId || !phase) {
        return;
      }

      if (activeNarrativeSessionRef.current && activeNarrativeSessionRef.current !== sessionId) {
        return; // Ignore updates for other sessions
      }

      if (!activeNarrativeSessionRef.current) {
        setActiveNarrativeSession(sessionId);
      }

      setNarrativePhase(phase);
      setGenerationError(null);
      handlePhaseEvent(phase);

      if (phase === "complete") {
        stopElapsedTimer();
        fetchIncubatorData();
      } else if (phase === "error") {
        stopElapsedTimer();
        const errorMessage =
          (payload.data && (payload.data.error as string)) || "Narrative generation failed";
        setGenerationError(errorMessage);
        setShowApprovalModal(false);
      }
    },
    [fetchIncubatorData, handlePhaseEvent, stopElapsedTimer],
  );

  const triggerNarrativeTurn = useCallback(
    async (userInput: string) => {
      if (!selectedChunk) {
        toast({
          title: "Select a chunk",
          description: "Choose a narrative chunk to continue (currently limited to chunk 1425).",
        });
        return;
      }

      if (selectedChunk.id !== 1425) {
        toast({
          title: "Test rollout limited",
          description: "Continue is temporarily restricted to chunk 1425 for safety.",
          variant: "destructive",
        });
        return;
      }

      if (
        activeNarrativeSessionRef.current &&
        ["initiated", "loading_chunk", "building_context", "calling_llm", "processing_response"].includes(
          narrativePhase ?? "",
        )
      ) {
        toast({
          title: "Generation in progress",
          description: "Wait for the current turn to finish or cancel before starting another.",
        });
        return;
      }

      const trimmedInput = userInput.trim() || "Continue.";
      setLastUserInput(trimmedInput);
      setGenerationParentChunk(selectedChunk);
      setNarrativePhase("initiated");
      setGenerationError(null);
      setIncubatorData(null);
      setShowApprovalModal(false);
      setActiveNarrativeSession(null);

      const startedAt = Date.now();
      startElapsedTimer(startedAt);
      handlePhaseEvent("initiated");

      try {
        const response = await fetch("/api/narrative/continue", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chunk_id: selectedChunk.id,
            user_text: trimmedInput,
            test_mode: isTestModeEnabled,
          }),
        });

        if (!response.ok) {
          const message = (await response.text()) || "Failed to start narrative generation";
          throw new Error(message);
        }

        const payload = await response.json();
        setActiveNarrativeSession(payload.session_id ?? null);
        setNarrativePhase(payload.status ?? "initiated");
      } catch (error) {
        console.error("Narrative generation failed:", error);
        stopElapsedTimer();
        setNarrativePhase(null);
        setActiveNarrativeSession(null);
        setGenerationParentChunk(null);
        setApexStatus("OFFLINE");
        const message = error instanceof Error ? error.message : "Narrative generation failed";
        setGenerationError(message);
        toast({
          title: "Narrative generation failed",
          description: message,
          variant: "destructive",
        });
      } finally {
        setIsInputExpanded(false);
      }
    },
    [
      activeNarrativeSessionRef,
      handlePhaseEvent,
      isTestModeEnabled,
      narrativePhase,
      selectedChunk,
      startElapsedTimer,
      stopElapsedTimer,
    ],
  );

  // Check if LLM server is running and has model loaded
  useEffect(() => {
    refreshModelStatus();
    const interval = setInterval(refreshModelStatus, 5000);
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
    const interval = setInterval(checkApexConnectivity, 10000);
    return () => clearInterval(interval);
  }, [apexStatus]);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const websocketUrl = `${protocol}//${window.location.host}/ws/narrative`;
    const socket = new WebSocket(websocketUrl);
    narrativeStreamRef.current = socket;

    socket.onopen = () => {
      if (!isMountedRef.current) {
        return;
      }
      if (apexStatusRef.current === "OFFLINE") {
        setApexStatus("READY");
      }
    };

    socket.onmessage = (event) => {
      if (!isMountedRef.current) {
        return;
      }
      try {
        const payload = JSON.parse(event.data);
        handleNarrativeProgress(payload);
      } catch (error) {
        console.warn("Malformed narrative event", error);
      }
    };

    const markOffline = () => {
      if (!isMountedRef.current) {
        return;
      }
      setApexStatus((previous) => (previous === "OFFLINE" ? previous : "OFFLINE"));
    };

    socket.onerror = markOffline;
    socket.onclose = markOffline;

    return () => {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      socket.close();
      if (narrativeStreamRef.current === socket) {
        narrativeStreamRef.current = null;
      }
    };
  }, [handleNarrativeProgress, setApexStatus]);

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
      triggerNarrativeTurn(command);
      setIsInputExpanded(false);
    }
  };

  const handleApprove = useCallback(async () => {
    if (!activeNarrativeSession) {
      toast({
        title: "No active session",
        description: "Start a generation before approving.",
      });
      return;
    }

    try {
      const response = await fetch(`/api/narrative/approve/${activeNarrativeSession}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ commit: true }),
      });

      if (!response.ok) {
        const message = (await response.text()) || "Failed to approve narrative";
        throw new Error(message);
      }

      const payload = await response.json().catch(() => null);
      const chunkId = payload?.chunk_id ?? incubatorData?.chunk_id;

      toast({
        title: "Narrative approved",
        description: chunkId ? `Committed as chunk ${chunkId}` : "Committed to database",
      });
      setShowApprovalModal(false);
      setNarrativePhase(null);
      setActiveNarrativeSession(null);
      setGenerationParentChunk(null);
      setIncubatorData(null);
      stopElapsedTimer();
      setApexStatus("READY");
    } catch (error) {
      console.error("Failed to approve narrative:", error);
      const message = error instanceof Error ? error.message : "Failed to approve narrative";
      setGenerationError(message);
      toast({
        title: "Approval failed",
        description: message,
        variant: "destructive",
      });
    }
  }, [activeNarrativeSession, incubatorData, stopElapsedTimer]);

  const handleRegenerate = useCallback(() => {
    setShowApprovalModal(false);
    setNarrativePhase(null);
    setIncubatorData(null);
    triggerNarrativeTurn(lastUserInput);
  }, [lastUserInput, triggerNarrativeTurn]);

  const phaseLabels: Record<string, string> = {
    initiated: "Request received...",
    loading_chunk: "Loading parent chunk...",
    building_context: "Assembling context package...",
    calling_llm: "Calling LORE / LOGON...",
    processing_response: "Processing response...",
    complete: "Awaiting approval",
    error: "Generation failed",
  };

  const isMidGeneration = ["initiated", "loading_chunk", "building_context", "calling_llm", "processing_response"].includes(
    narrativePhase ?? "",
  );
  const progressLabel = narrativePhase ? phaseLabels[narrativePhase] ?? narrativePhase : null;
  const showElapsed = elapsedMs > 5000;
  const canContinue = selectedChunk?.id === 1425;
  const continueDisabled = !canContinue || (narrativePhase !== null && narrativePhase !== "error");
  const approvalOpen = showApprovalModal && !!incubatorData;
  const entityChanges: any = incubatorData?.entity_changes || {};
  const referenceChanges: any = incubatorData?.references || {};
  const characterChanges = Array.isArray(entityChanges?.characters) ? entityChanges.characters : [];
  const locationChanges = Array.isArray(entityChanges?.locations) ? entityChanges.locations : [];
  const factionChanges = Array.isArray(entityChanges?.factions) ? entityChanges.factions : [];
  const referencedCharacters = Array.isArray(referenceChanges?.characters) ? referenceChanges.characters : [];
  const referencedPlaces = Array.isArray(referenceChanges?.places) ? referenceChanges.places : [];
  const referencedFactions = Array.isArray(referenceChanges?.factions) ? referenceChanges.factions : [];
  const chunkLabel =
    generationParentChunk?.metadata?.season !== null &&
    generationParentChunk?.metadata?.season !== undefined &&
    generationParentChunk?.metadata?.episode !== null &&
    generationParentChunk?.metadata?.episode !== undefined
      ? `S${String(generationParentChunk.metadata.season).padStart(2, "0")}E${String(
          generationParentChunk.metadata.episode,
        ).padStart(2, "0")}`
      : incubatorData?.parent_chunk_id
        ? `Chunk ${incubatorData.parent_chunk_id}`
        : "Narrative turn";
  const subtitle = generationParentChunk?.metadata?.slug || "Awaiting metadata";

  return (
    <FontProvider>
      <div className="h-screen w-full bg-background flex flex-col font-mono overflow-hidden dark">
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
          onHamburgerClick={() => {
            // Can be used for mobile menu in the future
          }}
        />

        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="flex-1 flex flex-col overflow-hidden"
        >
          <div className="border-b border-border bg-card/50 overflow-x-auto">
            <TabsList className="h-10 bg-transparent border-0 rounded-none p-0 inline-flex min-w-full">
              <TabsTrigger
                value="narrative"
                className="data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-10 px-3 md:px-4 font-mono text-xs terminal-glow flex items-center gap-1 md:gap-2 flex-1 md:flex-initial"
                data-testid="tab-narrative"
              >
                <Book className="h-3 w-3" />
                <span className="hidden sm:inline">NARRATIVE</span>
                <span className="sm:hidden">NAR</span>
              </TabsTrigger>
              <TabsTrigger
                value="map"
                className="data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-10 px-3 md:px-4 font-mono text-xs terminal-glow flex items-center gap-1 md:gap-2 flex-1 md:flex-initial"
                data-testid="tab-map"
              >
                <Map className="h-3 w-3" />
                MAP
              </TabsTrigger>
              <TabsTrigger
                value="characters"
                className="data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-10 px-3 md:px-4 font-mono text-xs terminal-glow flex items-center gap-1 md:gap-2 flex-1 md:flex-initial"
                data-testid="tab-characters"
              >
                <Users className="h-3 w-3" />
                <span className="hidden sm:inline">CHARACTERS</span>
                <span className="sm:hidden">CHAR</span>
              </TabsTrigger>
              <TabsTrigger
                value="audition"
                className="data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-10 px-3 md:px-4 font-mono text-xs terminal-glow flex items-center gap-1 md:gap-2 flex-1 md:flex-initial"
                data-testid="tab-audition"
              >
                <Sparkles className="h-3 w-3" />
                <span className="hidden sm:inline">AUDITION</span>
                <span className="sm:hidden">AUD</span>
              </TabsTrigger>
              <TabsTrigger
                value="settings"
                className="data-[state=active]:bg-transparent data-[state=active]:text-primary data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-10 px-3 md:px-4 font-mono text-xs terminal-glow flex items-center gap-1 md:gap-2 ml-auto"
                data-testid="tab-settings"
              >
                <Settings className="h-3 w-3" />
                <span className="hidden sm:inline">SETTINGS</span>
                <span className="sm:hidden">SET</span>
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="narrative" className="flex-1 overflow-hidden m-0">
            <NarrativeTab onChunkSelected={handleChunkSelection} />
          </TabsContent>

          <TabsContent value="map" className="flex-1 overflow-hidden m-0">
            <MapTab currentChunkLocation={currentChunkLocation} />
          </TabsContent>

          <TabsContent value="characters" className="flex-1 overflow-hidden m-0">
            <CharactersTab />
          </TabsContent>

          <TabsContent value="audition" className="flex-1 overflow-hidden m-0">
            <AuditionTab />
          </TabsContent>

          <TabsContent value="settings" className="flex-1 overflow-hidden m-0">
            <SettingsTab />
          </TabsContent>
        </Tabs>

        {activeTab === "narrative" && narrativePhase && (
          <div className="border-t border-border bg-card/80 text-xs font-mono px-3 py-2 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className={narrativePhase === "error" ? "text-destructive" : "text-primary terminal-glow"}>
                {narrativePhase === "error" ? "!" : ">>"}
              </span>
              <span className={narrativePhase === "error" ? "text-destructive" : "text-foreground"}>
                {progressLabel}
              </span>
              {narrativePhase === "error" && generationError && (
                <span className="text-destructive/80 truncate max-w-[42ch]">{generationError}</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {narrativePhase === "complete" && incubatorData && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 px-3 font-mono"
                  onClick={() => setShowApprovalModal(true)}
                >
                  Review & approve
                </Button>
              )}
              {showElapsed && (
                <span className="text-muted-foreground">
                  {Math.round(elapsedMs / 1000)}s elapsed
                </span>
              )}
            </div>
          </div>
        )}
        {activeTab === "narrative" && !narrativePhase && generationError && (
          <div className="border-t border-destructive/40 bg-destructive/10 text-destructive font-mono text-xs px-3 py-2 flex items-center justify-between">
            <span>{generationError}</span>
          </div>
        )}

        {activeTab === "narrative" && (
          <CommandBar
            onCommand={handleCommand}
            placeholder={
              isStoryMode
                ? canContinue
                  ? "continue the story"
                  : "Continue available only for chunk 1425"
                : "Enter directive or /command..."
            }
            userPrefix={isStoryMode ? "" : "NEXUS:USER"}
            showButton={isStoryMode && !isInputExpanded}
            onButtonClick={() => triggerNarrativeTurn(lastUserInput)}
            onExpandInput={() => setIsInputExpanded(true)}
            isGenerating={isMidGeneration}
            continueDisabled={continueDisabled}
          />
        )}
      </div>

      <Dialog open={approvalOpen} onOpenChange={setShowApprovalModal}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span>Review generated narrative</span>
              <div className="flex items-center gap-2">
                {isTestModeEnabled && <Badge variant="destructive">TEST MODE</Badge>}
                {activeNarrativeSession && (
                  <Badge variant="outline">Session {activeNarrativeSession.slice(0, 8)}</Badge>
                )}
              </div>
            </DialogTitle>
            <DialogDescription className="font-mono text-xs">
              {chunkLabel} -> proposed chunk {incubatorData?.chunk_id ?? "pending"}
            </DialogDescription>
          </DialogHeader>

          {incubatorData && (
            <div className="grid gap-4 md:grid-cols-3 text-sm">
              <div className="md:col-span-2 space-y-3">
                <div className="space-y-1">
                  <div className="text-primary terminal-glow font-mono text-sm">{chunkLabel}</div>
                  <div className="text-muted-foreground italic text-xs">{subtitle}</div>
                  <div className="text-muted-foreground text-xs">
                    {incubatorData.time_delta || "Time delta pending"}
                  </div>
                </div>
                <ScrollArea className="h-72 rounded border border-border bg-card/70 p-4">
                  <div className="whitespace-pre-wrap leading-relaxed text-foreground">
                    {incubatorData.storyteller_text || "No narrative captured"}
                  </div>
                </ScrollArea>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-muted-foreground">Entity changes</span>
                  <Badge variant="outline">{incubatorData.entity_update_count ?? 0}</Badge>
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
            <Button variant="ghost" onClick={() => setShowApprovalModal(false)}>
              Cancel
            </Button>
            <Button variant="outline" onClick={handleRegenerate} disabled={isMidGeneration}>
              Regenerate
            </Button>
            <Button onClick={handleApprove} disabled={!activeNarrativeSession}>
              Approve &amp; Commit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </FontProvider>
  );
}
