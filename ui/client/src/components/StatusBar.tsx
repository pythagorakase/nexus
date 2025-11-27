import { useEffect, useMemo, useRef, useState } from "react";
import { Menu, Home, Settings, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast as showToast } from "@/hooks/use-toast";
import { Link } from "wouter";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTheme } from "@/contexts/ThemeContext";
import { CornerSunburst } from "@/components/deco";
import { cn } from "@/lib/utils";

interface StatusBarProps {
  model: string;
  modelId: string;
  season: number;
  episode: number;
  scene: number;
  apexStatus: "OFFLINE" | "READY" | "TRANSMITTING" | "GENERATING" | "RECEIVING";
  isStoryMode: boolean;
  isTestModeEnabled?: boolean;
  modelStatus?: "unloaded" | "loading" | "loaded" | "generating";
  onHamburgerClick?: () => void;
  onModelStatusChange?: (status: "unloaded" | "loading" | "loaded" | "generating") => void;
  onRefreshModelStatus?: () => Promise<void> | void;
  onNavigate?: (tab: string) => void;
}

export function StatusBar({
  model,
  modelId,
  season,
  episode,
  scene,
  apexStatus,
  isStoryMode,
  isTestModeEnabled = false,
  modelStatus = "unloaded",
  onHamburgerClick,
  onModelStatusChange,
  onRefreshModelStatus,
  onNavigate,
}: StatusBarProps) {
  const { isGilded, isCyberpunk } = useTheme();
  const [isModelHovered, setIsModelHovered] = useState(false);
  const [isModelOperating, setIsModelOperating] = useState(false);
  const [modelError, setModelError] = useState<string | null>(null);
  const modelErrorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const slowOperationTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastDismissTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const operationToastRef = useRef<ReturnType<typeof showToast> | null>(null);
  const [isSlowOperation, setIsSlowOperation] = useState(false);
  const [pendingOperation, setPendingOperation] = useState<"load" | "unload" | null>(null);

  useEffect(() => {
    return () => {
      if (modelErrorTimeoutRef.current) {
        clearTimeout(modelErrorTimeoutRef.current);
      }
      if (slowOperationTimeoutRef.current) {
        clearTimeout(slowOperationTimeoutRef.current);
        slowOperationTimeoutRef.current = null;
      }
      if (toastDismissTimeoutRef.current) {
        clearTimeout(toastDismissTimeoutRef.current);
        toastDismissTimeoutRef.current = null;
      }
      if (operationToastRef.current) {
        operationToastRef.current.dismiss();
        operationToastRef.current = null;
      }
    };
  }, []);

  // Theme-aware glow classes
  const glowClass = isGilded ? "deco-glow" : "terminal-glow";
  const generatingClass = isGilded ? "deco-shimmer deco-glow" : "terminal-generating terminal-generating-glow";

  const modelVisualClasses = useMemo(() => {
    // In Gilded mode, force gold color for loaded/loading states to avoid green tint
    if (isGilded && (modelStatus === "loaded" || modelStatus === "loading")) {
      return "text-primary/90 deco-glow";
    }

    switch (modelStatus) {
      case "unloaded":
        return "text-muted-foreground";
      case "loading":
        return `text-primary ${glowClass}`;
      case "loaded":
        return `text-primary ${glowClass}`;
      case "generating":
        return generatingClass;
      default:
        return "text-muted-foreground";
    }
  }, [modelStatus, glowClass, generatingClass, isGilded]);
  const isBarLoading = modelStatus === "loading";
  const shouldShowProgressBar = isBarLoading || isModelOperating || modelStatus === "generating";
  const loaderMessage = useMemo(() => {
    if (pendingOperation === "load") {
      return "Loading LM Studio model...";
    }
    if (pendingOperation === "unload") {
      return "Unloading LM Studio model...";
    }
    if (modelStatus === "generating") {
      return "Model generating response...";
    }
    return "Synchronizing LM Studio status...";
  }, [modelStatus, pendingOperation]);

  const startSlowIndicator = () => {
    if (slowOperationTimeoutRef.current) {
      clearTimeout(slowOperationTimeoutRef.current);
    }
    slowOperationTimeoutRef.current = setTimeout(() => {
      setIsSlowOperation(true);
      slowOperationTimeoutRef.current = null;
    }, 1500);
  };

  const stopSlowIndicator = () => {
    if (slowOperationTimeoutRef.current) {
      clearTimeout(slowOperationTimeoutRef.current);
      slowOperationTimeoutRef.current = null;
    }
    setIsSlowOperation(false);
  };

  const scheduleToastDismiss = (delay = 1400) => {
    if (toastDismissTimeoutRef.current) {
      clearTimeout(toastDismissTimeoutRef.current);
    }
    toastDismissTimeoutRef.current = setTimeout(() => {
      operationToastRef.current?.dismiss();
      operationToastRef.current = null;
      toastDismissTimeoutRef.current = null;
    }, delay);
  };

  const startOperationToast = (action: "load" | "unload") => {
    if (operationToastRef.current) {
      operationToastRef.current.dismiss();
    }
    const actionText = action === "load" ? "Loading model" : "Unloading model";
    operationToastRef.current = showToast({
      title: actionText,
      description: "Contacting LM Studio...",
      duration: 60000,
    });
  };

  const succeedOperationToast = (message: string) => {
    if (!operationToastRef.current) {
      operationToastRef.current = showToast({
        title: "Model ready",
        description: message,
      });
    } else {
      operationToastRef.current.update({
        id: operationToastRef.current.id,
        title: "Model ready",
        description: message,
        variant: "default",
        open: true,
      });
    }
    scheduleToastDismiss();
  };

  const failOperationToast = (message: string) => {
    if (!operationToastRef.current) {
      operationToastRef.current = showToast({
        title: "Model operation failed",
        description: message,
        variant: "destructive",
        duration: 6000,
      });
    } else {
      operationToastRef.current.update({
        id: operationToastRef.current.id,
        title: "Model operation failed",
        description: message,
        variant: "destructive",
        open: true,
      });
    }
  };

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
    setPendingOperation(isLoadingAction ? "load" : "unload");
    setIsSlowOperation(false);
    startSlowIndicator();
    startOperationToast(isLoadingAction ? "load" : "unload");
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
        succeedOperationToast(`Loaded ${model}`);
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
        succeedOperationToast(`Unloaded ${model}`);
        onModelStatusChange?.("unloaded");
      }
    } catch (error) {
      console.error("Model operation failed:", error);
      showModelError(
        error instanceof Error ? error.message : "Model operation failed"
      );
      failOperationToast(error instanceof Error ? error.message : "Model operation failed");
      onModelStatusChange?.(isLoadingAction ? "unloaded" : "loaded");
    } finally {
      stopSlowIndicator();
      setPendingOperation(null);
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
      className={cn(
        "relative h-10 md:h-12 border-b border-border bg-card flex items-center px-2 md:px-4 gap-2 md:gap-4 overflow-hidden flex-shrink-0",
        isCyberpunk && "terminal-scanlines",
        isBarLoading && "status-bar-loading"
      )}
    >
      {/* Art Deco corner sunbursts */}
      {isGilded && (
        <>
          <CornerSunburst position="tl" size={60} rays={8} opacity={0.08} />
          <CornerSunburst position="tr" size={60} rays={8} opacity={0.08} />
        </>
      )}

      {/* Centered NEXUS title - absolutely positioned for true window centering */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-0">
        <span className={`font-display text-xl md:text-2xl text-primary ${glowClass} tracking-wider`}>
          NEXUS
        </span>
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 md:h-8 md:w-8 flex-shrink-0 z-10"
            data-testid="button-hamburger-menu"
          >
            <Menu className="h-3 w-3 md:h-4 md:w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem asChild>
            <Link href="/">
              <div className="flex items-center gap-2 cursor-pointer">
                <Home className="h-4 w-4" />
                <span>Home</span>
              </div>
            </Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => onNavigate?.("settings")}>
            <div className="flex items-center gap-2 cursor-pointer">
              <Settings className="h-4 w-4" />
              <span>Settings</span>
            </div>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onNavigate?.("audition")}>
            <div className="flex items-center gap-2 cursor-pointer">
              <Sparkles className="h-4 w-4" />
              <span>Audition</span>
            </div>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Left side: MODEL status */}
      <div className="hidden md:flex items-center gap-2 text-sm md:text-base font-mono z-10" data-testid="text-model-status">
        <span className="text-primary/70">MODEL:</span>
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
            <span className={`absolute inset-0 flex items-center justify-center bg-background/95 text-destructive ${glowClass} font-bold text-[0.6rem] md:text-xs px-2 text-center leading-snug`}>
              {modelError}
            </span>
          )}
          {isModelHovered && !isModelOperating && !modelError && modelStatus !== "loading" && modelStatus !== "generating" && (
            <span className={`absolute inset-0 flex items-center justify-center bg-background/90 text-primary ${glowClass} font-bold`}>
              {modelStatus === "unloaded" ? "LOAD" : "UNLOAD"}
            </span>
          )}
          {/* Operating state */}
          {isModelOperating && !modelError && (
            <span className={`absolute inset-0 flex items-center justify-center bg-background/90 text-accent ${glowClass} font-bold`}>
              ...
            </span>
          )}
        </div>
      </div>

      {/* Spacer to push right-side elements */}
      <div className="flex-1" />

      {/* Right side: APEX status and TEST MODE badge */}
      <div className="flex items-center gap-2 md:gap-4 text-sm md:text-base font-mono z-10">
        {isStoryMode && (
          <div className="flex items-center gap-1 md:gap-2" data-testid="text-apex-status">
            <span className="text-primary/70 hidden sm:inline">APEX:</span>
            <span className={`${getStatusColor()} ${glowClass} text-sm md:text-base`}>{apexStatus}</span>
          </div>
        )}
        {isTestModeEnabled && (
          <div className="flex items-center gap-1 md:gap-2" data-testid="text-test-mode">
            <span className="px-2 py-1 rounded-sm border border-destructive/40 bg-destructive/10 text-[10px] md:text-xs font-semibold tracking-wide text-destructive">
              TEST MODE
            </span>
          </div>
        )}
      </div>
      {shouldShowProgressBar && (
        <div className="status-bar-progress" role="status" aria-live="polite">
          <div className="status-bar-progress-bar" />
          <span className="sr-only">{loaderMessage}</span>
          {isSlowOperation && (
            <span className="status-bar-progress-label">
              {pendingOperation === "load"
                ? "Awaiting LM Studio to finish loading..."
                : pendingOperation === "unload"
                  ? "Shutting down loaded model..."
                  : "LM Studio is busy..."}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
