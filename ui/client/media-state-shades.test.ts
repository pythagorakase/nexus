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

  it("preserves nested parentheses and their commas as one excluded feature", () => {
    const excluded = "(forced-colors: nested(a, nested(b, c)))";
    const media = mediaConditions(rule(`${excluded}, ${width}`));
    expect(media.excluded).toEqual([
      { prelude: `media ${excluded}`, parentList: `media ${excluded}, ${width}`, reason: expect.any(String) },
    ]);
    expect(media.unsupported).toEqual([]);
    expect(media.representatives.find(v => v.band === "w640-759")?.satisfied).toEqual([`media ${width}`]);
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
        `media ${width}`, `media (prefers-reduced-motion: ${vector.features["prefers-reduced-motion"]})`,
      ]);
    }
  });
});

// Codex, GPT-6.
