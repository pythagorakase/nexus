import { useMemo } from "react";
import { Menu, Home, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
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
import { ThemeMenu } from "@/components/ThemeMenu";
import { cn } from "@/lib/utils";

interface StatusBarProps {
  model: string;
  apexStatus: "OFFLINE" | "READY" | "TRANSMITTING" | "GENERATING" | "RECEIVING";
  isStoryMode: boolean;
  isTestModeEnabled?: boolean;
  activeSlot?: number;
  userCharacterName?: string;
  onNavigate?: (tab: string) => void;
}

export function StatusBar({
  model,
  apexStatus,
  isStoryMode,
  isTestModeEnabled = false,
  activeSlot,
  userCharacterName,
  onNavigate,
}: StatusBarProps) {
  const { isGilded, isVector, glowClass, generatingClass } = useTheme();

  const modelVisualClasses = useMemo(() => {
    if (apexStatus === "GENERATING") {
      return generatingClass;
    }
    if (isGilded) {
      return "text-primary/90 deco-glow";
    }
    return `text-primary ${glowClass}`;
  }, [apexStatus, glowClass, generatingClass, isGilded]);
  const shouldShowProgressBar = apexStatus === "GENERATING";

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
        isVector && "terminal-scanlines",
        shouldShowProgressBar && "status-bar-loading"
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
          <ThemeMenu />
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Left side: Slot indicator */}
      {activeSlot !== undefined && userCharacterName && (
        <div className="hidden md:flex items-center gap-1 text-xs font-mono z-10 text-muted-foreground">
          <span className="text-primary/70">SLOT {activeSlot}:</span>
          <span className={`${glowClass}`}>{userCharacterName}</span>
        </div>
      )}

      {/* Spacer to push right-side elements */}
      <div className="flex-1" />

      {/* Right side: MODEL status, SKALD status, and TEST MODE badge */}
      <div className="flex items-center gap-2 md:gap-4 text-sm md:text-base font-mono z-10">
        {/* MODEL status */}
        <div className="hidden md:flex items-center gap-2" data-testid="text-model-status">
          <span className="text-primary/70 text-xs">MODEL:</span>
          <div className="relative text-sm tracking-wide">
            <span className={`relative inline-block min-w-[3rem] px-0.5 transition-colors duration-300 ${modelVisualClasses}`}>
              {model}
            </span>
          </div>
        </div>

        {/* SKALD status */}
        {isStoryMode && (
          <div className="flex items-center gap-1 md:gap-2" data-testid="text-apex-status">
            <span className="text-primary/70 hidden sm:inline">SKALD:</span>
            <span className={`${getStatusColor()} ${glowClass} text-sm md:text-base`}>{apexStatus}</span>
          </div>
        )}

        {/* TEST MODE badge */}
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
          <span className="sr-only">Model generating response...</span>
        </div>
      )}
    </div>
  );
}
