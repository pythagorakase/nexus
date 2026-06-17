/**
 * Gilded theme splash page - the approved Art Deco home screen.
 *
 * The composition comes from the NEXUS IRIS design handoff: an off-screen brass
 * ray field behind the marquee and the licensed r1c1 Deco frame dynamically
 * sliced around the whole viewport. The marquee font appears exactly once.
 */
import { CSSProperties, ReactNode, useState } from 'react';

import decoFrameR1C1 from '@/assets/ArtDecoFrames-549888080/r1c1.png';
import { DECO_FRAME_META } from '@/assets/ArtDecoFrames-549888080/frames-meta';
import { DecoFrameSliced, DecoRays } from './GildedDeco';
import { useSplashNavigation, SplashThemeMenu } from './shared';

const gilded = {
  bg: 'hsl(0 0% 4%)',
  brass: '#c9a227',
  brassBright: '#e8c766',
  bronze: 'hsl(30 50% 45%)',
  cream: 'hsl(45 20% 93%)',
  panelHover: 'hsl(43 45% 12%)',
} as const;

const GILDED_SPLASH_FRAME = {
  scale: 0.75,
  margin: 16,
  tint: 2,
} as const;

const GILDED_SPLASH_RAYS = {
  sourceXvw: 50,
  sourceYvh: -34,
  rayCount: 50,
  spinSeconds: 160,
  reachVmax: 1.15,
  spreadDeg: 360,
  color: '#c9a227',
  accentColor: '#e8c766',
  thickness: 1,
  intensity: 0.5,
  falloff: 0.65,
  pulse: 1.5,
  rings: false,
} as const;

interface GildedButtonProps {
  children: ReactNode;
  onClick: () => void;
  animationClass?: string;
  primary?: boolean;
}

const cornerBase: CSSProperties = {
  position: 'absolute',
  width: 12,
  height: 12,
  borderStyle: 'solid',
  borderColor: gilded.bronze,
  transition: 'border-color .2s',
};

const GildedButton = ({
  children,
  onClick,
  animationClass = '',
  primary = false,
}: GildedButtonProps) => {
  const [hovered, setHovered] = useState(false);

  const base: CSSProperties = {
    position: 'relative',
    width: 280,
    padding: '14px 28px',
    fontFamily: 'var(--font-menu)',
    fontSize: 14,
    letterSpacing: '0.3em',
    textTransform: 'uppercase',
    fontWeight: 600,
    background: gilded.bg,
    border: `2px solid ${hovered ? gilded.brass : gilded.bronze}`,
    color: hovered ? gilded.brassBright : gilded.cream,
    borderRadius: 2,
    cursor: 'pointer',
    transition: 'background .2s, color .2s, border-color .2s, box-shadow .2s',
  };

  const primaryStyle: CSSProperties = {
    background: hovered ? gilded.brassBright : gilded.brass,
    border: 'none',
    color: gilded.bg,
    boxShadow: 'none',
  };

  const hoverStyle: CSSProperties = {
    background: gilded.panelHover,
    boxShadow: primary ? 'none' : '0 0 18px hsl(43 74% 47% / 0.28)',
  };

  const cornerColor = hovered ? gilded.brass : gilded.bronze;

  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={animationClass}
      style={{
        ...base,
        ...(hovered ? hoverStyle : {}),
        ...(primary ? primaryStyle : {}),
      }}
    >
      {!primary && (
        <>
          <span
            aria-hidden="true"
            style={{
              ...cornerBase,
              top: -2,
              left: -2,
              borderWidth: '2px 0 0 2px',
              borderColor: cornerColor,
            }}
          />
          <span
            aria-hidden="true"
            style={{
              ...cornerBase,
              top: -2,
              right: -2,
              borderWidth: '2px 2px 0 0',
              borderColor: cornerColor,
            }}
          />
          <span
            aria-hidden="true"
            style={{
              ...cornerBase,
              bottom: -2,
              left: -2,
              borderWidth: '0 0 2px 2px',
              borderColor: cornerColor,
            }}
          />
          <span
            aria-hidden="true"
            style={{
              ...cornerBase,
              right: -2,
              bottom: -2,
              borderWidth: '0 2px 2px 0',
              borderColor: cornerColor,
            }}
          />
        </>
      )}
      {children}
    </button>
  );
};

export function GildedSplash() {
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
        justifyContent: 'center',
        background: 'hsl(var(--background))',
        overflow: 'hidden',
      }}
    >
      <SplashThemeMenu />

      <div
        className={isExiting ? 'animate-fade-out-fast' : ''}
        style={{ position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none' }}
      >
        <DecoRays {...GILDED_SPLASH_RAYS} zIndex={0} />
        <DecoFrameSliced
          src={decoFrameR1C1}
          meta={DECO_FRAME_META.r1c1}
          scale={GILDED_SPLASH_FRAME.scale}
          margin={GILDED_SPLASH_FRAME.margin}
          tint={GILDED_SPLASH_FRAME.tint}
          zIndex={2}
        />
      </div>

      <div
        className={isExiting ? 'animate-fade-out-fast' : ''}
        style={{
          position: 'relative',
          zIndex: 4,
          width: '100%',
          height: 'min(220px, 30vh)',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'center',
          overflow: 'visible',
          marginTop: 0,
          pointerEvents: 'none',
        }}
      >
        <h1
          className="deco-glow"
          style={{
            position: 'relative',
            zIndex: 4,
            margin: '8px 0 0',
            fontFamily: 'var(--font-display)',
            fontSize: 128,
            fontWeight: 400,
            letterSpacing: '0.1em',
            lineHeight: 1,
            color: gilded.brassBright,
            textShadow:
              '0 0 12px hsl(43 74% 47% / .6), 0 0 24px hsl(43 74% 47% / .35)',
          }}
        >
          NEXUS
        </h1>
      </div>

      <div
        style={{
          position: 'relative',
          zIndex: 5,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12,
          marginTop: 0,
        }}
      >
        <GildedButton primary onClick={handleContinue} animationClass={getAnimationClass('continue')}>
          Continue
        </GildedButton>
        <GildedButton onClick={handleLoad} animationClass={getAnimationClass('load')}>
          Load
        </GildedButton>
        <GildedButton onClick={handleSettings} animationClass={getAnimationClass('settings')}>
          Settings
        </GildedButton>
      </div>
    </div>
  );
}
