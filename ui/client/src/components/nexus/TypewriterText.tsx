/**
 * TypewriterText - character-by-character reveal for incoming narrative.
 *
 * The signature interaction of the NEXUS IRIS design system: 30-50 ms/char
 * (configurable via `[ui] typewriter_ms_per_char` in nexus.toml, surfaced
 * through GET /api/settings). Chunks loaded from history render instantly;
 * only freshly generated text animates (the parent decides via `animate`).
 *
 * Markdown mode (`markdown`) renders each frame's visible slice through
 * ProseMarkdown instead of as plain text, so emphasis and headings appear
 * correctly formatted mid-reveal and the finished frame is identical to the
 * committed-chunk rendering - no end-of-reveal swap, no layout jump. The
 * caret rides the reveal frontier inside the rendered markdown. Block
 * content cannot live inside a span, so markdown mode ignores `className`
 * and returns the bare block stream (wrap it in a styled container).
 */
import { useEffect, useRef, useState } from "react";
import { ProseMarkdown } from "./ProseMarkdown";

interface TypewriterTextProps {
  text: string;
  /** Milliseconds per character. */
  msPerChar: number;
  /** When false, render the full text immediately. */
  animate: boolean;
  /** Render the visible slice as narrative markdown (block content). */
  markdown?: boolean;
  className?: string;
  onDone?: () => void;
}

export function TypewriterText({
  text,
  msPerChar,
  animate,
  markdown = false,
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

  if (markdown) {
    return (
      <ProseMarkdown text={text.slice(0, visibleChars)} revealing={revealing} />
    );
  }

  return (
    <span className={className}>
      {text.slice(0, visibleChars)}
      {revealing && <span className="type-caret" aria-hidden="true" />}
    </span>
  );
}
