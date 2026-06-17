/**
 * Gilded splash ornament helpers, ported from the NEXUS IRIS design handoff.
 *
 * DecoFrameSliced uses measured multi-band slicing for the licensed r1c1 Art
 * Deco frame. Do not replace it with a simple CSS border-image: the fixed
 * tracks preserve the corner and center ornaments while the straight bands
 * stretch to the viewport.
 */
import { useId, useLayoutEffect, useRef, useState } from 'react';

import type { DecoFrameMeta } from '@/assets/ArtDecoFrames-549888080/frames-meta';

interface DecoRaysProps {
  sourceXvw?: number;
  sourceYvh?: number;
  rayCount?: number;
  spinSeconds?: number;
  reverse?: boolean;
  reachVmax?: number;
  spreadDeg?: number;
  color?: string;
  accentColor?: string;
  accentEvery?: number;
  thickness?: number;
  intensity?: number;
  falloff?: number;
  pulse?: number;
  rings?: boolean;
  ringCount?: number;
  zIndex?: number;
}

export function DecoRays({
  sourceXvw = 50,
  sourceYvh = -32,
  rayCount = 96,
  spinSeconds = 160,
  reverse = false,
  reachVmax = 1.15,
  spreadDeg = 360,
  color = '#c9a227',
  accentColor = '#e8c766',
  accentEvery = 4,
  thickness = 2,
  intensity = 0.5,
  falloff = 0.65,
  pulse = 0,
  rings = true,
  ringCount = 3,
  zIndex = 0,
}: DecoRaysProps) {
  const rayId = useId().replace(/[:]/g, '');
  const containerHalf = reachVmax * 92 + Math.abs(sourceYvh) + 54;
  const sizeVmax = containerHalf * 2;
  const viewBox = 1000;
  const center = viewBox / 2;
  const rayLength = (viewBox / 2) * 0.99;
  const innerRadius = viewBox * 0.01;
  const halfSpread = spreadDeg / 2;

  const lines = Array.from({ length: rayCount }, (_, index) => {
    const fraction = rayCount === 1 ? 0.5 : index / rayCount;
    const degrees =
      spreadDeg >= 360
        ? fraction * 360
        : 90 - halfSpread + (index / Math.max(1, rayCount - 1)) * spreadDeg;
    const angle = (degrees * Math.PI) / 180;
    const isAccent = index % accentEvery === 0;
    const isMid = !isAccent && index % 2 === 0;

    return (
      <line
        key={index}
        x1={center + Math.cos(angle) * innerRadius}
        y1={center + Math.sin(angle) * innerRadius}
        x2={center + Math.cos(angle) * rayLength}
        y2={center + Math.sin(angle) * rayLength}
        stroke={isAccent ? accentColor : color}
        strokeWidth={isAccent ? thickness * 1.8 : isMid ? thickness * 1.1 : thickness * 0.6}
        strokeLinecap="butt"
        opacity={isAccent ? 0.95 : isMid ? 0.7 : 0.5}
      />
    );
  });

  const spin =
    spinSeconds > 0
      ? `decoRaySpin_${rayId} ${spinSeconds}s linear infinite${reverse ? ' reverse' : ''}`
      : 'none';

  return (
    <div
      aria-hidden="true"
      style={{
        position: 'absolute',
        left: `${sourceXvw}vw`,
        top: `${sourceYvh}vh`,
        width: `min(${sizeVmax}vmax, 7600px)`,
        height: `min(${sizeVmax}vmax, 7600px)`,
        transform: 'translate(-50%, -50%)',
        WebkitMaskImage: `radial-gradient(circle closest-side, #000 0%, #000 ${Math.round(
          (1 - falloff) * 70,
        )}%, transparent 100%)`,
        maskImage: `radial-gradient(circle closest-side, #000 0%, #000 ${Math.round(
          (1 - falloff) * 70,
        )}%, transparent 100%)`,
        pointerEvents: 'none',
        zIndex,
        opacity: intensity,
        animation:
          pulse > 0
            ? `decoRayPulse_${rayId} ${(6 / pulse).toFixed(2)}s ease-in-out infinite`
            : 'none',
      }}
    >
      <style>{`
        @keyframes decoRaySpin_${rayId} { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes decoRayPulse_${rayId} { 0%,100% { opacity: ${intensity}; } 50% { opacity: ${Math.min(
          1,
          intensity * 1.35,
        ).toFixed(3)}; } }
      `}</style>
      <svg
        viewBox={`0 0 ${viewBox} ${viewBox}`}
        width="100%"
        height="100%"
        style={{
          display: 'block',
          transformOrigin: '50% 50%',
          animation: spin,
          willChange: spinSeconds > 0 ? 'transform' : 'auto',
        }}
      >
        <g>
          {lines}
          {rings &&
            Array.from({ length: ringCount }, (_, index) => {
              const radius = rayLength * (0.16 + index * (0.5 / Math.max(1, ringCount)));

              return (
                <circle
                  key={`ring-${index}`}
                  cx={center}
                  cy={center}
                  r={radius}
                  fill="none"
                  stroke={index % 2 === 1 ? accentColor : color}
                  strokeWidth={index % 2 === 1 ? thickness * 0.9 : thickness * 0.5}
                  opacity={0.18 + index * 0.04}
                />
              );
            })}
        </g>
      </svg>
    </div>
  );
}

