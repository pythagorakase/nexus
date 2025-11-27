/**
 * Splash page - Art Deco home screen with animated sunburst and navigation.
 * Showcases the display font (Monoton) and provides entry points to the app.
 */
import { useState } from 'react';
import { useLocation } from 'wouter';

// CSS variable references for theme-aware colors
// These map to the Gilded theme variables in index.css
const themeColors = {
  bg: 'hsl(var(--background))',
  primary: 'hsl(var(--primary))',
  accent: 'hsl(var(--accent))',
  foreground: 'hsl(var(--foreground))',
  mutedForeground: 'hsl(var(--muted-foreground))',
  bronze: 'hsl(var(--chart-2))',
  darkBronze: 'hsl(var(--chart-4))',
};

const HeroSunburst = () => {
  const rays = 72;
  const size = 1600;
  const pulseGroups = 6;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="absolute overflow-visible"
      style={{
        top: -size/2,
        left: '50%',
        transform: 'translateX(-50%)',
      }}
    >
      <style>{`
        @keyframes rotateSunburst {
          from { transform: rotate(0deg); }
          to { transform: rotate(-360deg); }
        }
        @keyframes rayPulse {
          0%, 100% { opacity: 0.15; }
          50% { opacity: 0.5; }
        }
        @keyframes rayPulseAccent {
          0%, 100% { opacity: 0.25; }
          50% { opacity: 0.7; }
        }
        @keyframes rayPulseBronze {
          0%, 100% { opacity: 0.2; }
          50% { opacity: 0.6; }
        }
      `}</style>

      <g style={{
        transformOrigin: `${size/2}px ${size/2}px`,
        animation: 'rotateSunburst 120s linear infinite',
      }}>
        {[...Array(rays)].map((_, i) => {
          const angle = (i * (360 / rays)) * Math.PI / 180;
          const isAccent = i % 4 === 0;
          const isBronze = i % 6 === 2;
          const isMajor = i % 2 === 0;
          const groupIndex = Math.floor(i / (rays / pulseGroups));
          const pulseDelay = (groupIndex / pulseGroups) * 8;

          let rayColor, rayWidth, animName;
          if (isAccent) {
            rayColor = themeColors.primary;
            rayWidth = 2.5;
            animName = 'rayPulseAccent';
          } else if (isBronze) {
            rayColor = themeColors.bronze;
            rayWidth = 2;
            animName = 'rayPulseBronze';
          } else {
            rayColor = isMajor ? themeColors.darkBronze : themeColors.mutedForeground;
            rayWidth = isMajor ? 1.5 : 0.75;
            animName = 'rayPulse';
          }

          return (
            <line
              key={i}
              x1={size / 2}
              y1={size / 2}
              x2={size / 2 + Math.cos(angle) * size}
              y2={size / 2 + Math.sin(angle) * size}
              stroke={rayColor}
              strokeWidth={rayWidth}
              style={{
                animation: `${animName} 8s ease-in-out infinite`,
                animationDelay: `${pulseDelay}s`,
              }}
            />
          );
        })}
      </g>

      {/* Concentric circles */}
      {[150, 250, 380].map((r, i) => (
        <circle
          key={r}
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={i === 1 ? themeColors.bronze : themeColors.primary}
          strokeWidth={i === 1 ? 2 : 1}
          opacity={0.12 + i * 0.04}
        />
      ))}
    </svg>
  );
};

