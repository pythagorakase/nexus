import { useEffect, useState } from "react";

export const NARROW_SHELL_QUERY = "(max-width: 760px)";

/** Keep shell DOM order aligned with its narrow-width CSS layout. */
export function useNarrowShell(): boolean {
  const [narrow, setNarrow] = useState(
    () => window.matchMedia(NARROW_SHELL_QUERY).matches,
  );
  useEffect(() => {
    const media = window.matchMedia(NARROW_SHELL_QUERY);
    const changed = (event: MediaQueryListEvent) => setNarrow(event.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  return narrow;
}
