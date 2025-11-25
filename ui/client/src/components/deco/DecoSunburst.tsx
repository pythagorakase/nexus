import { cn } from "@/lib/utils";

interface DecoSunburstProps {
  size?: number;
  rays?: number;
  spread?: number;
  opacity?: number;
  className?: string;
}

/**
 * Radiating sunburst decoration - classic Art Deco motif.
 * Every 3rd ray is accented (thicker, brighter).
 */
export function DecoSunburst({
  size = 200,
  rays = 24,
  spread = 180,
  opacity = 0.15,
  className
}: DecoSunburstProps) {
  const angleStep = spread / (rays - 1);
  const startAngle = -spread / 2 - 90;
  const isHalfCircle = spread <= 180;
  const height = isHalfCircle ? size * 0.5 : size;
  const centerY = isHalfCircle ? size * 0.5 : size / 2;

  const rayElements = Array.from({ length: rays }, (_, i) => {
    const angle = (startAngle + i * angleStep) * Math.PI / 180;
    const x2 = size / 2 + Math.cos(angle) * size;
    const y2 = centerY + Math.sin(angle) * size;
    const isAccent = i % 3 === 0;

    return (
      <line
        key={i}
        x1={size / 2}
        y1={centerY}
        x2={x2}
        y2={y2}
        className={isAccent ? "stroke-primary" : "stroke-muted-foreground"}
        strokeWidth={isAccent ? 2 : 1}
        opacity={isAccent ? opacity * 1.5 : opacity}
      />
    );
  });

  return (
    <svg
      width={size}
      height={height}
      viewBox={`0 0 ${size} ${height}`}
      className={cn("overflow-visible pointer-events-none", className)}
    >
      {rayElements}
      {/* Center circle */}
      <circle
        cx={size / 2}
        cy={centerY}
        r={6}
        fill="none"
        className="stroke-primary"
        strokeWidth={2}
        opacity={opacity * 2}
      />
    </svg>
  );
}

interface CornerSunburstProps {
  position: 'tl' | 'tr' | 'bl' | 'br';
  size?: number;
  rays?: number;
  opacity?: number;
  className?: string;
}

/**
 * Corner-positioned sunburst - 90-degree spread radiating from corner.
 */
export function CornerSunburst({
  position,
  size = 100,
  rays = 12,
  opacity = 0.12,
  className
}: CornerSunburstProps) {
  const configs = {
    tl: { startAngle: 0, anchor: { x: 0, y: 0 } },
    tr: { startAngle: 90, anchor: { x: size, y: 0 } },
    br: { startAngle: 180, anchor: { x: size, y: size } },
    bl: { startAngle: 270, anchor: { x: 0, y: size } },
  };

  const { startAngle, anchor } = configs[position];
  const spread = 90;
  const angleStep = spread / (rays - 1);

  const rayElements = Array.from({ length: rays }, (_, i) => {
    const angle = (startAngle + i * angleStep) * Math.PI / 180;
    const x2 = anchor.x + Math.cos(angle) * size * 1.5;
    const y2 = anchor.y + Math.sin(angle) * size * 1.5;
    const isAccent = i % 3 === 0;

    return (
      <line
        key={i}
        x1={anchor.x}
        y1={anchor.y}
        x2={x2}
        y2={y2}
        className={isAccent ? "stroke-primary" : "stroke-muted-foreground"}
        strokeWidth={isAccent ? 1.5 : 0.75}
        opacity={isAccent ? opacity * 1.5 : opacity}
      />
    );
  });

  const positionStyles = {
    tl: { top: 0, left: 0 },
    tr: { top: 0, right: 0 },
    bl: { bottom: 0, left: 0 },
    br: { bottom: 0, right: 0 },
  };

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={cn("absolute overflow-hidden pointer-events-none", className)}
      style={positionStyles[position]}
    >
      {rayElements}
    </svg>
  );
}
