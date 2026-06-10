/**
 * Veil theme splash page — the canonical NEXUS IRIS hero.
 *
 * A living logarithmic-spiral field (VeilSpiral) draws the Megrim NEXUS
 * wordmark and knocks the field out behind it with a feathered rect mask;
 * the licensed Art Nouveau border (NouveauFrame) frames the wordmark. The
 * three-button menu drops to the lower third of the screen.
 *
 * The hero prop values below are the approved exploration values, locked in
 * the design handoff (design_handoff/project/ui_kits/nexus_iris/splash.jsx)
 * — treat them as canon: gold wordmark #e1cd97 at 120px, magenta frame
 * #b83d7a at 0.82 opacity, 2.25x width, frame size 400u, composition
 * anchored at y=312 so the frame clears the menu.
 *
 * The marquee font (Megrim) appears EXACTLY ONCE: the big NEXUS, drawn
 * inside VeilSpiral. Everything else uses the menu font.
 */
import { CSSProperties, ReactNode, useState } from 'react';

import { NouveauFrame, VeilSpiral } from '@/components/veil';
import { useSplashNavigation, SplashThemeMenu } from './shared';

// Veil brand values (lifted from the .dark theme tokens; hard-coded here so
// the locked splash composition cannot drift with token edits)
const veil = {
  bg: '#09101c',
  magenta: '#b83d7a',
  copper: '#b87333',
  gold: '#e1cd97',
} as const;

interface VeilButtonProps {
  children: ReactNode;
  onClick: () => void;
  animationClass?: string;
  primary?: boolean;
}

/**
 * Veil splash menu button, per the kit's `.splash-btn` rules: wide-tracked
 * uppercase menu font on a transparent ground with a deep-violet border;
 * hover swaps to a magenta wash + glow. No corner pips (those are Gilded).
 */
const VeilButton = ({ children, onClick, animationClass = '', primary = false }: VeilButtonProps) => {
  const [hovered, setHovered] = useState(false);

  const base: CSSProperties = {
    position: 'relative',
    width: 280,
    padding: '16px 28px',
    fontFamily: 'var(--font-menu)',
    fontSize: 13,
    letterSpacing: '0.3em',
    textTransform: 'uppercase',
    fontWeight: 600,
    background: 'transparent',
    border: '1px solid hsl(270 40% 28% / 0.8)',
    color: 'hsl(42 45% 80%)',
    borderRadius: 'var(--radius-sm)',
    cursor: 'pointer',
    transition: 'background .2s, color .2s, border-color .2s, box-shadow .2s',
  };

  const hover: CSSProperties = {
    background: 'hsl(320 55% 50% / 0.08)',
    color: 'hsl(42 50% 92%)',
    border: '1px solid var(--brass)',
    boxShadow: '0 0 18px hsl(320 55% 50% / 0.35)',
    textShadow: '0 0 10px hsl(320 55% 60% / 0.6)',
  };

  const primaryStyle: CSSProperties = {
    border: '2px solid var(--brass)',
    color: 'hsl(42 50% 90%)',
    boxShadow: '0 0 12px hsl(320 55% 50% / 0.35), inset 0 0 18px hsl(320 55% 50% / 0.12)',
  };

  const primaryHover: CSSProperties = {
    background: 'hsl(320 55% 50% / 0.12)',
    boxShadow: '0 0 22px hsl(320 55% 50% / 0.55), inset 0 0 22px hsl(320 55% 50% / 0.2)',
  };

  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={animationClass}
      style={{
        ...base,
        ...(primary ? primaryStyle : {}),
        ...(hovered ? hover : {}),
        ...(hovered && primary ? { ...primaryStyle, ...primaryHover } : {}),
      }}
    >
      {children}
    </button>
  );
};

export function VeilSplash() {
  const { isExiting, handleContinue, handleLoad, handleSettings, getAnimationClass } =
    useSplashNavigation();

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        // Hero mode: the spiral fills the frame; the menu drops to the
        // lower third.
        justifyContent: 'flex-end',
        backgroundColor: veil.bg,
        overflow: 'hidden',
      }}
    >
      {/* Theme switcher menu */}
      <SplashThemeMenu />

      {/* Hero layer: living spiral field + licensed Art Nouveau border.
          Both render the same 1200x700 viewBox with xMidYMid slice so the
          frame tracks the wordmark across viewport sizes. */}
      <div
        className={isExiting ? 'animate-fade-out-fast' : ''}
        style={{ position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none' }}
      >
        <VeilSpiral
          arms={18}
          growth={0.62}
          rotation={70}
          reverse
          anchorY={312}
          wordmarkY={312}
          pulseRate={1.6}
          pulseColor={veil.gold}
          emberRate={2.5}
          emberColor={veil.gold}
          emberSize={1.8}
          maskMode="rect"
          rectPaddingX={42}
          rectPaddingY={22}
          rectFeather={24}
          maskHaloPx={28}
          maskStrength={0.95}
          primaryColor={veil.magenta}
          secondaryColor={veil.copper}
          wordmarkColor={veil.gold}
          fontSize={120}
        />
        <NouveauFrame
          color={veil.magenta}
          opacity={0.82}
          sizeU={400}
          widthFactor={2.25}
          heightFactor={1}
          anchorY={312}
          glow
        />
      </div>

      {/* Menu buttons — lower third */}
      <div
        style={{
          position: 'relative',
          zIndex: 5,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 14,
          marginBottom: '9vh',
        }}
      >
        <VeilButton primary onClick={handleContinue} animationClass={getAnimationClass('continue')}>
          Continue
        </VeilButton>
        <VeilButton onClick={handleLoad} animationClass={getAnimationClass('load')}>
          Load
        </VeilButton>
        <VeilButton onClick={handleSettings} animationClass={getAnimationClass('settings')}>
          Settings
        </VeilButton>
      </div>

      {/* Footnote */}
      <div
        className={isExiting ? 'animate-fade-out-fast' : ''}
        style={{
          position: 'absolute',
          bottom: 28,
          display: 'flex',
          gap: 14,
          alignItems: 'center',
          fontFamily: 'var(--font-menu)',
          fontSize: 10,
          letterSpacing: '0.25em',
          textTransform: 'uppercase',
          color: 'var(--fg-muted)',
          opacity: 0.7,
          zIndex: 5,
        }}
      >
        <span>NEXUS IRIS</span>
        <span style={{ color: 'var(--brass)' }}>◆</span>
        <span>narrative intelligence system</span>
      </div>
    </div>
  );
}