interface DecoFrameSlicedProps {
  src: string;
  meta: DecoFrameMeta;
  scale?: number;
  margin?: number;
  tint?: number;
  zIndex?: number;
}

interface AxisLayout {
  srcSizes: number[];
  dstSizes: number[];
  offsets: number[];
}

const getRequiredNumber = (value: number | null | undefined): number => {
  if (value == null) {
    throw new Error('Deco frame metadata has a missing fixed-band ink center.');
  }

  return value;
};

function layoutAxis(
  bounds: number[],
  stretchFlags: boolean[],
  inkCenters: Array<number | null>,
  total: number,
  requestedScale: number,
): AxisLayout {
  const bandCount = stretchFlags.length;
  const sourceWidth = bounds[bandCount];
  const srcSizes = bounds.slice(1).map((bound, index) => bound - bounds[index]);
  const fixedSourceSize = srcSizes.reduce(
    (sum, size, index) => sum + (stretchFlags[index] ? 0 : size),
    0,
  );
  const palindromic = stretchFlags.every(
    (flag, index) => flag === stretchFlags[bandCount - 1 - index],
  );
  const fractions = inkCenters.map((centerValue, index) => {
    if (centerValue == null) return null;

    const mirrored = inkCenters[bandCount - 1 - index];
    return palindromic && mirrored != null
      ? ((centerValue + (sourceWidth - mirrored)) / 2) / sourceWidth
      : centerValue / sourceWidth;
  });

  let scale = Math.min(requestedScale, (total * 0.96) / fixedSourceSize);
  let dstSizes: number[] = [];

  for (let iteration = 0; iteration < 24; iteration += 1) {
    dstSizes = new Array<number>(bandCount);
    for (let index = 0; index < bandCount; index += 1) {
      if (!stretchFlags[index]) {
        dstSizes[index] = srcSizes[index] * scale;
      }
    }

    let position = 0;
    let ok = true;
    for (let index = 0; index < bandCount; index += 1) {
      if (!stretchFlags[index]) {
        position += dstSizes[index];
        continue;
      }

      const nextIndex = index + 1;
      const nextInkCenter = getRequiredNumber(inkCenters[nextIndex]);
      const nextFraction = getRequiredNumber(fractions[nextIndex]);
      const inkOffset = (nextInkCenter - bounds[nextIndex]) * scale;
      const nextStart =
        nextIndex === bandCount - 1
          ? total - dstSizes[nextIndex]
          : nextFraction * total - inkOffset;
      const stretchSize = nextStart - position;

      if (stretchSize < 2) {
        ok = false;
        break;
      }

      dstSizes[index] = stretchSize;
      position = nextStart;
    }

    if (ok) break;
    scale *= 0.94;
  }

  if (dstSizes.some((value) => value === undefined)) {
    let position = 0;
    for (let index = 0; index < bandCount; index += 1) {
      if (!stretchFlags[index]) {
        position += dstSizes[index];
        continue;
      }

      const nextIndex = index + 1;
      const nextInkCenter = getRequiredNumber(inkCenters[nextIndex]);
      const nextFraction = getRequiredNumber(fractions[nextIndex]);
      const inkOffset = (nextInkCenter - bounds[nextIndex]) * scale;
      const nextStart =
        nextIndex === bandCount - 1
          ? total - dstSizes[nextIndex]
          : nextFraction * total - inkOffset;

      dstSizes[index] = Math.max(2, nextStart - position);
      position += dstSizes[index];
    }
  }

  const offsets = [0];
  dstSizes.forEach((size) => offsets.push(offsets[offsets.length - 1] + size));

  return { srcSizes, dstSizes, offsets };
}

