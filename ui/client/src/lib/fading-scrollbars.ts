/**
 * Fading scrollbars - the JS half of the global overlay-scrollbar treatment.
 *
 * The CSS half lives in index.css ("FADING SCROLLBARS"): every scroll
 * surface gets a custom ::-webkit-scrollbar whose thumb alpha is driven by
 * the registered custom property `--scrollbar-alpha` (0 at rest). CSS cannot
 * observe scrolling, so this module listens for scroll events in the capture
 * phase (scroll does not bubble, but capture still visits ancestors) and
 * toggles `.scrollbar-active` on the scrolled element; the property
 * transition on the element produces the fade in both directions.
 *
 * The idle delay is a stylesheet tunable (`--scrollbar-idle-ms` on :root)
 * so all scrollbar tuning lives in one CSS block. A missing or malformed
 * value throws - fail loud, no silent default.
 */

/** Class toggled on actively scrolling elements (styled in index.css). */
export const SCROLLBAR_ACTIVE_CLASS = "scrollbar-active";

/** Read the idle delay from the stylesheet; loud failure if absent. */
export function readScrollbarIdleMs(doc: Document): number {
  // Inline value first (lets tests pin it without a stylesheet), then the
  // cascaded :root value from index.css.
  const raw =
    doc.documentElement.style.getPropertyValue("--scrollbar-idle-ms") ||
    doc.defaultView
      ?.getComputedStyle(doc.documentElement)
      .getPropertyValue("--scrollbar-idle-ms");
  const parsed = Number.parseFloat(raw ?? "");
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(
      `--scrollbar-idle-ms missing or invalid on :root (got ${JSON.stringify(raw)})`,
    );
  }
  return parsed;
}

/**
 * Install the global scroll listener. Returns an uninstall function
 * (used by tests; the app installs once for its lifetime in main.tsx).
 */
export function installFadingScrollbars(doc: Document = document): () => void {
  const idleMs = readScrollbarIdleMs(doc);
  const timers = new Map<Element, number>();

  const onScroll = (event: Event) => {
    // A document-level scroll targets the document itself; the scrollbar
    // belongs to the root element.
    const target =
      event.target instanceof Element
        ? event.target
        : doc.scrollingElement ?? doc.documentElement;
    if (!target) return;

    target.classList.add(SCROLLBAR_ACTIVE_CLASS);
    const pending = timers.get(target);
    if (pending !== undefined) window.clearTimeout(pending);
    timers.set(
      target,
      window.setTimeout(() => {
        target.classList.remove(SCROLLBAR_ACTIVE_CLASS);
        timers.delete(target);
      }, idleMs),
    );
  };

  doc.addEventListener("scroll", onScroll, { capture: true, passive: true });
  return () => {
    doc.removeEventListener("scroll", onScroll, { capture: true });
    timers.forEach((id) => window.clearTimeout(id));
    timers.clear();
  };
}
