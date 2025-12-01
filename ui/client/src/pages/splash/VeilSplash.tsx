/**
 * Veil theme splash page - Art Nouveau aesthetic with ornamental frames.
 * Features Arwes Puffs particles, elegant frames, and mystical coral/magenta palette.
 */
import { useState } from 'react';
import { Animator } from '@arwes/react-animator';
import { Puffs } from '@arwes/react-bgs';
import { useSplashNavigation, SplashThemeMenu } from './shared';
import nexusFrameSrc from '@/assets/veil/nexus-frame.svg';
// Button frame SVG available at '@/assets/veil/button-frame.svg' for future ornamental buttons

// Veil color palette - Magenta is PRIMARY, Coral is ACCENT
const colors = {
  bg: '#0a0f1a',
  cream: '#e8d5a3',
  creamLight: '#f0e6c8',
  // Primary: Magenta Rose (hue 320)
  magenta: '#b83d7a',
  magentaLight: '#c94d8a',
  // Accent: Coral Fire (hue 15)
  coral: '#e86a4a',
  deepViolet: '#4a2d6b',
  copper: '#b87333',
};

// Art Nouveau button with ornamental frame
interface VeilButtonProps {
  children: string;
  onClick: () => void;
  animationClass?: string;
  primary?: boolean;
}

const VeilButton = ({ children, onClick, animationClass = '', primary = false }: VeilButtonProps) => {
  const [hovered, setHovered] = useState(false);

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={animationClass}
      style={{
        position: 'relative',
        width: 220,
        height: 56,
        background: 'transparent',
        border: `2px solid ${hovered ? colors.magenta : colors.deepViolet}aa`,
        borderRadius: 4,
        cursor: 'pointer',
        padding: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'all 0.3s ease',
        boxShadow: hovered
          ? `0 0 15px ${colors.magenta}40`
          : 'none',
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-display, 'Cinzel'), serif",
          fontSize: 14,
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          color: hovered ? colors.cream : `${colors.cream}cc`,
          textShadow: hovered ? `0 0 10px ${colors.magenta}60` : 'none',
          transition: 'color 0.3s, text-shadow 0.3s',
        }}
      >
        {children}
      </span>
    </button>
  );
};

export function VeilSplash() {
  const { isExiting, handleContinue, handleLoad, handleSettings, getAnimationClass } = useSplashNavigation();

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
        backgroundColor: colors.bg,
        fontFamily: 'var(--font-body, Spectral), serif',
        overflow: 'hidden',
      }}
    >
      {/* Theme switcher menu */}
      <SplashThemeMenu />

      {/* Arwes Puffs background */}
      <div
        className={isExiting ? 'animate-fade-out-fast' : ''}
        style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
      >
        <Animator duration={{ enter: 0.5, exit: 0.5, interval: 4 }}>
          <Puffs
            color="hsla(320, 55%, 60%, 0.4)"
            quantity={100}
            padding={20}
            xOffset={[40, -80]}
            yOffset={[40, -80]}
            radiusOffset={[4, 0]}
          />
        </Animator>
      </div>

      {/* Content container */}
      <div
        style={{
          position: 'relative',
          zIndex: 10,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 48,
        }}
      >
        {/* NEXUS Title with frame - made more prominent */}
        <div
          className={isExiting ? 'animate-fade-out-fast' : ''}
          style={{
            position: 'relative',
            width: 560,
            height: 210,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {/* Ornamental frame with stronger glow */}
          <img
            src={nexusFrameSrc}
            alt=""
            style={{
              position: 'absolute',
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              filter: `drop-shadow(0 0 15px ${colors.magenta}80) drop-shadow(0 0 30px ${colors.magenta}40)`,
            }}
          />
          {/* Title text - larger and more prominent */}
          <h1
            style={{
              position: 'relative',
              margin: 0,
              fontFamily: 'var(--font-display, Cinzel), serif',
              fontSize: 64,
              fontWeight: 700,
              color: colors.cream,
              letterSpacing: '0.15em',
              textShadow: `
                0 0 30px ${colors.magenta},
                0 0 60px ${colors.magenta}80,
                0 2px 4px ${colors.deepViolet}
              `,
            }}
          >
            NEXUS
          </h1>
        </div>

        {/* Menu buttons - more subtle */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <VeilButton
            primary
            onClick={handleContinue}
            animationClass={getAnimationClass('continue')}
          >
            Continue
          </VeilButton>
          <VeilButton
            onClick={handleLoad}
            animationClass={getAnimationClass('load')}
          >
            Load
          </VeilButton>
          <VeilButton
            onClick={handleSettings}
            animationClass={getAnimationClass('settings')}
          >
            Settings
          </VeilButton>
        </div>
      </div>

      {/* Bottom gradient overlay */}
      <div
        className={isExiting ? 'animate-fade-out-fast' : ''}
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: 200,
          background: `linear-gradient(to top, ${colors.magenta}15, transparent)`,
          pointerEvents: 'none',
        }}
      />
    </div>
  );
}
