import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export type Theme = 'gilded' | 'cyberpunk';

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  isGilded: boolean;
  isCyberpunk: boolean;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const STORAGE_KEY = 'nexus-theme';
const DEFAULT_THEME: Theme = 'gilded';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return (stored === 'gilded' || stored === 'cyberpunk') ? stored : DEFAULT_THEME;
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'cyberpunk') {
      root.classList.add('theme-cyberpunk');
    } else {
      root.classList.remove('theme-cyberpunk');
    }
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const setTheme = (newTheme: Theme) => setThemeState(newTheme);
  const toggleTheme = () => setThemeState(t => t === 'gilded' ? 'cyberpunk' : 'gilded');

  return (
    <ThemeContext.Provider value={{
      theme,
      setTheme,
      toggleTheme,
      isGilded: theme === 'gilded',
      isCyberpunk: theme === 'cyberpunk'
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
