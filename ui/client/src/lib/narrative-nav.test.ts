/**
 * narrative-nav tests - the reader's ladder model.
 *
 * Outline fixtures mirror the real corpora: the slot-1 legacy corpus
 * (contiguous ids, no pending chunk, scene 1:1 with chunk) and the slot-5
 * modern corpus (pending incubator chunk at the frontier). Ids are sparse
 * in places to prove the logic never assumes id arithmetic.
 */
import { describe, expect, it } from "vitest";
import {
  buildOutlineTree,
  freeformPresentation,
  isLiveRow,
  resolveReaderNav,
  type OutlineRow,
} from "./narrative-nav";

const row = (
  id: number,
  season: number,
  episode: number,
  scene: number,
): OutlineRow => ({
  id,
  season,
  episode,
  scene,
  slug: `S${String(season).padStart(2, "0")}E${String(episode).padStart(2, "0")}_${String(scene).padStart(3, "0")}`,
});

describe("buildOutlineTree", () => {
  it("groups rows into season -> episode -> chunk preserving story order", () => {
    const rows = [
      row(1, 1, 1, 1),
      row(2, 1, 1, 2),
      row(3, 1, 2, 1),
      row(7, 2, 1, 1),
    ];
    const tree = buildOutlineTree(rows);
    expect(tree.map((s) => s.season)).toEqual([1, 2]);
    expect(tree[0].episodes.map((e) => e.episode)).toEqual([1, 2]);
    expect(tree[0].episodes[0].chunks.map((c) => c.id)).toEqual([1, 2]);
    expect(tree[1].episodes[0].chunks.map((c) => c.id)).toEqual([7]);
  });

  it("folds null season/episode into 0 (prologue convention)", () => {
    const tree = buildOutlineTree([
      { id: 1, season: null, episode: null, scene: null, slug: null },
    ]);
    expect(tree).toHaveLength(1);
    expect(tree[0].season).toBe(0);
    expect(tree[0].episodes[0].episode).toBe(0);
  });

  it("returns an empty tree for an empty outline", () => {
    expect(buildOutlineTree([])).toEqual([]);
  });
});

describe("resolveReaderNav - live frontier", () => {
  const ids = [1, 2, 5, 9];

  it("never has a forward step at the frontier", () => {
    expect(
      resolveReaderNav({ readingChunkId: null, outlineIds: ids, hasPending: false })
        .forward,
    ).toBeNull();
    expect(
      resolveReaderNav({ readingChunkId: null, outlineIds: ids, hasPending: true })
        .forward,
    ).toBeNull();
  });

  it("steps back onto the latest committed chunk when a pending chunk exists", () => {
    const nav = resolveReaderNav({
      readingChunkId: null,
      outlineIds: ids,
      hasPending: true,
    });
    expect(nav.back).toBe(9);
  });

  it("steps back past the latest chunk when nothing is pending (it is already on screen)", () => {
    const nav = resolveReaderNav({
      readingChunkId: null,
      outlineIds: ids,
      hasPending: false,
    });
    expect(nav.back).toBe(5);
  });

  it("disables back on a single-chunk story with nothing pending", () => {
    const nav = resolveReaderNav({
      readingChunkId: null,
      outlineIds: [1],
      hasPending: false,
    });
    expect(nav).toEqual({ back: null, forward: null });
  });

  it("disables both controls with no committed chunks (bootstrap)", () => {
    expect(
      resolveReaderNav({ readingChunkId: null, outlineIds: [], hasPending: false }),
    ).toEqual({ back: null, forward: null });
  });
});

describe("resolveReaderNav - historical reading", () => {
  const ids = [1, 2, 5, 9];

  it("disables back at the very first chunk", () => {
    const nav = resolveReaderNav({
      readingChunkId: 1,
      outlineIds: ids,
      hasPending: false,
    });
    expect(nav.back).toBeNull();
    expect(nav.forward).toBe(2);
  });

  it("steps through sparse ids without arithmetic assumptions", () => {
    const nav = resolveReaderNav({
      readingChunkId: 2,
      outlineIds: ids,
      hasPending: false,
    });
    expect(nav.back).toBe(1);
    expect(nav.forward).toBe(5);
  });

  it("forwards to live when the next chunk is the frontier (no pending)", () => {
    const nav = resolveReaderNav({
      readingChunkId: 5,
      outlineIds: ids,
      hasPending: false,
    });
    expect(nav.forward).toBe("live");
  });

  it("forwards to the latest chunk as history when a pending chunk holds the frontier", () => {
    const nav = resolveReaderNav({
      readingChunkId: 5,
      outlineIds: ids,
      hasPending: true,
    });
    expect(nav.forward).toBe(9);
  });

  it("forwards from the latest committed chunk to live", () => {
    const nav = resolveReaderNav({
      readingChunkId: 9,
      outlineIds: ids,
      hasPending: true,
    });
    expect(nav.back).toBe(5);
    expect(nav.forward).toBe("live");
  });

  it("is symmetric: back then forward returns to the start", () => {
    // From live (pending): back -> 9, forward from 9 -> live.
    const down = resolveReaderNav({
      readingChunkId: null,
      outlineIds: ids,
      hasPending: true,
    });
    expect(down.back).toBe(9);
    const up = resolveReaderNav({
      readingChunkId: 9,
      outlineIds: ids,
      hasPending: true,
    });
    expect(up.forward).toBe("live");

    // From live (no pending): back -> 5, forward from 5 -> live.
    const down2 = resolveReaderNav({
      readingChunkId: null,
      outlineIds: ids,
      hasPending: false,
    });
    expect(down2.back).toBe(5);
    const up2 = resolveReaderNav({
      readingChunkId: 5,
      outlineIds: ids,
      hasPending: false,
    });
    expect(up2.forward).toBe("live");
  });

  it("keeps controls inert while outline and reading position disagree", () => {
    const nav = resolveReaderNav({
      readingChunkId: 777,
      outlineIds: ids,
      hasPending: false,
    });
    expect(nav).toEqual({ back: null, forward: null });
  });
});

describe("isLiveRow", () => {
  const ids = [1, 2, 5, 9];

  it("marks the latest committed chunk as the frontier row when nothing is pending", () => {
    expect(isLiveRow(9, ids, false)).toBe(true);
    expect(isLiveRow(5, ids, false)).toBe(false);
  });

  it("marks no chunk row as the frontier when a pending chunk exists", () => {
    expect(isLiveRow(9, ids, true)).toBe(false);
  });

  it("handles an empty outline", () => {
    expect(isLiveRow(1, [], false)).toBe(false);
  });
});

describe("freeformPresentation - the no-choices input rule", () => {
  it("keeps the escape-hatch placeholder when structured choices exist", () => {
    expect(freeformPresentation(3)).toEqual({
      placeholder: "…or something else",
      autoFocus: false,
    });
  });

  it("drops the placeholder and takes focus when no structured choices exist", () => {
    expect(freeformPresentation(0)).toEqual({
      placeholder: undefined,
      autoFocus: true,
    });
  });
});
