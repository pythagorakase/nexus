/**
 * CrescentFrame 9-slice geometry tests.
 */
import { describe, expect, it } from 'vitest';

import {
  CRESCENT_FRAME_H,
  CRESCENT_FRAME_W,
} from '@/assets/ArtNouveauFrames-482408992/r1c1-inner';
import { computeCrescentSlices } from './CrescentFrame';

describe('computeCrescentSlices', () => {
  // Locked splash geometry: 1440x900 viewport at the canonical 28px inset.
  const innerW = 1440 - 28 * 2;
  const innerH = 900 - 28 * 2;
  const cornerFrac = 0.3;
  const slices = computeCrescentSlices(innerW, innerH, cornerFrac);
  const byName = Object.fromEntries(slices.map((s) => [s.name, s]));

  it('produces exactly the eight border slices (center is skipped)', () => {
    expect(slices.map((s) => s.name).sort()).toEqual(
      ['b', 'bl', 'br', 'l', 'r', 't', 'tl', 'tr'].sort(),
    );
  });

  it('aspect-locks the corners to a uniform scale', () => {
    const scale = Math.min(innerW / CRESCENT_FRAME_W, innerH / CRESCENT_FRAME_H);
    for (const name of ['tl', 'tr', 'bl', 'br'] as const) {
      const s = byName[name];
      expect(s.dw / s.sw).toBeCloseTo(scale, 9);
      expect(s.dh / s.sh).toBeCloseTo(scale, 9);
    }
  });

  it('stretches the edges to exactly fill the runs between corners', () => {
    expect(byName.tl.dw + byName.t.dw + byName.tr.dw).toBeCloseTo(innerW, 6);
    expect(byName.tl.dh + byName.l.dh + byName.bl.dh).toBeCloseTo(innerH, 6);
  });

  it('crops each corner to the outer cornerFrac of the source art', () => {
    expect(byName.tl.sw).toBeCloseTo(CRESCENT_FRAME_W * cornerFrac, 6);
    expect(byName.br.sx).toBeCloseTo(CRESCENT_FRAME_W * (1 - cornerFrac), 6);
    expect(byName.br.sy).toBeCloseTo(CRESCENT_FRAME_H * (1 - cornerFrac), 6);
  });

  it('collapses to zero-size slices when the box is empty', () => {
    for (const s of computeCrescentSlices(0, 0, cornerFrac)) {
      expect(s.dw).toBe(0);
      expect(s.dh).toBe(0);
    }
  });
});
