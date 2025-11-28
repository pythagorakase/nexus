/**
 * Cyberpunk theme splash page - Terminal-style home screen with glitch effects.
 * Features animated grid background, deciphering text, and octagonal buttons.
 */
import { useState, useEffect, useMemo } from 'react';
import { useSplashNavigation } from './shared';

// Cyberpunk color palette
const colors = {
  bg: '#000906',
  cyan: '#00f0ff',
  cyanDim: 'hsla(180, 100%, 75%, 0.15)',
  cyanFaint: 'hsla(180, 100%, 75%, 0.05)',
  cyanGlow: 'hsla(185, 100%, 25%, 0.25)',
  text: '#c0f0f0',
};

const glyphSet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*<>[]{}';

// Decipher text component - individual characters can be targeted for glitch effect
interface DecipherTextProps {
  text: string;
  style?: React.CSSProperties;
  activeIndices?: number[];
}

const DecipherText = ({ text, style, activeIndices = [] }: DecipherTextProps) => {
  const [glyphStates, setGlyphStates] = useState<Record<number, string>>({});

  useEffect(() => {
    const intervals: Record<number, ReturnType<typeof setInterval>> = {};

    activeIndices.forEach(idx => {
      if (idx < text.length && text[idx] !== ' ') {
        let cycleCount = 0;
        const maxCycles = 8 + Math.floor(Math.random() * 6);

        intervals[idx] = setInterval(() => {
          if (cycleCount < maxCycles) {
            setGlyphStates(prev => ({
              ...prev,
              [idx]: glyphSet[Math.floor(Math.random() * glyphSet.length)]
            }));
            cycleCount++;
          } else {
            setGlyphStates(prev => {
              const next = { ...prev };
              delete next[idx];
              return next;
            });
            clearInterval(intervals[idx]);
          }
        }, 60);
      }
    });

    return () => {
      Object.values(intervals).forEach(clearInterval);
    };
  }, [activeIndices.join(','), text]);

  return (
    <span style={style}>
      {text.split('').map((char, i) => {
        const displayChar = glyphStates[i] || char;
        const isGlitching = glyphStates[i] !== undefined;

        return (
          <span
            key={i}
            style={{
              display: 'inline-block',
              color: isGlitching ? colors.cyan : undefined,
              textShadow: isGlitching ? `0 0 8px ${colors.cyan}, 0 0 16px ${colors.cyan}` : undefined,
              transform: isGlitching ? `translateY(${Math.random() > 0.5 ? -1 : 1}px)` : undefined,
              transition: 'color 0.1s',
            }}
          >
            {displayChar}
          </span>
        );
      })}
    </span>
  );
};

// Global decipher controller - manages which characters are active across all text
const useDecipherController = (textItems: string[]) => {
  const [activeTargets, setActiveTargets] = useState<Record<number, number[]>>({});

  const charMap = useMemo(() => {
    const map: { textIdx: number; charIdx: number; char: string }[] = [];
    textItems.forEach((text, textIdx) => {
      text.split('').forEach((char, charIdx) => {
        if (char !== ' ') {
          map.push({ textIdx, charIdx, char });
        }
      });
    });
    return map;
  }, [textItems.join('|')]);

  useEffect(() => {
    const pickNewTargets = () => {
      const count = Math.random() > 0.5 ? 2 : 1;
      const newTargets: Record<number, number[]> = {};

      for (let i = 0; i < count; i++) {
        const target = charMap[Math.floor(Math.random() * charMap.length)];
        if (target) {
          if (!newTargets[target.textIdx]) {
            newTargets[target.textIdx] = [];
          }
          if (!newTargets[target.textIdx].includes(target.charIdx)) {
            newTargets[target.textIdx].push(target.charIdx);
          }
        }
      }

      setActiveTargets(newTargets);
    };

    pickNewTargets();
    const interval = setInterval(pickNewTargets, 800 + Math.random() * 400);

    return () => clearInterval(interval);
  }, [charMap]);

  return activeTargets;
};

// Moving lines grid background
const GridBackground = () => {
  const [lines, setLines] = useState<{
    id: number;
    x: number;
    y: number;
    horizontal: boolean;
    speed: number;
    length: number;
    opacity: number;
  }[]>([]);
  const distance = 30;

  useEffect(() => {
    const initialLines = Array.from({ length: 35 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      horizontal: Math.random() > 0.5,
      speed: 0.15 + Math.random() * 0.25,
      length: 4 + Math.random() * 8,
      opacity: 0.15 + Math.random() * 0.2,
    }));
    setLines(initialLines);

    const interval = setInterval(() => {
      setLines(prev => prev.map(line => {
        if (line.horizontal) {
          let newX = line.x + line.speed;
          if (newX > 110) newX = -10;
          return { ...line, x: newX };
        } else {
          let newY = line.y + line.speed;
          if (newY > 110) newY = -10;
          return { ...line, y: newY };
        }
      }));
    }, 40);

    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{
      position: 'absolute',
      inset: 0,
      backgroundColor: colors.bg,
      backgroundImage: `radial-gradient(85% 85% at 50% 50%, ${colors.cyanGlow} 0%, hsla(185, 100%, 25%, 0.12) 50%, hsla(185, 100%, 25%, 0) 100%)`,
      overflow: 'hidden',
    }}>
      <svg width="100%" height="100%" style={{ position: 'absolute' }}>
        <defs>
          <pattern id="grid" width={distance} height={distance} patternUnits="userSpaceOnUse">
            <path d={`M ${distance} 0 L 0 0 0 ${distance}`} fill="none" stroke={colors.cyanFaint} strokeWidth="1" />
          </pattern>
          <pattern id="dots" width={distance} height={distance} patternUnits="userSpaceOnUse">
            <circle cx="0" cy="0" r="1" fill={colors.cyanFaint} />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
        <rect width="100%" height="100%" fill="url(#dots)" />

        {/* Moving lines */}
        {lines.map(line => (
          <line
            key={line.id}
            x1={`${line.x}%`}
            y1={`${line.y}%`}
            x2={line.horizontal ? `${line.x + line.length}%` : `${line.x}%`}
            y2={line.horizontal ? `${line.y}%` : `${line.y + line.length}%`}
            stroke={colors.cyan}
            strokeWidth="1.5"
            strokeLinecap="round"
            opacity={line.opacity}
            style={{ filter: `drop-shadow(0 0 2px ${colors.cyan})` }}
          />
        ))}
      </svg>
    </div>
  );
};

