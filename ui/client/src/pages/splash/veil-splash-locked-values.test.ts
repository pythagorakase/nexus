/**
 * The Veil splash ships the "Veil Hero Spiral v3" composition. These values
 * are the locked TWEAK_DEFAULTS of the design handoff
 * (design_handoff/project/hero/app-v3.jsx) and must not drift — the previous
 * splash shipped the forgone "Veil Hero Frame" variant by mistake.
 */
import { describe, expect, it } from 'vitest';

import { SPIRAL_V3 } from './VeilSplash';

describe('SPIRAL_V3 locked values', () => {
  it('matches the design-handoff TWEAK_DEFAULTS', () => {
    expect(SPIRAL_V3).toEqual({
      arms: 18,
      growth: 0.62,
      rotation: 70,
      reverse: true,
      pulseRate: 1.6,
      pulseColor: '#e1cd97',
      emberRate: 2.5,
      emberColor: '#e1cd97',
      emberSize: 1.8,
      maskMode: 'rect',
      maskHaloPx: 28,
      maskStrength: 0.95,
      rectPaddingX: 42,
      rectPaddingY: 22,
      rectFeather: 24,
      primaryColor: '#b83d7a',
      secondaryColor: '#b87333',
      fontSize: 124,
      frameColor: '#b83d7a',
      frameOpacity: 0.85,
      frameInset: 28,
      frameCornerFrac: 0.3,
      // app-v3 leaves the spiral anchor and wordmark at the component
      // defaults (600, 380).
      anchorX: 600,
      anchorY: 380,
      wordmarkY: 380,
      // Deliberate deviation from the prototype: product wordmark is gold.
      wordmarkColor: '#e1cd97',
    });
  });
});
