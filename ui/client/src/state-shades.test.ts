import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import postcss from "postcss";
import { inputs } from "../../scripts/state-surfaces/inputs.mjs";
import { describe, expect, it } from "vitest";
import { ciede2000, deutanLab, hslRgb, type Triple } from "./state-shades-measurement";
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
// Amendment 2 moves every mutable pigment into a dedicated static token.
const BASE_ROOTS: Record<string, string> = {
  "--state-map-rest": "--bronze", "--state-map-current": "--brass-bright",
  "--state-map-selected": "--brass", "--state-map-hovered": "--brass-bright",
  "--state-key-absent": "--fg-dim", "--state-key-missing": "--bronze",
  "--state-key-present": "--fg-muted", "--state-key-verified": "--brass",
  "--state-mem-normal": "--brass", "--state-mem-over": "--bronze",
  "--state-delete-unarmed": "--fg-muted", "--state-delete-armed": "--destructive",
};
const ROOTS = Object.keys(BASE_ROOTS);
const ANCHOR: Triple = [184 / 255, 61 / 255, 122 / 255];
const ANCHOR_HUE = 330.2439024390244;
// Amendment 3: this shared list is the sole declared global exemption.
const VEIL_ANCHOR_TOKENS = ["--brass", "--magenta", "--primary", "--sidebar-primary", "--sidebar-ring", "--ring", "--chart-1"];
const ANCHOR_HSL = "330.2439024390244 50.20408163265306% 48.03921568627451%";
function tokens(css: string, theme: Theme): Record<string, string> {
  const result: Record<string, string> = {};
  postcss.parse(css).walkRules(rule => {
    if (rule.parent?.type === "root" && (rule.selector === ":root" || rule.selector === ".dark" || (theme !== "Veil" && rule.selector.includes(`.dark.theme-${theme.toLowerCase()}`))))
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
  return root;
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
type Layer = {
  tag: string; classes: string; opacity: string; backgroundColor: string;
  backgroundImage: string; stackingContext: boolean;
  underlay?: { color: string; opacity: string; source: string };
};
type Sample = { property: string; color: string; chain: Layer[] };
type Receipt = {
  inputs: ReturnType<typeof inputs>;
  themes: Record<Theme, Record<"shipped" | "before", Record<string, Record<string, Sample>>>>;
  candidateColors: Record<Theme, Record<string, string>>;
};
const receipt = JSON.parse(readFileSync(resolve(import.meta.dirname, "state-surfaces.resolved.json"), "utf8")) as Receipt;
const currentInputs = inputs(resolve(import.meta.dirname, "../.."));
if (JSON.stringify(receipt.inputs) !== JSON.stringify(currentInputs))
  throw new Error("Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).");
// The browser has already resolved selectors, inheritance, media, specificity,
// !important, custom properties and color-mix. Only numeric source-over remains.
function browserColor(value: string): { rgb: Triple; alpha: number } {
  const srgb = value.match(/^color\(srgb ([\d.e+-]+) ([\d.e+-]+) ([\d.e+-]+)(?: \/ ([\d.e+-]+))?\)$/);
  const legacy = value.match(/^rgba?\(([\d.]+), ([\d.]+), ([\d.]+)(?:, ([\d.]+))?\)$/);
  const match = srgb ?? legacy;
  if (!match) throw new Error(`Unsupported browser color serialization: ${value}`);
  return { rgb: match.slice(1, 4).map(v => Number(v) / (srgb ? 1 : 255)) as unknown as Triple, alpha: Number(match[4] ?? 1) };
}
function over(front: { rgb: Triple; alpha: number }, back: { rgb: Triple; alpha: number }) {
  const alpha = front.alpha + back.alpha * (1 - front.alpha);
  return { alpha, rgb: (alpha === 0 ? [0, 0, 0] : front.rgb.map((v, i) =>
    (v * front.alpha + back.rgb[i] * back.alpha * (1 - front.alpha)) / alpha)) as Triple };
}
function painted(sample: Sample, candidate?: Triple): Triple {
  let pixel = candidate ? { rgb: candidate, alpha: 1 } : browserColor(sample.color);
  for (const [i, layer] of sample.chain.entries()) {
    // A background-color surface IS the leaf background. Substitution replaces
    // that one token value, never its browser-reported opacity or any backdrop.
    let back = i === 0 && sample.property === "background-color"
      ? { rgb: [0, 0, 0] as Triple, alpha: 0 } : browserColor(layer.backgroundColor);
    if (layer.underlay) {
      const underlay = browserColor(layer.underlay.color);
      back = over({ ...underlay, alpha: underlay.alpha * Number(layer.underlay.opacity) }, back);
    }
    pixel = over(pixel, back);
    pixel.alpha *= Number(layer.opacity);
  }
  if (Math.abs(pixel.alpha - 1) > 1e-12) throw new Error("Browser chain has no opaque final backdrop");
  return pixel.rgb;
}
type Context = { surface: Surface; name: string; render: (state: string, p: Palette | undefined, before: boolean, theme: Theme) => Triple };
// Explicit inventory; adding or dropping a context cannot silently change the proof.
const CONTEXTS: Context[] = [
  ["memory", "fill"],
  ...["ready", "ready-exceeds"].flatMap(row => ["rest", "hover", "focus"].map(action => ["delete", `${row}/${action}`])),
  ...["required", "optional"].flatMap(need => ["rest", "hover", "focus"].map(action => ["key", `${need}/${action}`])),
  ...["sea", "land"].flatMap(terrain => ["fill", "ring"].map(part => ["map", `canvas-${terrain}/${part}`])),
  ...[0, .07].flatMap(wash => ["rest", "hover", "selected-current"].flatMap(action => ["fill", "ring"].map(part => ["map", `sidebar-wash-${wash}/${action}/${part}`]))),
].map(([surface, name]) => ({ surface: surface as Surface, name, render: (state, p, before, theme) => {
  const sample = receipt.themes[theme][before ? "before" : "shipped"][`${surface}/${name}`][state];
  if (!p) return painted(sample);
  // Joint-search substitution rule: vary only the surface's own state-token
  // pigment. Every opacity, background and ancestor comes from Chromium. The
  // domain is unchanged; Chromium also reports candidate RGB serialization.
  const root = MAPPINGS[surface as Surface][state];
  const candidate = candidates(theme, root).find(c => c.rgb.every((v, i) => Math.abs(v - p[root][i]) < 1e-12));
  if (!candidate) throw new Error(`Candidate outside domain: ${theme}/${root}`);
  return painted(sample, browserColor(receipt.candidateColors[theme][candidate.value]).rgb);
} }));
function palette(css: string, theme: Theme): Palette {
  return Object.fromEntries(Object.entries(tokens(css, theme))
    .filter(([, value]) => value === "#b83d7a" || /^(?:hsl\()?([\d.]+)\s+([\d.]+)%\s+([\d.]+)%/.test(value))
    .map(([root, value]) => [root, rgb(value)]));
}
function baselineValue(theme: Theme, root: string): string {
  return theme === "Veil" && BASE_ROOTS[root] === "--brass"
    ? `hsl(${ANCHOR_HSL})` : tokens(baseCss, theme)[BASE_ROOTS[root]];
}
const domainCache = new Map<string, { value: string; rgb: Triple; changed: number }[]>();
function candidates(theme: Theme, root: string): { value: string; rgb: Triple; changed: number }[] {
  const key = `${theme}/${root}`;
  const cached = domainCache.get(key);
  if (cached) return cached;
  const base = baselineValue(theme, root);
  const old = rgb(base);
  let [h, s, l] = hsl(base);
  if (theme === "Veil" && ["--brass", "--brass-bright"].includes(BASE_ROOTS[root])) h = ANCHOR_HUE;
  const destructive = root === "--state-delete-armed";
  const sats = [...new Set(destructive ? [80, 90, 100] : [s, Math.min(100, s + 10), Math.min(100, s + 20)])];
  const lights = [...new Set(destructive ? [50, 55, 60, 65] : [l, 30, 40, 50, 60, 70])];
  const result = sats.flatMap(s => lights.map(l => {
    const next = hslRgb([h, s, l]);
    return { value: `hsl(${h} ${s}% ${l}%)`, rgb: next, changed: next.every((v, i) => Math.abs(v - old[i]) < 1e-12) ? 0 : 1 };
  }));
  domainCache.set(key, result);
  return result;
}
function measures(theme: Theme, p: Palette | undefined, before: boolean) {
  return CONTEXTS.flatMap(ctx => STATE_PAIRS[ctx.surface].map(states => {
    const colors = states.map(s => ctx.render(s, p, before, theme));
    return { theme, surface: ctx.surface, context: ctx.name, states, rgb: colors, delta: ciede2000(deutanLab(colors[0]), deutanLab(colors[1])), signatures: states.map(s => SIGNATURES[ctx.surface][s]) };
  }));
}
/** Exact exhaustive factorization: fixed global backgrounds mean that the
 * four surfaces share no mutable pigment. Each pair/context matrix visits all
 * candidate pairs; each surface then visits its complete Cartesian product.
 * The global optimum is the minimum of the four surface maxima. Choosing the
 * fewest changes above that threshold in each factor gives the global tie-break.
 * BigInt counts retain the exact size of the twelve-token Cartesian domain.
 */
function jointSearch(theme: Theme) {
  const domains = Object.fromEntries(ROOTS.map(r => [r, candidates(theme, r)]));
  const p = palette(shippedCss, theme);
  const maxima: Record<string, { maximum: number; count: number; witness: Record<string, string> }> = {};
  const factors = (Object.keys(STATE_PAIRS) as Surface[]).map(surface => {
    const roots = Object.values(MAPPINGS[surface]);
    const ctxs = CONTEXTS.filter(c => c.surface === surface);
    const edges = STATE_PAIRS[surface].map(([a, b]) => {
      const ra = MAPPINGS[surface][a], rb = MAPPINGS[surface][b];
      const scores = domains[ra].map(() => domains[rb].map(() => Infinity));
      for (const ctx of ctxs) {
        const labs = [a, b].map(state => {
          const root = MAPPINGS[surface][state];
          return domains[root].map(c => { p[root] = c.rgb; return deutanLab(ctx.render(state, p, false, theme)); });
        });
        let maximum = -Infinity, witness: Record<string, string> = {};
        let count = 0;
        for (let i = 0; i < domains[ra].length; i++)
          for (let j = 0; j < domains[rb].length; j++) {
            count++;
            const delta = ciede2000(labs[0][i], labs[1][j]);
            scores[i][j] = Math.min(scores[i][j], delta);
            if (delta > maximum) { maximum = delta; witness = { [ra]: domains[ra][i].value, [rb]: domains[rb][j].value }; }
          }
        maxima[`${surface}/${ctx.name}/${a}/${b}`] = { maximum, count, witness };
      }
      return { ra, rb, scores };
    });
    const entries: { minimum: number; ix: Record<string, number>; changed: number }[] = [];
    const ix: Record<string, number> = {};
    const unique = new Set<string>();
    let visited = 0;
    function visit(depth: number) {
      if (depth < roots.length) {
        const root = roots[depth];
        for (let i = 0; i < domains[root].length; i++) { ix[root] = i; visit(depth + 1); }
        return;
      }
      visited++;
      unique.add(roots.map(r => ix[r]).join(","));
      entries.push({ minimum: Math.min(...edges.map(e => e.scores[ix[e.ra]][ix[e.rb]])), ix: { ...ix }, changed: roots.reduce((n, r) => n + domains[r][ix[r]].changed, 0) });
    }
    visit(0);
    const expected = roots.reduce((n, r) => n * domains[r].length, 1);
    if (visited !== expected || unique.size !== expected) throw new Error(`${theme} ${surface}: incomplete exhaustive factor search`);
    return { roots, entries, best: entries.reduce((n, e) => Math.max(n, e.minimum), -Infinity), coverage: { surface, roots, visited, unique: unique.size, expected } };
  });
  const best = Math.min(...factors.map(f => f.best));
  const chosen = factors.map(f => f.entries.filter(e => e.minimum >= best).sort((a, b) => a.changed - b.changed)[0]);
  const assignment = Object.assign({}, ...chosen.map(e => Object.fromEntries(Object.entries(e.ix).map(([r, i]) => [r, domains[r][i].value])))) as Record<string, string>;
  const shipped = { ...palette(shippedCss, theme), ...Object.fromEntries(ROOTS.map(r => [r, rgb(assignment[r])])) };
  return {
    theme, sizes: ROOTS.map(r => domains[r].length),
    count: ROOTS.reduce((n, r) => n * BigInt(domains[r].length), 1n).toString(),
    feasible: factors.reduce((n, f) => n * BigInt(f.entries.filter(e => e.minimum >= 15).length), 1n).toString(),
    best, changes: chosen.reduce((n, e) => n + e.changed, 0), assignment,
    coverage: factors.map(f => f.coverage), factorMaxima: factors.map(f => ({ surface: f.coverage.surface, best: f.best })),
    maxima, measurements: measures(theme, shipped, false),
  };
}
let searches: ReturnType<typeof jointSearch>[] | undefined;
const searchAll = () => searches ??= THEMES.map(jointSearch);
// Explicit one-theme exception manifests; the context inventory is fixed above,
// while shortfall IDs are committed and checked below.
const exceptions = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../../docs/qa/777-glyph-first-states/amendment-2/theme-exceptions.json"), "utf8")) as Record<Theme, string[]>;
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
      const values = measures(theme, undefined, false);
      expect(values).toHaveLength(139);
      for (const ctx of CONTEXTS) expect(values.filter(v => v.context === ctx.name && v.surface === ctx.surface)).toHaveLength(STATE_PAIRS[ctx.surface].length);
    }
  });
  it("browser_measurements_cover_production_compositing_chains", () => {
    for (const theme of THEMES) for (const phase of ["before", "shipped"] as const) {
      const contexts = receipt.themes[theme][phase];
      expect(Object.keys(contexts)).toEqual(CONTEXTS.map(c => `${c.surface}/${c.name}`));
      for (const ctx of CONTEXTS) {
        const samples = contexts[`${ctx.surface}/${ctx.name}`];
        expect(Object.keys(samples)).toEqual(Object.keys(MAPPINGS[ctx.surface]));
        for (const [state, sample] of Object.entries(samples)) {
          if (phase === "before") {
            // Historical declarations are immutable and use legacy HSL RGB
            // serialization. Check the pigment independently of the fixture's
            // theme overlay; opacity/backdrops still come only from the receipt.
            const value = tokens(baseCss, theme)[BASE_ROOTS[MAPPINGS[ctx.surface][state]]];
            const actual = browserColor(sample.color).rgb;
            // Chromium serializes legacy RGB to 8-bit channels. A half-channel
            // bound avoids imposing JavaScript's floating-point tie rounding.
            rgb(value).forEach((v, i) => expect(Math.abs(actual[i] - v) * 255,
              `${theme} before/${ctx.surface}/${state}`).toBeLessThanOrEqual(.5 + 1e-9));
          }
          expect(sample.chain.length).toBeGreaterThan(0);
          for (const layer of sample.chain)
            expect(layer.stackingContext).toBe(Number(layer.opacity) < 1);
          expect(() => painted(sample)).not.toThrow();
        }
      }
      const optional = contexts["key/optional/rest"].present.chain;
      expect(optional.some(n => n.classes.split(" ").includes("optional") && n.stackingContext)).toBe(true);
      expect(optional.at(-1)?.classes.split(" ")).toContain("set-card-frame");
      const exceeds = contexts["delete/ready-exceeds/rest"].unarmed.chain;
      expect(exceeds.some(n => n.classes.split(" ").includes("exceeds") && n.stackingContext)).toBe(true);
      expect(exceeds.at(-1)?.classes.split(" ")).toContain("model-provider");
    }
  });
  it("browser_measurements_match_recorded_tables", () => {
    // The browser is the oracle; this consistency check makes a changed
    // measurement require refreshed evidence as well as a refreshed receipt.
    for (const theme of THEMES) {
      const evidence = JSON.parse(readFileSync(resolve(import.meta.dirname,
        `../../../docs/qa/777-glyph-first-states/amendment-2/${theme.toLowerCase()}-joint.json`), "utf8"));
      expect(measures(theme, undefined, false)).toEqual(evidence.measurements);
      expect(measures(theme, undefined, true)).toEqual(evidence.before);
    }
  });
  it("reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures", () => {
    expect(MAPPINGS).toEqual({
      memory: { normal: "--state-mem-normal", over: "--state-mem-over" },
      delete: { unarmed: "--state-delete-unarmed", armed: "--state-delete-armed" },
      map: { rest: "--state-map-rest", current: "--state-map-current", selected: "--state-map-selected", hovered: "--state-map-hovered" },
      key: { "optional-absent": "--state-key-absent", "required-missing": "--state-key-missing", present: "--state-key-present", verified: "--state-key-verified" },
    });
    const results = searchAll();
    for (const result of results) {
      console.log(JSON.stringify({ ...result, maxima: undefined, measurements: undefined }));
      if (process.env.STATE_SHADES_EVIDENCE_DIR) writeFileSync(resolve(process.env.STATE_SHADES_EVIDENCE_DIR, `${result.theme.toLowerCase()}-joint.json`), JSON.stringify({ ...result, measurements: measures(result.theme, undefined, false), before: measures(result.theme, undefined, true) }, null, 2) + "\n");
      const actual = palette(shippedCss, result.theme);
      for (const root of ROOTS) expect(candidates(result.theme, root).some(c => c.rgb.every((v, i) => Math.abs(v - actual[root][i]) < 1e-12)), `${result.theme} ${root} outside domain`).toBe(true);
      const shipped = measures(result.theme, undefined, false);
      expect(Math.min(...shipped.map(m => m.delta))).toBeCloseTo(result.best, 10);
      const shortfalls = shipped.filter(m => m.delta < 15);
      expect(exceptions[result.theme]).toEqual(shortfalls.map(m => `${m.surface}/${m.context}/${m.states.join("/")}`));
      expect(shortfalls.length > 0).toBe(result.feasible === "0");
      for (const m of shortfalls) expect(m.signatures[0]).not.toEqual(m.signatures[1]);
      expect(result.count).toBe(result.sizes.reduce((n, s) => n * BigInt(s), 1n).toString());
      expect(ROOTS.filter(root => actual[root].some((v, i) => Math.abs(v - rgb(baselineValue(result.theme, root))[i]) >= 1e-12))).toHaveLength(result.changes);
    }
  }, 120000);
  it("global_tokens_are_unchanged_from_baseline", () => {
    function otherGlobals(css: string): string[] {
      const result: string[] = [];
      postcss.parse(css).walkDecls(decl => {
        if (!decl.prop.startsWith("--")) return;
        const rule = decl.parent;
        if (rule?.type === "rule" && rule.parent?.type === "root" &&
          (rule.selector === ".dark" || rule.selector.includes(".dark.theme-gilded") || rule.selector.includes(".dark.theme-vector"))) return;
        result.push(`${rule?.toString().split("{")[0].trim()}:${decl.prop}:${decl.value}`);
      });
      return result;
    }
    expect(otherGlobals(shippedCss)).toEqual(otherGlobals(baseCss));
    for (const theme of THEMES) {
      const before = tokens(baseCss, theme), after = tokens(shippedCss, theme);
      expect(Object.keys(after).filter(r => r.startsWith("--state-")).sort()).toEqual([...ROOTS].sort());
      expect(Object.keys(after).filter(r => !r.startsWith("--state-")).sort()).toEqual(Object.keys(before).sort());
      for (const [root, value] of Object.entries(before)) {
        // Identical expressions include backgrounds, alpha colors, shadows,
        // fonts and computed aliases. Changed color syntax must resolve equally.
        if (theme === "Veil" && VEIL_ANCHOR_TOKENS.includes(root))
          rgb(after[root]).forEach((v, i) => expect(v, `${theme} anchor exemption ${root}`).toBeCloseTo(ANCHOR[i], 12));
        else if (value !== after[root])
          rgb(after[root]).forEach((v, i) => expect(v, `${theme} frozen ${root}`).toBeCloseTo(rgb(value)[i], 12));
      }
    }
  });
  it("state_surfaces_read_only_state_tokens", () => {
    // Closure by class identity, not by an exact selector allowlist. Pin
    // fill/ring classes occur on both surfaces; leaders have their own class.
    const surfaces = new Set(["map-pin", "map-state-glyph", "map-state-fill", "map-state-ring", "map-pin-leader", "map-place-dot", "key-status", "key-glyph-optional-absent", "key-glyph-required-missing", "key-glyph-present", "key-glyph-verified", "mem-fill", "mem-over-glyph", "lm-trash"]);
    const mentionsSurface = (selector: string) => [...selector.matchAll(/\.([a-zA-Z_-][a-zA-Z0-9_-]*)/g)].some(m => surfaces.has(m[1]));
    const colorProperty = (prop: string) => /^(?:color|fill|stroke|background(?:$|-)|border(?:$|-.*color$)|outline(?:$|-color$)|box-shadow|text-shadow|filter$)/.test(prop);
    const files: { path: string; source: string }[] = [];
    function sweep(dir: string): void {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const path = resolve(dir, entry.name);
        if (entry.isDirectory()) { sweep(path); continue; }
        if (/\.(css|tsx?)$/.test(path) && !path.includes(".test.")) files.push({ path, source: readFileSync(path, "utf8") });
      }
    }
    sweep(import.meta.dirname);
    const css = files.filter(f => f.path.endsWith(".css")).map(f => ({ ...f, ast: postcss.parse(f.source) }));
    // Discover custom properties consumed by the closure, including transitive
    // dependencies. Definitions on ancestors are checked as well as overrides.
    const consumed = new Set<string>();
    const refs = (value: string) => [...value.matchAll(/var\(\s*(--[a-z0-9-]+)/g)].map(m => m[1]);
    for (const f of css) f.ast.walkRules(rule => {
      if (rule.selectors.some(mentionsSurface)) rule.walkDecls(decl => {
        if (colorProperty(decl.prop)) refs(decl.value).forEach(r => consumed.add(r));
      });
    });
    let size = -1;
    while (size !== consumed.size) {
      size = consumed.size;
      for (const f of css) f.ast.walkDecls(decl => {
        if (consumed.has(decl.prop)) refs(decl.value).forEach(r => consumed.add(r));
      });
    }
    function stateOnly(value: string, label: string): void {
      for (const ref of refs(value)) expect(ROOTS, `${label}: global dependency ${ref}`).toContain(ref);
      // After removing state references, only neutral colors and the numeric
      // syntax of shadow/color-mix expressions may remain. Literal pigments,
      // global var fallbacks and RGB/HSL functions fail this grammar.
      const neutral = value.replace(/var\(\s*--state-[a-z-]+\s*\)/g, "currentColor")
        .replace(/\b(?:currentColor|transparent|inherit|none|color-mix|in|srgb|drop-shadow)\b/g, "")
        .replace(/-?(?:\d*\.)?\d+(?:px|rem|em|%)?/g, "")
        .replace(/[\s(),/]+/g, "");
      expect(neutral, `${label}: non-state color ${value}`).toBe("");
    }
    for (const f of css) f.ast.walkRules(rule => {
      const members = rule.selectors.map(mentionsSurface);
      rule.walkDecls(decl => {
        const stateRefs = refs(decl.value).filter(r => r.startsWith("--state-"));
        // Theme declarations define pigments; they do not consume them.
        if (stateRefs.length) expect(members.every(Boolean), `${f.path}: ${rule.selector} outside state surfaces`).toBe(true);
        if ((members.some(Boolean) && colorProperty(decl.prop)) ||
          (decl.prop.startsWith("--") && consumed.has(decl.prop) && !ROOTS.includes(decl.prop)))
          stateOnly(decl.value, `${rule.selector} ${decl.prop}`);
      });
    });
    for (const { path, source } of files.filter(f => !f.path.endsWith(".css") && f.source.includes("--state-"))) {
      expect(path).toBe(resolve(import.meta.dirname, "components/nexus/MapPane.tsx"));
      expect(refs(source).filter(r => r.startsWith("--state-")).sort()).toEqual(Object.values(MAPPINGS.map).sort());
    }
    for (const theme of THEMES) for (const root of ROOTS) {
      const value = tokens(shippedCss, theme)[root];
      expect(value, root).not.toContain("var(");
      expect(() => rgb(value)).not.toThrow();
    }
    for (const cls of ["map-state-glyph", "map-state-fill", "map-state-ring", "map-pin-leader"])
      expect(mapSource).toContain(cls);
    const topbar = readFileSync(resolve(import.meta.dirname, "components/nexus/TopBar.tsx"), "utf8");
    const local = readFileSync(resolve(import.meta.dirname, "components/nexus/LocalModelRows.tsx"), "utf8");
    const keys = readFileSync(resolve(import.meta.dirname, "components/nexus/SettingsPane.tsx"), "utf8");
    expect(topbar).toContain('className={`mem-fill');
    expect(topbar).toContain('className="mem-over-glyph"');
    expect(local).toContain('className={`lm-trash');
    expect(keys).toContain('className={`key-status ${status}`}');
    expect(mapSource.match(/<MapStateGlyph/g)).toHaveLength(2);
    expect(mapSource).toContain("color={PIN_COLOR[state]}");
    expect(mapSource).toContain("color={pinColor}");
    expect(mapSource).toContain("const pinColor = PIN_COLOR[state]");
    expect(mapSource).toContain('stroke={PIN_COLOR[pinState(place)]}');
    expect(shippedCss + layoutCss + mapSource).not.toContain("--map-hovered");
  });
  it("veil_anchor_is_exact_b83d7a", () => {
    const veil = tokens(shippedCss, "Veil");
    for (const root of VEIL_ANCHOR_TOKENS)
      rgb(veil[root]).forEach((v, i) => expect(v).toBeCloseTo(ANCHOR[i], 12));
  });
});
