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

describe("normalized media grammar and exhaustive at-rule dispatch", () => {
  it.each([
    "@MEDIA (min-width: 640px) and (max-width: 759px)",
    "@Media SCREEN AND (MIN-WIDTH: 640PX) AND (MAX-WIDTH: 759PX)",
    "@media /* note */ (min-width:640px)and(max-width:759px)",
    "@media (min-width:/* note, (and) */640px)and(max-width:759px)",
    "@media \n  screen  AND  ( MIN-WIDTH : 640PX ) AND ( MAX-WIDTH : 759PX )",
  ])("measures the 759 band through PostCSS for %s", header => {
    const media = mediaConditions(shipped + `${header} { .key-row.optional { opacity: .35 } }`);
    expect(media.unsupported).toEqual([]);
    expect(media.variants).toHaveLength(30);
    expect(media.representatives.find(v => v.band === "w640-759")?.viewport.width).toBe(759);
  });

  it("parses an at-rule without whitespace before its feature", () => {
    const media = mediaConditions("@media(min-width:640px) { .key-row.optional { opacity: .35 } }");
    expect(media.unsupported).toEqual([]);
    expect(media.representatives.find(v => v.band === "w640+")?.satisfied).toEqual(["media (min-width: 640px)"]);
  });

  it.each(["759.5px", "6.4e2px", "48em", "+759px", "-759px", ".5px", "9007199254740993px"])(
    "refuses the numeric grammar outside unsigned integer px: %s", value => {
      expect(mediaConditions(rule(`(max-width: ${value})`)).unsupported).toEqual([`media (max-width: ${value})`]);
    },
  );

  it.each([
    [String.raw`@\6d edia (max-width: 759px)`, String.raw`\6d edia (max-width: 759px)`],
    [String.raw`@med\69 a (max-width: 759px)`, String.raw`med \69 a (max-width: 759px)`],
    [String.raw`@media (max-width: 759p\78)`, String.raw`media (max-width: 759p\78)`],
    [String.raw`@supports (display: g\72 id)`, String.raw`supports (display: g\72 id)`],
    ["@CONTAINER (min-width: 400px)", "container (min-width: 400px)"],
    ["@frobnicate (max-width: 759px)", "frobnicate (max-width: 759px)"],
  ])("refuses %s by name", (header, name) => {
    expect(mediaConditions(`${header} { .key-row.optional { opacity: .35 } }`).unsupported).toEqual([name]);
  });

  it("refuses surviving imports by name", () => {
    expect(mediaConditions("@import url(extra.css) screen and (max-width: 759px);").unsupported)
      .toEqual(["import url(extra.css) screen and (max-width: 759px)"]);
  });

  it.each(["supports (display: grid)", "layer base"])("walks media nested inside @%s", parent => {
    const media = mediaConditions(shipped + `@${parent} { ${rule("(max-width: 759px)")} }`);
    expect(media.unsupported).toEqual([]);
    expect(media.variants).toHaveLength(30);
    expect(media.variants.some(v => v.viewport.width === 759)).toBe(true);
  });

  it.each([
    '@font-face { font-family: x; src: url(x.woff2); }',
    '@keyframes x { from { opacity: 0; } to { opacity: 1; } }',
    '@property --x { syntax: "<color>"; inherits: false; initial-value: red; }',
    '@scope (.x) {}', '@page {}', '@starting-style {}', '@charset "utf-8";',
    '@namespace svg url(http://www.w3.org/2000/svg);', '@font-feature-values x {}',
    '@counter-style x {}', '@view-transition {}', '@SUPPORTS (display: grid) {}', '@LAYER base {}',
  ])("ignores the non-media at-rule %s", css => {
    const media = mediaConditions(shipped + css);
    expect(media.unsupported).toEqual([]);
    expect(media.variants).toHaveLength(27);
  });

  it("names unknown children even inside excluded media", () => {
    const media = mediaConditions("@media print { @frobnicate x { } }");
    expect(media.unsupported).toEqual(["frobnicate x"]);
  });
});

// Codex, GPT-6.
