/**
 * Shared utilities for splash page variants.
 * Contains navigation hooks, animation constants, and common types.
 */
import { useState } from 'react';
import { useLocation } from 'wouter';

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
