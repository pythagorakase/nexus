import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import postcss from "postcss";
import { describe, expect, it } from "vitest";
import { ciede2000, composite, deutanLab, hslRgb, type Triple } from "./state-shades-measurement";
// Typed from Sharma, Wu, Dalal's published supplementary table, not our helper.
// https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/dataNprograms/ciede2000testdata.txt
const SHARMA: readonly (readonly [
  number,
  number,
  number,
  number,
  number,
  number,
  number
])[] = [
  [50, 2.6772, -79.7751, 50, 0, -82.7485, 2.0425],
  [50, 3.1571, -77.2803, 50, 0, -82.7485, 2.8615],
  [50, 2.8361, -74.0200, 50, 0, -82.7485, 3.4412],
  [50, -1.3802, -84.2814, 50, 0, -82.7485, 1],
  [50, -1.1848, -84.8006, 50, 0, -82.7485, 1],
  [50, -.9009, -85.5211, 50, 0, -82.7485, 1],
  [50, 0, 0, 50, -1, 2, 2.3669], [50, -1, 2, 50, 0, 0, 2.3669],
  [50, 2.49, -.001, 50, -2.49, .0009, 7.1792],
  [50, 2.49, -.001, 50, -2.49, .001, 7.1792],
  [50, 2.49, -.001, 50, -2.49, .0011, 7.2195],
  [50, 2.49, -.001, 50, -2.49, .0012, 7.2195],
  [50, -.001, 2.49, 50, .0009, -2.49, 4.8045],
  [50, -.001, 2.49, 50, .001, -2.49, 4.8045],
  [50, -.001, 2.49, 50, .0011, -2.49, 4.7461],
  [50, 2.5, 0, 50, 0, -2.5, 4.3065],
  [50, 2.5, 0, 73, 25, -18, 27.1492], [50, 2.5, 0, 61, -5, 29, 22.8977],
  [50, 2.5, 0, 56, -27, -3, 31.9030], [50, 2.5, 0, 58, 24, 15, 19.4535],
  [50, 2.5, 0, 50, 3.1736, .5854, 1], [50, 2.5, 0, 50, 3.2972, 0, 1],
  [50, 2.5, 0, 50, 1.8634, .5757, 1], [50, 2.5, 0, 50, 3.2592, .335, 1],
  [60.2574, -34.0099, 36.2677, 60.4626, -34.1751, 39.4387, 1.2644],
  [63.0109, -31.0961, -5.8663, 62.8187, -29.7946, -4.0864, 1.2630],
  [61.2901, 3.7196, -5.3901, 61.4292, 2.2480, -4.9620, 1.8731],
  [35.0831, -44.1164, 3.7933, 35.0232, -40.0716, 1.5901, 1.8645],
  [22.7233, 20.0904, -46.6940, 23.0331, 14.9730, -42.5619, 2.0373],
  [36.4612, 47.8580, 18.3852, 36.2715, 50.5065, 21.2231, 1.4146],
  [90.8027, -2.0831, 1.4410, 91.1528, -1.6435, .0447, 1.4441],
  [90.9257, -.5406, -.9208, 88.6381, -.8985, -.7239, 1.5381],
  [6.7747, -.2908, -2.4247, 5.8714, -.0985, -2.2286, .6377],
  [2.0776, .0795, -1.1350, .9033, -.0636, -.5514, .9082],
];
const START = "8ccd3008a48bdf8115232667399868e2bdf66f93";
const baseCss = execFileSync("git", ["show", `${START}:ui/client/src/index.css`], { encoding: "utf8" });
const shippedCss = readFileSync(resolve(import.meta.dirname, "index.css"), "utf8");
const layoutCss = readFileSync(resolve(import.meta.dirname, "components/nexus/nexus-layout.css"), "utf8");
const mapSource = readFileSync(resolve(import.meta.dirname, "components/nexus/MapPane.tsx"), "utf8");
const THEMES = ["Veil", "Gilded", "Vector"] as const;
type Theme = typeof THEMES[number];
const ROOTS = ["--brass", "--bronze", "--brass-bright", "--map-hovered", "--fg-muted", "--fg-dim", "--destructive"] as const;
const ANCHOR: Triple = [184 / 255, 61 / 255, 122 / 255];
const ANCHOR_HUE = 330.2439024390244;
function tokens(css: string, theme: Theme): Record<string, string> {
  const result: Record<string, string> = {};
  postcss.parse(css).walkRules(rule => {
    if (rule.parent?.type === "root" && (rule.selector === ".dark" || (theme !== "Veil" && rule.selector.includes(`.dark.theme-${theme.toLowerCase()}`))))
      rule.walkDecls(decl => { result[decl.prop] = decl.value; });
  });
  return result;
}
function hsl(value: string): Triple {
  const match = value.match(/(?:hsl\()?([\d.]+)\s+([\d.]+)%\s+([\d.]+)%/);
  if (!match) throw new Error(`Not HSL: ${value}`);
  return match.slice(1, 4).map(Number) as unknown as Triple;
}
function rgb(value: string): Triple {
  if (value === "#b83d7a") return ANCHOR;
  return hslRgb(hsl(value));
}
const declarationCache = new Map<string, string>();
function declaration(selector: string, property: string): string {
  const key = `${selector}:${property}`;
  const cached = declarationCache.get(key);
  if (cached) return cached;
  let result: string | undefined;
  postcss.parse(layoutCss).walkRules(rule => {
    if (rule.selectors.includes(selector))
      rule.walkDecls(property, decl => { result = decl.value; });
  });
  if (!result) throw new Error(`Missing production declaration ${selector}: ${property}`);
  declarationCache.set(key, result);
  return result;
}
function rootOf(value: string): string {
  const root = value.match(/var\((--[a-z-]+)\)/)?.[1];
  if (!root) throw new Error(`Missing production token ${value}`);
  return ["--danger", "--warning"].includes(root) ? rootOf(declaration(".settings-pane-v2", root)) : root;
}
const pairwise = (states: readonly string[]) => states.flatMap((a, i) => states.slice(i + 1).map(b => [a, b] as const));
// Exactly 14 base pairs, expanded below into production opacity contexts.
const STATE_PAIRS = {
  memory: pairwise(["normal", "over"]),
  delete: pairwise(["unarmed", "armed"]),
  map: pairwise(["rest", "current", "selected", "hovered"]),
  key: pairwise(["optional-absent", "required-missing", "present", "verified"]),
};
type Surface = keyof typeof STATE_PAIRS;
const MAPPINGS: Record<Surface, Record<string, string>> = {
  memory: { normal: rootOf(declaration(".topbar .mem-fill", "background")), over: rootOf(declaration(".topbar .mem-fill.over", "background")) },
  delete: { unarmed: rootOf(declaration(".lm-trash", "color")), armed: rootOf(declaration(".lm-trash.armed", "color")) },
  map: Object.fromEntries(["rest", "current", "selected", "hovered"].map(state => {
    const block = mapSource.match(/const PIN_COLOR[^=]*=\s*\{([^}]+)\}/)?.[1];
    const value = block?.match(new RegExp(`${state}:\\s*"([^"]+)"`))?.[1];
    if (!value) throw new Error(`Missing pin mapping ${state}`);
    return [state, rootOf(value)];
  })),
  key: {
    "optional-absent": rootOf(declaration(".key-status", "color")),
    "required-missing": rootOf(declaration(".key-row.missing .key-status", "color")),
    present: rootOf(declaration(".key-status.present", "color")),
    verified: rootOf(declaration(".key-status.verified", "color")),
  },
};
const SIGNATURES: Record<Surface, Record<string, string>> = {
  memory: { normal: "meter; warning absent", over: "meter + AlertTriangle" },
  delete: { unarmed: "Trash2", armed: "AlertTriangle" },
  map: { rest: "filled circle; no ring", current: "filled circle + circular ring", selected: "filled square + square ring", hovered: "filled diamond + diamond ring" },
  key: { "optional-absent": "Circle", "required-missing": "AlertTriangle", present: "CircleDot", verified: "CircleCheck" },
};
type Palette = Record<string, Triple>;
type Context = { surface: Surface; name: string; render: (state: string, p: Palette, before: boolean) => Triple };
// CSS interpolation/compositing is encoded sRGB (CSS `in srgb`), THEN the
// simulation linearizes. Interior fill/stroke samples exclude edge AA/glow.
function background(value: string, p: Palette, under?: Triple): Triple {
  if (value === "none" || value === "transparent") {
    if (!under) throw new Error("Transparent background needs parent");
    return under;
  }
  const mix = value.match(/^color-mix\(in srgb, var\((--[a-z0-9-]+)\) ([\d.]+)%, (.+)\)$/);
  if (mix) return composite(p[mix[1]], background(mix[3], p, under), Number(mix[2]) / 100);
  const root = value.match(/^var\((--[a-z0-9-]+)\)$/)?.[1];
  if (root) return p[root];
  return rgb(value);
}
const opacity = (selector: string) => Number(declaration(selector, "opacity"));
const ringOpacity = Number(mapSource.match(/opacity: outline \? ([\d.]+)/)?.[1]);
if (!Number.isFinite(ringOpacity)) throw new Error("Missing production ring opacity");
function contexts(): Context[] {
  const result: Context[] = [];
  const pigment = (surface: Surface, state: string, p: Palette, before: boolean) => p[before && surface === "map" && state === "hovered" ? "--brass-bright" : MAPPINGS[surface][state]];
  result.push({ surface: "memory", name: "fill", render: (s, p, b) => pigment("memory", s, p, b) });
  for (const row of ["ready", "ready-exceeds"])
    for (const interaction of ["rest", "hover", "focus"]) {
      // No hover/focus rule changes .lm-trash foreground/background. Resolve
      // the ready row first, then its group opacity against provider parent.
      result.push({ surface: "delete", name: `${row}/${interaction}`, render: (s, p, b) => {
        const rowBg = background(declaration(".lm-quant.ready", "background"), p);
        const glyph = composite(pigment("delete", s, p, b), rowBg, 1);
        return composite(glyph, background(declaration(".model-provider", "background"), p), row === "ready-exceeds" ? opacity(".lm-quant.exceeds") : 1);
      } });
    }
  // Include required and optional presence/verification rows at rest and
  // hover/focus-within; required-missing cannot be an optional row.
  for (const requiredness of ["required", "optional"])
    for (const interaction of ["rest", "hover", "focus"]) {
      result.push({ surface: "key", name: `${requiredness}/${interaction}`, render: (s, p, b) => {
        const optional = s === "optional-absent" || (requiredness === "optional" && s !== "required-missing");
        const alpha = optional ? opacity(interaction === "rest" ? ".key-row.optional" : `.key-row.optional:${interaction === "hover" ? "hover" : "focus-within"}`) : 1;
        return composite(pigment("key", s, p, b), background(declaration(".key-row", "background"), p), alpha);
      } });
    }
  for (const terrain of ["sea", "land"])
    for (const part of ["fill", "ring"]) {
      result.push({ surface: "map", name: `canvas-${terrain}/${part}`, render: (s, p, b) => {
        const bg = background(declaration(".mappane-canvas", `--map-${terrain}`), p);
        return composite(pigment("map", s, p, b), bg, part === "ring" && s !== "rest" ? ringOpacity : 1);
      } });
    }
  // The sidebar inherits .nexus-content's fixed radial wash over --bg.
  // Sample both zero and maximum wash endpoints; opaque fills are invariant.
  const content = declaration(".nexus-content", "background");
  const wash = content.match(/hsl\(([\d.]+ [\d.]+% [\d.]+%) \/ ([\d.]+)\)/);
  if (!wash) throw new Error("Content gradient changed: extend backdrop proof");
  for (const washAlpha of [0, Number(wash[2])])
    for (const interaction of ["rest", "hover", "selected-current"])
      for (const part of ["fill", "ring"]) {
        result.push({ surface: "map", name: `sidebar-wash-${washAlpha}/${interaction}/${part}`, render: (s, p, b) => {
          const parent = composite(rgb(wash[1]), p[rootOf(content)], washAlpha);
          const on = s === "selected" || (interaction === "selected-current" && s === "current");
          const bg = background(declaration(on ? ".map-place-row.on" : interaction === "hover" ? ".map-place-row:hover" : ".map-place-row", "background"), p, parent);
          return composite(pigment("map", s, p, b), bg, !b && part === "ring" && s !== "rest" ? ringOpacity : 1);
        } });
      }
  return result;
}
const CONTEXTS = contexts();
function palette(css: string, theme: Theme): Palette {
  return Object.fromEntries(Object.entries(tokens(css, theme)).filter(([root, value]) => ROOTS.includes(root as typeof ROOTS[number]) || /^--(?:bg(?:-elev-[123])?|border-faint)$/.test(root)).map(([root, value]) => [root, rgb(value)]));
}
function candidates(theme: Theme, root: string): { value: string; rgb: Triple; changed: number }[] {
  const base = tokens(baseCss, theme)[root === "--map-hovered" ? "--brass-bright" : root];
  const old = rgb(base);
  if (theme === "Veil" && root === "--brass") return [{ value: "#b83d7a", rgb: ANCHOR, changed: 1 }];
  let [h, s, l] = hsl(base);
  if (theme === "Veil" && ["--brass-bright", "--map-hovered"].includes(root)) h = ANCHOR_HUE;
  const sats = [...new Set(root === "--destructive" ? [80, 90, 100] : [s, Math.min(100, s + 10), Math.min(100, s + 20)])];
  const lights = [...new Set(root === "--destructive" ? [50, 55, 60, 65] : [l, 30, 40, 50, 60, 70])];
  return sats.flatMap(s => lights.map(l => {
    const next = hslRgb([h, s, l]);
    return { value: `hsl(${h} ${s}% ${l}%)`, rgb: next, changed: next.every((v, i) => Math.abs(v - old[i]) < 1e-12) ? 0 : 1 };
  }));
}
function measures(theme: Theme, p: Palette, before: boolean) {
  return CONTEXTS.flatMap(ctx => STATE_PAIRS[ctx.surface].map(states => {
    const colors = states.map(s => ctx.render(s, p, before));
    return { theme, surface: ctx.surface, context: ctx.name, states, rgb: colors, delta: ciede2000(deutanLab(colors[0]), deutanLab(colors[1])), signatures: states.map(s => SIGNATURES[ctx.surface][s]) };
  }));
}
/** Exhaustive finite-domain max-min via exact variable elimination.
 * For fixed brass/bronze/fg-muted, the map's current+hovered, key's fg-dim,
 * and delete's destructive are independent. Enumerate ALL assignments of
 * each factor, then combine their minima. This represents every full
 * Cartesian assignment exactly, without a heuristic or sampled search.
 * A second pass at the global optimum handles the fewest-changed-roots tie.
 */
