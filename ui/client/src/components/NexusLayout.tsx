import { useState, useEffect } from "react";
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

export function NexusLayout() {
  const [currentModel, setCurrentModel] = useState("LOADING");
  const [isModelLoaded, setIsModelLoaded] = useState(false);
  const [isStoryMode, setIsStoryMode] = useState(true);
  const [apexStatus, setApexStatus] = useState<
    "OFFLINE" | "READY" | "TRANSMITTING" | "GENERATING" | "RECEIVING"
  >("READY");
  const [activeTab, setActiveTab] = useState("narrative");
  const [currentChunkLocation, setCurrentChunkLocation] = useState<string | null>("Night City Center");

  // Fetch settings to get model name
  const {
    data: settings,
    isSuccess: settingsLoaded,
    isError: settingsError,
  } = useQuery<SettingsPayload>({
    queryKey: ["/api/settings"],
    refetchInterval: 30000, // Refetch every 30 seconds
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
      } else {
        setCurrentModel("UNCONFIGURED");
      }
    } else if (settingsError) {
      setCurrentModel("UNAVAILABLE");
    }
  }, [settings, settingsError, settingsLoaded]);

  // Check if LLM server is running and has model loaded
  useEffect(() => {
    const checkModelStatus = async () => {
      try {
        const apiBase = settings?.["Agent Settings"]?.global?.llm?.api_base || "http://localhost:1234";
        const response = await fetch(`${apiBase}/v1/models`);
        setIsModelLoaded(response.ok);
      } catch {
        setIsModelLoaded(false);
      }
    };

    checkModelStatus();
    const interval = setInterval(checkModelStatus, 5000);
    return () => clearInterval(interval);
  }, [settings]);

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
      // Story mode command processing
      setApexStatus("TRANSMITTING");
      setTimeout(() => setApexStatus("GENERATING"), 1000);
      setTimeout(() => setApexStatus("RECEIVING"), 3000);
      setTimeout(() => setApexStatus("READY"), 5000);
    }
  };

  return (
    <FontProvider>
      <div className="h-screen w-full bg-background flex flex-col font-mono overflow-hidden dark">
        <StatusBar
          model={currentModel}
          season={1}
          episode={1}
          scene={1}
          apexStatus={apexStatus}
          isStoryMode={isStoryMode}
          isModelLoaded={isModelLoaded}
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
            userPrefix={isStoryMode ? "ALEX" : "NEXUS:USER"}
          />
        )}
      </div>
    </FontProvider>
  );
}
