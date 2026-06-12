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
 * (design_handoff/project/hero/spiral-v2.jsx, the Veil Hero Spiral v3
 * composition). The approved splash values are hard-coded where this
 * component is instantiated (pages/splash/VeilSplash.tsx) — treat them as
 * canon.
 *
 * ── Rendering architecture (performance) ──────────────────────────────────
 * The prototype rendered the field as SVG and animated it with CSS keyframes
 * (rotate on a masked <g>, stroke-dashoffset per pulse, per-ember React
 * state). None of those animations are compositor-promotable for SVG
 * content, so every displayed frame forced the full main-thread pipeline —
 * style/layout/paint/layerize/commit — plus a fresh raster of the whole
 * field and three feGaussianBlur passes (profiled at ~2400 Paint events,
 * ~40k raster tasks, and ~1.9 s of GPU-process work per 10 s).
 *
 * This port instead draws the field into a single <canvas> from one rAF
 * loop, with zero per-frame React/DOM work:
 *   - filament geometry is precomputed into two Path2D batches (primary /
 *     secondary), stroked once each per frame;
 *   - pulses and embers live in plain arrays owned by the loop (no state,
 *     no DOM churn) and are drawn as arc-length slices / dots;
 *   - the feathered wordmark mask is rasterized ONCE per resize into an
 *     offscreen sprite and applied per frame with destination-out;
 *   - the wordmark itself (Megrim + glow filter) stays a static SVG overlay,
 *     painted once and cached by the compositor.
 * A prefers-reduced-motion query renders a single static composition (no
 * rotation, no pulses, no embers) and skips the loop entirely.
 *
 * One <VeilSpiral /> per artboard: each instance owns its own pulses,
 * embers, and animation loop.
 */
import { CSSProperties, useEffect, useId, useRef } from 'react';

// Veil brand palette (locked splash values; mirrors the .dark theme tokens)
const VEIL = {
  bg: '#09101c',
  primary: '#b83d7a',
  secondary: '#b87333',
  fg: '#e1cd97',
} as const;

// Fixed design viewBox shared with the wordmark overlay; the canvas
// replicates preserveAspectRatio="xMidYMid slice" over the same coordinates.
const W = 1200;
const H = 700;
const MAX_R = Math.hypot(W, H) * 0.6;

const WORDMARK_TEXT = 'NEXUS';
const WORDMARK_FONT = "'Megrim', 'Cormorant Garamond', 'Didot', serif";

// Filament stroke styling (prototype constants).
const FILAMENT_WIDTH = 0.55;
const PRIMARY_OPACITY = 0.42;
const SECONDARY_OPACITY = 0.3;
const PULSE_WIDTH = 1.7;
/** Fraction of the filament length lit by a traveling pulse. */
const PULSE_SEGMENT_FRAC = 0.12;
/** Pulse opacity ramps over the first/last 8% of its travel. */
const PULSE_RAMP = 0.08;

// Safety caps on concurrent dynamics (steady state at the locked splash
// rates is ~9 pulses / ~7 embers; the caps only bite under pathological
// prop values).
const MAX_PULSES = 32;
const MAX_EMBERS = 48;
/** Clamp spawn-accumulator steps so background-tab pauses cannot burst. */
const MAX_SPAWN_STEP_MS = 250;

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

