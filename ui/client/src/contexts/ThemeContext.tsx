import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useSettingsMutation, useSettingsQuery } from '@/hooks/useSettings';
import { applyThemeIcons } from '@/lib/themeIcons';

export type Theme = 'gilded' | 'vector' | 'veil';

const THEMES: Theme[] = ['gilded', 'vector', 'veil'];

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  isGilded: boolean;
  isVector: boolean;
  isVeil: boolean;
  // Centralized glow classes to prevent theme drift
  glowClass: string;
  generatingClass: string;
  // Legacy aliases for backwards compatibility during transition
  isCyberpunk: boolean;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const STORAGE_KEY = 'nexus-theme';
const DEFAULT_THEME: Theme = 'veil';

export function ThemeProvider({ children }: { children: ReactNode }) {
  // localStorage seeds the first paint only; the persisted source of truth
  // is ui.theme in nexus.toml (GET/PATCH /api/settings).
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    // Handle migration from old 'cyberpunk' to 'vector'
    if (stored === 'cyberpunk') return 'vector';
    return THEMES.includes(stored as Theme) ? (stored as Theme) : DEFAULT_THEME;
  });

  const { data: settings } = useSettingsQuery();
  const mutation = useSettingsMutation();
  const serverTheme = settings?.ui?.theme;

  // Adopt the server-persisted theme when it arrives or changes. Because
  // setTheme() updates the query cache optimistically, this also reverts the
  // chrome automatically if a PATCH fails and the cache rolls back.
  useEffect(() => {
    if (serverTheme && THEMES.includes(serverTheme) && serverTheme !== theme) {
      setThemeState(serverTheme);
    }
  }, [serverTheme, theme]);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.add('dark');
    // Veil is the default theme (bare .dark); Gilded and Vector are override
    // classes. Remove all override classes first (theme-veil is legacy).
    root.classList.remove('theme-gilded', 'theme-vector', 'theme-veil');
    if (theme === 'gilded') {
      root.classList.add('theme-gilded');
    } else if (theme === 'vector') {
      root.classList.add('theme-vector');
    }
    localStorage.setItem(STORAGE_KEY, theme);
    // Favicon + apple-touch icons follow the active theme (one mark, three
    // liveries). PWA manifest icons are bake-time and stay on Veil.
    applyThemeIcons(theme);
  }, [theme]);

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    mutation.mutate({ theme: newTheme });
  };

  const isGilded = theme === 'gilded';
  const isVector = theme === 'vector';
  const isVeil = theme === 'veil';

  // Centralized glow classes - single source of truth for all components
  const glowClass = isGilded ? "deco-glow" : isVeil ? "veil-glow" : "terminal-glow";
  const generatingClass = isGilded
    ? "deco-shimmer deco-glow"
    : isVeil
    ? "veil-shimmer veil-glow"
    : "terminal-generating terminal-generating-glow";

  return (
    <ThemeContext.Provider value={{
      theme,
      setTheme,
      isGilded,
      isVector,
      isVeil,
      glowClass,
      generatingClass,
      // Legacy alias
      isCyberpunk: isVector
    }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error('useTheme must be used within ThemeProvider');
  return context;
}
