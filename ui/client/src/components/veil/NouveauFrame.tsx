/**
 * NouveauFrame — the licensed Art Nouveau border around the Veil splash
 * wordmark.
 *
 * Renders its OWN svg using the SAME viewBox (1200x700) and the SAME
 * preserveAspectRatio ("xMidYMid slice") as VeilSpiral, layered directly over
 * it, so the frame tracks the wordmark across viewport sizes and never
 * reaches the screen edges.
 *
 * Typed port of the NEXUS IRIS design handoff prototype
 * (design_handoff/project/ui_kits/nexus_iris/nouveau-frame.jsx). The frame
 * art is Adobe Stock 482408992 cell r1c5, vendored landscape-rotated at
 * assets/ArtNouveauFrames-482408992/r1c5-inner.ts (see LICENSE.md there).
 *
 * ── 9-slice stretch ────────────────────────────────────────────────────────
 * The source art is sliced into a 3x5 grid so Width and Height can be
 * adjusted WITHOUT distorting the ornaments:
 *
 *   cols:  [ corner | TOP/BOTTOM straight run | corner ]   <- middle stretches W
 *   rows:  [ top assembly                              ]
 *          [ LEFT/RIGHT straight run (2/10 o'clock)    ]   <- stretches H
 *          [ side ornaments (3/9 o'clock) — FIXED      ]
 *          [ LEFT/RIGHT straight run (4/8 o'clock)     ]   <- stretches H
 *          [ bottom assembly                           ]
 *
 * Seam positions were measured from a raster scan of the frame's straight
 * runs. Each cell clips the shared art (defined once in <defs>, referenced by
 * <use>) to its source rect and maps that rect to a destination rect; fixed
 * bands keep scale 1 on their locked axis, stretch bands scale by the
 * width/height factor.
 */
import { ReactElement, useId } from 'react';

import {
  NOUVEAU_FRAME_H,
  NOUVEAU_FRAME_INNER,
  NOUVEAU_FRAME_W,
} from '@/assets/ArtNouveauFrames-482408992/r1c5-inner';

const FRAME_VB_W = 1200;
const FRAME_VB_H = 700;

// Natural landscape dimensions of the source art.
const NF_W = NOUVEAU_FRAME_W;
const NF_H = NOUVEAU_FRAME_H;

// Slice seams (natural coords). Measured by a fine per-row raster scan of the
// frame's constant line-bundle zones. The stretch bands sit STRICTLY inside
// the pure straight runs (top y296-336, bottom y640-688); every ornament,
// petal bud and transition curve lives in a FIXED band so height stretch
// never distorts the side (3/9 o'clock) ornaments.
const COL_SEAMS = [0, 460, 934, NF_W]; // 3 columns
const ROW_SEAMS = [0, 298, 334, 644, 684, NF_H]; // 5 rows
const COL_STRETCH = [false, true, false]; // middle col follows widthFactor
const ROW_STRETCH = [false, true, false, true, false]; // runs 1 & 3 follow heightFactor

export interface NouveauFrameProps {
  /** Frame fill color. */
  color?: string;
  /** Frame fill opacity. */
  opacity?: number;
  /** Baseline outer width (unstretched) of the frame, in viewBox user units. */
  sizeU?: number;
  /** Horizontal stretch factor applied to the straight top/bottom runs. */
  widthFactor?: number;
  /** Vertical stretch factor applied to the straight side runs. */
  heightFactor?: number;
  /** Center of the assembled frame, in viewBox user units. */
  anchorX?: number;
  anchorY?: number;
  /** Apply the soft magenta glow filter. */
  glow?: boolean;
  zIndex?: number;
}

export function NouveauFrame({
  color = '#b83d7a',
  opacity = 0.82,
  sizeU = 660,
  widthFactor = 1,
  heightFactor = 1,
  anchorX = 600,
  anchorY = 380,
  glow = true,
  zIndex = 4,
}: NouveauFrameProps) {
  const uid = useId().replace(/[:]/g, '');
  const glowId = `frameGlow_${uid}`;
  const artId = `frameArt_${uid}`;

  // Source band sizes.
  const srcColW = COL_SEAMS.slice(1).map((v, i) => v - COL_SEAMS[i]);
  const srcRowH = ROW_SEAMS.slice(1).map((v, i) => v - ROW_SEAMS[i]);
  // Destination band sizes (stretch bands scale on their axis).
  const dstColW = srcColW.map((w, i) => (COL_STRETCH[i] ? w * widthFactor : w));
  const dstRowH = srcRowH.map((h, i) => (ROW_STRETCH[i] ? h * heightFactor : h));
  // Destination band offsets.
  const dx = [0];
  dstColW.forEach((w) => dx.push(dx[dx.length - 1] + w));
  const dy = [0];
  dstRowH.forEach((h) => dy.push(dy[dy.length - 1] + h));
  const totalW = dx[dx.length - 1];
  const totalH = dy[dy.length - 1];

  // Place the assembled (possibly stretched) frame centred on the anchor.
  const scale = sizeU / NF_W;
  const tx = anchorX - (totalW * scale) / 2;
  const ty = anchorY - (totalH * scale) / 2;

  // Build the 15 cells.
  const cells: ReactElement[] = [];
  const clips: ReactElement[] = [];
  for (let ci = 0; ci < 3; ci++) {
    for (let ri = 0; ri < 5; ri++) {
      const sx0 = COL_SEAMS[ci];
      const sx1 = COL_SEAMS[ci + 1];
      const sy0 = ROW_SEAMS[ri];
      const sy1 = ROW_SEAMS[ri + 1];
      const sX = dstColW[ci] / srcColW[ci];
      const sY = dstRowH[ri] / srcRowH[ri];
      const clipId = `c_${uid}_${ci}_${ri}`;
      clips.push(
        <clipPath key={clipId} id={clipId} clipPathUnits="userSpaceOnUse">
          <rect x={sx0} y={sy0} width={sx1 - sx0} height={sy1 - sy0} />
        </clipPath>,
      );
      cells.push(
        <g
          key={clipId}
          transform={`translate(${dx[ci]} ${dy[ri]}) scale(${sX} ${sY}) translate(${-sx0} ${-sy0})`}
        >
          <g clipPath={`url(#${clipId})`}>
            <use href={`#${artId}`} />
          </g>
        </g>,
      );
    }
  }

  return (
    <svg
      aria-hidden="true"
      viewBox={`0 0 ${FRAME_VB_W} ${FRAME_VB_H}`}
      preserveAspectRatio="xMidYMid slice"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex,
        display: 'block',
      }}
    >
      <defs>
        <filter id={glowId} x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="3.4" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        {/* Shared copy of the heavy path data — referenced by every cell. */}
        <g
          id={artId}
          fill={color}
          fillOpacity={opacity}
          dangerouslySetInnerHTML={{ __html: NOUVEAU_FRAME_INNER }}
        />
        {clips}
      </defs>
      <g
        transform={`translate(${tx} ${ty}) scale(${scale})`}
        filter={glow ? `url(#${glowId})` : undefined}
      >
        {cells}
      </g>
    </svg>
  );
}
