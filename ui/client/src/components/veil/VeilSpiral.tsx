/**
 * VeilSpiral — the living logarithmic-spiral hero behind the Veil splash.
 *
 * A parametric moire field of spiral filaments that slowly rotates, sheds
 * warm-cream pulses along randomly selected arms, and twinkles with ember
 * motes. The component draws the NEXUS wordmark itself (Megrim, the Veil
 * marquee font) and knocks the field out behind it with a feathered mask so
 * pulses appear to emerge from behind the wordmark.
 *
 * Typed port of the NEXUS IRIS design handoff prototype
 * (design_handoff/project/ui_kits/nexus_iris/spiral-v2.jsx). The approved
 * splash values are hard-coded where this component is instantiated
 * (pages/splash/VeilSplash.tsx) — treat them as canon.
 *
 * One <VeilSpiral /> per artboard: each instance owns its own pulses,
 * embers, and animation loop.
 */
import {
  CSSProperties,
  Fragment,
  ReactNode,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react';

// Veil brand palette (locked splash values; mirrors the .dark theme tokens)
const VEIL = {
  bg: '#09101c',
  primary: '#b83d7a',
  secondary: '#b87333',
  fg: '#e1cd97',
} as const;

// Fixed design viewBox shared with NouveauFrame so the frame tracks the
// wordmark across viewport sizes.
const W = 1200;
const H = 700;
const MAX_R = Math.hypot(W, H) * 0.6;

const WORDMARK_TEXT = 'NEXUS';
const WORDMARK_FONT = "'Megrim', 'Cormorant Garamond', 'Didot', serif";

// ─── Geometry ────────────────────────────────────────────────────────────

interface SpiralPoint {
  x: number;
  y: number;
  t: number;
}

interface SpiralFilament {
  id: string;
  layer: 'primary' | 'secondary';
  d: string;
  points: SpiralPoint[];
}

function buildSpiral(
  turns: number,
  growth: number,
  startAngle: number,
  cx: number,
  cy: number,
  samples = 360,
): { d: string; points: SpiralPoint[] } {
  const totalTheta = turns * Math.PI * 2;
  const a = MAX_R / Math.exp(growth * totalTheta);
  const points: SpiralPoint[] = [];
  let d = '';
  for (let i = 0; i <= samples; i++) {
    const t = i / samples;
    const theta = t * totalTheta;
    const r = a * Math.exp(growth * theta);
    const angle = theta + startAngle;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    points.push({ x, y, t });
    d += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1) + ' ';
  }
  return { d, points };
}

function buildField(
  arms: number,
  growth: number,
  anchorX: number,
  anchorY: number,
): SpiralFilament[] {
  const filaments: SpiralFilament[] = [];
  for (let i = 0; i < arms; i++) {
    const start = (i / arms) * Math.PI * 2;
    filaments.push({
      id: `a${i}`,
      layer: 'primary',
      ...buildSpiral(2.6, growth, start, anchorX, anchorY),
    });
    filaments.push({
      id: `b${i}`,
      layer: 'secondary',
      ...buildSpiral(2.6, growth * 0.78, start + 0.05, anchorX, anchorY),
    });
  }
  return filaments;
}

// ─── Filaments + Pulses ──────────────────────────────────────────────────

interface FilamentProps {
  filament: SpiralFilament;
  primaryColor: string;
  secondaryColor: string;
}

function Filament({ filament, primaryColor, secondaryColor }: FilamentProps) {
  const isPrimary = filament.layer === 'primary';
  return (
    <path
      d={filament.d}
      fill="none"
      stroke={isPrimary ? primaryColor : secondaryColor}
      strokeWidth="0.55"
      strokeOpacity={isPrimary ? 0.42 : 0.3}
    />
  );
}

interface PulseProps {
  filament: SpiralFilament;
  duration: number;
  color: string;
  /** Globally unique CSS <custom-ident> suffix for this pulse's keyframes. */
  animKey: string;
}

