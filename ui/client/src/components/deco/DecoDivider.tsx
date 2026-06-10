import { cn } from "@/lib/utils";
import { useTheme, type Theme } from "@/contexts/ThemeContext";

interface DecoDividerProps {
  className?: string;
  variant?: 'diamond' | 'chevron' | 'line' | 'glyph';
}

/** Theme-aware center glyphs for the `glyph` variant (NEXUS IRIS spec). */
const THEME_GLYPHS: Record<Theme, string> = {
  veil: '⟡',   // ⟡ white concave-sided diamond
  gilded: '◆', // ◆ black diamond
  vector: '▮', // ▮ black vertical rectangle
};

/**
 * Decorative horizontal separator with Art Deco motifs.
 *
 * The `glyph` variant centers the active theme's signature character
 * (Veil ⟡, Gilded ◆, Vector ▮) between the gradient rules. The default
 * stays `diamond` so callers that omit `variant` are visually unchanged.
 *
 * Trade-off: `useTheme()` runs unconditionally (rules of hooks), so every
 * DecoDivider subscribes to ThemeContext even when variant !== 'glyph'.
 * Theme switches are rare user actions; the extra re-render is negligible.
 */
export function DecoDivider({ className, variant = 'diamond' }: DecoDividerProps) {
  const { theme } = useTheme();

  return (
    <div className={cn("w-full flex items-center justify-center gap-3 py-3", className)}>
      <div className="flex-1 h-px bg-gradient-to-r from-transparent via-muted-foreground/30 to-muted-foreground/50" />

      {variant === 'glyph' && (
        <span
          aria-hidden="true"
          className="text-primary/60 flex-shrink-0 text-[13px] leading-none"
        >
          {THEME_GLYPHS[theme]}
        </span>
      )}

      {variant === 'diamond' && (
        <svg width="24" height="12" viewBox="0 0 24 12" className="text-primary flex-shrink-0">
          <path
            d="M0 6 L6 0 L12 6 L18 0 L24 6 L18 12 L12 6 L6 12 Z"
            fill="currentColor"
            opacity="0.6"
          />
        </svg>
      )}

      {variant === 'chevron' && (
        <svg width="32" height="8" viewBox="0 0 32 8" className="text-primary flex-shrink-0">
          <path
            d="M0 4 L8 0 L16 4 L24 0 L32 4 L24 8 L16 4 L8 8 Z"
            fill="currentColor"
            opacity="0.5"
          />
        </svg>
      )}

      {variant === 'line' && (
        <div className="w-8 h-0.5 bg-primary/50 flex-shrink-0" />
      )}

      <div className="flex-1 h-px bg-gradient-to-r from-muted-foreground/50 via-muted-foreground/30 to-transparent" />
    </div>
  );
}
