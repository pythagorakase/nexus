/**
 * PCB-aesthetic border component for Cyberpunk theme.
 * Renders circuit-trace-style borders with corner pads and optional via decorations.
 */
import { useRef, useState, useEffect, useId } from 'react';

// Cyberpunk color palette (matches CyberpunkSplash)
const colors = {
  cyan: '#00f0ff',
  cyanDim: 'hsla(180, 100%, 75%, 0.3)',
};

type CornerStyle = 'chamfer' | 'fillet' | 'square';
type ViaPosition = 'corners' | 'midpoints' | 'both';

interface PcbBorderProps {
  children: React.ReactNode;

  // Trace styling
  traceWidth?: number;
  traceColor?: string;

  // Corner configuration
  cornerStyle?: CornerStyle;
  cornerSize?: number;

  // Pad styling
  padSize?: number;
  showPads?: boolean;

  // Via decorations
  showVias?: boolean;
  viaSize?: number;
  viaPositions?: ViaPosition;
  viaInset?: number;

  // Glow effect
  glowIntensity?: number;

  // Layout
  padding?: number | string;
  className?: string;
}

interface Point {
  x: number;
  y: number;
}

/**
 * Generate SVG path for a chamfered rectangle.
 * Corners are cut at 45° angles.
 */
function generateChamferedPath(w: number, h: number, c: number): string {
  // Clamp chamfer to half of smallest dimension
  const chamfer = Math.min(c, w / 2, h / 2);

  return [
    `M ${chamfer} 0`,           // Start after top-left chamfer
    `L ${w - chamfer} 0`,       // Top edge
    `L ${w} ${chamfer}`,        // Top-right chamfer
    `L ${w} ${h - chamfer}`,    // Right edge
    `L ${w - chamfer} ${h}`,    // Bottom-right chamfer
    `L ${chamfer} ${h}`,        // Bottom edge
    `L 0 ${h - chamfer}`,       // Bottom-left chamfer
    `L 0 ${chamfer}`,           // Left edge
    'Z',                         // Close path
  ].join(' ');
}

/**
 * Generate SVG path for a filleted (rounded) rectangle.
 * Uses quadratic Bézier curves at corners.
 */
function generateFilletedPath(w: number, h: number, r: number): string {
  // Clamp radius to half of smallest dimension
  const radius = Math.min(r, w / 2, h / 2);

  return [
    `M ${radius} 0`,                              // Start after top-left curve
    `L ${w - radius} 0`,                          // Top edge
    `Q ${w} 0 ${w} ${radius}`,                    // Top-right curve
    `L ${w} ${h - radius}`,                       // Right edge
    `Q ${w} ${h} ${w - radius} ${h}`,             // Bottom-right curve
    `L ${radius} ${h}`,                           // Bottom edge
    `Q 0 ${h} 0 ${h - radius}`,                   // Bottom-left curve
    `L 0 ${radius}`,                              // Left edge
    `Q 0 0 ${radius} 0`,                          // Top-left curve (closes to start)
    'Z',
  ].join(' ');
}

/**
 * Generate SVG path for a square rectangle (no corner treatment).
 */
function generateSquarePath(w: number, h: number): string {
  return `M 0 0 L ${w} 0 L ${w} ${h} L 0 ${h} Z`;
}

/**
 * Generate corner pad positions.
 */
function generatePadPositions(w: number, h: number, cornerSize: number, style: CornerStyle): Point[] {
  if (style === 'square') {
    // Pads at exact corners
    return [
      { x: 0, y: 0 },
      { x: w, y: 0 },
      { x: w, y: h },
      { x: 0, y: h },
    ];
  }

  // For chamfer/fillet, pads are at the corner cut points
  const c = Math.min(cornerSize, w / 2, h / 2);
  return [
    { x: c, y: 0 },           // Top-left (on top edge)
    { x: 0, y: c },           // Top-left (on left edge)
    { x: w - c, y: 0 },       // Top-right (on top edge)
    { x: w, y: c },           // Top-right (on right edge)
    { x: w, y: h - c },       // Bottom-right (on right edge)
    { x: w - c, y: h },       // Bottom-right (on bottom edge)
    { x: c, y: h },           // Bottom-left (on bottom edge)
    { x: 0, y: h - c },       // Bottom-left (on left edge)
  ];
}

