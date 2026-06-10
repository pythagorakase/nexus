/**
 * TypewriterText - character-by-character reveal for incoming narrative.
 *
 * The signature interaction of the NEXUS IRIS design system: 30-50 ms/char
 * (configurable via `[ui] typewriter_ms_per_char` in nexus.toml, surfaced
 * through GET /api/settings). Chunks loaded from history render instantly;
 * only freshly generated text animates (the parent decides via `animate`).
 */
import { useEffect, useRef, useState } from "react";

interface TypewriterTextProps {
  text: string;
  /** Milliseconds per character. */
  msPerChar: number;
  /** When false, render the full text immediately. */
  animate: boolean;
  className?: string;
  onDone?: () => void;
}

export function TypewriterText({
  text,
  msPerChar,
  animate,
  className,
  onDone,
}: TypewriterTextProps) {
  const [visibleChars, setVisibleChars] = useState(animate ? 0 : text.length);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (!animate) {
      setVisibleChars(text.length);
      return;
    }

    setVisibleChars(0);
    let index = 0;
    const interval = window.setInterval(() => {
      index += 1;
      setVisibleChars(index);
      if (index >= text.length) {
        window.clearInterval(interval);
        onDoneRef.current?.();
      }
    }, msPerChar);

    return () => window.clearInterval(interval);
  }, [text, animate, msPerChar]);

  const revealing = animate && visibleChars < text.length;

  return (
    <span className={className}>
      {text.slice(0, visibleChars)}
      {revealing && <span className="type-caret" aria-hidden="true" />}
    </span>
  );
}