// Corner component for the Art Deco frame
const Corner = ({ position }: { position: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' }) => {
  const isLeft = position.includes('left');
  const isTop = position.includes('top');

  return (
    <div
      className="absolute w-2 h-2 border border-primary"
      style={{
        [isTop ? 'top' : 'bottom']: -8,
        [isLeft ? 'left' : 'right']: -8,
      }}
    >
      {/* Horizontal extension */}
      <div
        className="absolute w-8 h-[15px]"
        style={{
          [isTop ? 'top' : 'bottom']: -1,
          [isLeft ? 'left' : 'right']: 14,
          [isTop ? 'borderTop' : 'borderBottom']: '1px solid hsl(var(--primary))',
        }}
      />
      {/* Vertical extension */}
      <div
        className="absolute w-[15px] h-8"
        style={{
          [isTop ? 'top' : 'bottom']: 14,
          [isLeft ? 'left' : 'right']: -1,
          [isLeft ? 'borderLeft' : 'borderRight']: '1px solid hsl(var(--primary))',
        }}
      />
    </div>
  );
};

// Art Deco frame
const DecoFrame = () => {
  return (
    <div className="absolute inset-5 border border-primary pointer-events-none">
      <Corner position="top-left" />
      <Corner position="top-right" />
      <Corner position="bottom-left" />
      <Corner position="bottom-right" />

      {/* Horizontal bars extending beyond frame */}
      <div
        className="absolute top-[10px] bottom-[10px] -left-5 -right-5 border-t border-b border-primary pointer-events-none"
      />

      {/* Vertical bars extending beyond frame */}
      <div
        className="absolute -top-5 -bottom-5 left-[10px] right-[10px] border-l border-r border-primary pointer-events-none"
      />
    </div>
  );
};

interface MenuButtonProps {
  children: React.ReactNode;
  onClick: () => void;
  primary?: boolean;
  animationClass?: string;
}

const MenuButton = ({ children, onClick, primary = false, animationClass = '' }: MenuButtonProps) => {
  const [hover, setHover] = useState(false);

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className={`relative w-[280px] py-[18px] px-8 font-mono text-lg tracking-[0.25em] uppercase cursor-pointer transition-all duration-200 ${animationClass}`}
      style={{
        background: primary
          ? (hover ? themeColors.accent : themeColors.primary)
          : (hover ? 'hsla(var(--primary) / 0.15)' : 'transparent'),
        border: primary ? 'none' : `2px solid ${hover ? themeColors.primary : themeColors.bronze}`,
        color: primary ? themeColors.bg : (hover ? themeColors.accent : themeColors.foreground),
      }}
    >
      {!primary && (
        <>
          {/* Corner accents */}
          <span
            className="absolute -top-0.5 -left-0.5 w-3 h-3 transition-colors duration-200"
            style={{
              borderTop: `2px solid ${hover ? themeColors.primary : themeColors.bronze}`,
              borderLeft: `2px solid ${hover ? themeColors.primary : themeColors.bronze}`,
            }}
          />
          <span
            className="absolute -top-0.5 -right-0.5 w-3 h-3 transition-colors duration-200"
            style={{
              borderTop: `2px solid ${hover ? themeColors.primary : themeColors.bronze}`,
              borderRight: `2px solid ${hover ? themeColors.primary : themeColors.bronze}`,
            }}
          />
          <span
            className="absolute -bottom-0.5 -left-0.5 w-3 h-3 transition-colors duration-200"
            style={{
              borderBottom: `2px solid ${hover ? themeColors.primary : themeColors.bronze}`,
              borderLeft: `2px solid ${hover ? themeColors.primary : themeColors.bronze}`,
            }}
          />
          <span
            className="absolute -bottom-0.5 -right-0.5 w-3 h-3 transition-colors duration-200"
            style={{
              borderBottom: `2px solid ${hover ? themeColors.primary : themeColors.bronze}`,
              borderRight: `2px solid ${hover ? themeColors.primary : themeColors.bronze}`,
            }}
          />
        </>
      )}
      {children}
    </button>
  );
};

export default function SplashPage() {
  const [, setLocation] = useLocation();
  const [isExiting, setIsExiting] = useState(false);
  const [clickedButton, setClickedButton] = useState<string | null>(null);

  // Unified navigation handler with staggered fade-out
  // Uses client-side routing for instant page loads (no full page reload)
  const handleNavigation = (destination: string, buttonId: string) => {
    setClickedButton(buttonId);
    setIsExiting(true);

    // Navigate after the clicked element's animation completes (0.75s)
    // The destination page starts mounting immediately via client-side routing
    setTimeout(() => {
      setLocation(destination);
    }, 750);
  };

  const handleContinue = () => {
    const activeSlot = localStorage.getItem('activeSlot');
    const destination = activeSlot ? '/nexus' : '/new-story';
    handleNavigation(destination, 'continue');
  };

  const handleLoad = () => {
    handleNavigation('/new-story', 'load');
  };

  const handleSettings = () => {
    handleNavigation('/nexus?tab=settings', 'settings');
  };

  // Helper to get animation class based on exit state and which button was clicked
  const getAnimationClass = (buttonId: string) => {
    if (!isExiting) return '';
    return clickedButton === buttonId ? 'animate-fade-out-slow' : 'animate-fade-out-fast';
  };

  return (
    <div className="min-h-screen bg-background relative overflow-hidden flex flex-col items-center">
      {/* DecoFrame fades out fast (not the clicked element) */}
      <div className={isExiting ? 'animate-fade-out-fast' : ''}>
        <DecoFrame />
      </div>

      {/* Hero section with sunburst */}
      <div className={`relative w-full h-[200px] flex items-start justify-center overflow-visible ${isExiting ? 'animate-fade-out-fast' : ''}`}>
        <HeroSunburst />

        <h1
          className={`font-display text-[112px] font-normal tracking-[0.1em] text-accent m-0 mt-9 relative z-10 deco-glow ${isExiting ? 'animate-fade-out-fast' : ''}`}
        >
          NEXUS
        </h1>
      </div>

      {/* Menu buttons */}
      <div className="flex flex-col items-center gap-5 mt-10">
        <MenuButton primary onClick={handleContinue} animationClass={getAnimationClass('continue')}>
          Continue
        </MenuButton>

        <MenuButton onClick={handleLoad} animationClass={getAnimationClass('load')}>
          Load
        </MenuButton>

        <MenuButton onClick={handleSettings} animationClass={getAnimationClass('settings')}>
          Settings
        </MenuButton>
      </div>
    </div>
  );
}
