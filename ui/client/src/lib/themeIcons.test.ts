import { beforeEach, describe, expect, it } from "vitest";

import { ICON_VERSION, applyThemeIcons, themeIconPath } from "./themeIcons";

describe("themeIconPath", () => {
  it("builds per-theme cache-busted icon paths", () => {
    expect(themeIconPath("veil", 32)).toBe(
      `/icons/veil/icon-32.png?v=${ICON_VERSION}`,
    );
    expect(themeIconPath("gilded", 512)).toBe(
      `/icons/gilded/icon-512.png?v=${ICON_VERSION}`,
    );
    expect(themeIconPath("vector", 180)).toBe(
      `/icons/vector/icon-180.png?v=${ICON_VERSION}`,
    );
  });
});

describe("applyThemeIcons", () => {
  beforeEach(() => {
    document.head
      .querySelectorAll('link[rel="icon"], link[rel="apple-touch-icon"]')
      .forEach((link) => link.remove());
  });

  const href = (selector: string) =>
    document.head.querySelector<HTMLLinkElement>(selector)?.getAttribute("href");

  it("creates favicon and apple-touch links when none exist", () => {
    applyThemeIcons("veil");

    expect(href('link[rel="icon"][sizes="32x32"]')).toBe(
      themeIconPath("veil", 32),
    );
    expect(href('link[rel="icon"][sizes="16x16"]')).toBe(
      themeIconPath("veil", 16),
    );
    expect(href('link[rel="apple-touch-icon"]')).toBe(
      themeIconPath("veil", 180),
    );
  });

  it("retargets existing links on theme change without duplicating them", () => {
    applyThemeIcons("veil");
    applyThemeIcons("vector");

    expect(href('link[rel="icon"][sizes="32x32"]')).toBe(
      themeIconPath("vector", 32),
    );
    expect(href('link[rel="icon"][sizes="16x16"]')).toBe(
      themeIconPath("vector", 16),
    );
    expect(href('link[rel="apple-touch-icon"]')).toBe(
      themeIconPath("vector", 180),
    );
    expect(document.head.querySelectorAll('link[rel="icon"]')).toHaveLength(2);
    expect(
      document.head.querySelectorAll('link[rel="apple-touch-icon"]'),
    ).toHaveLength(1);
  });
});