/**
 * Generate via positions based on configuration.
 */
function generateViaPositions(
  w: number,
  h: number,
  cornerSize: number,
  positions: ViaPosition,
  inset: number
): Point[] {
  const vias: Point[] = [];
  const c = Math.min(cornerSize, w / 2, h / 2);

  // Corner vias (inset from the chamfer/fillet)
  if (positions === 'corners' || positions === 'both') {
    vias.push(
      { x: inset, y: inset },
      { x: w - inset, y: inset },
      { x: w - inset, y: h - inset },
      { x: inset, y: h - inset },
    );
  }

  // Midpoint vias (center of each edge)
  if (positions === 'midpoints' || positions === 'both') {
    vias.push(
      { x: w / 2, y: inset },       // Top center
      { x: w - inset, y: h / 2 },   // Right center
      { x: w / 2, y: h - inset },   // Bottom center
      { x: inset, y: h / 2 },       // Left center
    );
  }

  return vias;
}

export function PcbBorder({
  children,
  traceWidth = 2,
  traceColor = colors.cyan,
  cornerStyle = 'chamfer',
  cornerSize = 12,
  padSize = 6,
  showPads = true,
  showVias = false,
  viaSize = 4,
  viaPositions = 'corners',
  viaInset = 16,
  glowIntensity = 0.5,
  padding = 16,
  className = '',
}: PcbBorderProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const filterId = useId();

  // Track container size with ResizeObserver
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setSize({ width, height });
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Generate path based on corner style
  const path =
    cornerStyle === 'chamfer'
      ? generateChamferedPath(size.width, size.height, cornerSize)
      : cornerStyle === 'fillet'
        ? generateFilletedPath(size.width, size.height, cornerSize)
        : generateSquarePath(size.width, size.height);

  // Generate decoration positions
  const pads = showPads ? generatePadPositions(size.width, size.height, cornerSize, cornerStyle) : [];
  const vias = showVias ? generateViaPositions(size.width, size.height, cornerSize, viaPositions, viaInset) : [];

  // Don't render SVG until we have dimensions
  const hasSize = size.width > 0 && size.height > 0;

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        position: 'relative',
        padding: typeof padding === 'number' ? `${padding}px` : padding,
      }}
    >
      {hasSize && (
        <svg
          width={size.width}
          height={size.height}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            pointerEvents: 'none',
            overflow: 'visible',
          }}
        >
          {glowIntensity > 0 && (
            <defs>
              <filter id={filterId} x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation={2 * glowIntensity} result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
          )}

          {/* Main trace */}
          <path
            d={path}
            fill="none"
            stroke={traceColor}
            strokeWidth={traceWidth}
            filter={glowIntensity > 0 ? `url(#${filterId})` : undefined}
          />

          {/* Corner pads */}
          {pads.map((pos, i) => (
            <circle
              key={`pad-${i}`}
              cx={pos.x}
              cy={pos.y}
              r={padSize / 2}
              fill={traceColor}
              filter={glowIntensity > 0 ? `url(#${filterId})` : undefined}
            />
          ))}

          {/* Vias (hollow circles) */}
          {vias.map((pos, i) => (
            <circle
              key={`via-${i}`}
              cx={pos.x}
              cy={pos.y}
              r={viaSize / 2}
              fill="none"
              stroke={traceColor}
              strokeWidth={1}
              opacity={0.6}
            />
          ))}
        </svg>
      )}

      {children}
    </div>
  );
}

export default PcbBorder;
