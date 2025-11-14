import {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
  type MutableRefObject,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { StatusBar } from "./StatusBar";
import { CommandBar } from "./CommandBar";
import { NarrativeTab } from "./NarrativeTab";
import { MapTab } from "./MapTab";
import { CharactersTab } from "./CharactersTab";
import AuditionTab from "@/pages/AuditionTab";
import { SettingsTab } from "@/pages/SettingsTab";
import { FontProvider } from "@/contexts/FontContext";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Book, Map, Users, Sparkles, Settings } from "lucide-react";

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

interface StorySessionMetadata {
  session_id: string;
  session_name: string;
  created_at: string;
  last_accessed: string;
  turn_count: number;
  current_phase: string;
  initial_context?: Record<string, unknown> | null;
}

const EXPLICIT_STORY_SESSION_ID = (import.meta.env
  .VITE_STORY_SESSION_ID || "")
  .trim() || undefined;

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
  const [apexStatus, setApexStatus] = useState<
    "OFFLINE" | "READY" | "TRANSMITTING" | "GENERATING" | "RECEIVING"
  >("READY");
  const apexStatusRef = useRef(apexStatus);
  const [storySessionId, setStorySessionId] = useState<string | null>(
    () => EXPLICIT_STORY_SESSION_ID ?? null
  );
  const generatingTimeoutRef = useRef<number | null>(null);
  const readyTimeoutRef = useRef<number | null>(null);
  const sessionStreamRef = useRef<WebSocket | null>(null);
  const isMountedRef = useRef(true);
  const [activeTab, setActiveTab] = useState("narrative");
  const [currentChunkLocation, setCurrentChunkLocation] = useState<string | null>("Night City Center");
  const [isInputExpanded, setIsInputExpanded] = useState(false);

  useEffect(() => {
    apexStatusRef.current = apexStatus;
  }, [apexStatus]);

  // Fetch settings to get model name
  const {
    data: settings,
    isSuccess: settingsLoaded,
    isError: settingsError,
  } = useQuery<SettingsPayload>({
    queryKey: ["/api/settings"],
    refetchInterval: 30000, // Refetch every 30 seconds
  });

  const {
    data: storySessions,
    isError: storySessionsError,
  } = useQuery<StorySessionMetadata[]>({
    queryKey: ["/api/story/sessions"],
    refetchInterval: 15000,
    staleTime: 15000,
    retry: false,
  });

  const activeStorySession = useMemo(() => {
    if (!storySessions || !storySessions.length || !storySessionId) {
      return null;
    }
    return (
      storySessions.find((session) => session.session_id === storySessionId) ?? null
    );
  }, [storySessions, storySessionId]);

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

      if (phase === "processing" || phase === "regenerating") {
        if (apexStatusRef.current !== "TRANSMITTING") {
          setApexStatus("TRANSMITTING");
        }
        generatingTimeoutRef.current = window.setTimeout(() => {
          if (!isMountedRef.current) {
            return;
          }
          setApexStatus("GENERATING");
        }, 600);
        return;
      }

      if (!phase || phase === "idle") {
        setApexStatus("READY");
        return;
      }

      if (phase === "error") {
        setApexStatus("OFFLINE");
        return;
      }

      if (phase === "integration") {
        setApexStatus("RECEIVING");
        readyTimeoutRef.current = window.setTimeout(() => {
          if (!isMountedRef.current) {
            return;
          }
          setApexStatus("READY");
        }, 1200);
        return;
      }

      setApexStatus("GENERATING");
    },
    [clearTimeoutRef, setApexStatus],
  );

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      if (sessionStreamRef.current) {
        sessionStreamRef.current.close();
        sessionStreamRef.current = null;
      }
      clearTimeoutRef(generatingTimeoutRef);
      clearTimeoutRef(readyTimeoutRef);
    };
  }, [clearTimeoutRef]);

  useEffect(() => {
    if (!storySessions || storySessions.length === 0) {
      if (!EXPLICIT_STORY_SESSION_ID) {
        setStorySessionId(null);
      }
      return;
    }

    if (EXPLICIT_STORY_SESSION_ID) {
      const hasExplicitSession = storySessions.some(
        (session) => session.session_id === EXPLICIT_STORY_SESSION_ID
      );
      setStorySessionId(hasExplicitSession ? EXPLICIT_STORY_SESSION_ID : null);
      return;
    }

    setStorySessionId((current) => {
      if (current && storySessions.some((session) => session.session_id === current)) {
        return current;
      }
      return storySessions[0]?.session_id ?? null;
    });
  }, [storySessions]);

  useEffect(() => {
    if (!storySessionsError) {
      return;
    }
    setApexStatus((previous) => (previous === "OFFLINE" ? previous : "OFFLINE"));
  }, [storySessionsError, setApexStatus]);

  useEffect(() => {
    if (!activeStorySession) {
      return;
    }
    handlePhaseEvent(activeStorySession.current_phase);
  }, [activeStorySession, handlePhaseEvent]);

  useEffect(() => {
    if (!storySessionId) {
      if (sessionStreamRef.current) {
        sessionStreamRef.current.close();
        sessionStreamRef.current = null;
      }
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const websocketUrl = `${protocol}//${window.location.host}/api/story/stream/${storySessionId}`;
    const socket = new WebSocket(websocketUrl);
    sessionStreamRef.current = socket;

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
        if (!payload || typeof payload !== "object") {
          return;
        }

        if (payload.event === "phase") {
          handlePhaseEvent(typeof payload.phase === "string" ? payload.phase : null);
        } else if (payload.event === "complete") {
          handleCompleteEvent();
        } else if (payload.event === "error") {
          setApexStatus("OFFLINE");
        }
      } catch {
        // Ignore malformed events
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
      if (sessionStreamRef.current === socket) {
        sessionStreamRef.current = null;
      }
    };
  }, [storySessionId, handlePhaseEvent, handleCompleteEvent, setApexStatus]);

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
    } else if (settingsError) {
      setCurrentModel("UNAVAILABLE");
      setCurrentModelId("");
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
      if (!storySessionId) {
        handlePhaseEvent("processing");
        readyTimeoutRef.current = window.setTimeout(() => {
          if (!isMountedRef.current) {
            return;
          }
          handleCompleteEvent();
        }, 3200);
      }
      // Reset input to button after submission
      setIsInputExpanded(false);
    }
  };

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
            <NarrativeTab />
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

        {activeTab === "narrative" && (
          <CommandBar
            onCommand={handleCommand}
            placeholder={
              isStoryMode
                ? "continue the story"
                : "Enter directive or /command..."
            }
            userPrefix={isStoryMode ? "" : "NEXUS:USER"}
            showButton={isStoryMode && !isInputExpanded}
            onButtonClick={() => setIsInputExpanded(true)}
          />
        )}
      </div>
    </FontProvider>
  );
}