export function buildSpiral(
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

export function buildField(
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

/** Cumulative arc length at every polyline vertex. */
function cumulativeLengths(points: SpiralPoint[]): Float64Array {
  const cum = new Float64Array(points.length);
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    cum[i] = cum[i - 1] + Math.hypot(b.x - a.x, b.y - a.y);
  }
  return cum;
}

// ─── Animation math (exported for tests) ─────────────────────────────────

export interface PulseWindow {
  /** Visible arc-length range along the filament. */
  a: number;
  b: number;
  /** Opacity envelope. */
  alpha: number;
}

/**
 * Visible arc window of a traveling pulse, replicating the prototype's
 * stroke-dash animation: dasharray [seg, total + 2*seg], dashoffset running
 * linearly from +seg to -(total + seg), stroke-opacity ramping over the
 * first and last 8%.
 */
export function pulseWindow(progress: number, totalLen: number): PulseWindow {
  const seg = totalLen * PULSE_SEGMENT_FRAC;
  const offset = seg - progress * (totalLen + 2 * seg);
  const head = -offset; // dash segment covers [-offset, -offset + seg]
  const a = Math.max(0, head);
  const b = Math.min(totalLen, head + seg);
  let alpha = 1;
  if (progress < PULSE_RAMP) alpha = progress / PULSE_RAMP;
  else if (progress > 1 - PULSE_RAMP) alpha = (1 - progress) / PULSE_RAMP;
  return { a, b, alpha: Math.max(0, Math.min(1, alpha)) };
}

export interface EmberEnvelope {
  alpha: number;
  scale: number;
}

/** CSS ease-out per keyframe segment, approximated quadratically. */
function easeOut(u: number): number {
  return 1 - (1 - u) * (1 - u);
}

/**
 * Ember twinkle envelope, replicating the prototype's keyframes:
 * opacity 0 -> 1 over 0-18%, hold to 70%, fade to 0 at 100%; scale
 * 0.4 -> 1 -> 0.4 on the same stops. The prototype used CSS `ease-out`
 * per segment; we approximate it quadratically (visually identical for a
 * 1.8-3.6 s twinkle).
 */
export function emberEnvelope(progress: number): EmberEnvelope {
  const p = Math.max(0, Math.min(1, progress));
  if (p < 0.18) {
    const u = easeOut(p / 0.18);
    return { alpha: u, scale: 0.4 + 0.6 * u };
  }
  if (p < 0.7) return { alpha: 1, scale: 1 };
  const u = easeOut((p - 0.7) / 0.3);
  return { alpha: 1 - u, scale: 1 - 0.6 * u };
}

// ─── Mask sprites ────────────────────────────────────────────────────────
// The prototype knocked the field out with an SVG luminance mask (white
// ground, black feathered shape at `maskStrength`). The canvas equivalent is
// destination-out with a sprite whose alpha equals (1 - mask luminance);
// for a black shape at alpha `s` blurred over white ground that is exactly
// the blurred shape coverage times `s`.

interface MaskSprite {
  canvas: HTMLCanvasElement;
  /** Device-pixel position of the sprite's top-left corner. */
  dx: number;
  dy: number;
}

interface ViewTransform {
  /** viewBox -> device-pixel scale (includes devicePixelRatio). */
  scale: number;
  tx: number;
  ty: number;
  deviceW: number;
  deviceH: number;
}

function makeSpriteCanvas(w: number, h: number): CanvasRenderingContext2D {
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.ceil(w));
  c.height = Math.max(1, Math.ceil(h));
  const ctx = c.getContext('2d');
  if (!ctx) throw new Error('VeilSpiral: 2D canvas context unavailable for mask sprite');
  return ctx;
}

function buildRectMaskSprite(
  view: ViewTransform,
  fontSize: number,
  wordmarkY: number,
  rectPaddingX: number,
  rectPaddingY: number,
  rectFeather: number,
  maskStrength: number,
): MaskSprite {
  // Estimate the wordmark box exactly as the prototype does.
  const estW = fontSize * (5 * 0.62 + 4 * 0.16);
  const estH = fontSize * 0.92;
  const rectW = (estW + rectPaddingX * 2) * view.scale;
  const rectH = (estH + rectPaddingY * 2) * view.scale;
  const feather = rectFeather * view.scale;
  const margin = Math.ceil(feather * 3);
  const ctx = makeSpriteCanvas(rectW + margin * 2, rectH + margin * 2);
  ctx.filter = `blur(${feather}px)`;
  ctx.globalAlpha = maskStrength;
  ctx.fillStyle = '#000';
  ctx.fillRect(margin, margin, rectW, rectH);
  const cxDev = view.tx + 600 * view.scale;
  const cyDev = view.ty + wordmarkY * view.scale;
  return { canvas: ctx.canvas, dx: cxDev - rectW / 2 - margin, dy: cyDev - rectH / 2 - margin };
}

