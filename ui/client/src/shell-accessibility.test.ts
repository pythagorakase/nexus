/**
 * Shell accessibility invariants that live in static assets (#777): the
 * viewport must let readers pinch-zoom, content names render in natural
 * case, and every looping or moving effect holds still under
 * prefers-reduced-motion. The assertions read the shipped files themselves.
 */
import postcss, { type AtRule, type Container, type Root, type Rule } from "postcss";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const read = (...path: string[]) => readFileSync(resolve(here, ...path), "utf-8");

const REDUCED_MOTION = "prefers-reduced-motion: reduce";

function isReducedMotion(node: Container | undefined): boolean {
  return (
    node?.type === "atrule" &&
    (node as AtRule).name === "media" &&
    (node as AtRule).params.includes(REDUCED_MOTION)
  );
}

function within(rule: Rule, test: (node: Container) => boolean): boolean {
  for (let node = rule.parent; node; node = node.parent as Container | undefined) {
    if (test(node as Container)) return true;
  }
  return false;
}

const inKeyframes = (rule: Rule) =>
  within(
    rule,
    (node) => node.type === "atrule" && /keyframes$/.test((node as AtRule).name),
  );

/** Split a declaration value on top-level commas (not inside parentheses). */
function items(value: string): string[] {
  const out: string[] = [];
  let depth = 0;
  let current = "";
  for (const char of value) {
    if (char === "(") depth += 1;
    if (char === ")") depth -= 1;
    if (char === "," && depth === 0) {
      out.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  out.push(current.trim());
  return out.filter(Boolean);
}

const normalize = (selector: string) => selector.replace(/\s+/g, " ").trim();

/** Selectors a reduced-motion block sets `<property>: none` on. */
function guarded(root: Root, property: "animation" | "transition"): Set<string> {
  const selectors = new Set<string>();
  root.walkAtRules("media", (media) => {
    if (!media.params.includes(REDUCED_MOTION)) return;
    media.walkRules((rule) => {
      const stilled = rule.nodes.some(
        (node) =>
          node.type === "decl" && node.prop === property && node.value === "none",
      );
      if (stilled) rule.selectors.forEach((s) => selectors.add(normalize(s)));
    });
  });
  return selectors;
}

/** Selectors outside the guard whose declaration of `props` satisfies `moves`. */
function consumers(
  root: Root,
  props: string[],
  moves: (value: string) => boolean,
): Set<string> {
  const selectors = new Set<string>();
  root.walkRules((rule) => {
    if (inKeyframes(rule) || within(rule, isReducedMotion)) return;
    const hit = rule.nodes.some(
      (node) => node.type === "decl" && props.includes(node.prop) && moves(node.value),
    );
    if (hit) rule.selectors.forEach((s) => selectors.add(normalize(s)));
  });
  return selectors;
}

describe("viewport (index.html)", () => {
  it("lets the reader pinch-zoom", () => {
    const doc = new DOMParser().parseFromString(read("..", "index.html"), "text/html");
    const metas = doc.querySelectorAll('meta[name="viewport"]');
    expect(metas).toHaveLength(1);
    const content = metas[0].getAttribute("content") ?? "";
    const fields = Object.fromEntries(
      content.split(",").map((pair) => {
        const [key, value = ""] = pair.split("=").map((part) => part.trim());
        return [key.toLowerCase(), value.toLowerCase()];
      }),
    );

    expect(fields).toMatchObject({ width: "device-width", "initial-scale": "1.0" });
    expect(fields).not.toHaveProperty("maximum-scale");
    expect(["no", "0"]).not.toContain(fields["user-scalable"]);
  });
});

describe("natural case (nexus-layout.css)", () => {
  it("renders the scene title's place names as stored", () => {
    const root = postcss.parse(read("components", "nexus", "nexus-layout.css"));
    const declared: string[] = [];
    root.walkRules((rule) => {
      if (!rule.selectors.map(normalize).includes(".scene-title")) return;
      rule.walkDecls(/^(text-transform|letter-spacing)$/, (decl) => {
        declared.push(`${decl.prop}: ${decl.value}`);
      });
    });

    expect(declared).not.toContain("text-transform: uppercase");
    expect(declared.filter((d) => d.startsWith("letter-spacing"))).toEqual([]);
  });
});

describe("reduced motion (nexus-layout.css)", () => {
  const root = postcss.parse(read("components", "nexus", "nexus-layout.css"));
  const GEOMETRY =
    /^(all|width|height|min-width|min-height|max-width|max-height|left|right|top|bottom|inset|transform|translate|rotate|scale|margin(-\w+)?|padding(-\w+)?)$/;

  it("stills every animation in the shell", () => {
    const animated = consumers(root, ["animation", "animation-name"], (value) =>
      items(value).some((item) => item !== "none"),
    );
    const stilled = guarded(root, "animation");

    // The shell's pulses, shimmers, spinner, drawer, row entrances and slides.
    expect(animated.size).toBeGreaterThanOrEqual(15);
    for (const selector of animated) {
      expect(stilled, selector).toContain(`.nexus-shell ${selector}`);
    }
    for (const selector of stilled) {
      expect(animated, selector).toContain(selector.replace(/^\.nexus-shell /, ""));
    }
  });

  it("lands every moving transition at once, the memory fill included", () => {
    const moving = consumers(root, ["transition", "transition-property"], (value) =>
      items(value).some((item) => GEOMETRY.test(item.split(/\s+/)[0])),
    );
    const settled = guarded(root, "transition");

    expect(moving).toContain(".topbar .mem-fill");
    for (const selector of moving) {
      expect(settled, selector).toContain(`.nexus-shell ${selector}`);
    }
    for (const selector of settled) {
      expect(moving, selector).toContain(selector.replace(/^\.nexus-shell /, ""));
    }
  });
});

describe("reduced motion (index.css theme effects)", () => {
  const root = postcss.parse(read("index.css"));
  const THEME_KEYFRAMES = [
    "flicker",
    "terminal-scanline-fade",
    "terminal-shimmer",
    "deco-pulse",
    "deco-shimmer",
    "veil-shimmer",
    "slow-pulse",
    "status-bar-progress-marquee",
  ];

  it("defines each theme keyframe this guard answers for", () => {
    const defined = new Set<string>();
    root.walkAtRules(/keyframes$/, (rule) => {
      defined.add(rule.params);
    });
    for (const name of THEME_KEYFRAMES) expect(defined, name).toContain(name);
  });

  it("stills every consumer of a theme keyframe", () => {
    const animated = consumers(root, ["animation", "animation-name"], (value) =>
      items(value).some((item) =>
        item.split(/\s+/).some((token) => THEME_KEYFRAMES.includes(token)),
      ),
    );
    const stilled = guarded(root, "animation");

    expect(animated.size).toBeGreaterThanOrEqual(8);
    for (const selector of animated) expect(stilled, selector).toContain(selector);
  });
});
