/**
 * Selectable fonts per theme per slot (NEXUS IRIS keeper matrix + approved
 * alternates from the design system's FONT_CATALOG). This lives client-side
 * because the option set is bounded by the fonts actually loaded by the
 * bundle (@font-face / Google Fonts) - it is not runtime configuration.
 * The *persisted choices* live in nexus.toml [ui.fonts.*].
 *
 * The display slot is the marquee font - reserved for the NEXUS wordmark
 * (the design system's marquee rule) and locked to a single option.
 */
import type { FontSlotId, ThemeId } from "@/types/settings";

export interface FontOption {
  id: string;
  label: string;
  note: string;
  locked?: boolean;
}

export const FONT_CATALOG: Record<ThemeId, Record<FontSlotId, FontOption[]>> = {
  veil: {
    body: [
      { id: "Spectral", label: "Spectral", note: "default · serif" },
      { id: "Cormorant Garamond", label: "Cormorant Garamond", note: "serif · alt" },
    ],
    menu: [{ id: "Cinzel", label: "Cinzel", note: "default · small-caps" }],
    display: [
      { id: "Megrim", label: "Megrim", note: "marquee · locked", locked: true },
    ],
  },
  gilded: {
    body: [
      { id: "Cormorant Garamond", label: "Cormorant Garamond", note: "default · serif" },
    ],
    menu: [{ id: "Space Mono", label: "Space Mono", note: "default · mono" }],
    display: [
      { id: "Monoton", label: "Monoton", note: "marquee · locked", locked: true },
    ],
  },
  vector: {
    body: [{ id: "Rajdhani", label: "Rajdhani", note: "default · sans" }],
    menu: [
      { id: "Source Code Pro", label: "Source Code Pro", note: "default · mono" },
      { id: "Monaco", label: "Monaco", note: "mono · system" },
      { id: "Consolas", label: "Consolas", note: "mono · system" },
    ],
    display: [
      { id: "Sixtyfour", label: "Sixtyfour", note: "marquee · locked", locked: true },
    ],
  },
};
