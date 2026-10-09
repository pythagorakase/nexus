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
import { SplashThemeMenu } from './splash/shared';

export default function SplashPage() {
  const { isVector, isVeil } = useTheme();
  // One theme menu outside the variant swap: a pick switches the variant
  // optimistically and a rejected save switches it back, and a menu inside
  // the variant would remount and lose the rejection it should show.
  return (
    <>
      {isVeil ? <VeilSplash /> : isVector ? <VectorSplash /> : <GildedSplash />}
      <SplashThemeMenu />
    </>
  );
}