export function DecoFrameSliced({
  src,
  meta,
  scale = 1,
  margin = 16,
  tint = 0,
  zIndex = 2,
}: DecoFrameSlicedProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return undefined;

    const measure = () => {
      setBox((current) => {
        const width = element.clientWidth;
        const height = element.clientHeight;
        return current.width === width && current.height === height ? current : { width, height };
      });
    };

    measure();

    let animationFrame = 0;
    let tries = 0;
    const pollUntilSized = () => {
      if (!ref.current) return;
      if (ref.current.clientWidth > 0 && ref.current.clientHeight > 0) {
        measure();
        return;
      }
      tries += 1;
      if (tries < 600) animationFrame = requestAnimationFrame(pollUntilSized);
    };

    if (element.clientWidth === 0 || element.clientHeight === 0) {
      animationFrame = requestAnimationFrame(pollUntilSized);
    }

    window.addEventListener('resize', measure);

    let resizeObserver: ResizeObserver | undefined;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(measure);
      resizeObserver.observe(element);
    }

    return () => {
      window.removeEventListener('resize', measure);
      resizeObserver?.disconnect();
      if (animationFrame) cancelAnimationFrame(animationFrame);
    };
  }, [margin]);

  const cells = [];
  if (box.width > 4 && box.height > 4) {
    const fit = Math.min(box.width / meta.w, box.height / meta.h);
    const requestedScale = fit * scale;
    const xLayout = layoutAxis(
      meta.cols,
      meta.colStretch,
      meta.colInkC,
      box.width,
      requestedScale,
    );
    const yLayout = layoutAxis(
      meta.rows,
      meta.rowStretch,
      meta.rowInkC,
      box.height,
      requestedScale,
    );
    const lastColumn = xLayout.dstSizes.length - 1;
    const lastRow = yLayout.dstSizes.length - 1;

    for (let row = 0; row <= lastRow; row += 1) {
      for (let column = 0; column <= lastColumn; column += 1) {
        if (row !== 0 && row !== lastRow && column !== 0 && column !== lastColumn) continue;

        const width = xLayout.dstSizes[column];
        const height = yLayout.dstSizes[row];
        if (width < 0.5 || height < 0.5) continue;

        const scaleX = width / xLayout.srcSizes[column];
        const scaleY = height / yLayout.srcSizes[row];
        cells.push(
          <div
            key={`${row}-${column}`}
            style={{
              position: 'absolute',
              left: `${xLayout.offsets[column]}px`,
              top: `${yLayout.offsets[row]}px`,
              width: `${width}px`,
              height: `${height}px`,
              backgroundImage: `url("${src}")`,
              backgroundRepeat: 'no-repeat',
              backgroundSize: `${meta.w * scaleX}px ${meta.h * scaleY}px`,
              backgroundPosition: `${-meta.cols[column] * scaleX}px ${
                -meta.rows[row] * scaleY
              }px`,
            }}
          />,
        );
      }
    }
  }

  return (
    <div
      ref={ref}
      aria-hidden="true"
      style={{
        position: 'absolute',
        inset: `${margin}px`,
        pointerEvents: 'none',
        zIndex,
        filter: tint ? `hue-rotate(${tint}deg)` : 'none',
      }}
    >
      {cells}
    </div>
  );
}
