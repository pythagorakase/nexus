/**
 * Font preferences context for managing typography across the application.
 * Theme-aware: Applies appropriate fonts for each theme (Gilded, Vector, Veil).
 */
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useTheme } from './ThemeContext';

interface FontPreferences {
  // Vector (Cyberpunk) theme fonts
  vectorNarrativeFont: string;
  vectorUIFont: string;
  vectorDisplayFont: string;
  // Gilded theme fonts
  gildedBodyFont: string;
  gildedMenuFont: string;
  gildedDisplayFont: string;
  // Veil theme fonts
  veilBodyFont: string;
  veilMenuFont: string;
  veilDisplayFont: string;
  // Legacy aliases (deprecated - use vector* instead)
  cyberpunkNarrativeFont?: string;
  cyberpunkUIFont?: string;
  cyberpunkDisplayFont?: string;
}

interface FontContextType {
  fonts: FontPreferences;
  // Vector (Cyberpunk) setters
  setVectorNarrativeFont: (font: string) => void;
  setVectorUIFont: (font: string) => void;
  setVectorDisplayFont: (font: string) => void;
  // Gilded setters
  setGildedBodyFont: (font: string) => void;
  setGildedMenuFont: (font: string) => void;
  setGildedDisplayFont: (font: string) => void;
  // Veil setters
  setVeilBodyFont: (font: string) => void;
  setVeilMenuFont: (font: string) => void;
  setVeilDisplayFont: (font: string) => void;
  resetToDefaults: () => void;
  // Convenience getters for current theme
  currentBodyFont: string;
  currentMenuFont: string;
  currentDisplayFont: string;
  // Legacy aliases
  setCyberpunkNarrativeFont: (font: string) => void;
  setCyberpunkUIFont: (font: string) => void;
  setCyberpunkDisplayFont: (font: string) => void;
}

const FontContext = createContext<FontContextType | undefined>(undefined);

const DEFAULT_FONTS: FontPreferences = {
  // Vector (Cyberpunk) theme
  vectorNarrativeFont: 'Source Code Pro',
  vectorUIFont: 'Source Code Pro',
  vectorDisplayFont: 'Sixtyfour',
  // Gilded theme
  gildedBodyFont: 'Cormorant Garamond',
  gildedMenuFont: 'Space Mono',
  gildedDisplayFont: 'Monoton',
  // Veil theme (Art Nouveau)
  veilBodyFont: 'Spectral',
  veilMenuFont: 'Cinzel',
  veilDisplayFont: 'Cinzel',
};

const STORAGE_KEY = 'nexus-font-preferences-v4';

export function FontProvider({ children }: { children: ReactNode }) {
  const { theme, isGilded, isVector, isVeil } = useTheme();

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
      // Gilded theme: Art Deco aesthetic
      root.style.setProperty('--font-narrative', fonts.gildedBodyFont);
      root.style.setProperty('--font-sans', fonts.gildedBodyFont);
      root.style.setProperty('--font-serif', fonts.gildedBodyFont);
      root.style.setProperty('--font-mono', fonts.gildedMenuFont);
      root.style.setProperty('--font-display', fonts.gildedDisplayFont);
    } else if (isVector) {
      // Vector theme: Cyberpunk/terminal aesthetic
      root.style.setProperty('--font-narrative', fonts.vectorNarrativeFont);
      root.style.setProperty('--font-sans', fonts.vectorUIFont);
      root.style.setProperty('--font-serif', fonts.vectorUIFont);
      root.style.setProperty('--font-mono', fonts.vectorUIFont);
      root.style.setProperty('--font-display', fonts.vectorDisplayFont);
    } else if (isVeil) {
      // Veil theme: Art Nouveau aesthetic
      root.style.setProperty('--font-narrative', fonts.veilBodyFont);
      root.style.setProperty('--font-sans', fonts.veilBodyFont);
      root.style.setProperty('--font-serif', fonts.veilBodyFont);
      root.style.setProperty('--font-mono', fonts.veilMenuFont);
      root.style.setProperty('--font-display', fonts.veilDisplayFont);
    }

    // Save to localStorage
    localStorage.setItem(STORAGE_KEY, JSON.stringify(fonts));
  }, [fonts, isGilded, isVector, isVeil, theme]);

  // Vector setters
  const setVectorNarrativeFont = (font: string) => {
    setFonts(prev => ({ ...prev, vectorNarrativeFont: font }));
  };

  const setVectorUIFont = (font: string) => {
    setFonts(prev => ({ ...prev, vectorUIFont: font }));
  };

  const setVectorDisplayFont = (font: string) => {
    setFonts(prev => ({ ...prev, vectorDisplayFont: font }));
  };

  // Gilded setters
  const setGildedBodyFont = (font: string) => {
    setFonts(prev => ({ ...prev, gildedBodyFont: font }));
  };

  const setGildedMenuFont = (font: string) => {
    setFonts(prev => ({ ...prev, gildedMenuFont: font }));
  };

  const setGildedDisplayFont = (font: string) => {
    setFonts(prev => ({ ...prev, gildedDisplayFont: font }));
  };

  // Veil setters
  const setVeilBodyFont = (font: string) => {
    setFonts(prev => ({ ...prev, veilBodyFont: font }));
  };

  const setVeilMenuFont = (font: string) => {
    setFonts(prev => ({ ...prev, veilMenuFont: font }));
  };

  const setVeilDisplayFont = (font: string) => {
    setFonts(prev => ({ ...prev, veilDisplayFont: font }));
  };

  const resetToDefaults = () => {
    setFonts(DEFAULT_FONTS);
  };

  // Convenience getters for current theme
  const currentBodyFont = isGilded ? fonts.gildedBodyFont
    : isVector ? fonts.vectorNarrativeFont
    : fonts.veilBodyFont;
  const currentMenuFont = isGilded ? fonts.gildedMenuFont
    : isVector ? fonts.vectorUIFont
    : fonts.veilMenuFont;
  const currentDisplayFont = isGilded ? fonts.gildedDisplayFont
    : isVector ? fonts.vectorDisplayFont
    : fonts.veilDisplayFont;

  // Legacy aliases for backwards compatibility
  const setCyberpunkNarrativeFont = setVectorNarrativeFont;
  const setCyberpunkUIFont = setVectorUIFont;
  const setCyberpunkDisplayFont = setVectorDisplayFont;

  return (
    <FontContext.Provider value={{
      fonts,
      setVectorNarrativeFont,
      setVectorUIFont,
      setVectorDisplayFont,
      setGildedBodyFont,
      setGildedMenuFont,
      setGildedDisplayFont,
      setVeilBodyFont,
      setVeilMenuFont,
      setVeilDisplayFont,
      resetToDefaults,
      currentBodyFont,
      currentMenuFont,
      currentDisplayFont,
      // Legacy aliases
      setCyberpunkNarrativeFont,
      setCyberpunkUIFont,
      setCyberpunkDisplayFont,
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
