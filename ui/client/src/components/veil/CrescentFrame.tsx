/**
 * CrescentFrame — the edge-stretched crescent border around the Veil splash.
 *
 * Full-bleed 9-slice overlay of the licensed crescent ornament
 * (Adobe Stock 482408992 cell r1c1 "CrescentMoon", vendored landscape-rotated
 * at assets/ArtNouveauFrames-482408992/r1c1-inner.ts; see LICENSE.md there).
 *
 * Typed port of the NEXUS IRIS design handoff prototype
 * (design_handoff/project/hero/spiral-v2.jsx — the Veil Hero Spiral v3
 * composition). The approved splash values are hard-coded where this
 * component is instantiated (pages/splash/VeilSplash.tsx) — treat them as
 * canon.
 *
 * ── 9-slice stretch ───────────────────────────────────────────────────────
 * The four corners are aspect-locked to a uniform scale (auto = the scale at
 * which the full source art fits inside the inset viewport); the four edges
 * stretch independently to fill the space between corners. The center slice
 * is skipped (transparent). Each slice is a nested <svg> whose viewBox crops
 * the shared art to its 1/9th of the source.
 *
 * `cornerFrac` sets the source-side corner/edge breakpoint (0.30 = the outer
 * 30% of each side is "corner"); `inset` insets the whole frame from the
 * parent edges in CSS pixels.
 *
 * Deviation from the prototype (visual no-op, perf win): the prototype
 * repeats the full path payload in all eight slices and flattens it to the
 * frame color through an feColorMatrix filter. Because the vendored payload
 * has its fill stripped, we instead define the art ONCE in <defs> with a
 * plain `fill`, and each slice pulls it in via <use> — same pixels, no
 * filter pass, an eighth of the DOM.
 */
import { useEffect, useId, useRef, useState } from 'react';

import {
  CRESCENT_FRAME_H,
  CRESCENT_FRAME_INNER,
  CRESCENT_FRAME_W,
} from '@/assets/ArtNouveauFrames-482408992/r1c1-inner';

export interface CrescentSlice {
  name: 'tl' | 'tr' | 'bl' | 'br' | 't' | 'b' | 'l' | 'r';
  /** Destination rect, CSS px relative to the inset frame box. */
  dx: number;
  dy: number;
  dw: number;
  dh: number;
  /** Source rect, art coordinates. */
  sx: number;
  sy: number;
  sw: number;
  sh: number;
}

/**
 * Pure 9-slice geometry: corners aspect-locked to `scale`, edges stretched to
 * fill the remaining run. Exported for tests.
 */
export function computeCrescentSlices(
  innerW: number,
  innerH: number,
  cornerFrac: number,
): CrescentSlice[] {
  // Source-side slice geometry.
  const sCw = CRESCENT_FRAME_W * cornerFrac;
  const sCh = CRESCENT_FRAME_H * cornerFrac;
  const sEw = CRESCENT_FRAME_W - 2 * sCw;
  const sEh = CRESCENT_FRAME_H - 2 * sCh;

  // Corner scale: the source art fits proportionally inside the frame box.
  const scale =
    innerW > 0 && innerH > 0
      ? Math.min(innerW / CRESCENT_FRAME_W, innerH / CRESCENT_FRAME_H)
      : 0;

  const dCw = sCw * scale;
  const dCh = sCh * scale;
  const dEw = Math.max(0, innerW - 2 * dCw);
  const dEh = Math.max(0, innerH - 2 * dCh);

  /* prettier-ignore */
  return [
    { name: 'tl', dx: 0,         dy: 0,         dw: dCw, dh: dCh, sx: 0,                       sy: 0,                       sw: sCw, sh: sCh },
    { name: 'tr', dx: dCw + dEw, dy: 0,         dw: dCw, dh: dCh, sx: CRESCENT_FRAME_W - sCw,  sy: 0,                       sw: sCw, sh: sCh },
    { name: 'bl', dx: 0,         dy: dCh + dEh, dw: dCw, dh: dCh, sx: 0,                       sy: CRESCENT_FRAME_H - sCh,  sw: sCw, sh: sCh },
    { name: 'br', dx: dCw + dEw, dy: dCh + dEh, dw: dCw, dh: dCh, sx: CRESCENT_FRAME_W - sCw,  sy: CRESCENT_FRAME_H - sCh,  sw: sCw, sh: sCh },
    { name: 't',  dx: dCw,       dy: 0,         dw: dEw, dh: dCh, sx: sCw,                     sy: 0,                       sw: sEw, sh: sCh },
    { name: 'b',  dx: dCw,       dy: dCh + dEh, dw: dEw, dh: dCh, sx: sCw,                     sy: CRESCENT_FRAME_H - sCh,  sw: sEw, sh: sCh },
    { name: 'l',  dx: 0,         dy: dCh,       dw: dCw, dh: dEh, sx: 0,                       sy: sCh,                     sw: sCw, sh: sEh },
    { name: 'r',  dx: dCw + dEw, dy: dCh,       dw: dCw, dh: dEh, sx: CRESCENT_FRAME_W - sCw,  sy: sCh,                     sw: sCw, sh: sEh },
  ];
}

export interface CrescentFrameProps {
  /** Frame fill color. */
  color?: string;
  /** Frame opacity (applied to the whole overlay). */
  opacity?: number;
  /** Inset of the frame box from the parent edges, CSS px. */
  inset?: number;
  /** Source-side corner/edge breakpoint as a fraction of each side. */
  cornerFrac?: number;
  zIndex?: number;
}

export function CrescentFrame({
  color = '#b83d7a',
  opacity = 0.9,
  inset = 24,
  cornerFrac = 0.3,
  zIndex = 5,
}: CrescentFrameProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => {
      const r = el.getBoundingClientRect();
      setBox({ w: r.width, h: r.height });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    window.addEventListener('resize', measure);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, []);

  const artId = `crescentArt_${useId().replace(/[:]/g, '')}`;
  const innerW = box ? Math.max(0, box.w - inset * 2) : 0;
  const innerH = box ? Math.max(0, box.h - inset * 2) : 0;
  const slices = computeCrescentSlices(innerW, innerH, cornerFrac);

  return (
    <div
      ref={ref}
      aria-hidden="true"
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        zIndex,
        opacity,
      }}
    >
      {box && innerW > 0 && innerH > 0 && (
        <svg
          width={innerW}
          height={innerH}
          viewBox={`0 0 ${innerW} ${innerH}`}
          style={{ position: 'absolute', left: inset, top: inset }}
          preserveAspectRatio="none"
        >
          <defs>
            {/* Shared copy of the heavy path data — referenced by every slice. */}
            <g id={artId} fill={color} dangerouslySetInnerHTML={{ __html: CRESCENT_FRAME_INNER }} />
          </defs>
          {slices.map((s) => {
            if (s.dw <= 0 || s.dh <= 0) return null;
            return (
              <svg
                key={s.name}
                x={s.dx}
                y={s.dy}
                width={s.dw}
                height={s.dh}
                viewBox={`${s.sx} ${s.sy} ${s.sw} ${s.sh}`}
                preserveAspectRatio="none"
              >
                <use href={`#${artId}`} />
              </svg>
            );
          })}
        </svg>
      )}
    </div>
  );
}
