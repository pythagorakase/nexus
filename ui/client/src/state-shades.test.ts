import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import postcss from "postcss";
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
const THEMES = ["Veil", "Gilded", "Vector"] as const;
type Theme = typeof THEMES[number];
function tokens(css: string, theme: Theme): Record<string, string> {
  const result: Record<string, string> = {};
  postcss.parse(css).walkRules(rule => {
    const matches = theme === "Veil" ? rule.selector === ".dark" : rule.selector.includes(`.dark.theme-${theme.toLowerCase()}`);
    if (matches)
      rule.walkDecls(decl => { result[decl.prop] = decl.value; });
  });
  return result;
}
function hsl(value: string): Triple {
  const match = value.match(/(?:hsl\()?([\d.]+)\s+([\d.]+)%\s+([\d.]+)%/);
  if (!match)
    throw new Error(`Not HSL: ${value}`);
  return match.slice(1, 4).map(Number) as unknown as Triple;
}
const ANCHOR: Triple = [184 / 255, 61 / 255, 122 / 255];
// Exact anchor HSL: H=330.2439024390244, S=50.20408163265306, L=48.03921568627451.
const ANCHOR_HUE = 330.2439024390244;
function candidates(theme: Theme, root: string): {
  hsl: Triple | "#b83d7a";
  rgb: Triple;
  lab: Triple;
}[] {
  if (theme === "Veil" && root === "--brass")
    return [{ hsl: "#b83d7a", rgb: ANCHOR, lab: deutanLab(ANCHOR) }];
  let [h, s, l] = hsl(tokens(baseCss, theme)[root === "--map-hovered" ? "--brass-bright" : root]);
  if (theme === "Veil" && ["--brass-bright", "--map-hovered"].includes(root))
    h = ANCHOR_HUE;
  const sats = new Set(root === "--destructive" ? [80, 90, 100] : [s, Math.min(100, s + 10), Math.min(100, s + 20)]);
  const lights = new Set(root === "--destructive" ? [50, 55, 60, 65] : [l, 30, 40, 50, 60, 70]);
  return [...sats].flatMap(s => [...lights].map(l => {
    const value: Triple = [h, s, l];
    const rgb = hslRgb(value);
    return { hsl: value, rgb, lab: deutanLab(rgb) };
  }));
}
const pairs = (states: readonly string[]) => states.flatMap((a, i) => states.slice(i + 1).map(b => [a, b] as const));
// Complete base inventory: 14 pairs per theme, before production opacity contexts.
export const STATE_PAIRS = {
  memory: pairs(["normal", "over"]),
  delete: pairs(["unarmed", "armed"]),
  map: pairs(["rest", "current", "selected", "hovered"]),
  key: pairs(["optional-absent", "required-missing", "present", "verified"]),
};
const MAP_STATES = ["rest", "current", "selected", "hovered"] as const;
const MAP_ROOTS = ["--bronze", "--brass-bright", "--brass", "--map-hovered"] as const;
export function mapSearch(theme: Theme) {
  const domains = MAP_ROOTS.map(root => candidates(theme, root));
  // Opaque fills fully cover their backdrop, so no background root can
  // affect this subset. Sea, land and sidebar fills share this same result.
  const edge = (i: number, j: number, a: number, b: number) => ciede2000(domains[i][a].lab, domains[j][b].lab);
  const maxima = pairs(["0", "1", "2", "3"]).map(([is, js]) => {
    const i = Number(is), j = Number(js);
    let maximum = -Infinity;
    let witness = [0, 0];
    for (let a = 0; a < domains[i].length; a++)
      for (let b = 0; b < domains[j].length; b++) {
        const value = edge(i, j, a, b);
        if (value > maximum) {
          maximum = value;
          witness = [a, b];
        }
      }
    return { pair: [MAP_ROOTS[i], MAP_ROOTS[j]], states: [MAP_STATES[i], MAP_STATES[j]], maximum, count: domains[i].length * domains[j].length,
      witness: [domains[i][witness[0]].hsl, domains[j][witness[1]].hsl] };
  });
  let total = 0, feasible = 0, best = -Infinity;
  let bestWitness: number[] = [];
  for (let a = 0; a < domains[0].length; a++)
    for (let b = 0; b < domains[1].length; b++)
      for (let c = 0; c < domains[2].length; c++)
        for (let d = 0; d < domains[3].length; d++) {
          total++;
          const ix = [a, b, c, d];
          const minimum = Math.min(...maxima.map((m, k) => {
            const [i, j] = [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]][k];
            // Only pairs whose individual maximum reaches 15 are mandatory.
            return m.maximum >= 15 ? edge(i, j, ix[i], ix[j]) : Infinity;
          }));
          if (minimum >= 15)
            feasible++;
          if (minimum > best) {
            best = minimum;
            bestWitness = ix;
          }
        }
  return { theme, sizes: domains.map(d => d.length), total, feasible, best,
    bestWitness: bestWitness.map((i, root) => domains[root][i].hsl),
    bestWitnessRgb: bestWitness.map((i, root) => domains[root][i].rgb),
    bestWitnessPairs: maxima.map((m, k) => {
      const [i, j] = [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]][k];
      return { states: m.states, delta: edge(i, j, bestWitness[i], bestWitness[j]) };
    }), maxima };
}
const layoutCss = readFileSync(resolve(import.meta.dirname, "components/nexus/nexus-layout.css"), "utf8");
const mapSource = readFileSync(resolve(import.meta.dirname, "components/nexus/MapPane.tsx"), "utf8");
function declaration(selector: string, property: string): string {
  let result: string | undefined;
  postcss.parse(layoutCss).walkRules(rule => {
    if (rule.selector.split(",").map(s => s.trim()).includes(selector)) {
      rule.walkDecls(property, decl => { result = decl.value; });
    }
  });
  if (!result) throw new Error(`Missing production declaration ${selector}: ${property}`);
  return result;
}
function rootOf(value: string): string {
  const match = value.match(/var\((--[a-z-]+)\)/);
  if (!match) throw new Error(`Missing production token: ${value}`);
  const root = match[1];
  return ["--danger", "--warning"].includes(root)
    ? rootOf(declaration(".settings-pane-v2", root)) : root;
}
function productionMapRoots(): Record<string, string> {
  const block = mapSource.match(/const PIN_COLOR[^=]*=\s*\{([^}]+)\}/)?.[1];
  if (!block) throw new Error("Missing production pin mapping");
  return Object.fromEntries(MAP_STATES.map(state => {
    const value = block.match(new RegExp(`${state}:\\s*"([^"]+)"`))?.[1];
    if (!value) throw new Error(`Missing production mapping: ${state}`);
    return [state, rootOf(value)];
  }));
}
function baseMeasurements(theme: Theme) {
  const values = tokens(shippedCss, theme);
  const mappings: Record<keyof typeof STATE_PAIRS, Record<string, string>> = {
    memory: {
      normal: rootOf(declaration(".topbar .mem-fill", "background")),
      over: rootOf(declaration(".topbar .mem-fill.over", "background")),
    },
    delete: {
      unarmed: rootOf(declaration(".lm-trash", "color")),
      armed: rootOf(declaration(".lm-trash.armed", "color")),
    },
    // Actual unchanged production mapping: hovered still aliases current.
    map: productionMapRoots(),
    key: {
      "optional-absent": rootOf(declaration(".key-status", "color")),
      "required-missing": rootOf(declaration(".key-row.missing .key-status", "color")),
      present: rootOf(declaration(".key-status.present", "color")),
      verified: rootOf(declaration(".key-status.verified", "color")),
    },
  };
  return (Object.keys(STATE_PAIRS) as (keyof typeof STATE_PAIRS)[]).flatMap(surface => STATE_PAIRS[surface].map(([first, second]) => {
    const roots = [mappings[surface][first], mappings[surface][second]];
    const rgb = roots.map(root => hslRgb(hsl(values[root])));
    return { theme, surface, states: [first, second], roots, rgb,
      delta: ciede2000(deutanLab(rgb[0]), deutanLab(rgb[1])) };
  }));
}
describe("777-S2 numerical preflight", () => {
  it("ciede2000_matches_published_reference_vectors", () => {
    expect(SHARMA).toHaveLength(34);
    for (const [l1, a1, b1, l2, a2, b2, expected] of SHARMA) {
      expect(Math.abs(ciede2000([l1, a1, b1], [l2, a2, b2]) - expected)).toBeLessThan(.00005);
    }
  });
  it("declares_all_14_base_pairs", () => {
    expect(Object.values(STATE_PAIRS).flat()).toHaveLength(14);
    for (const theme of THEMES)
      expect(tokens(shippedCss, theme)["--brass"]).toBeDefined();
  });
  it("records_the_complete_opaque_base_inventory_without_claiming_opacity_proof", () => {
    const results = THEMES.flatMap(baseMeasurements);
    expect(results).toHaveLength(42);
    if (process.env.STATE_SHADES_EVIDENCE_DIR) {
      writeFileSync(resolve(process.env.STATE_SHADES_EVIDENCE_DIR, "base-measurements.json"), JSON.stringify(results, null, 2) + "\n");
    }
  });
  it("exhausts_the_joint_map_fill_domain_before_product_changes", () => {
    for (const theme of THEMES) {
      const result = mapSearch(theme);
      console.log(JSON.stringify(result));
      if (process.env.STATE_SHADES_EVIDENCE_DIR) {
        writeFileSync(resolve(process.env.STATE_SHADES_EVIDENCE_DIR, `${theme.toLowerCase()}-search.json`), JSON.stringify(result, null, 2) + "\n");
      }
      if (theme === "Vector") {
        expect(result.sizes).toEqual([12, 15, 5, 15]);
        expect(result.maxima.every(pair => pair.maximum >= 15)).toBe(true);
        expect(result.feasible).toBe(0);
        expect(result.best).toBeLessThan(15);
        expect(result.best).toBeCloseTo(12.49178898372119, 12);
      }
      expect(result.total).toBe(result.sizes.reduce((a, b) => a * b, 1));
    }
  });
});