function Pulse({ filament, duration, color, animKey }: PulseProps) {
  const ref = useRef<SVGPathElement>(null);
  const [pathLen, setPathLen] = useState<number | null>(null);

  useEffect(() => {
    if (ref.current) {
      try {
        setPathLen(ref.current.getTotalLength());
      } catch {
        let len = 0;
        for (let i = 1; i < filament.points.length; i++) {
          const a = filament.points[i - 1];
          const b = filament.points[i];
          len += Math.hypot(b.x - a.x, b.y - a.y);
        }
        setPathLen(len);
      }
    }
  }, [filament]);

  const segment = pathLen ? pathLen * 0.12 : 0;
  const total = pathLen ?? 0;
  const startOffset = segment;
  const endOffset = -(total + segment);
  const animName = pathLen ? `pulseTravel_${animKey}` : null;

  return (
    <Fragment>
      {animName && (
        <style>{`
          @keyframes ${animName} {
            0%   { stroke-dashoffset: ${startOffset}; stroke-opacity: 0; }
            8%   { stroke-dashoffset: ${startOffset + (endOffset - startOffset) * 0.08}; stroke-opacity: 1; }
            92%  { stroke-dashoffset: ${startOffset + (endOffset - startOffset) * 0.92}; stroke-opacity: 1; }
            100% { stroke-dashoffset: ${endOffset}; stroke-opacity: 0; }
          }
        `}</style>
      )}
      <path
        ref={ref}
        d={filament.d}
        fill="none"
        stroke={color}
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeOpacity={pathLen ? 1 : 0}
        style={{
          strokeDasharray: pathLen ? `${segment} ${total + segment * 2}` : 'none',
          animation: animName ? `${animName} ${duration}ms linear forwards` : 'none',
        }}
      />
    </Fragment>
  );
}

// ─── Ember motes (ambient texture) ───────────────────────────────────────
// Small bright dots that fade in and out at random points along random
// filaments. They do not move — they twinkle. Cheaper than a full particle
// system; reads as starfield/dust on the spiral arms.

interface EmberProps {
  filament: SpiralFilament;
  pointIdx: number;
  duration: number;
  color: string;
  size: number;
  /** Globally unique CSS <custom-ident> suffix for this ember's keyframes. */
  animKey: string;
}

function Ember({ filament, pointIdx, duration, color, size, animKey }: EmberProps) {
  const p = filament.points[pointIdx];
  if (!p) return null;
  const animName = `emberLife_${animKey}`;
  return (
    <Fragment>
      <style>{`
        @keyframes ${animName} {
          0%   { opacity: 0; transform: scale(0.4); }
          18%  { opacity: 1; transform: scale(1); }
          70%  { opacity: 1; transform: scale(1); }
          100% { opacity: 0; transform: scale(0.4); }
        }
      `}</style>
      <circle
        cx={p.x}
        cy={p.y}
        r={size}
        fill={color}
        style={{
          transformOrigin: `${p.x}px ${p.y}px`,
          animation: `${animName} ${duration}ms ease-out forwards`,
          mixBlendMode: 'screen',
        }}
      />
    </Fragment>
  );
}

// ─── Wordmark ────────────────────────────────────────────────────────────

interface NexusWordmarkProps {
  glowId: string;
  fontSize: number;
  anchorY: number;
  color: string;
  strokeWidth: number;
}

function NexusWordmark({ glowId, fontSize, anchorY, color, strokeWidth }: NexusWordmarkProps) {
  // SVG text-anchor="middle" centers the full advance INCLUDING the trailing
  // letter-spacing gap after the final glyph, and Megrim's N/S side bearings
  // are uneven — so the visible ink lands ~0.0595em left of the anchor.
  // (Measured against the real Megrim face via canvas measureText; constant
  // is stable across font sizes.) Nudge the anchor right to re-center the ink.
  const inkOffset = fontSize * 0.0595;
  return (
    <text
      x={600 + inkOffset}
      y={anchorY}
      textAnchor="middle"
      dominantBaseline="middle"
      fontFamily={WORDMARK_FONT}
      fontSize={fontSize}
      fontWeight="400"
      letterSpacing={fontSize * 0.16}
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth}
      filter={`url(#${glowId})`}
    >
      {WORDMARK_TEXT}
    </text>
  );
}

