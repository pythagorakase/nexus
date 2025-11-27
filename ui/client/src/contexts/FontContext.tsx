/**
 * Font preferences context for managing typography across the application.
 * Theme-aware: Only applies custom font overrides for Cyberpunk theme.
 * Gilded theme uses CSS-defined fonts (Cormorant Garamond + Xanh Mono).
 */
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useTheme } from './ThemeContext';

interface FontPreferences {
  // Cyberpunk theme fonts
  cyberpunkNarrativeFont: string;
  cyberpunkUIFont: string;
  cyberpunkDisplayFont: string;
  // Gilded theme fonts
  gildedBodyFont: string;
  gildedMenuFont: string;
  gildedDisplayFont: string;
}

interface FontContextType {
  fonts: FontPreferences;
  // Cyberpunk setters
  setCyberpunkNarrativeFont: (font: string) => void;
  setCyberpunkUIFont: (font: string) => void;
  setCyberpunkDisplayFont: (font: string) => void;
  // Gilded setters
  setGildedBodyFont: (font: string) => void;
  setGildedMenuFont: (font: string) => void;
  setGildedDisplayFont: (font: string) => void;
  resetToDefaults: () => void;
  // Convenience getters for current theme
  currentBodyFont: string;
  currentMenuFont: string;
  currentDisplayFont: string;
}

const FontContext = createContext<FontContextType | undefined>(undefined);

const DEFAULT_FONTS: FontPreferences = {
  cyberpunkNarrativeFont: 'Source Code Pro',
  cyberpunkUIFont: 'Source Code Pro',
  cyberpunkDisplayFont: 'Sixtyfour',
  gildedBodyFont: 'Cormorant Garamond',
  gildedMenuFont: 'Xanh Mono',
  gildedDisplayFont: 'Monoton',
};

const STORAGE_KEY = 'nexus-font-preferences-v3';

export function FontProvider({ children }: { children: ReactNode }) {
  const { theme, isGilded } = useTheme();

  const [fonts, setFonts] = useState<FontPreferences>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        return { ...DEFAULT_FONTS, ...JSON.parse(stored) };
      } catch {
        return DEFAULT_FONTS;
      }
    }
    return DEFAULT_FONTS;
  });

  useEffect(() => {
    const root = document.documentElement;

    if (isGilded) {
      // Gilded theme: Use theme-specific fonts
      root.style.setProperty('--font-narrative', fonts.gildedBodyFont);
      root.style.setProperty('--font-sans', fonts.gildedBodyFont);
      root.style.setProperty('--font-serif', fonts.gildedBodyFont);
      root.style.setProperty('--font-mono', fonts.gildedMenuFont);
      root.style.setProperty('--font-display', fonts.gildedDisplayFont);
    } else {
      // Cyberpunk theme: Use cyberpunk-specific fonts
      root.style.setProperty('--font-narrative', fonts.cyberpunkNarrativeFont);
      root.style.setProperty('--font-sans', fonts.cyberpunkUIFont);
      root.style.setProperty('--font-serif', fonts.cyberpunkUIFont);
      root.style.setProperty('--font-mono', fonts.cyberpunkUIFont);
      root.style.setProperty('--font-display', fonts.cyberpunkDisplayFont);
    }

    // Save to localStorage
    localStorage.setItem(STORAGE_KEY, JSON.stringify(fonts));
  }, [fonts, isGilded, theme]);

  const setCyberpunkNarrativeFont = (font: string) => {
    setFonts(prev => ({ ...prev, cyberpunkNarrativeFont: font }));
  };

  const setCyberpunkUIFont = (font: string) => {
    setFonts(prev => ({ ...prev, cyberpunkUIFont: font }));
  };

  const setGildedBodyFont = (font: string) => {
    setFonts(prev => ({ ...prev, gildedBodyFont: font }));
  };

  const setGildedMenuFont = (font: string) => {
    setFonts(prev => ({ ...prev, gildedMenuFont: font }));
  };

  const setGildedDisplayFont = (font: string) => {
    setFonts(prev => ({ ...prev, gildedDisplayFont: font }));
  };

  const setCyberpunkDisplayFont = (font: string) => {
    setFonts(prev => ({ ...prev, cyberpunkDisplayFont: font }));
  };

  const resetToDefaults = () => {
    setFonts(DEFAULT_FONTS);
  };

  // Convenience getters for current theme
  const currentBodyFont = isGilded ? fonts.gildedBodyFont : fonts.cyberpunkNarrativeFont;
  const currentMenuFont = isGilded ? fonts.gildedMenuFont : fonts.cyberpunkUIFont;
  const currentDisplayFont = isGilded ? fonts.gildedDisplayFont : fonts.cyberpunkDisplayFont;

  return (
    <FontContext.Provider value={{
      fonts,
      setCyberpunkNarrativeFont,
      setCyberpunkUIFont,
      setCyberpunkDisplayFont,
      setGildedBodyFont,
      setGildedMenuFont,
      setGildedDisplayFont,
      resetToDefaults,
      currentBodyFont,
      currentMenuFont,
      currentDisplayFont,
    }}>
      {children}
    </FontContext.Provider>
  );
}

export function useFonts() {
  const context = useContext(FontContext);
  if (context === undefined) {
    throw new Error('useFonts must be used within a FontProvider');
  }
  return context;
}
