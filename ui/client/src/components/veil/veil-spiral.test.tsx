/**
 * VeilSpiral unit tests: animation math (pulse dash-window + ember envelope),
 * field geometry, and the prefers-reduced-motion wiring.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render } from '@testing-library/react';

import { buildField, emberEnvelope, pulseWindow, VeilSpiral } from './VeilSpiral';

const VIEW_W = 1200;
const VIEW_H = 700;
const MAX_R = Math.hypot(VIEW_W, VIEW_H) * 0.6;

describe('pulseWindow', () => {
  const total = 1000;

  it('starts empty and invisible (dash segment still behind the path start)', () => {
    const w = pulseWindow(0, total);
    expect(w.alpha).toBe(0);
    expect(w.b).toBeLessThanOrEqual(w.a);
  });

  it('travels from the path start outward', () => {
    const early = pulseWindow(0.2, total);
    const late = pulseWindow(0.6, total);
    expect(early.a).toBeGreaterThanOrEqual(0);
    expect(late.a).toBeGreaterThan(early.a);
    expect(late.b).toBeGreaterThan(early.b);
  });

  it('spans exactly the 12% dash segment mid-travel', () => {
    const w = pulseWindow(0.5, total);
    expect(w.b - w.a).toBeCloseTo(total * 0.12, 6);
    expect(w.alpha).toBe(1);
  });

  it('ramps opacity over the first and last 8%', () => {
    expect(pulseWindow(0.04, total).alpha).toBeCloseTo(0.5, 6);
    expect(pulseWindow(0.96, total).alpha).toBeCloseTo(0.5, 6);
    expect(pulseWindow(0.5, total).alpha).toBe(1);
  });

  it('ends empty and invisible (dash segment past the path end)', () => {
    const w = pulseWindow(1, total);
    expect(w.alpha).toBe(0);
    expect(w.b).toBeLessThanOrEqual(w.a);
  });
});

describe('emberEnvelope', () => {
  it('fades in from nothing at 40% scale', () => {
    expect(emberEnvelope(0)).toEqual({ alpha: 0, scale: 0.4 });
  });

  it('holds full presence through the 18-70% plateau', () => {
    expect(emberEnvelope(0.18)).toEqual({ alpha: 1, scale: 1 });
    expect(emberEnvelope(0.5)).toEqual({ alpha: 1, scale: 1 });
  });

  it('fades back out to nothing at 40% scale', () => {
    const end = emberEnvelope(1);
    expect(end.alpha).toBeCloseTo(0, 6);
    expect(end.scale).toBeCloseTo(0.4, 6);
  });
});

describe('buildField', () => {
  it('builds a primary and a secondary filament per arm', () => {
    const field = buildField(18, 0.62, 600, 380);
    expect(field).toHaveLength(36);
    expect(field.filter((f) => f.layer === 'primary')).toHaveLength(18);
    expect(field.filter((f) => f.layer === 'secondary')).toHaveLength(18);
  });

  it('terminates every primary arm on the MAX_R circle around the anchor', () => {
    const field = buildField(6, 0.62, 600, 380);
    for (const f of field.filter((x) => x.layer === 'primary')) {
      const last = f.points[f.points.length - 1];
      expect(Math.hypot(last.x - 600, last.y - 380)).toBeCloseTo(MAX_R, 6);
    }
  });
});

describe('VeilSpiral reduced-motion wiring', () => {
  const ctxByCanvas = new WeakMap<HTMLCanvasElement, Record<string, ReturnType<typeof vi.fn>>>();

  const stubGetContext = function (this: HTMLCanvasElement) {
    let fns = ctxByCanvas.get(this);
    if (!fns) {
      fns = {};
      ctxByCanvas.set(this, fns);
    }
    const canvas = this;
    const recorded = fns;
    return new Proxy(
      {},
      {
        get(_t, prop: string) {
          if (prop === 'canvas') return canvas;
          if (!recorded[prop]) recorded[prop] = vi.fn();
          return recorded[prop];
        },
        set() {
          return true;
        },
      },
    );
  };

  let rafSpy: ReturnType<typeof vi.fn>;
  let reducedMatches = false;

  beforeEach(() => {
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    vi.stubGlobal(
      'Path2D',
      class {
        addPath() {}
      },
    );
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: reducedMatches,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    HTMLCanvasElement.prototype.getContext = stubGetContext as never;
    rafSpy = vi.fn(() => 1);
    vi.stubGlobal('requestAnimationFrame', rafSpy);
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('renders one static frame and never schedules the loop when reduced', () => {
    reducedMatches = true;
    const { container } = render(<VeilSpiral maskMode="rect" />);
    expect(rafSpy).not.toHaveBeenCalled();
    const canvas = container.querySelector('canvas') as HTMLCanvasElement;
    const fns = ctxByCanvas.get(canvas);
    expect(fns).toBeDefined();
    // The static composition still strokes the filament batches.
    expect(fns!.stroke).toBeDefined();
    expect(fns!.stroke.mock.calls.length).toBeGreaterThan(0);
  });

  it('schedules the rAF loop when motion is allowed', () => {
    reducedMatches = false;
    render(<VeilSpiral maskMode="rect" />);
    expect(rafSpy).toHaveBeenCalled();
  });
});