function jointSearch(theme: Theme) {
  const domains = ROOTS.map(r => candidates(theme, r));
  const p = palette(shippedCss, theme);
  const maxima = new Map<string, { maximum: number; count: number; witness: Record<string, string> }>();
  const groups = [
    { name: "map", roots: [0, 1, 2, 3], surfaces: ["map", "memory"] },
    { name: "key", roots: [0, 1, 4, 5], surfaces: ["key"] },
    { name: "delete", roots: [4, 6], surfaces: ["delete"] },
  ];
  type Entry = { minimum: number; ix: number[]; changed: number };
  const tables: Map<string, Entry[]>[] = [];
  for (const group of groups) {
    const table = new Map<string, Entry[]>();
    const ctxs = CONTEXTS.filter(c => group.surfaces.includes(c.surface));
    // Cache the composited Lab per context/state/relevant candidate subset.
    const labs = new Map<string, Triple>();
    const ix: number[] = Array(7).fill(0);
    const visit = (depth: number) => {
      if (depth < group.roots.length) {
        const root = group.roots[depth];
        for (let i = 0; i < domains[root].length; i++) {
          ix[root] = i; p[ROOTS[root]] = domains[root][i].rgb; visit(depth + 1);
        }
        return;
      }
      let minimum = Infinity;
      for (const ctx of ctxs) {
        const colors = new Map<string, Triple>();
        for (const state of new Set(STATE_PAIRS[ctx.surface].flat())) {
          const root = ROOTS.indexOf(MAPPINGS[ctx.surface][state] as typeof ROOTS[number]);
          // Only map-land/sidebar backgrounds depend on brass; key opacity
          // and deletion parent background are fixed. Include brass for map.
          const key = `${ctx.name}:${state}:${ix[root]}:${ctx.surface === "map" ? ix[0] : ""}`;
          let lab = labs.get(key);
          if (!lab) { lab = deutanLab(ctx.render(state, p, false)); labs.set(key, lab); }
          colors.set(state, lab);
        }
        for (const [a, b] of STATE_PAIRS[ctx.surface]) {
          const value = ciede2000(colors.get(a)!, colors.get(b)!);
          minimum = Math.min(minimum, value);
          const key = `${ctx.surface}/${ctx.name}/${a}/${b}`;
          const prev = maxima.get(key);
          if (!prev || value > prev.maximum) maxima.set(key, { maximum: value, count: 0, witness: Object.fromEntries(group.roots.map(r => [ROOTS[r], domains[r][ix[r]].value])) });
        }
      }
      const key = group.name === "delete" ? `${ix[4]}` : group.name === "key" ? `${ix[0]},${ix[1]},${ix[4]}` : `${ix[0]},${ix[1]}`;
      const entries = table.get(key) ?? [];
      const leaves = group.name === "map" ? [2, 3] : group.name === "key" ? [5] : [6];
      entries.push({ minimum, ix: [...ix], changed: leaves.reduce((n, r) => n + domains[r][ix[r]].changed, 0) });
      table.set(key, entries);
    };
    visit(0);
    tables.push(table);
    const count = group.roots.reduce((n, r) => n * domains[r].length, 1);
    for (const [key, entry] of maxima) if (group.surfaces.some(s => key.startsWith(`${s}/`))) entry.count = count;
  }
  let best = -Infinity, feasible = 0;
  const cores: { a: number; b: number; f: number; lists: Entry[][]; minimum: number }[] = [];
  for (let a = 0; a < domains[0].length; a++)
    for (let b = 0; b < domains[1].length; b++)
      for (let f = 0; f < domains[4].length; f++) {
        const lists = [tables[0].get(`${a},${b}`)!, tables[1].get(`${a},${b},${f}`)!, tables[2].get(`${f}`)!];
        const minimum = Math.min(...lists.map(list => Math.max(...list.map(e => e.minimum))));
        best = Math.max(best, minimum);
        feasible += lists.reduce((n, list) => n * list.filter(e => e.minimum >= 15).length, 1);
        cores.push({ a, b, f, lists, minimum });
      }
  let changes = Infinity, witness: number[] = [];
  for (const core of cores) {
    if (core.minimum !== best) continue;
    const chosen = core.lists.map(list => list.filter(e => e.minimum >= best).sort((a, b) => a.changed - b.changed)[0]);
    const changed = [0, 1, 4].reduce((n, r, j) => n + domains[r][[core.a, core.b, core.f][j]].changed, 0) + chosen.reduce((n, e) => n + e.changed, 0);
    if (changed < changes) {
      changes = changed;
      witness = [core.a, core.b, chosen[0].ix[2], chosen[0].ix[3], core.f, chosen[1].ix[5], chosen[2].ix[6]];
    }
  }
  const assignment = Object.fromEntries(ROOTS.map((r, i) => [r, domains[i][witness[i]].value]));
  const shipped = { ...palette(shippedCss, theme), ...Object.fromEntries(ROOTS.map((r, i) => [r, domains[i][witness[i]].rgb])) };
  return { theme, sizes: domains.map(d => d.length), count: domains.reduce((n, d) => n * d.length, 1), feasible, best, changes, assignment, maxima: Object.fromEntries(maxima), measurements: measures(theme, shipped, false) };
}
let searches: ReturnType<typeof jointSearch>[] | undefined;
const searchAll = () => searches ??= THEMES.map(jointSearch);
// Explicit one-theme exception manifests; exact context inventory is generated
// from CSS, while shortfall IDs are committed and checked below.
const exceptions = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../../docs/qa/777-glyph-first-states/theme-exceptions.json"), "utf8")) as Record<Theme, string[]>;
describe("777-S2 state shades", () => {
  it("ciede2000_matches_published_reference_vectors", () => {
    expect(SHARMA).toHaveLength(34);
    for (const [l1, a1, b1, l2, a2, b2, expected] of SHARMA)
      expect(Math.abs(ciede2000([l1, a1, b1], [l2, a2, b2]) - expected)).toBeLessThan(.00005);
  });
  it("every_state_pair_is_measured_in_every_theme", () => {
    expect(Object.values(STATE_PAIRS).flat()).toHaveLength(14);
    expect(CONTEXTS.filter(c => c.surface === "delete").map(c => c.name)).toEqual(["ready/rest", "ready/hover", "ready/focus", "ready-exceeds/rest", "ready-exceeds/hover", "ready-exceeds/focus"]);
    expect(CONTEXTS.filter(c => c.surface === "key")).toHaveLength(6);
    expect(CONTEXTS.filter(c => c.surface === "map")).toHaveLength(16);
    for (const theme of THEMES) {
      const values = measures(theme, palette(shippedCss, theme), false);
      expect(values).toHaveLength(139);
      for (const ctx of CONTEXTS) expect(values.filter(v => v.context === ctx.name && v.surface === ctx.surface)).toHaveLength(STATE_PAIRS[ctx.surface].length);
    }
  });
  it("reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures", () => {
    expect(MAPPINGS).toEqual({ memory: { normal: "--brass", over: "--bronze" }, delete: { unarmed: "--fg-muted", armed: "--destructive" }, map: { rest: "--bronze", current: "--brass-bright", selected: "--brass", hovered: "--map-hovered" }, key: { "optional-absent": "--fg-dim", "required-missing": "--bronze", present: "--fg-muted", verified: "--brass" } });
    for (const theme of THEMES) {
      const after = tokens(shippedCss, theme), before = tokens(baseCss, theme);
      for (const root of Object.keys(before).filter(r => r.startsWith("--bg") || r.includes("background"))) expect(after[root], `${theme} background ${root}`).toBe(before[root]);
      expect(after["--destructive"]).not.toMatch(/^hsl/); // consumed as hsl(var(...))
      const aliases: Record<string, string[]> = {
        "--brass": ["--primary", "--sidebar-primary", "--sidebar-ring", "--ring", "--chart-1", ...(theme === "Veil" ? ["--magenta"] : [])],
        "--fg-muted": ["--muted-foreground"],
        "--bronze": ["--chart-2", ...(theme === "Veil" ? ["--accent", "--sidebar-accent", "--coral"] : [])],
        "--brass-bright": theme === "Veil" ? ["--magenta-light"] : ["--accent"],
      };
      for (const [root, linked] of Object.entries(aliases)) for (const alias of linked) rgb(after[alias]).forEach((v, i) => expect(v, `${theme} ${alias}`).toBeCloseTo(rgb(after[root])[i], 12));
    }
    const results = searchAll();
    if (process.env.STATE_SHADES_EVIDENCE_DIR) for (const result of results) writeFileSync(resolve(process.env.STATE_SHADES_EVIDENCE_DIR, `${result.theme.toLowerCase()}-joint.json`), JSON.stringify({ ...result, before: measures(result.theme, palette(baseCss, result.theme), true) }, null, 2) + "\n");
    for (const result of results) {
      console.log(JSON.stringify({ ...result, maxima: undefined, measurements: undefined }));
      if (process.env.STATE_SHADES_EVIDENCE_DIR) writeFileSync(resolve(process.env.STATE_SHADES_EVIDENCE_DIR, `${result.theme.toLowerCase()}-joint.json`), JSON.stringify({ ...result, before: measures(result.theme, palette(baseCss, result.theme), true) }, null, 2) + "\n");
      const actual = palette(shippedCss, result.theme);
      for (const root of ROOTS) expect(candidates(result.theme, root).some(c => c.rgb.every((v, i) => Math.abs(v - actual[root][i]) < 1e-12)), `${result.theme} ${root} outside domain`).toBe(true);
      const shipped = measures(result.theme, actual, false);
      expect(Math.min(...shipped.map(m => m.delta))).toBeCloseTo(result.best, 10);
      const shortfalls = shipped.filter(m => m.delta < 15);
      expect(exceptions[result.theme]).toEqual(shortfalls.map(m => `${m.surface}/${m.context}/${m.states.join("/")}`));
      expect(shortfalls.length > 0).toBe(result.feasible === 0);
      for (const m of shortfalls) expect(m.signatures[0]).not.toEqual(m.signatures[1]);
      expect(result.count).toBe(result.sizes.reduce((n, s) => n * s, 1));
      expect(ROOTS.filter(root => actual[root].some((v, i) => Math.abs(v - rgb(tokens(baseCss, result.theme)[root === "--map-hovered" ? "--brass-bright" : root])[i]) >= 1e-12))).toHaveLength(result.changes);
    }
  }, 120000);
  it("veil_anchor_is_exact_b83d7a", () => {
    const veil = tokens(shippedCss, "Veil");
    expect(veil["--brass"]).toBe("#b83d7a");
    expect(veil["--magenta"]).toBe("#b83d7a");
    for (const root of ["--primary", "--sidebar-primary", "--sidebar-ring", "--ring", "--chart-1"])
      rgb(veil[root]).forEach((v, i) => expect(v).toBeCloseTo(ANCHOR[i], 12));
  });
});
