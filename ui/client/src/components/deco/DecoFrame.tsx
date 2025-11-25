import { cn } from "@/lib/utils";
import { useTheme } from "@/contexts/ThemeContext";
import { DecoCorner } from "./DecoCorner";

interface DecoFrameProps {
  children: React.ReactNode;
  className?: string;
  cornerSize?: number;
  showCorners?: boolean;
}

/**
 * Wrapper component that adds Art Deco corner decorations.
 * Only renders decorations in gilded theme.
 */
export function DecoFrame({
  children,
  className,
  cornerSize = 20,
  showCorners = true
}: DecoFrameProps) {
  const { isGilded } = useTheme();

  return (
    <div className={cn("relative", className)}>
      {isGilded && showCorners && (
        <>
          <DecoCorner position="tl" size={cornerSize} />
          <DecoCorner position="tr" size={cornerSize} />
          <DecoCorner position="bl" size={cornerSize} />
          <DecoCorner position="br" size={cornerSize} />
        </>
      )}
      {children}
    </div>
  );
}