// ─── Main component ──────────────────────────────────────────────────────

let pulseSeq = 0;
let emberSeq = 0;

interface ActivePulse {
  id: number;
  filamentId: string;
  duration: number;
  startedAt: number;
}

interface ActiveEmber {
  id: number;
  filamentId: string;
  pointIdx: number;
  duration: number;
  startedAt: number;
  size: number;
}

export type VeilSpiralMaskMode = 'radial' | 'text' | 'rect' | 'none';

export interface VeilSpiralProps {
  /** Number of spiral arms (each arm renders a primary + secondary filament). */
  arms?: number;
  /** Spiral growth rate — low = tight coils, high = loose splay. */
  growth?: number;
  /** Field rotation period in seconds (0 disables rotation). */
  rotation?: number;
  /** Rotate counterclockwise. */
  reverse?: boolean;
  /**
   * Field anchor — co-located with the wordmark by default so the dense inner
   * coils are hidden by the mask and pulses appear to emerge from behind the
   * wordmark instead of winding visibly in place near center.
   */
  anchorX?: number;
  anchorY?: number;
  /** Wordmark vertical anchor in viewBox units. */
  wordmarkY?: number;
  /** Wordmark font size in viewBox units. */
  fontSize?: number;
  /** Mask shape knocking the field out around the wordmark. */
  maskMode?: VeilSpiralMaskMode;
  /** Radial mask: fade radius in viewBox units around (600, wordmarkY). */
  fadeRadius?: number;
  /** Radial mask: maximum opacity attenuation at center. */
  fadeStrength?: number;
  /** Text mask: letterform halo width in px (dilate + blur). */
  maskHaloPx?: number;
  /** Mask opacity attenuation (text + rect modes). */
  maskStrength?: number;
  /** Rect mask: horizontal padding around the estimated wordmark box. */
  rectPaddingX?: number;
  /** Rect mask: vertical padding around the estimated wordmark box. */
  rectPaddingY?: number;
  /** Rect mask: feather (Gaussian blur) radius. */
  rectFeather?: number;
  /** Pulse spawn rate per second (0 disables pulses). */
  pulseRate?: number;
  pulseColor?: string;
  pulseMinDuration?: number;
  pulseMaxDuration?: number;
  /** Ember spawn rate per second (0 disables embers). */
  emberRate?: number;
  emberColor?: string;
  emberSize?: number;
  emberMinDuration?: number;
  emberMaxDuration?: number;
  /** Filament stroke colors. */
  primaryColor?: string;
  secondaryColor?: string;
  /** Wordmark stroke color. */
  wordmarkColor?: string;
  wordmarkStroke?: number;
  showWordmark?: boolean;
  className?: string;
  style?: CSSProperties;
}

