import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import postcss from "postcss";
import { decodePng, foreground } from "../../scripts/state-surfaces/png.mjs";
import { inputs } from "../../scripts/state-surfaces/inputs.mjs";
import { describe, expect, it } from "vitest";
import { ciede2000, deutanLinearLab, hslRgb, type Triple } from "./state-shades-measurement";
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
// Thirteen reachable pairs. Optional-absent/required-missing has no shared row context.
const STATE_PAIRS = {
  memory: pairwise(["normal", "over"]),
  delete: pairwise(["unarmed", "armed"]),
  map: pairwise(["rest", "current", "selected", "hovered"]),
  key: pairwise(["optional-absent", "required-missing", "present", "verified"]).filter(([a, b]) => !(a === "optional-absent" && b === "required-missing")),
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
type Sample = {
  meanLinear: [number, number, number]; maskSize: number; coreSize: number;
  controlMeanLinear: [number, number, number]; effectiveOpacity: number; mapPart: string | null;
  histogram: { rgb: number[]; count: number }[]; width: number; height: number;
  action: string; animationsRunning: number;
  settleCriteria: { tooltipExpected: string; tooltipState: string | null;
    tooltipPresent: boolean; scope: string; animations: string; pseudoClasses: string };
  pseudos: { pinHover: boolean; hover: boolean; focusVisible: boolean; ancestorHover: boolean; focusWithin: boolean };
  target: { hover: boolean; focusVisible: boolean };
  stateAttributes: { mapState: string | null; keyNeed: string | null; armed: string | null };
};
type ContextSamples = Record<string, Record<string, Sample>>;
type Receipt = {
  inputs: Awaited<ReturnType<typeof inputs>>;
  media: { preludes: string[]; unsupported: string[]; variants: { id: string }[] };
  proof: { coreThreshold: number; calibration: Record<Theme, {
    condition: string; pigments: Record<Surface, string>; samples: ContextSamples;
    groups: Record<Surface, { opaqueMaximum: number; translucentMaximum: number;
      pairs: { context: string; states: string[]; opacity: string; delta: number; backdropDelta: number }[];
      skippedPairs: { context: string; states: string[]; reason: string; backdropDelta?: number }[] }>;
    requiredPairs: { context: string; states: string[]; opacity: string }[];
    tolerances: { opaque: number; translucent: number; backdrop: number }; passed: boolean;
  }>; acceptanceComplete: boolean; minimumMaskPixels: number; measurement: string; renderCount: number; wallSeconds: number; pageErrors: string[]; networkRequests: string[] };
  conditions: Record<string, Record<Theme, {
    shipped: ContextSamples; before: ContextSamples; fonts: Record<string, { family: string; status: string }[]>;
    candidates: Record<string, Record<string, Record<string, Sample>>>;
  }>>;
};
const receiptPath = resolve(import.meta.dirname, "state-surfaces.resolved.json");
let receipt: Receipt;
try { receipt = JSON.parse(readFileSync(receiptPath, "utf8")) as Receipt; }
catch (error) {
  if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  throw new Error("Missing browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).");
}
const currentInputs = JSON.parse(execFileSync(process.execPath,
  [resolve(import.meta.dirname, "../../scripts/state-surfaces/inputs.mjs"), resolve(import.meta.dirname, "../..")], { encoding: "utf8" }));
if (JSON.stringify(currentInputs) !== JSON.stringify(receipt.inputs))
  throw new Error("Stale browser-resolved state surfaces: run npm --prefix ui run resolve-state-surfaces (see ui/scripts/state-surfaces/README.md).");
if (receipt.proof.acceptanceComplete !== true)
  throw new Error("Incomplete painted state surfaces: filtered/probe captures are not acceptance receipts.");
const painted = (sample: Sample): Triple => sample.meanLinear;
// No DOM/cascade/compositing model: only browser-painted candidate captures.
const contextInventory = [
  { name: "memory/fill", pseudoState: "none" },
  ...["ready", "ready-exceeds"].flatMap(row => ["rest", "row-hover", "button-hover", "focus-visible"].map(action => ({ name: `delete/${row}/${action}`, pseudoState: action === "rest" ? "none" : action }))),
  ...["required", "optional"].flatMap(need => ["rest", "hover", "focus-visible"].map(action => ({ name: `key/${need}/${action}`, pseudoState: action === "rest" ? "none" : action === "hover" ? "row-hover" : action }))),
  ...["sea", "land"].flatMap(terrain => ["fill", "ring"].map(part => ({ name: `map/canvas-${terrain}/${part}`, pseudoState: "pin-hover" }))),
  ...["rest", "hover", "selected-current"].flatMap(action => ["fill", "ring"].map(part => ({ name: `map/sidebar/${action}/${part}`, pseudoState: action === "hover" ? "row-hover" : "pin-hover" }))),
];
const contextNames = contextInventory.map(c => c.name);

function statesIn(context: string): string[] {
  const surface = context.split("/")[0] as Surface;
  return Object.keys(MAPPINGS[surface]).filter(state =>
    !(context.startsWith("map/sidebar/hover/") && state === "hovered") &&
    !(context.startsWith("key/required/") && state === "optional-absent") &&
    !(context.startsWith("key/optional/") && state === "required-missing"));
}
const pairsIn = (context: string) => STATE_PAIRS[context.split("/")[0] as Surface]
  .filter(pair => pair.every(state => statesIn(context).includes(state)));
const CONTEXTS = receipt.media.variants.flatMap(({ id: condition }) => contextNames.map(context => {
  const [surface, ...name] = context.split("/");
  return { surface: surface as Surface, name: name.join("/"), condition,
    render(state: string, p: Palette | undefined, before: boolean, theme: Theme): Triple {
      const data = receipt.conditions[condition][theme];
      if (!p) return painted(data[before ? "before" : "shipped"][context][state]);
      const root = MAPPINGS[surface as Surface][state];
      const candidate = candidates(theme, root).find(c => c.rgb.every((v, i) => Math.abs(v - p[root][i]) < 1e-12));
      if (!candidate) throw new Error(`Candidate outside domain: ${theme}/${root}`);
      return painted(data.candidates[root][candidate.value][context]);
    } };
}));
// Rings enter their pulsing states independently. Every motion pair uses
// the Cartesian product of both recorded phases, within the same media band.
function phaseColors(ctx: typeof CONTEXTS[number], state: string, p: Palette | undefined, before: boolean, theme: Theme): Triple[] {
  const phases = ctx.condition.match(/\/motion\/(start|trough)$/)
    ? CONTEXTS.filter(c => c.surface === ctx.surface && c.name === ctx.name &&
      c.condition.replace(/\/(start|trough)$/, "") === ctx.condition.replace(/\/(start|trough)$/, "")) : [ctx];
  return phases.map(c => c.render(state, p, before, theme));
}
function pairColors(ctx: typeof CONTEXTS[number], states: readonly string[], p: Palette | undefined, before: boolean, theme: Theme): Triple[] {
  const first = phaseColors(ctx, states[0], p, before, theme), second = phaseColors(ctx, states[1], p, before, theme);
  let minimum = Infinity, colors: Triple[] = [];
  for (const a of first) for (const b of second) {
    const delta = ciede2000(deutanLinearLab(a), deutanLinearLab(b));
    if (delta < minimum) { minimum = delta; colors = [a, b]; }
  }
  return colors;
}
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
  return CONTEXTS.flatMap(ctx => pairsIn(`${ctx.surface}/${ctx.name}`).map(states => {
    const colors = pairColors(ctx, states, p, before, theme);
    return { theme, surface: ctx.surface, context: ctx.name, condition: ctx.condition, states, rgb: colors, delta: ciede2000(deutanLinearLab(colors[0]), deutanLinearLab(colors[1])), signatures: states.map(s => SIGNATURES[ctx.surface][s]) };
  }));
}
/** Exact exhaustive factorization: fixed global backgrounds mean that the
 * four surfaces share no mutable pigment. Each pair/context matrix visits all
 * candidate pairs; each surface then visits its complete Cartesian product.
 * Amendment 4 accepts each group independently at 15 when reachable, otherwise
 * its own maximum; ties within that group go to the fewest changed tokens.
 * BigInt counts retain the exact size of the twelve-token Cartesian domain.
 */
