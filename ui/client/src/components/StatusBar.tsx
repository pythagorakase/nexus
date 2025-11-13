import { useState } from "react";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";

interface StatusBarProps {
  model: string;
  modelId: string;
  season: number;
  episode: number;
  scene: number;
  apexStatus: "OFFLINE" | "READY" | "TRANSMITTING" | "GENERATING" | "RECEIVING";
  isStoryMode: boolean;
  modelStatus?: "unloaded" | "loading" | "loaded" | "generating";
  onHamburgerClick?: () => void;
}

export function StatusBar({
  model,
  modelId,
  season,
  episode,
  scene,
  apexStatus,
  isStoryMode,
  modelStatus = "unloaded",
  onHamburgerClick,
}: StatusBarProps) {
  const [isModelHovered, setIsModelHovered] = useState(false);
  const [isModelOperating, setIsModelOperating] = useState(false);

  const handleModelClick = async () => {
    if (isModelOperating || modelStatus === "loading" || modelStatus === "generating" || !modelId) {
      return; // Don't allow operations while busy or if no model ID
    }

    setIsModelOperating(true);
    try {
      if (modelStatus === "unloaded") {
        // Load the model
        const response = await fetch("/api/models/load", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_id: modelId }),
        });
        if (!response.ok) throw new Error("Failed to load model");
      } else if (modelStatus === "loaded") {
        // Unload the model
        const response = await fetch("/api/models/unload", {
          method: "POST",
        });
        if (!response.ok) throw new Error("Failed to unload model");
      }
    } catch (error) {
      console.error("Model operation failed:", error);
    } finally {
      setIsModelOperating(false);
    }
  };

  const getStatusColor = () => {
    switch (apexStatus) {
      case "OFFLINE":
        return "text-muted-foreground";
      case "READY":
        return "text-primary";
      case "TRANSMITTING":
      case "RECEIVING":
        return "text-accent";
      case "GENERATING":
        return "text-chart-2";
      default:
        return "text-foreground";
    }
  };

  return (
    <div className="h-10 md:h-12 border-b border-border bg-card flex items-center px-2 md:px-4 gap-2 md:gap-4 terminal-scanlines">
      <Button
        size="icon"
        variant="ghost"
        onClick={onHamburgerClick}
        className="h-7 w-7 md:h-8 md:w-8 flex-shrink-0"
        data-testid="button-hamburger-menu"
      >
        <Menu className="h-3 w-3 md:h-4 md:w-4" />
      </Button>

      <div className="flex items-center gap-2 md:gap-6 text-xs md:text-sm font-mono flex-1 overflow-hidden">
        <div className="hidden md:flex items-center gap-2" data-testid="text-model-status">
          <span className="text-muted-foreground">MODEL:</span>
          <div
            className="relative cursor-pointer"
            onMouseEnter={() => setIsModelHovered(true)}
            onMouseLeave={() => setIsModelHovered(false)}
            onClick={handleModelClick}
          >
            <span className={`transition-colors duration-300 ${
              modelStatus === 'unloaded' ? 'text-muted-foreground' :
              modelStatus === 'loading' ? 'text-foreground terminal-loading' :
              modelStatus === 'loaded' ? 'text-foreground terminal-glow' :
              modelStatus === 'generating' ? 'terminal-generating terminal-generating-glow' :
              'text-muted-foreground'
            }`}>
              {model}
            </span>
            {/* Hover overlay */}
            {isModelHovered && !isModelOperating && modelStatus !== "loading" && modelStatus !== "generating" && (
              <span className="absolute inset-0 flex items-center justify-center bg-background/90 text-primary terminal-glow font-bold">
                {modelStatus === "unloaded" ? "LOAD" : "UNLOAD"}
              </span>
            )}
            {/* Operating state */}
            {isModelOperating && (
              <span className="absolute inset-0 flex items-center justify-center bg-background/90 text-accent terminal-glow font-bold">
                ...
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1 md:gap-2" data-testid="text-chapter-info">
          <span className="text-muted-foreground hidden sm:inline">CHAPTER:</span>
          <span className="text-foreground">
            S{season.toString().padStart(2, '0')}-E{episode.toString().padStart(2, '0')}-S{scene.toString().padStart(3, '0')}
          </span>
        </div>

        {isStoryMode && (
          <div className="flex items-center gap-1 md:gap-2" data-testid="text-apex-status">
            <span className="text-muted-foreground hidden sm:inline">APEX:</span>
            <span className={`${getStatusColor()} terminal-glow text-xs md:text-sm`}>{apexStatus}</span>
          </div>
        )}
      </div>
    </div>
  );
}
