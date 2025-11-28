/**
 * Splash page router - Renders theme-appropriate splash variant.
 * Gilded theme gets Art Deco aesthetic, Cyberpunk gets terminal aesthetic.
 */
import { useTheme } from '@/contexts/ThemeContext';
import { GildedSplash } from './splash/GildedSplash';
import { CyberpunkSplash } from './splash/CyberpunkSplash';

export default function SplashPage() {
  const { isCyberpunk } = useTheme();
  return isCyberpunk ? <CyberpunkSplash /> : <GildedSplash />;
}