function buildTextMaskSprite(
  view: ViewTransform,
  fontSize: number,
  wordmarkY: number,
  maskHaloPx: number,
  maskStrength: number,
): MaskSprite {
  // Approximates the prototype's feMorphology dilate + blur by stroking the
  // glyphs with a round-joined outline of the dilation diameter, then
  // blurring. Same halo footprint; the dilation corners are rounder.
  const dilate = Math.max(0.5, maskHaloPx * 0.4) * view.scale;
  const blur = maskHaloPx * 0.6 * view.scale;
  const fs = fontSize * view.scale;
  const padX = fs * 6;
  const padY = fs;
  const ctx = makeSpriteCanvas(padX * 2, padY * 2 + fs);
  ctx.filter = `blur(${blur}px)`;
  ctx.globalAlpha = maskStrength;
  ctx.font = `400 ${fs}px ${WORDMARK_FONT}`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  try {
    (ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing =
      `${fs * 0.16}px`;
  } catch {
    // letterSpacing is a recent canvas addition; the halo merely widens less.
  }
  ctx.fillStyle = '#000';
  ctx.strokeStyle = '#000';
  ctx.lineWidth = dilate * 2;
  ctx.lineJoin = 'round';
  const cx = padX + fs * 0.0595;
  const cy = padY + fs / 2;
  ctx.strokeText(WORDMARK_TEXT, cx, cy);
  ctx.fillText(WORDMARK_TEXT, cx, cy);
  const cxDev = view.tx + 600 * view.scale;
  const cyDev = view.ty + wordmarkY * view.scale;
  return { canvas: ctx.canvas, dx: cxDev - padX, dy: cyDev - (padY + fs / 2) };
}

function buildRadialMaskSprite(
  view: ViewTransform,
  wordmarkY: number,
  fadeRadius: number,
  fadeStrength: number,
): MaskSprite {
  // SVG mask value = luminance * alpha. The prototype's gradient: black at
  // `fadeStrength` alpha (0%), black at half alpha (55%), white opaque
  // (100%). Erase alpha = 1 - value; sample the 55-100% color+alpha ramp at
  // an intermediate stop so the canvas gradient's linear-rgba interpolation
  // tracks the luminance product.
  const r = fadeRadius * view.scale;
  const ctx = makeSpriteCanvas(r * 2, r * 2);
  const g = ctx.createRadialGradient(r, r, 0, r, r, r);
  const value = (f: number): number => {
    if (f <= 0.55) return 0; // black -> luminance 0 regardless of alpha
    const u = (f - 0.55) / 0.45;
    const lum = u;
    const alpha = fadeStrength * 0.5 + (1 - fadeStrength * 0.5) * u;
    return lum * alpha;
  };
  for (const stop of [0, 0.55, 0.775, 1]) {
    g.addColorStop(stop, `rgba(0,0,0,${(1 - value(stop)).toFixed(4)})`);
  }
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  const cxDev = view.tx + 600 * view.scale;
  const cyDev = view.ty + wordmarkY * view.scale;
  return { canvas: ctx.canvas, dx: cxDev - r, dy: cyDev - r };
}

// ─── Wordmark overlay ────────────────────────────────────────────────────

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

interface ActivePulse {
  filamentIdx: number;
  duration: number;
  startedAt: number;
}

interface ActiveEmber {
  filamentIdx: number;
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
  const inst = useId().replace(/[:]/g, '');
  const glowId = `glow_${inst}`;
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return undefined;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('VeilSpiral: 2D canvas context unavailable');

    // ── precomputed geometry
    const filaments = buildField(arms, growth, anchorX, anchorY);
    const cums = filaments.map((f) => cumulativeLengths(f.points));
    const primaryBatch = new Path2D();
    const secondaryBatch = new Path2D();
    filaments.forEach((f) => {
      (f.layer === 'primary' ? primaryBatch : secondaryBatch).addPath(new Path2D(f.d));
    });

    // ── view + mask sprite (rebuilt on resize)
    let view: ViewTransform | null = null;
    let mask: MaskSprite | null = null;

    const rebuildMask = () => {
      if (!view) return;
      if (maskMode === 'rect') {
        mask = buildRectMaskSprite(
          view, fontSize, wordmarkY, rectPaddingX, rectPaddingY, rectFeather, maskStrength,
        );
      } else if (maskMode === 'text') {
        mask = buildTextMaskSprite(view, fontSize, wordmarkY, maskHaloPx, maskStrength);
      } else if (maskMode === 'radial') {
        mask = buildRadialMaskSprite(view, wordmarkY, fadeRadius, fadeStrength);
      } else {
        mask = null;
      }
    };

    const resize = () => {
      const rect = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const deviceW = Math.max(1, Math.round(rect.width * dpr));
      const deviceH = Math.max(1, Math.round(rect.height * dpr));
      if (canvas.width !== deviceW) canvas.width = deviceW;
      if (canvas.height !== deviceH) canvas.height = deviceH;
      // preserveAspectRatio="xMidYMid slice" over the 1200x700 viewBox.
      const scale = Math.max(deviceW / W, deviceH / H);
      view = {
        scale,
        tx: (deviceW - W * scale) / 2,
        ty: (deviceH - H * scale) / 2,
        deviceW,
        deviceH,
      };
      rebuildMask();
    };

    // ── dynamics owned by the loop — never touches React state
    const pulses: ActivePulse[] = [];
    const embers: ActiveEmber[] = [];
    let pulseAccMs = 0;
    let emberAccMs = 0;

    const spawn = (now: number, dtMs: number) => {
      const step = Math.min(dtMs, MAX_SPAWN_STEP_MS);
      if (pulseRate > 0) {
        const interval = 1000 / pulseRate;
        pulseAccMs += step;
        while (pulseAccMs >= interval) {
          pulseAccMs -= interval;
          if (pulses.length >= MAX_PULSES) continue;
          pulses.push({
            filamentIdx: Math.floor(Math.random() * filaments.length),
            duration:
              pulseMinDuration + Math.random() * (pulseMaxDuration - pulseMinDuration),
            startedAt: now,
          });
        }
      }
      if (emberRate > 0) {
        const interval = 1000 / emberRate;
        emberAccMs += step;
        while (emberAccMs >= interval) {
          emberAccMs -= interval;
          if (embers.length >= MAX_EMBERS) continue;
          const filamentIdx = Math.floor(Math.random() * filaments.length);
          // Avoid the wordmark region — bias toward the outer span of the arm.
          const tBias = 0.25 + Math.random() * 0.75;
          embers.push({
            filamentIdx,
            pointIdx: Math.floor(tBias * (filaments[filamentIdx].points.length - 1)),
            duration:
              emberMinDuration + Math.random() * (emberMaxDuration - emberMinDuration),
            startedAt: now,
            size: emberSize * (0.6 + Math.random() * 0.8),
          });
        }
      }
    };

    const expire = (now: number) => {
      for (let i = pulses.length - 1; i >= 0; i--) {
        if (now - pulses[i].startedAt >= pulses[i].duration) pulses.splice(i, 1);
      }
      for (let i = embers.length - 1; i >= 0; i--) {
        if (now - embers[i].startedAt >= embers[i].duration) embers.splice(i, 1);
      }
    };

    /** Stroke the polyline slice of filament `fi` between arc lengths a..b. */
    const strokeArcSlice = (fi: number, a: number, b: number) => {
      if (b <= a) return;
      const pts = filaments[fi].points;
      const cum = cums[fi];
      // Binary search for the first vertex past `a`.
      let lo = 0;
      let hi = cum.length - 1;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (cum[mid] < a) lo = mid + 1;
        else hi = mid;
      }
      const lerpAt = (target: number, idx: number) => {
        // Interpolate between vertices idx-1 and idx.
        const l0 = cum[idx - 1];
        const l1 = cum[idx];
        const u = l1 > l0 ? (target - l0) / (l1 - l0) : 0;
        const p0 = pts[idx - 1];
        const p1 = pts[idx];
        return { x: p0.x + (p1.x - p0.x) * u, y: p0.y + (p1.y - p0.y) * u };
      };
      ctx.beginPath();
      const start = lo > 0 ? lerpAt(a, lo) : pts[0];
      ctx.moveTo(start.x, start.y);
      let i = lo;
      while (i < cum.length && cum[i] < b) {
        ctx.lineTo(pts[i].x, pts[i].y);
        i++;
      }
      if (i > 0 && i < cum.length) {
        const end = lerpAt(b, i);
        ctx.lineTo(end.x, end.y);
      }
      ctx.stroke();
    };

    const t0 = performance.now();

    const draw = (now: number, animate: boolean) => {
      if (!view) return;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, view.deviceW, view.deviceH);
      ctx.setTransform(view.scale, 0, 0, view.scale, view.tx, view.ty);

      // Field rotation (time-based; one full turn per `rotation` seconds).
      if (animate && rotation > 0) {
        const turns = ((now - t0) / 1000 / rotation) % 1;
        const angle = (reverse ? -1 : 1) * turns * Math.PI * 2;
        ctx.translate(anchorX, anchorY);
        ctx.rotate(angle);
        ctx.translate(-anchorX, -anchorY);
      }

      // Filaments — two batched strokes.
      ctx.lineWidth = FILAMENT_WIDTH;
      ctx.lineCap = 'butt';
      ctx.globalAlpha = PRIMARY_OPACITY;
      ctx.strokeStyle = primaryColor;
      ctx.stroke(primaryBatch);
      ctx.globalAlpha = SECONDARY_OPACITY;
      ctx.strokeStyle = secondaryColor;
      ctx.stroke(secondaryBatch);

      // Pulses — arc-length slices with round caps.
      ctx.lineWidth = PULSE_WIDTH;
      ctx.lineCap = 'round';
      ctx.strokeStyle = pulseColor;
      for (const p of pulses) {
        const progress = (now - p.startedAt) / p.duration;
        const total = cums[p.filamentIdx][cums[p.filamentIdx].length - 1];
        const win = pulseWindow(progress, total);
        if (win.alpha <= 0) continue;
        ctx.globalAlpha = win.alpha;
        strokeArcSlice(p.filamentIdx, win.a, win.b);
      }

      // Embers — screen-blended twinkle dots.
      ctx.globalCompositeOperation = 'screen';
      ctx.fillStyle = emberColor;
      for (const e of embers) {
        const env = emberEnvelope((now - e.startedAt) / e.duration);
        if (env.alpha <= 0) continue;
        const pt = filaments[e.filamentIdx].points[e.pointIdx];
        ctx.globalAlpha = env.alpha;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, e.size * env.scale, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;

      // Wordmark knockout — static sprite, device space.
      if (mask) {
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.globalCompositeOperation = 'destination-out';
        ctx.drawImage(mask.canvas, mask.dx, mask.dy);
        ctx.globalCompositeOperation = 'source-over';
      }
    };

    // ── loop / reduced-motion wiring
    let raf = 0;
    let last = performance.now();
    const frame = (now: number) => {
      spawn(now, now - last);
      expire(now);
      last = now;
      draw(now, true);
      raf = requestAnimationFrame(frame);
    };

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let reducedMode = reduced.matches;

    const start = () => {
      if (reducedMode) {
        // Static composition: no rotation, no pulses, no embers.
        pulses.length = 0;
        embers.length = 0;
        draw(performance.now(), false);
      } else {
        last = performance.now();
        raf = requestAnimationFrame(frame);
      }
    };
    const stop = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    };
    const onMotionChange = () => {
      stop();
      reducedMode = reduced.matches;
      start();
    };
    reduced.addEventListener('change', onMotionChange);

    const ro = new ResizeObserver(() => {
      resize();
      if (reducedMode) draw(performance.now(), false);
    });
    ro.observe(container);
    resize();
    start();

    return () => {
      stop();
      reduced.removeEventListener('change', onMotionChange);
      ro.disconnect();
    };
  }, [
    arms, growth, rotation, reverse, anchorX, anchorY, wordmarkY, fontSize,
    maskMode, fadeRadius, fadeStrength, maskHaloPx, maskStrength,
    rectPaddingX, rectPaddingY, rectFeather,
    pulseRate, pulseColor, pulseMinDuration, pulseMaxDuration,
    emberRate, emberColor, emberSize, emberMinDuration, emberMaxDuration,
    primaryColor, secondaryColor,
  ]);

  return (
    <div
      ref={containerRef}
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
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          display: 'block',
        }}
      />
      {showWordmark && (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="xMidYMid slice"
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            display: 'block',
            pointerEvents: 'none',
          }}
        >
          <defs>
            <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <NexusWordmark
            glowId={glowId}
            fontSize={fontSize}
            anchorY={wordmarkY}
            color={wordmarkColor}
            strokeWidth={wordmarkStroke}
          />
        </svg>
      )}
    </div>
  );
}
