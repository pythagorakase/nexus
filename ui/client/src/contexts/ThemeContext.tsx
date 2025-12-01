import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export type Theme = 'gilded' | 'vector' | 'veil';

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  isGilded: boolean;
  isVector: boolean;
  isVeil: boolean;
  // Legacy aliases for backwards compatibility during transition
  isCyberpunk: boolean;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const STORAGE_KEY = 'nexus-theme';
const DEFAULT_THEME: Theme = 'gilded';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    // Handle migration from old 'cyberpunk' to 'vector'
    if (stored === 'cyberpunk') return 'vector';
    return (stored === 'gilded' || stored === 'vector' || stored === 'veil') ? stored : DEFAULT_THEME;
  });

  useEffect(() => {
    const root = document.documentElement;
    root.classList.add('dark');
    // Remove all theme classes first
    root.classList.remove('theme-vector', 'theme-veil');
    // Add the appropriate theme class
    if (theme === 'vector') {
      root.classList.add('theme-vector');
    } else if (theme === 'veil') {
      root.classList.add('theme-veil');
    }
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const setTheme = (newTheme: Theme) => setThemeState(newTheme);

  return (
    <ThemeContext.Provider value={{
      theme,
      setTheme,
      isGilded: theme === 'gilded',
      isVector: theme === 'vector',
      isVeil: theme === 'veil',
      // Legacy alias
      isCyberpunk: theme === 'vector'
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
