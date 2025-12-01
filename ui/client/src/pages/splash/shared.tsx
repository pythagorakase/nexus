/**
 * Shared utilities for splash page variants.
 * Contains navigation hooks, animation constants, and common types.
 */
import { useState } from 'react';
import { useLocation } from 'wouter';
import { Menu, Sparkles, Monitor, Wand2 } from 'lucide-react';
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
 * Safe localStorage access - handles environments where localStorage
 * may not be available (SSR, strict privacy mode, etc.)
 */
export const getActiveSlot = (): string | null => {
  try {
    return localStorage.getItem('activeSlot');
  } catch {
    return null;
  }
};

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
    const activeSlot = getActiveSlot();
    const destination = activeSlot ? '/nexus' : '/new-story';
    handleNavigation(destination, 'continue');
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
 * Theme switcher menu for splash screens.
 * Positioned in top-left corner with theme-aware styling.
 */
export const SplashThemeMenu = () => {
  const { theme, setTheme, glowClass } = useTheme();

  const themeOptions: { value: Theme; label: string; icon: typeof Sparkles }[] = [
    { value: 'gilded', label: 'Gilded', icon: Sparkles },
    { value: 'vector', label: 'Vector', icon: Monitor },
    { value: 'veil', label: 'Veil', icon: Wand2 },
  ];

  return (
    <div style={{ position: 'absolute', top: 16, left: 16, zIndex: 50 }}>
      <DropdownMenu>
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
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
};
