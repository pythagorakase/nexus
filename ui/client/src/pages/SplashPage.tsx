/**
 * Splash page router - Renders theme-appropriate splash variant.
 * - Gilded: Art Deco aesthetic
 * - Vector: Terminal/digital aesthetic
 * - Veil: Art Nouveau aesthetic
 */
import { useTheme } from '@/contexts/ThemeContext';
import { GildedSplash } from './splash/GildedSplash';
import { VectorSplash } from './splash/VectorSplash';
import { VeilSplash } from './splash/VeilSplash';

export default function SplashPage() {
  const { isVector, isVeil } = useTheme();
  return isVeil ? <VeilSplash />
       : isVector ? <VectorSplash />
       : <GildedSplash />;
}