export function VeilSpiral({
  arms = 32,
  growth = 0.4,
  rotation = 70,
  reverse = true,
  anchorX = 600,
  anchorY = 380,
  wordmarkY = 380,
  fontSize = 120,
  maskMode = 'radial',
  fadeRadius = 450,
  fadeStrength = 0.85,
  maskHaloPx = 24,
  maskStrength = 0.92,
  rectPaddingX = 36,
  rectPaddingY = 18,
  rectFeather = 22,
  pulseRate = 2.2,
  pulseColor = VEIL.fg,
  pulseMinDuration = 4200,
  pulseMaxDuration = 6500,
  emberRate = 3.5,
  emberColor = VEIL.fg,
  emberSize = 1.6,
  emberMinDuration = 1800,
  emberMaxDuration = 3600,
  primaryColor = VEIL.primary,
  secondaryColor = VEIL.secondary,
  wordmarkColor = VEIL.primary,
  wordmarkStroke = 1.4,
  showWordmark = true,
  className,
  style,
}: VeilSpiralProps) {
  // Unique key for keyframes/ids per instance so multiple instances don't
  // collide. CSS animation-name is a <custom-ident> — strip the colons React
  // puts in useId.
  const inst = useId().replace(/[:]/g, '');

  const filaments = useMemo(
    () => buildField(arms, growth, anchorX, anchorY),
    [arms, growth, anchorX, anchorY],
  );
  const filamentsById = useMemo(() => {
    const m: Record<string, SpiralFilament> = {};
    filaments.forEach((f) => {
      m[f.id] = f;
    });
    return m;
  }, [filaments]);

  // ── pulses
  const [pulses, setPulses] = useState<ActivePulse[]>([]);
  useEffect(() => {
    if (pulseRate <= 0) {
      setPulses([]);
      return;
    }
    const intervalMs = 1000 / pulseRate;
    const tick = setInterval(() => {
      const f = filaments[Math.floor(Math.random() * filaments.length)];
      pulseSeq += 1;
      setPulses((prev) => [
        ...prev,
        {
          id: pulseSeq,
          filamentId: f.id,
          duration: pulseMinDuration + Math.random() * (pulseMaxDuration - pulseMinDuration),
          startedAt: performance.now(),
        },
      ]);
    }, intervalMs);
    return () => clearInterval(tick);
  }, [pulseRate, filaments, pulseMinDuration, pulseMaxDuration]);

  useEffect(() => {
    const gc = setInterval(() => {
      const now = performance.now();
      setPulses((prev) => prev.filter((p) => now - p.startedAt < p.duration + 200));
    }, 1500);
    return () => clearInterval(gc);
  }, []);

  // ── embers
  const [embers, setEmbers] = useState<ActiveEmber[]>([]);
  useEffect(() => {
    if (emberRate <= 0) {
      setEmbers([]);
      return;
    }
    const intervalMs = 1000 / emberRate;
    const tick = setInterval(() => {
      const f = filaments[Math.floor(Math.random() * filaments.length)];
      // Avoid the wordmark region — bias point index toward the outer 60% of
      // the arm.
      const tBias = 0.25 + Math.random() * 0.75;
      const pointIdx = Math.floor(tBias * (f.points.length - 1));
      emberSeq += 1;
      setEmbers((prev) => [
        ...prev,
        {
          id: emberSeq,
          filamentId: f.id,
          pointIdx,
          duration: emberMinDuration + Math.random() * (emberMaxDuration - emberMinDuration),
          startedAt: performance.now(),
          size: emberSize * (0.6 + Math.random() * 0.8),
        },
      ]);
    }, intervalMs);
    return () => clearInterval(tick);
  }, [emberRate, filaments, emberMinDuration, emberMaxDuration, emberSize]);

  useEffect(() => {
    const gc = setInterval(() => {
      const now = performance.now();
      setEmbers((prev) => prev.filter((e) => now - e.startedAt < e.duration + 200));
    }, 1500);
    return () => clearInterval(gc);
  }, []);

  // ── ids
  const glowId = `glow_${inst}`;
  const fadeId = `fade_${inst}`;
  const maskId = `mask_${inst}`;
  const textMaskFilterId = `tmf_${inst}`;
  const spinAnim = `spin_${inst}`;
  const rotateOrigin = `${anchorX}px ${anchorY}px`;

  // ── mask render
  const renderMask = (): ReactNode => {
    if (maskMode === 'none') return null;
    if (maskMode === 'radial') {
      return (
        <Fragment>
          <radialGradient
            id={fadeId}
            cx={600}
            cy={wordmarkY}
            r={fadeRadius}
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" stopColor="#000" stopOpacity={fadeStrength} />
            <stop offset="55%" stopColor="#000" stopOpacity={fadeStrength * 0.5} />
            <stop offset="100%" stopColor="#fff" stopOpacity="1" />
          </radialGradient>
          <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width={W} height={H}>
            <rect x="0" y="0" width={W} height={H} fill={`url(#${fadeId})`} />
          </mask>
        </Fragment>
      );
    }
    if (maskMode === 'text') {
      // Per-letter halo: render the text itself, dilated + blurred.
      return (
        <Fragment>
          <filter id={textMaskFilterId} x="-50%" y="-50%" width="200%" height="200%">
            <feMorphology operator="dilate" radius={Math.max(0.5, maskHaloPx * 0.4)} />
            <feGaussianBlur stdDeviation={maskHaloPx * 0.6} />
          </filter>
          <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width={W} height={H}>
            <rect x="0" y="0" width={W} height={H} fill="white" />
            <text
              x={600 + fontSize * 0.0595}
              y={wordmarkY}
              textAnchor="middle"
              dominantBaseline="middle"
              fontFamily={WORDMARK_FONT}
              fontSize={fontSize}
              fontWeight="400"
              letterSpacing={fontSize * 0.16}
              fill="black"
              fillOpacity={maskStrength}
              filter={`url(#${textMaskFilterId})`}
            >
              {WORDMARK_TEXT}
            </text>
          </mask>
        </Fragment>
      );
    }
    // 'rect' — rectangle around the wordmark with soft feathered edges.
    // Estimate text width from font metrics: NEXUS at fontSize with
    // letter-spacing 0.16em ≈ 5 chars × ~0.62em advance + 4 × 0.16em spacing.
    // We over-estimate slightly and let feather smooth the edges.
    const estW = fontSize * (5 * 0.62 + 4 * 0.16);
    const estH = fontSize * 0.92;
    const rectW = estW + rectPaddingX * 2;
    const rectH = estH + rectPaddingY * 2;
    const rectX = 600 - rectW / 2;
    const rectY = wordmarkY - rectH / 2;
    return (
      <Fragment>
        <filter id={textMaskFilterId} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation={rectFeather} />
        </filter>
        <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width={W} height={H}>
          <rect x="0" y="0" width={W} height={H} fill="white" />
          <rect
            x={rectX}
            y={rectY}
            width={rectW}
            height={rectH}
            fill="black"
            fillOpacity={maskStrength}
            filter={`url(#${textMaskFilterId})`}
          />
        </mask>
      </Fragment>
    );
  };

  const fieldGroup = (
    <g
      style={{
        transformOrigin: rotateOrigin,
        animation:
          rotation > 0
            ? `${spinAnim} ${rotation}s linear infinite ${reverse ? 'reverse' : 'normal'}`
            : 'none',
      }}
    >
      {filaments.map((f) => (
        <Filament
          key={f.id}
          filament={f}
          primaryColor={primaryColor}
          secondaryColor={secondaryColor}
        />
      ))}
      {embers.map((e) => {
        const f = filamentsById[e.filamentId];
        if (!f) return null;
        return (
          <Ember
            key={e.id}
            filament={f}
            pointIdx={e.pointIdx}
            duration={e.duration}
            color={emberColor}
            size={e.size}
            animKey={`${inst}_${e.id}`}
          />
        );
      })}
      {pulses.map((p) => {
        const f = filamentsById[p.filamentId];
        if (!f) return null;
        return (
          <Pulse
            key={p.id}
            filament={f}
            duration={p.duration}
            color={pulseColor}
            animKey={`${inst}_${p.id}`}
          />
        );
      })}
    </g>
  );

  return (
    <div
      className={className}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        background: VEIL.bg,
        overflow: 'hidden',
        ...style,
      }}
    >
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height="100%"
        preserveAspectRatio="xMidYMid slice"
        style={{ display: 'block' }}
      >
        <defs>
          <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          {renderMask()}
        </defs>

        <style>{`
          @keyframes ${spinAnim} {
            from { transform: rotate(0deg); }
            to   { transform: rotate(360deg); }
          }
        `}</style>

        {maskMode === 'none' ? fieldGroup : <g mask={`url(#${maskId})`}>{fieldGroup}</g>}

        {showWordmark && (
          <NexusWordmark
            glowId={glowId}
            fontSize={fontSize}
            anchorY={wordmarkY}
            color={wordmarkColor}
            strokeWidth={wordmarkStroke}
          />
        )}
      </svg>
    </div>
  );
}
