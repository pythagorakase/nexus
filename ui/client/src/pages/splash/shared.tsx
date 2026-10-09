/**
 * Shared utilities for splash page variants.
 * Contains navigation hooks, animation constants, and common types.
 */
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { useLocation } from 'wouter';
import { AlertTriangle, Menu, Sparkles, Monitor, Wand2 } from 'lucide-react';
import { useTheme, Theme } from '@/contexts/ThemeContext';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';

// Animation timing constants (in milliseconds)
export const ANIMATION = {
  FADE_OUT_FAST: 500,
  FADE_OUT_SLOW: 750,
  FADE_IN: 500,
} as const;

/**
 * Shared navigation hook for splash page variants.
 * Handles staggered fade-out animation before navigation.
 */
export const useSplashNavigation = () => {
  const [, setLocation] = useLocation();
  const [isExiting, setIsExiting] = useState(false);
  const [clickedButton, setClickedButton] = useState<string | null>(null);

  const handleNavigation = (destination: string, buttonId: string) => {
    setClickedButton(buttonId);
    setIsExiting(true);
    // Navigate after clicked element's animation completes
    setTimeout(() => setLocation(destination), ANIMATION.FADE_OUT_SLOW);
  };

  const handleContinue = () => {
    handleNavigation('/continue', 'continue');
  };

  const handleLoad = () => {
    handleNavigation('/new-story', 'load');
  };

  const handleSettings = () => {
    handleNavigation('/nexus?tab=settings', 'settings');
  };

  /**
   * Returns the appropriate animation class based on exit state.
   * Clicked button gets slow fade, others get fast fade.
   */
  const getAnimationClass = (buttonId: string): string => {
    if (!isExiting) return '';
    return clickedButton === buttonId
      ? 'animate-fade-out-slow'
      : 'animate-fade-out-fast';
  };

  return {
    isExiting,
    handleContinue,
    handleLoad,
    handleSettings,
    getAnimationClass,
  };
};

/**
 * The Settings card's danger alert reads --danger, which nexus-layout.css
 * defines only inside the Settings pane; the menu portal sits outside it,
 * so map the same token here.
 */
const SPLASH_ALERT_STYLE = { '--danger': 'hsl(var(--destructive))' } as CSSProperties;

/**
 * Theme switcher menu for splash screens.
 * Positioned in top-left corner with theme-aware styling.
 * A rejected save reopens the menu and shows the reason below the themes.
 */
export const SplashThemeMenu = () => {
  const { theme, setTheme, glowClass, saveError, clearSaveError } = useTheme();
  const [open, setOpen] = useState(false);
  const lastError = useRef(saveError);

  // Show a rejection where the pick happened: open the menu when a save
  // fails, not when the menu mounts with an earlier failure.
  useEffect(() => {
    if (saveError !== null && lastError.current === null) setOpen(true);
    lastError.current = saveError;
  }, [saveError]);

  // Settings must not inherit a failure caused on Home.
  useEffect(() => clearSaveError, [clearSaveError]);

  const themeOptions: { value: Theme; label: string; icon: typeof Sparkles }[] = [
    { value: 'gilded', label: 'Gilded', icon: Sparkles },
    { value: 'vector', label: 'Vector', icon: Monitor },
    { value: 'veil', label: 'Veil', icon: Wand2 },
  ];

  return (
    <div style={{ position: 'absolute', top: 28, left: 28, zIndex: 50 }}>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className={`text-primary/70 hover:text-primary hover:bg-primary/10 ${glowClass}`}
          >
            <Menu className="h-5 w-5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-[140px]">
          <DropdownMenuLabel className="text-xs text-muted-foreground">
            Theme
          </DropdownMenuLabel>
          {themeOptions.map(({ value, label, icon: Icon }) => (
            <DropdownMenuItem key={value} onClick={() => setTheme(value)}>
              <div className="flex items-center gap-2 cursor-pointer">
                <Icon className="h-4 w-4" />
                <span>{label}{theme === value ? ' ✓' : ''}</span>
              </div>
            </DropdownMenuItem>
          ))}
          {saveError !== null && (
            <div
              className="alert danger mt-1 max-w-[280px] break-words"
              role="alert"
              data-testid="splash-theme-save-error"
              style={SPLASH_ALERT_STYLE}
            >
              <AlertTriangle size={14} />
              <div className="min-w-0">
                <div className="alert-title">WRITE REJECTED</div>
                <div className="alert-body">{saveError}</div>
              </div>
            </div>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
};