// Octagon button with assembly animation
interface OctagonButtonProps {
  children: string;
  textId: number;
  activeIndices?: number[];
  primary?: boolean;
  onClick: () => void;
  animationClass?: string;
}

const OctagonButton = ({ children, textId, activeIndices = [], primary = false, onClick, animationClass = '' }: OctagonButtonProps) => {
  const [hovered, setHovered] = useState(false);
  const [assembled, setAssembled] = useState(true);

  useEffect(() => {
    if (hovered) {
      setAssembled(false);
      const timeout = setTimeout(() => setAssembled(true), 300);
      return () => clearTimeout(timeout);
    }
  }, [hovered]);

  const cut = 12;
  const w = 280;
  const h = 52;

  const path = `M ${cut},0 L ${w - cut},0 L ${w},${cut} L ${w},${h - cut} L ${w - cut},${h} L ${cut},${h} L 0,${h - cut} L 0,${cut} Z`;

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      aria-label={`${children}${primary ? ' - Primary action' : ''}`}
      className={animationClass}
      style={{
        position: 'relative',
        width: w,
        height: h,
        background: 'transparent',
        border: 'none',
        cursor: 'pointer',
        padding: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <svg width={w} height={h} style={{ position: 'absolute', top: 0, left: 0 }}>
        <defs>
          <filter id={`btnGlow-${textId}`}>
            <feGaussianBlur stdDeviation="3" result="blur"/>
            <feMerge>
              <feMergeNode in="blur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>

        <path
          d={path}
          fill={primary ? `${colors.cyan}15` : 'transparent'}
          stroke="none"
        />

        <path
          d={path}
          fill="none"
          stroke={colors.cyan}
          strokeWidth="2"
          strokeDasharray={assembled ? '1000' : '20 30'}
          strokeDashoffset={assembled ? '0' : '50'}
          style={{
            filter: hovered ? `url(#btnGlow-${textId})` : 'none',
            transition: 'all 0.3s ease-out',
            opacity: hovered ? 1 : 0.5,
          }}
        />
      </svg>

      <DecipherText
        text={children}
        activeIndices={activeIndices}
        style={{
          position: 'relative',
          zIndex: 1,
          fontFamily: 'var(--font-mono)',
          fontSize: 14,
          letterSpacing: '0.2em',
          color: hovered ? colors.cyan : colors.text,
          textShadow: hovered ? `0 0 10px ${colors.cyan}` : 'none',
          transition: 'color 0.2s, text-shadow 0.2s',
        }}
      />
    </button>
  );
};

export function CyberpunkSplash() {
  const { isExiting, handleContinue, handleLoad, handleSettings, getAnimationClass } = useSplashNavigation();
  const textItems = ['NEXUS', 'CONTINUE', 'LOAD', 'SETTINGS'];
  const activeTargets = useDecipherController(textItems);

  return (
    <div style={{
      position: 'relative',
      width: '100%',
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      overflow: 'hidden',
    }}>
      {/* Background fades out fast */}
      <div className={isExiting ? 'animate-fade-out-fast' : ''} style={{ position: 'absolute', inset: 0 }}>
        <GridBackground />
      </div>

      {/* Content */}
      <div style={{
        position: 'relative',
        zIndex: 10,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        paddingTop: 100,
        gap: 16,
      }}>
        {/* NEXUS Title */}
        <div
          className={isExiting ? 'animate-fade-out-fast' : ''}
          style={{ marginBottom: 60 }}
        >
          <DecipherText
            text="NEXUS"
            activeIndices={activeTargets[0] || []}
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 72,
              color: colors.cyan,
              textShadow: `0 0 20px ${colors.cyan}, 0 0 40px ${colors.cyan}50`,
              letterSpacing: '0.1em',
            }}
          />
        </div>

        {/* Menu buttons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <OctagonButton
            textId={1}
            activeIndices={activeTargets[1] || []}
            primary
            onClick={handleContinue}
            animationClass={getAnimationClass('continue')}
          >
            CONTINUE
          </OctagonButton>
          <OctagonButton
            textId={2}
            activeIndices={activeTargets[2] || []}
            onClick={handleLoad}
            animationClass={getAnimationClass('load')}
          >
            LOAD
          </OctagonButton>
          <OctagonButton
            textId={3}
            activeIndices={activeTargets[3] || []}
            onClick={handleSettings}
            animationClass={getAnimationClass('settings')}
          >
            SETTINGS
          </OctagonButton>
        </div>
      </div>
    </div>
  );
}
