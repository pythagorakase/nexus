import { describe, expect, it } from "vitest";
import type { OutlineRow } from "@/lib/narrative-nav";
import { outlineSceneLabel } from "./RightLedger";

const row = (overrides: Partial<OutlineRow>): OutlineRow => ({
  id: 91_337,
  season: 2,
  episode: 4,
  scene: 7,
  slug: null,
  ...overrides,
});

describe("outlineSceneLabel", () => {
  it("prefers the narrative slug", () => {
    expect(outlineSceneLabel(row({ slug: "S02E04_007" }), 3)).toBe(
      "S02E04_007",
    );
  });

  it("falls back to scene metadata rather than the raw chunk id", () => {
    expect(outlineSceneLabel(row({}), 3)).toBe("Scene 7");
  });

  it("uses episode order when legacy metadata has no scene", () => {
    expect(outlineSceneLabel(row({ scene: null }), 3)).toBe("Scene 3");
  });
});
