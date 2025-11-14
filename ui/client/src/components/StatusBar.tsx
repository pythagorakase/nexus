import { useEffect, useMemo, useRef, useState } from "react";
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
  onModelStatusChange?: (status: "unloaded" | "loading" | "loaded" | "generating") => void;
  onRefreshModelStatus?: () => Promise<void> | void;
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
  onModelStatusChange,
  onRefreshModelStatus,
}: StatusBarProps) {
  const [isModelHovered, setIsModelHovered] = useState(false);
  const [isModelOperating, setIsModelOperating] = useState(false);
  const [modelError, setModelError] = useState<string | null>(null);
  const modelErrorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (modelErrorTimeoutRef.current) {
        clearTimeout(modelErrorTimeoutRef.current);
      }
    };
  }, []);

  const modelVisualClasses = useMemo(() => {
    switch (modelStatus) {
      case "unloaded":
        return "text-muted-foreground";
      case "loading":
        return "text-primary terminal-glow";
      case "loaded":
        return "text-primary terminal-glow";
      case "generating":
        return "terminal-generating terminal-generating-glow";
      default:
        return "text-muted-foreground";
    }
  }, [modelStatus]);
  const isBarLoading = modelStatus === "loading";

  const showModelError = (message: string) => {
    if (modelErrorTimeoutRef.current) {
      clearTimeout(modelErrorTimeoutRef.current);
    }
    setModelError(message);
    modelErrorTimeoutRef.current = setTimeout(() => {
      setModelError(null);
      modelErrorTimeoutRef.current = null;
    }, 4000);
  };

  const handleModelClick = async () => {
    if (isModelOperating || modelStatus === "loading" || modelStatus === "generating") {
      return; // Don't allow operations while busy
    }

    if (!modelId) {
      showModelError("No default model configured");
      return;
    }

    const isLoadingAction = modelStatus === "unloaded";
    setIsModelOperating(true);
    onModelStatusChange?.("loading");
    try {
      if (isLoadingAction) {
        // Load the model
        const response = await fetch("/api/models/load", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_id: modelId }),
        });
        if (!response.ok) {
          const message = await response.text();
          throw new Error(message || "Failed to load model");
        }
        onModelStatusChange?.("loaded");
      } else if (modelStatus === "loaded") {
        // Unload the model
        const response = await fetch("/api/models/unload", {
          method: "POST",
        });
        if (!response.ok) {
          const message = await response.text();
          throw new Error(message || "Failed to unload model");
        }
        onModelStatusChange?.("unloaded");
      }
    } catch (error) {
      console.error("Model operation failed:", error);
      showModelError(
        error instanceof Error ? error.message : "Model operation failed"
      );
      onModelStatusChange?.(isLoadingAction ? "unloaded" : "loaded");
    } finally {
      setIsModelOperating(false);
      await onRefreshModelStatus?.();
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
    <div
      className={`h-10 md:h-12 border-b border-border bg-card flex items-center px-2 md:px-4 gap-2 md:gap-4 terminal-scanlines ${
        isBarLoading ? "status-bar-loading" : ""
      }`}
    >
      <Button
        size="icon"
        variant="ghost"
        onClick={onHamburgerClick}
        className="h-7 w-7 md:h-8 md:w-8 flex-shrink-0"
        data-testid="button-hamburger-menu"
      >
        <Menu className="h-3 w-3 md:h-4 md:w-4" />
      </Button>

      <div className="flex items-center gap-2 md:gap-6 text-sm md:text-base font-mono flex-1 overflow-hidden">
        <div className="hidden md:flex items-center gap-2" data-testid="text-model-status">
          <span className="text-muted-foreground">MODEL:</span>
          <div
            className="relative cursor-pointer text-base md:text-lg tracking-wide"
            onMouseEnter={() => setIsModelHovered(true)}
            onMouseLeave={() => setIsModelHovered(false)}
            onClick={handleModelClick}
          >
            <span className={`relative inline-block min-w-[3rem] px-0.5 transition-colors duration-300 ${modelVisualClasses}`}>
              {model}
            </span>
            {/* Hover overlay */}
            {modelError && (
              <span className="absolute inset-0 flex items-center justify-center bg-background/95 text-destructive terminal-glow font-bold text-[0.6rem] md:text-xs px-2 text-center leading-snug">
                {modelError}
              </span>
            )}
            {isModelHovered && !isModelOperating && !modelError && modelStatus !== "loading" && modelStatus !== "generating" && (
              <span className="absolute inset-0 flex items-center justify-center bg-background/90 text-primary terminal-glow font-bold">
                {modelStatus === "unloaded" ? "LOAD" : "UNLOAD"}
              </span>
            )}
            {/* Operating state */}
            {isModelOperating && !modelError && (
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
            <span className={`${getStatusColor()} terminal-glow text-sm md:text-base`}>{apexStatus}</span>
          </div>
        )}
      </div>
    </div>
  );
}
