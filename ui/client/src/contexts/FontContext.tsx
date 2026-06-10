/**
 * Font preferences context. Theme-aware: applies the persisted font matrix
 * (ui.fonts in nexus.toml, served via GET /api/settings) to the CSS custom
 * properties for the active theme. Writes go through PATCH /api/settings -
 * localStorage only seeds the first paint before the query resolves.
 */
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useTheme } from './ThemeContext';
import { useSettingsMutation, useSettingsQuery } from '@/hooks/useSettings';
import type { FontMatrix, FontSlotId, ThemeId } from '@/types/settings';

/**
 * The NEXUS IRIS keeper matrix - first-paint seed only. The persisted
 * defaults live in UISettings (settings_models.py) and nexus.toml [ui.fonts].
 */
const KEEPERS: FontMatrix = {
  veil: { body: 'Spectral', menu: 'Cinzel', display: 'Megrim' },
  gilded: { body: 'Cormorant Garamond', menu: 'Space Mono', display: 'Monoton' },
  vector: { body: 'Rajdhani', menu: 'Source Code Pro', display: 'Sixtyfour' },
};

const STORAGE_KEY = 'nexus-font-preferences-v5';

interface FontContextType {
  fonts: FontMatrix;
  setFont: (theme: ThemeId, slot: FontSlotId, font: string) => void;
  resetToKeepers: () => void;
  // Convenience getters for the active theme
  currentBodyFont: string;
  currentMenuFont: string;
  currentDisplayFont: string;
}

const FontContext = createContext<FontContextType | undefined>(undefined);

function seedFromStorage(): FontMatrix {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored) {
    try {
      const parsed = JSON.parse(stored) as Partial<FontMatrix>;
      return {
        veil: { ...KEEPERS.veil, ...parsed.veil },
        gilded: { ...KEEPERS.gilded, ...parsed.gilded },
        vector: { ...KEEPERS.vector, ...parsed.vector },
      };
    } catch {
      return KEEPERS;
    }
  }
  return KEEPERS;
}

export function FontProvider({ children }: { children: ReactNode }) {
  const { theme } = useTheme();
  const { data: settings } = useSettingsQuery();
  const mutation = useSettingsMutation();

  const [seed] = useState<FontMatrix>(seedFromStorage);
  const fonts: FontMatrix = settings?.ui?.fonts ?? seed;

  // Mirror the server matrix into localStorage so the next first paint
  // matches the persisted state.
  useEffect(() => {
    if (settings?.ui?.fonts) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings.ui.fonts));
    }
  }, [settings?.ui?.fonts]);

  useEffect(() => {
    const root = document.documentElement;
    const slots = fonts[theme as ThemeId] ?? KEEPERS[theme as ThemeId];

    root.style.setProperty('--font-narrative', slots.body);
    root.style.setProperty('--font-display', slots.display);
    if (theme === 'vector') {
      // Vector chrome is all-terminal: the menu font carries every UI face.
      root.style.setProperty('--font-sans', slots.menu);
      root.style.setProperty('--font-serif', slots.menu);
      root.style.setProperty('--font-mono', slots.menu);
    } else {
      root.style.setProperty('--font-sans', slots.body);
      root.style.setProperty('--font-serif', slots.body);
      root.style.setProperty('--font-mono', slots.menu);
    }
  }, [fonts, theme]);

  const setFont = (themeId: ThemeId, slot: FontSlotId, font: string) => {
    mutation.mutate({ fonts: { [themeId]: { [slot]: font } } });
  };

  const resetToKeepers = () => {
    mutation.mutate({ fonts: KEEPERS });
  };

  const active = fonts[theme as ThemeId] ?? KEEPERS[theme as ThemeId];

  return (
    <FontContext.Provider
      value={{
        fonts,
        setFont,
        resetToKeepers,
        currentBodyFont: active.body,
        currentMenuFont: active.menu,
        currentDisplayFont: active.display,
      }}
    >
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
