import { cn } from "@/lib/utils";

interface DecoCornerProps {
  position: 'tl' | 'tr' | 'bl' | 'br';
  size?: number;
  className?: string;
}

/**
 * Stepped corner decoration for Art Deco panels.
 * Renders an L-shaped corner with layered brass fills.
 */
export function DecoCorner({ position, size = 20, className }: DecoCornerProps) {
  const rotations = { tl: 0, tr: 90, br: 180, bl: 270 };
  const positions = {
    tl: { top: -1, left: -1 },
    tr: { top: -1, right: -1 },
    bl: { bottom: -1, left: -1 },
    br: { bottom: -1, right: -1 },
  };

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      className={cn("absolute pointer-events-none", className)}
      style={{
        ...positions[position],
        transform: `rotate(${rotations[position]}deg)`,
      }}
    >
      {/* Outer L-shape */}
      <path
        d="M0 0 L20 0 L20 3 L3 3 L3 20 L0 20 Z"
        className="fill-primary/70"
      />
      {/* Inner stepped detail */}
      <path
        d="M6 0 L10 0 L10 10 L0 10 L0 6 L6 6 Z"
        className="fill-primary/35"
      />
    </svg>
  );
}
