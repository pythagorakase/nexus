/**
 * Per-theme app icon wiring.
 *
 * One circuit-tree mark, three liveries (design handoff, brand-favicons
 * preview): Veil magenta tree / violet river, Gilded amber tree / teal
 * river, Vector blue tree / green river. The favicon and apple-touch link
 * tags follow the active theme at runtime; the PWA manifest icons are
 * bake-time and stay on the default theme (Veil).
 */
import type { ThemeId } from "@/types/settings";

export type ThemeIconSize = 16 | 32 | 180 | 192 | 512;

/** Cache-bust token for the icon set; bump when the PNGs change. */
export const ICON_VERSION = "20260612";

export function themeIconPath(theme: ThemeId, size: ThemeIconSize): string {
  return `/icons/${theme}/icon-${size}.png?v=${ICON_VERSION}`;
}

const HEAD_LINKS: Array<{ rel: string; sizes?: string; size: ThemeIconSize }> = [
  { rel: "icon", sizes: "32x32", size: 32 },
  { rel: "icon", sizes: "16x16", size: 16 },
  { rel: "apple-touch-icon", size: 180 },
];

/** Point the favicon + apple-touch link tags at the active theme's set. */
export function applyThemeIcons(theme: ThemeId): void {
  for (const { rel, sizes, size } of HEAD_LINKS) {
    const selector = sizes
      ? `link[rel="${rel}"][sizes="${sizes}"]`
      : `link[rel="${rel}"]`;
    let link = document.head.querySelector<HTMLLinkElement>(selector);
    if (!link) {
      link = document.createElement("link");
      link.rel = rel;
      if (sizes) link.setAttribute("sizes", sizes);
      link.type = "image/png";
      document.head.appendChild(link);
    }
    link.href = themeIconPath(theme, size);
  }
}
