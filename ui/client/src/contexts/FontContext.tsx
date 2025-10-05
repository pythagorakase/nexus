/**
 * Font preferences context for managing typography across the application.
 */
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface FontPreferences {
  narrativeFont: string;
  uiFont: string;
}

interface FontContextType {
  fonts: FontPreferences;
  setNarrativeFont: (font: string) => void;
  setUIFont: (font: string) => void;
  resetToDefaults: () => void;
}

const FontContext = createContext<FontContextType | undefined>(undefined);

const DEFAULT_FONTS: FontPreferences = {
  narrativeFont: 'Source Code Pro',
  uiFont: 'Source Code Pro',
};

const STORAGE_KEY = 'nexus-font-preferences';

export function FontProvider({ children }: { children: ReactNode }) {
  const [fonts, setFonts] = useState<FontPreferences>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        return JSON.parse(stored);
      } catch {
        return DEFAULT_FONTS;
      }
    }
    return DEFAULT_FONTS;
  });

  useEffect(() => {
    // Apply fonts to CSS variables
    const root = document.documentElement;
    root.style.setProperty('--font-narrative', fonts.narrativeFont);

    // Update all three Tailwind font variables to use the UI font
    root.style.setProperty('--font-sans', fonts.uiFont);
    root.style.setProperty('--font-serif', fonts.uiFont);
    root.style.setProperty('--font-mono', fonts.uiFont);

    // Save to localStorage
    localStorage.setItem(STORAGE_KEY, JSON.stringify(fonts));
  }, [fonts]);

  const setNarrativeFont = (font: string) => {
    setFonts(prev => ({ ...prev, narrativeFont: font }));
  };

  const setUIFont = (font: string) => {
    setFonts(prev => ({ ...prev, uiFont: font }));
  };

  const resetToDefaults = () => {
    setFonts(DEFAULT_FONTS);
  };

  return (
    <FontContext.Provider value={{ fonts, setNarrativeFont, setUIFont, resetToDefaults }}>
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
