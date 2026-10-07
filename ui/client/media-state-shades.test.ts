import { describe, expect, it } from "vitest";
import { mediaConditions } from "../scripts/state-surfaces/media.mjs";

const width = "(min-width: 640px) and (max-width: 759px)";
const rule = (prelude: string) => `@media ${prelude} { .key-row.optional { opacity: .35 } }`;

describe("media alternative exclusions", () => {
  it.each(["print", "(forced-colors: active)"])("keeps the width alternative beside %s", excluded => {
    const parentList = `media ${excluded}, ${width}`;
    const media = mediaConditions(rule(`${excluded}, ${width}`));
    expect(media.unsupported).toEqual([]);
    expect(media.excluded).toEqual([{ prelude: `media ${excluded}`, parentList, reason: expect.any(String) }]);
    expect(media.preludes).toContain(`media ${width}`);
    expect(media.preludes).not.toContain(parentList);
    const band = media.representatives.find(v => v.band === "w640-759");
    expect(band?.viewport).toEqual({ width: 759, height: 900 });
    expect(band?.satisfied).toEqual([`media ${width}`]);
    expect(media.variants.filter(v => v.band === "w640-759")).toEqual([
      expect.objectContaining({ viewport: { width: 759, height: 900 }, satisfied: [`media ${width}`] }),
    ]);
  });

  it("records print-only lists without extracting their widths", () => {
    const alternative = `print and ${width}`;
    const media = mediaConditions(rule(`print, ${alternative}`));
    expect(media.excluded.map(({ prelude, parentList }) => ({ prelude, parentList }))).toEqual([
      { prelude: "media print", parentList: `media print, ${alternative}` },
      { prelude: `media ${alternative}`, parentList: `media print, ${alternative}` },
    ]);
    expect(media.representatives).toEqual([
      expect.objectContaining({ band: "", viewport: { width: 1200, height: 900 }, satisfied: [] }),
    ]);
  });

  it("refuses unknown forced-colors values, preserving nested commas", () => {
    const excluded = "(forced-colors: nested(a, nested(b, c)))";
    const media = mediaConditions(rule(`${excluded}, ${width}`));
    expect(media.excluded).toEqual([]);
    expect(media.unsupported).toEqual([`media ${excluded}`]);
  });

  it("keeps each screen alternative and nested conjunction in the satisfied set", () => {
    const media = mediaConditions(`@media print, ${width} {
      @media (prefers-reduced-motion: reduce), (prefers-reduced-motion: no-preference) { .key-row.optional { opacity: .35 } }
    }`);
    const band = media.representatives.filter(v => v.band === "w640-759");
    expect(band).toHaveLength(2);
    for (const vector of band) {
      expect(vector.viewport.width).toBe(759);
      expect(vector.satisfied).toEqual([
        `media ${width}`, `media ${width} and (prefers-reduced-motion: ${vector.features["prefers-reduced-motion"]})`,
      ]);
    }
  });
});

// The shipped cuts and motion feature yield 27 renders before a new band.
const shipped = ["(max-width: 1280px)", "(max-width: 1100px)", "(max-width: 760px)",
  "(prefers-reduced-motion: reduce)", ...[640, 768, 1024, 1280, 1536].map(n => `(min-width: ${n}px)`)]
  .map(rule).join("\n");
const nested = (parent: string) => `@media ${parent} { ${rule(width)} }`;