function jointSearch(theme: Theme) {
  const domains = Object.fromEntries(ROOTS.map(r => [r, candidates(theme, r)]));
  const p = palette(shippedCss, theme);
  const maxima: Record<string, { maximum: number; count: number; witness: Record<string, string> }> = {};
  const factors = (Object.keys(STATE_PAIRS) as Surface[]).map(surface => {
    const roots = Object.values(MAPPINGS[surface]);
    const ctxs = CONTEXTS.filter(c => c.surface === surface);
    const edges = STATE_PAIRS[surface].filter(pair => ctxs.some(ctx => pairsIn(`${surface}/${ctx.name}`).some(p => p.join() === pair.join()))).map(([a, b]) => {
      const ra = MAPPINGS[surface][a], rb = MAPPINGS[surface][b];
      const scores = domains[ra].map(() => domains[rb].map(() => Infinity));
      for (const ctx of ctxs.filter(c => [a, b].every(s => statesIn(`${surface}/${c.name}`).includes(s)))) {
        const labs = [a, b].map(state => {
          const root = MAPPINGS[surface][state];
          return domains[root].map(c => { p[root] = c.rgb; return phaseColors(ctx, state, p, false, theme).map(deutanLinearLab); });
        });
        let maximum = -Infinity, witness: Record<string, string> = {};
        let count = 0;
        for (let i = 0; i < domains[ra].length; i++)
          for (let j = 0; j < domains[rb].length; j++) {
            count++;
            const delta = Math.min(...labs[0][i].flatMap(a => labs[1][j].map(b => ciede2000(a, b))));
            scores[i][j] = Math.min(scores[i][j], delta);
            if (delta > maximum) { maximum = delta; witness = { [ra]: domains[ra][i].value, [rb]: domains[rb][j].value }; }
          }
        maxima[`${ctx.condition}/${surface}/${ctx.name}/${a}/${b}`] = { maximum, count, witness };
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
  const chosen = factors.map(f => f.entries.filter(e => e.minimum >= Math.min(15, f.best)).sort((a, b) => a.changed - b.changed || b.minimum - a.minimum)[0]);
  const assignment = Object.assign({}, ...chosen.map(e => Object.fromEntries(Object.entries(e.ix).map(([r, i]) => [r, domains[r][i].value])))) as Record<string, string>;
  const shipped = { ...palette(shippedCss, theme), ...Object.fromEntries(ROOTS.map(r => [r, rgb(assignment[r])])) };
  return {
    theme, sizes: ROOTS.map(r => domains[r].length),
    count: ROOTS.reduce((n, r) => n * BigInt(domains[r].length), 1n).toString(),
    feasible: factors.reduce((n, f) => n * BigInt(f.entries.filter(e => e.minimum >= 15).length), 1n).toString(),
    best, changes: chosen.reduce((n, e) => n + e.changed, 0), assignment,
    coverage: factors.map(f => f.coverage), factorMaxima: factors.map(f => ({ surface: f.coverage.surface, best: f.best, threshold: Math.min(15, f.best), feasible: f.entries.filter(e => e.minimum >= 15).length, shippedMinimum: chosen[factors.indexOf(f)].minimum, changes: chosen[factors.indexOf(f)].changed })),
    maxima, measurements: measures(theme, shipped, false),
  };
}
let searches: ReturnType<typeof jointSearch>[] | undefined;
const searchAll = () => searches ??= THEMES.map(jointSearch);
// Explicit one-theme exception manifests; the context inventory is fixed above,
// while shortfall IDs are committed and checked below.
const exceptions = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../../docs/qa/777-glyph-first-states/amendment-2/theme-exceptions.json"), "utf8")) as Record<Theme, string[]>;
function assertStateDeclaration(decl: postcss.Declaration, path: string): void {
  if (!decl.prop.startsWith("--state-")) return;
  const rule = decl.parent;
  const themeRoots = [".dark", ".dark.theme-gilded", ".theme-gilded .dark", ".dark.theme-vector", ".theme-vector .dark"];
  expect(path === resolve(import.meta.dirname, "index.css") && rule?.type === "rule" &&
    rule.parent?.type === "root" && rule.selectors.every(s => themeRoots.includes(s)),
    `${path}: ${decl.prop} must be declared in an index.css theme root`).toBe(true);
}
describe("777-S2 state shades", () => {
  it("tooltip_gradient_uses_the_90_percent_core_in_linear_light_without_a_mode_floor", () => {
    const dir = resolve(import.meta.dirname, "../../../docs/qa/777-glyph-first-states/after-review-r4/absolute-floor");
    const paintedBytes = readFileSync(resolve(dir, "tooltip-repeat-1-painted.png"));
    const controlBytes = readFileSync(resolve(dir, "tooltip-repeat-1-control.png"));
    const sample = foreground(paintedBytes, controlBytes, "tooltip regression");
    const a = decodePng(paintedBytes), b = decodePng(controlBytes);
    const sums = [0, 0, 0]; let count = 0;
    const mask: { color: number[]; difference: number }[] = [];
    const linear = (v: number) => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; };
    for (let i = 0; i < a.pixels.length; i += a.channels) {
      if (a.pixels.subarray(i, i + a.channels).equals(b.pixels.subarray(i, i + b.channels))) continue;
      count++;
      const color = [0, 1, 2].map(c => linear(a.pixels[i + c]));
      mask.push({ color, difference: Math.hypot(...color.map((v, c) => v - linear(b.pixels[i + c]))) });
    }
    const maximum = Math.max(...mask.map(p => p.difference));
    const core = mask.filter(p => p.difference >= .9 * maximum);
    for (const p of core) p.color.forEach((v, c) => sums[c] += v);
    expect(sample.coreSize).toBe(core.length);
    expect(sample.maskSize).toBe(727);
    expect(sample.histogram[0].count).toBe(44);
    expect(sample.histogram.reduce((n, bucket) => n + bucket.count, 0)).toBeLessThan(count);
    sums.forEach((sum, channel) => expect(sample.meanLinear[channel]).toBeCloseTo(sum / core.length, 14));
    expect(() => foreground(controlBytes, controlBytes, "empty context")).toThrow("empty context: empty foreground mask");
  });

  it("identical_pigment_calibration_compares_like_parts_and_opacity_with_non_vacuous_coverage", () => {
    expect(Object.keys(receipt.proof.calibration)).toEqual([...THEMES]);
    for (const theme of THEMES) {
      const calibration = receipt.proof.calibration[theme];
      expect(calibration.passed).toBe(true);
      expect(calibration.tolerances).toEqual({ opaque: 1, translucent: 2.5, backdrop: 1 });
      expect(Object.keys(calibration.samples)).toEqual(contextNames);
      const maxima = Object.fromEntries(Object.keys(MAPPINGS).map(group => [group, { opaque: 0, translucent: 0 }]));
      for (const context of contextNames) {
        const samples = calibration.samples[context];
        expect(Object.keys(samples)).toEqual(statesIn(context));
        const group = context.split('/')[0] as Surface, record = calibration.groups[group];
        const states = Object.keys(samples);
        for (let i = 0; i < states.length; i++) for (let j = i + 1; j < states.length; j++) {
          const pair = [states[i], states[j]], [a, b] = pair.map(s => samples[s]);
          const find = <T extends { context: string; states: string[] }>(list: T[]) =>
            list.find(p => p.context === context && p.states.join('/') === pair.join('/'));
          if (a.mapPart !== b.mapPart) {
            expect(find(record.skippedPairs)?.reason).toBe('part-distinct'); continue;
          }
          const opacity = a.effectiveOpacity === 1 && b.effectiveOpacity === 1 ? 'opaque' : 'translucent';
          const backdropDelta = ciede2000(deutanLinearLab(a.controlMeanLinear), deutanLinearLab(b.controlMeanLinear));
          if (opacity === 'translucent' && backdropDelta > 1) {
            expect(find(record.skippedPairs)?.reason).toBe('backdrop-distinct');
            expect(find(record.skippedPairs)?.backdropDelta).toBe(backdropDelta); continue;
          }
          const delta = ciede2000(deutanLinearLab(a.meanLinear), deutanLinearLab(b.meanLinear));
          expect(find(record.pairs)).toMatchObject({ opacity, delta, backdropDelta });
          expect(delta, `${theme}/${context}/${pair.join('/')}: identical pigment`).toBeLessThanOrEqual(calibration.tolerances[opacity]);
          maxima[group][opacity] = Math.max(maxima[group][opacity], delta);
        }
      }
      for (const group of Object.keys(MAPPINGS) as Surface[]) {
        expect(calibration.groups[group].opaqueMaximum).toBe(maxima[group].opaque);
        expect(calibration.groups[group].translucentMaximum).toBe(maxima[group].translucent);
        expect(calibration.groups[group].pairs.some(p => p.opacity === 'opaque')).toBe(true);
      }
      const required = [
        ...['required', 'optional'].map(need => ({ context: `key/${need}/rest`, states: ['present', 'verified'], opacity: need === 'optional' ? 'translucent' : 'opaque' })),
        ...['sea', 'land'].flatMap(terrain => ['current', 'selected', 'hovered'].map(state => ({ context: `map/canvas-${terrain}/fill`, states: ['rest', state], opacity: 'opaque' }))),
        ...['current', 'selected', 'hovered'].map(state => ({ context: 'map/sidebar/rest/fill', states: ['rest', state], opacity: 'opaque' })),
      ];
      expect(calibration.requiredPairs).toEqual(required);
      expect(Object.keys(calibration.pigments).sort()).toEqual(Object.keys(MAPPINGS).sort());
    }
  });
  it("ciede2000_matches_published_reference_vectors", () => {
    expect(SHARMA).toHaveLength(34);
    for (const [l1, a1, b1, l2, a2, b2, expected] of SHARMA)
      expect(Math.abs(ciede2000([l1, a1, b1], [l2, a2, b2]) - expected)).toBeLessThan(.00005);
  });
  it("every_state_pair_is_measured_under_every_declared_media_condition", () => {
    expect(Object.values(STATE_PAIRS).flat()).toHaveLength(13);
    expect(receipt.media.unsupported, "Unemulatable media/container prelude").toEqual([]);
    expect(Object.keys(receipt.conditions)).toEqual(receipt.media.variants.map(v => v.id));
    expect(receipt.media.preludes.length).toBeGreaterThan(0);
    expect(receipt.inputs.conditions.deviceScaleFactor).toBe(4);
    expect(receipt.proof.pageErrors).toEqual([]);
    expect(receipt.proof.networkRequests).toEqual([]);
    for (const theme of THEMES) for (const { id } of receipt.media.variants) {
      for (const faces of Object.values(receipt.conditions[id][theme].fonts)) {
        expect(faces.some(f => f.status === "loaded")).toBe(true);
        expect(faces.some(f => f.status === "error")).toBe(false);
      }
      for (const phase of ["before", "shipped"] as const) {
        const contexts = receipt.conditions[id][theme][phase];
        expect(Object.keys(contexts)).toEqual(contextNames);
        for (const context of contextNames) {
          expect(Object.keys(contexts[context])).toEqual(statesIn(context));
        }
      }
      expect(measures(theme, undefined, false).filter(m => m.condition === id)).toHaveLength(contextNames.reduce((n, c) => n + pairsIn(c).length, 0));
    }
  });
  it("painted_mask_means_are_linear_and_interactions_are_real_and_settled", () => {
    expect(receipt.proof.minimumMaskPixels).toBe(16);
    expect(receipt.proof.coreThreshold).toBe(.9);
    expect(receipt.proof.measurement).toContain("mean in linear sRGB");
    const check = (sample: Sample, context: string, state: string) => {
      expect(sample.maskSize, `${context}: surface did not paint`).toBeGreaterThanOrEqual(receipt.proof.minimumMaskPixels);
      expect(sample.coreSize).toBeGreaterThan(0);
      expect(sample.coreSize).toBeLessThanOrEqual(sample.maskSize);
      expect(sample.meanLinear).toHaveLength(3);
      for (const channel of sample.meanLinear) {
        expect(Number.isFinite(channel)).toBe(true);
        expect(channel).toBeGreaterThanOrEqual(0);
        expect(channel).toBeLessThanOrEqual(1);
      }
      expect(sample.histogram.length).toBeGreaterThan(0);
      expect(sample.histogram.reduce((n, bucket) => n + bucket.count, 0)).toBeLessThanOrEqual(sample.maskSize);
      expect(sample.animationsRunning).toBe(0);
      expect(sample.settleCriteria.scope).toContain('overlapping/portalled siblings');
      expect(sample.settleCriteria.animations).toContain('all document animations finished');
      expect(sample.settleCriteria.pseudoClasses).toContain('read back');
      expect(sample.settleCriteria.tooltipPresent).toBe(sample.settleCriteria.tooltipExpected === 'open');
      if (sample.settleCriteria.tooltipExpected === 'open')
        expect(['delayed-open', 'instant-open']).toContain(sample.settleCriteria.tooltipState);
      const declared = contextInventory.find(c => c.name === context)!.pseudoState;
      const expected = declared === "pin-hover" && state !== "hovered" ? "none" : declared;
      expect(sample.target.focusVisible, `${context}: focus-visible`).toBe(expected === "focus-visible");
      expect(sample.pseudos.focusVisible).toBe(false); // sampled SVG/path/span is not the control
      expect(sample.pseudos.focusWithin).toBe(expected === "focus-visible");
      expect(sample.pseudos.pinHover).toBe(expected === "pin-hover");
      expect(sample.pseudos.ancestorHover).toBe(expected === "row-hover" || expected === "button-hover");
      if (expected !== "row-hover") expect(sample.target.hover).toBe(expected === "button-hover");
      if (expected === "none") expect(sample.pseudos.hover).toBe(false);
      if (expected === "focus-visible") expect(sample.action).toContain("Tab");

    };
    for (const { id } of receipt.media.variants) for (const theme of THEMES) {
      const data = receipt.conditions[id][theme];
      for (const phase of ["before", "shipped"] as const)
        for (const [context, samples] of Object.entries(data[phase])) Object.entries(samples).forEach(([state, s]) => {
          check(s, context, state);
          if (context.startsWith("map/")) {
            expect(s.stateAttributes.mapState).toBe(state);
            if (state === "hovered") expect(s.pseudos.pinHover).toBe(true);
          }
          if (context.startsWith("key/")) expect(s.stateAttributes.keyNeed).toBe(context.split("/")[1]);
          if (context.startsWith("delete/")) expect(s.stateAttributes.armed).toBe(state === "armed" ? "true" : "false");
        });
      for (const root of ROOTS) {
        expect(Object.keys(data.candidates[root])).toEqual(candidates(theme, root).map(c => c.value));
        const group = Object.entries(MAPPINGS).find(([, states]) => Object.values(states).includes(root))![0];
        for (const samples of Object.values(data.candidates[root])) {
          expect(Object.keys(samples)).toEqual(contextNames.filter(c => c.startsWith(`${group}/`) && statesIn(c).includes(Object.entries(MAPPINGS[group as Surface]).find(([, r]) => r === root)![0])));
          for (const [context, sample] of Object.entries(samples)) check(sample, context, Object.entries(MAPPINGS[group as Surface]).find(([, r]) => r === root)![0]);
        }
      }
    }
  });
  it("same_value_has_exactly_the_same_settled_mask_mean", () => {
    for (const { id } of receipt.media.variants) for (const theme of THEMES) {
      const data = receipt.conditions[id][theme];
      for (const [context, states] of Object.entries(data.shipped)) for (const [state, shipped] of Object.entries(states)) {
        const root = MAPPINGS[context.split('/')[0] as Surface][state];
        const value = candidates(theme, root).find(c => c.rgb.every((v, i) => Math.abs(v - rgb(tokens(shippedCss, theme)[root])[i]) < 1e-12))!.value;
        const candidate = data.candidates[root][value][context];
        expect(candidate.meanLinear, `${id}/${theme}/${context}/${state}: same value`).toEqual(shipped.meanLinear);
        expect(candidate.maskSize).toBe(shipped.maskSize);
        expect(candidate.coreSize).toBe(shipped.coreSize);
        expect(candidate.settleCriteria.tooltipExpected).toBe(shipped.settleCriteria.tooltipExpected);
        expect(candidate.settleCriteria.tooltipPresent).toBe(shipped.settleCriteria.tooltipPresent);
      }
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
    if (process.env.STATE_SHADES_EVIDENCE_DIR) for (const result of results)
      writeFileSync(resolve(process.env.STATE_SHADES_EVIDENCE_DIR, `${result.theme.toLowerCase()}-joint.json`), JSON.stringify({ ...result, measurements: measures(result.theme, undefined, false), before: measures(result.theme, undefined, true) }, null, 2) + "\n");
    for (const result of results) {
      console.log(JSON.stringify({ ...result, maxima: undefined, measurements: undefined }));
      if (process.env.STATE_SHADES_EVIDENCE_DIR) writeFileSync(resolve(process.env.STATE_SHADES_EVIDENCE_DIR, `${result.theme.toLowerCase()}-joint.json`), JSON.stringify({ ...result, measurements: measures(result.theme, undefined, false), before: measures(result.theme, undefined, true) }, null, 2) + "\n");
      const actual = palette(shippedCss, result.theme);
      for (const root of ROOTS) expect(candidates(result.theme, root).some(c => c.rgb.every((v, i) => Math.abs(v - actual[root][i]) < 1e-12)), `${result.theme} ${root} outside domain`).toBe(true);
      const shipped = measures(result.theme, undefined, false);
      for (const factor of result.factorMaxima) {
        const minimum = Math.min(...shipped.filter(m => m.surface === factor.surface).map(m => m.delta));
        if (factor.feasible) expect(minimum, `${result.theme}/${factor.surface}: reachable group`).toBeGreaterThanOrEqual(15);
        else expect(minimum, `${result.theme}/${factor.surface}: group maximum`).toBeCloseTo(factor.best, 10);
        expect(minimum).toBeCloseTo(factor.shippedMinimum, 10);
      }
      // Every candidate assignment is independently painted, including its shipped witness.
      expect(result.measurements).toEqual(shipped);
      const shortfalls = shipped.filter(m => m.delta < 15);
      expect(exceptions[result.theme]).toEqual(shortfalls.map(m => `${m.condition}/${m.surface}/${m.context}/${m.states.join("/")}`));
      for (const factor of result.factorMaxima) expect(shortfalls.some(m => m.surface === factor.surface)).toBe(factor.feasible === 0);
      for (const m of shortfalls) expect(m.signatures[0]).not.toEqual(m.signatures[1]);
      expect(result.count).toBe(result.sizes.reduce((n, s) => n * BigInt(s), 1n).toString());
      expect(ROOTS.filter(root => actual[root].some((v, i) => Math.abs(v - rgb(baselineValue(result.theme, root))[i]) >= 1e-12))).toHaveLength(result.changes);
    }
  }, 120000);
  it("global_tokens_are_unchanged_from_baseline_including_compound_and_alpha_values", () => {
    const normalize = (v: string) => v.replace(/\s+/g, "");
    function otherGlobals(css: string, skipThemes: boolean, path: string): string[] {
      const result: string[] = [];
      postcss.parse(css).walkDecls(decl => {
        assertStateDeclaration(decl, path);
        if (!decl.prop.startsWith("--") || ROOTS.includes(decl.prop)) return;
        const rule = decl.parent;
        if (skipThemes && rule?.type === "rule" && rule.parent?.type === "root" &&
          (rule.selector === ".dark" || rule.selector.includes(".dark.theme-gilded") || rule.selector.includes(".dark.theme-vector"))) return;
        result.push(`${normalize(rule?.toString().split("{")[0] ?? "")}:${decl.prop}:${normalize(decl.value)}`);
      });
      return result;
    }
    expect(otherGlobals(shippedCss, true, resolve(import.meta.dirname, "index.css"))).toEqual(otherGlobals(baseCss, true, resolve(import.meta.dirname, "index.css")));
    const baseLayout = execFileSync("git", ["show", `${START}:ui/client/src/components/nexus/nexus-layout.css`], { encoding: "utf8" });
    expect(otherGlobals(layoutCss, false, resolve(import.meta.dirname, "components/nexus/nexus-layout.css"))).toEqual(otherGlobals(baseLayout, false, resolve(import.meta.dirname, "components/nexus/nexus-layout.css")));
    for (const theme of THEMES) {
      const before = tokens(baseCss, theme), after = tokens(shippedCss, theme);
      expect(Object.keys(after).filter(r => r.startsWith("--state-")).sort()).toEqual([...ROOTS].sort());
      expect(Object.keys(after).filter(r => !r.startsWith("--state-")).sort()).toEqual(Object.keys(before).sort());
      for (const [root, value] of Object.entries(before)) {
        if (theme === "Veil" && VEIL_ANCHOR_TOKENS.includes(root))
          rgb(after[root]).forEach((v, i) => expect(v).toBeCloseTo(ANCHOR[i], 12));
        else expect(normalize(after[root]), `${theme} frozen ${root}`).toBe(normalize(value));
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
        if (colorProperty(decl.prop) && !(rule.selector === ".topbar .mem-fill" && decl.prop === "box-shadow")) refs(decl.value).forEach(r => consumed.add(r));
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
        assertStateDeclaration(decl, f.path);
        if (rule.selector === ".topbar .mem-fill" && decl.prop === "box-shadow") {
          expect(decl.value).toBe("var(--glow-soft)"); return;
        }
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
    expect(mapSource).toContain("fill={LABEL_COLOR[state]}");
    const labelMap = mapSource.match(/const LABEL_COLOR[^=]*=\s*\{([^}]+)\}/)![1];
    expect(labelMap).not.toContain("--state-");
    for (const [state, value] of Object.entries({ current: "--brass-bright", selected: "--brass", hovered: "--brass-bright", rest: "--bronze" }))
      expect(labelMap).toContain(`${state}: "var(${value})"`);
    expect(mapSource).toContain('stroke={PIN_COLOR[pinState(place)]}');
    expect(shippedCss + layoutCss + mapSource).not.toContain("--map-hovered");
  });
  it("veil_anchor_is_exact_b83d7a", () => {
    const veil = tokens(shippedCss, "Veil");
    for (const root of VEIL_ANCHOR_TOKENS)
      rgb(veil[root]).forEach((v, i) => expect(v).toBeCloseTo(ANCHOR[i], 12));
  });
});