describe("screen / forced-colors none evaluator", () => {
  it("keeps Astra's nested not print band and strips its true parent", () => {
    const media = mediaConditions(shipped + nested("not print"));
    expect(media.unsupported).toEqual([]);
    expect(media.excluded).toEqual([]);
    expect(media.variants).toHaveLength(30);
    expect(media.variants.some(v => v.viewport.width === 759)).toBe(true);
    expect(media.stripped).toContainEqual(expect.objectContaining({ term: "not print", parentList: "media not print" }));
  });

  it("records not screen and its skipped nested query without a band", () => {
    const media = mediaConditions(shipped + nested("not screen"));
    expect(media.unsupported).toEqual([]);
    expect(media.variants).toHaveLength(27);
    expect(media.variants.some(v => v.viewport.width === 759)).toBe(false);
    expect(media.excluded).toEqual([expect.objectContaining({
      prelude: "media not screen", parentList: "media not screen", skipped: [`media ${width}`],
    })]);
  });

  it.each(["screen", "all", "only screen", "only all", "not print"])("strips true type %s", type => {
    const media = mediaConditions(rule(type));
    expect(media.unsupported).toEqual([]);
    expect(media.excluded).toEqual([]);
    expect(media.stripped).toContainEqual(expect.objectContaining({ term: type }));
  });

  it.each(["print", "only print", "not screen", "not all", "screen and (forced-colors: active)", "not (forced-colors: none)"])("records false alternative %s", type => {
    const media = mediaConditions(rule(type));
    expect(media.unsupported).toEqual([]);
    expect(media.excluded).toEqual([expect.objectContaining({ prelude: `media ${type}`, parentList: `media ${type}`, reason: expect.any(String) })]);
  });

  it("strips forced-colors none and keeps the 759 band", () => {
    const media = mediaConditions(shipped + rule("(forced-colors: none) and (max-width: 759px)"));
    expect(media.unsupported).toEqual([]);
    expect(media.excluded).toEqual([]);
    expect(media.variants).toHaveLength(30);
    expect(media.variants.some(v => v.viewport.width === 759)).toBe(true);
    expect(media.stripped).toContainEqual(expect.objectContaining({ term: "(forced-colors: none)" }));
  });

  it("strips not forced-colors active without adding a band", () => {
    const media = mediaConditions(shipped + rule("not (forced-colors: active)"));
    expect(media.unsupported).toEqual([]);
    expect(media.excluded).toEqual([]);
    expect(media.variants).toHaveLength(27);
    expect(media.stripped).toContainEqual(expect.objectContaining({ term: "not (forced-colors: active)" }));
  });

  it("retains screen width beside print with 30 renders", () => {
    const media = mediaConditions(shipped + rule("print, screen and (max-width: 759px)"));
    expect(media.unsupported).toEqual([]);
    expect(media.excluded).toEqual([expect.objectContaining({ prelude: "media print", parentList: "media print, screen and (max-width: 759px)" })]);
    expect(media.variants).toHaveLength(30);
    expect(media.variants.some(v => v.viewport.width === 759)).toBe(true);
  });

  it.each([
    "not print and (min-width: 640px)", "not (min-width: 640px)",
    "not (forced-colors: active) and (max-width: 759px)",
    "screen or (max-width: 759px)", "speech", "only speech", "unknown",
    "(400px <= width <= 700px)", "(width >= 640px)", "(resolution: 2dppx)",
    "(orientation: portrait)", "(aspect-ratio: 4/3)", "(prefers-contrast: more)",
    "(display-mode: standalone)", "(color-gamut: srgb)", "(update: fast)",
    "(scripting: enabled)", "(hover: unknown)", "(any-hover: unknown)",
    "(pointer: unknown)", "(any-pointer: unknown)", "(forced-colors: unknown)",
    "print and (orientation: portrait)", "(unknown: value)",
  ])("refuses unmodelled prelude %s by name", prelude => {
    const media = mediaConditions(nested(prelude));
    expect(media.unsupported).toEqual([`media ${prelude}`]);
    expect(media.preludes).not.toContain(`media ${width}`);
    expect(media.excluded).toEqual([]);
  });

  it("models every allowlisted discrete value and height prefixes", () => {
    for (const [feature, values] of Object.entries({
      "prefers-reduced-motion": ["reduce", "no-preference"], "prefers-color-scheme": ["dark", "light"],
      hover: ["hover", "none"], "any-hover": ["hover", "none"],
      pointer: ["fine", "coarse", "none"], "any-pointer": ["fine", "coarse", "none"],
    })) for (const value of values) {
      const media = mediaConditions(rule(`(${feature}: ${value})`));
      expect(media.unsupported).toEqual([]);
      expect(media.representatives.some(v => v.features[feature] === value)).toBe(true);
    }
    const media = mediaConditions(rule("(min-height: 640px) and (max-height: 759px)"));
    expect(media.unsupported).toEqual([]);
    expect(media.representatives.some(v => v.viewport.height === 759)).toBe(true);
  });
});

// Codex, GPT-6.
