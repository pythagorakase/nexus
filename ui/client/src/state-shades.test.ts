import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import postcss from "postcss";
import ts from "typescript";
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
const measuredRoots = new Set<string>();
function rootOf(value: string): string {
  const root = value.match(/var\((--[a-z-]+)\)/)?.[1];
  if (!root) throw new Error(`Missing production token ${value}`);
  measuredRoots.add(root);
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
type Context = { surface: Surface; name: string; render: (state: string, p: Palette, before: boolean, theme: Theme) => Triple };
// CSS interpolation/compositing is encoded sRGB (CSS `in srgb`), THEN the
// simulation linearizes. Interior fill/stroke samples exclude edge AA/glow.
function background(value: string, p: Palette, under?: Triple): Triple {
  if (value === "none" || value === "transparent") {
    if (!under) throw new Error("Transparent background needs parent");
    return under;
  }
  const mix = value.match(/^color-mix\(in srgb, var\((--[a-z0-9-]+)\) ([\d.]+)%, (.+)\)$/);
  if (mix) { measuredRoots.add(mix[1]); return composite(p[mix[1]], background(mix[3], p, under), Number(mix[2]) / 100); }
  const root = value.match(/^var\((--[a-z0-9-]+)\)$/)?.[1];
  if (root) { measuredRoots.add(root); if (!p[root]) throw new Error(`Unmodeled background token ${root}`); return p[root]; }
  return rgb(value);
}
// Trace real JSX ancestors, including SettingsCard's children slot. This is
// source inspection only: it cannot mount the key card or read the secret store.
const settingsSource = readFileSync(resolve(import.meta.dirname, "components/nexus/SettingsPane.tsx"), "utf8");
const localSource = readFileSync(resolve(import.meta.dirname, "components/nexus/LocalModelRows.tsx"), "utf8");
const productionTags = new Map<string, string>();
function jsxAncestors(source: string, marker: string, tag = false, full = false): string[][] {
  const ast = ts.createSourceFile("surface.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let target: ts.Node | undefined;
  function classes(node: ts.Node): string[] {
    if (!ts.isJsxElement(node) && !ts.isJsxSelfClosingElement(node)) return [];
    const opening = ts.isJsxElement(node) ? node.openingElement : node;
    const attr = opening.attributes.properties.find(a => ts.isJsxAttribute(a) && a.name.getText(ast) === "className");
    if (!attr || !ts.isJsxAttribute(attr) || !attr.initializer) return [];
    const init = attr.initializer;
    // The first literal is the unconditional class prefix in the shipped JSX.
    const value = ts.isStringLiteral(init) ? init.text : init.getText(ast).match(/[`"]([^`"$]+)[`"$]/)?.[1];
    const names = value?.trim().split(/\s+/) ?? [];
    const tagName = opening.tagName.getText(ast);
    if (/^[a-z]/.test(tagName)) for (const name of names) {
      productionTags.set(name, productionTags.has(name) && productionTags.get(name) !== tagName ? "ambiguous" : tagName);
    }
    return names;
  }
  function visit(node: ts.Node) {
    const opening = ts.isJsxElement(node) ? node.openingElement : ts.isJsxSelfClosingElement(node) ? node : undefined;
    if ((tag && opening?.tagName.getText(ast) === marker) || (!tag && classes(node).includes(marker))) {
      if (target) throw new Error(`Ambiguous production element ${marker}`);
      target = node;
    }
    ts.forEachChild(node, visit);
  }
  visit(ast);
  if (!target) throw new Error(`Missing production element ${marker}`);
  const result: string[][] = [];
  for (let node: ts.Node | undefined = target.parent; node; node = node.parent) {
    if (ts.isJsxElement(node) && node.openingElement.tagName.getText(ast) === "SettingsCard") {
      // Find the real insertion point rather than copying the wrapper classes.
      const slot = settingsSource.indexOf("{children}");
      const slotAst = ts.createSourceFile("card.tsx", settingsSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
      let child: ts.Node | undefined;
      function find(n: ts.Node) {
        if (ts.isJsxExpression(n) && n.getStart(slotAst) === slot) child = n;
        ts.forEachChild(n, find);
      }
      find(slotAst);
      if (!child) throw new Error("SettingsCard children slot changed");
      for (let n: ts.Node | undefined = child.parent; n; n = n.parent) {
        const names = classes(n);
        if (names.length) result.push(names);
        else if (full && ts.isJsxElement(n) && /^[a-z]/.test(n.openingElement.tagName.getText(slotAst))) result.push([`proof-tag-${n.openingElement.tagName.getText(slotAst)}`]);
      }
    } else {
      const names = classes(node);
      if (names.length) result.push(names);
      else if (full && ts.isJsxElement(node) && /^[a-z]/.test(node.openingElement.tagName.getText(ast))) result.push([`proof-tag-${node.openingElement.tagName.getText(ast)}`]);
    }
  }
  return result;
}
// Model both shipped theme roots, the production class ancestry and the
// measured interaction. Unsupported contexts fail closed before cascade lookup.
const shellSource = readFileSync(resolve(import.meta.dirname, "components/nexus/NexusLayout.tsx"), "utf8");
const topbarSource = readFileSync(resolve(import.meta.dirname, "components/nexus/TopBar.tsx"), "utf8");
const keyAncestors = [...jsxAncestors(settingsSource, "key-row", false, true), ...jsxAncestors(settingsSource, "KeysSection", true, true), ...jsxAncestors(shellSource, "SettingsPane", true, true)];
const deleteAncestors = [...jsxAncestors(localSource, "lm-quant", false, true), ...jsxAncestors(settingsSource, "LocalModelRows", true, true), ...jsxAncestors(settingsSource, "ModelSection", true, true), ...jsxAncestors(shellSource, "SettingsPane", true, true)];
const mapOuter = jsxAncestors(shellSource, "MapPane", true, true);
const sidebarAncestors = [...jsxAncestors(mapSource, "map-place-dot", false, true), ...mapOuter];
const canvasAncestors = [...jsxAncestors(mapSource, "mappane-svg", false, true), ...mapOuter];
const memoryAncestors = [...jsxAncestors(topbarSource, "mem-fill", false, true), ...jsxAncestors(topbarSource, "MemoryMeter", true, true), ...jsxAncestors(shellSource, "TopBar", true, true)];
const warningAncestors = [...jsxAncestors(topbarSource, "mem-over-glyph", false, true), ...jsxAncestors(topbarSource, "MemoryMeter", true, true), ...jsxAncestors(shellSource, "TopBar", true, true)];
const pinAncestors = [...jsxAncestors(mapSource, "map-pin", false, true), ...mapOuter];
const leaderAncestors = [...jsxAncestors(mapSource, "map-pin-leader", false, true), ...mapOuter];
const cssRules = [postcss.parse(shippedCss, { from: resolve(import.meta.dirname, "index.css") }), postcss.parse(layoutCss, { from: resolve(import.meta.dirname, "components/nexus/nexus-layout.css") })].flatMap(ast => {
  const rules: postcss.Rule[] = []; ast.walkRules(rule => { rules.push(rule); }); return rules;
});
const modeledClasses = new Set([...keyAncestors, ...deleteAncestors, ...sidebarAncestors, ...canvasAncestors, ...memoryAncestors, ...warningAncestors, ...pinAncestors, ...leaderAncestors].flat().concat([
  "dark", "theme-veil", "theme-gilded", "theme-vector", "key-row", "optional", "missing", "present", "verified", "key-status",
  "lm-quant", "ready", "exceeds", "blocked", "staged", "dl", "active", "loading", "required", "lm-action", "lm-trash", "armed", "mem-fill", "over", "mem-over-glyph",
  "map-pin", "map-state-glyph", "map-state-fill", "map-state-ring", "map-pin-leader", "map-place-dot", "on", "here", "animate-pulse",
  ...Object.keys(MAPPINGS.key).map(state => `key-glyph-${state}`),
]));
// Additional source stylesheets cannot silently add an unmeasured override.
// Their bundler order is outside this resolver's two-file model, so any rule
// that can affect these elements must be explicitly modeled before acceptance.
const unorderedRules = new Set<postcss.Rule>();
function otherStyles(dir: string): void {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = resolve(dir, entry.name);
    if (entry.isDirectory()) { otherStyles(path); continue; }
    if (!path.endsWith(".css") || [resolve(import.meta.dirname, "index.css"), resolve(import.meta.dirname, "components/nexus/nexus-layout.css")].includes(path)) continue;
    postcss.parse(readFileSync(path, "utf8"), { from: path }).walkRules(rule => { unorderedRules.add(rule); cssRules.push(rule); });
  }
}
otherStyles(import.meta.dirname);
let themeForm = "compound";
function model(ancestors: string[][], theme: Theme, interaction = "rest", form = themeForm): HTMLElement[] {
  const root = document.createElement("html");
  root.className = `proof-root ${form === "compound" ? "dark " : ""}theme-${theme.toLowerCase()}`;
  const body = document.createElement("body"); root.appendChild(body);
  const appRoot = document.createElement("div"); appRoot.id = "root"; body.appendChild(appRoot);
  // main.tsx mounts App/NexusLayout into #root. Context providers add no box.
  let parent: HTMLElement = appRoot;
  if (form === "descendant") parent.className = "dark";
  const nodes: HTMLElement[] = [];
  for (const classes of [...ancestors].reverse()) {
    const shape = classes.find(c => c.startsWith("proof-shape-"))?.slice("proof-shape-".length) ?? classes.find(c => c.startsWith("proof-tag-"))?.slice("proof-tag-".length) ?? (classes.some(c => c.startsWith("key-glyph-")) ? "svg" : undefined);
    const tags: Record<string, string> = { "lm-trash": "button", "lm-action": "span", "lm-quant": "li", "key-status": "span", "key-row": "li", "map-pin": "g", "map-state-glyph": "g", "mem-fill": "span", "mem-over-glyph": "svg", "map-pin-leader": "line", "map-place-dot": "svg" };
    const node = document.createElement(shape ?? classes.map(c => tags[c] ?? productionTags.get(c)).find(t => t && t !== "ambiguous") ?? "div"); node.className = classes.join(" ");
    if (interaction === "hover") node.classList.add("proof-hover");
    if (interaction === "focus") node.classList.add("proof-focus-within");
    parent.appendChild(node); parent = node; nodes.unshift(node);
  }
  modeledPaths.set(`${theme}/${form}/${interaction}/${ancestors.map(c => c.join(".")).join("/")}`, nodes);
  return nodes;
}
type Paint = { selector: string; value: string };
const modeledPaths = new Map<string, HTMLElement[]>();
const cascadeCache = new Map<string, Paint | undefined>();
function cascade(nodes: HTMLElement[], index: number, property: string): Paint | undefined {
  const node = nodes[index];
  const key = `${node.localName}.${node.className}:${Array.from(function* () { for (let n = node.parentElement; n; n = n.parentElement) yield n.className; }()).join("/")}:${property}`;
  if (cascadeCache.has(key)) return cascadeCache.get(key);
  let paint: (Paint & { specificity: number[] }) | undefined;
  for (const rule of cssRules) {
    const declarations = rule.nodes.filter((n): n is postcss.Declaration => n.type === "decl" &&
      (n.prop === property || (property === "background" && n.prop === "background-color")));
    if (!declarations.length) continue;
    for (const selector of rule.selectors) {
      // A separate scrollbar box does not paint any measured element.
      if (selector.includes("::-webkit-scrollbar")) continue;
      // Conservative potential match: unknown context cannot hide a rule whose
      // subject names this element (including classes inside functional pseudos).
      const subject = selector.replace(/\([^)]*\)/g, m => m.replace(/\s+/g, "")).split(/[ >+~]+/).at(-1)!;
      const subjectClasses = [...subject.matchAll(/\.([a-zA-Z_-][a-zA-Z0-9_-]*)/g)].map(m => m[1]);
      const generic = new Set(["on", "here", "ready", "exceeds", "optional", "missing", "present", "verified", "over", "armed"]);
      const potential = subjectClasses.length ? subjectClasses.some(c => !generic.has(c) && node.classList.contains(c)) || (subjectClasses.every(c => node.classList.contains(c)) && (!subject.match(/^([a-z][\w-]*)/) || subject.match(/^([a-z][\w-]*)/)![1] === node.localName)) : /^(?:\*|:)/.test(subject) || subject.match(/^([a-z][\w-]*)/)?.[1] === node.localName;
      if (!potential) continue;
      const label = `${rule.source?.input.file ?? "shipped CSS"}: ${rule.selector} { ${declarations.map(d => d.toString()).join("; ")} }`;
      function unsupported(reason: string): never { throw new Error(`Unmodeled ${reason}: ${label}`); }
      const identity = subjectClasses.some(c => !generic.has(c) && node.classList.contains(c));
      if (identity && /[#>+~]/.test(selector)) unsupported("ancestor, child or sibling context");
      const classes = [...selector.matchAll(/\.([a-zA-Z_-][a-zA-Z0-9_-]*)/g)].map(m => m[1]);
      if (identity && classes.some(c => !modeledClasses.has(c))) unsupported("ancestor or compound class");
      // Remove unsupported pseudo/attribute conditions only to establish
      // possible relevance. An unrelated pane cannot match the real ancestry.
      // The real selector is never resolved through this relaxed skeleton.
      const skeleton = selector.replace(/:[a-z-]+\([^)]*\)/g, "").replace(/::?[a-z-]+/g, "").replace(/\[[^\]]*\]/g, "");
      try { if (skeleton.trim() && !node.matches(skeleton)) continue; } catch { /* Unsupported grammar is rejected below. */ }
      if (/[#>+~[\]]/.test(selector) || /::|:(?!root\b|hover\b|focus-within\b|disabled\b)/.test(selector)) unsupported("selector context");
      const evaluated = selector.replace(/:root\b/g, ".proof-root").replace(/:hover\b/g, ".proof-hover").replace(/:focus-within\b/g, ".proof-focus-within");
      if (!node.matches(evaluated)) continue;
      if (unorderedRules.has(rule)) unsupported("stylesheet ordering");
      if (rule.parent?.type !== "root") unsupported(`at-rule context ${rule.parent?.type === "atrule" ? "@" + rule.parent.name + " " + rule.parent.params : rule.parent?.type}`);
      if (declarations.some(d => d.important)) unsupported("!important conflict");
      const residue = selector.replace(/[.#][a-zA-Z_-][a-zA-Z0-9_-]*/g, "").replace(/:(?:root|hover|focus-within|disabled)\b/g, "").replace(/\bhtml\b|[\s>*]/g, "");
      if (residue) unsupported("element or selector syntax");
      const specificity = [(selector.match(/#/g) ?? []).length, (selector.match(/\.|:(?!:)/g) ?? []).length, (selector.match(/\bhtml\b/g) ?? []).length];
      const difference = paint ? specificity.findIndex((v, i) => v !== paint!.specificity[i]) : -1;
      const wins = !paint || difference === -1 || specificity[difference] > paint.specificity[difference];
      if (wins) for (const decl of declarations) paint = { selector, value: decl.value, specificity };
    }
  }
  const result = paint && { selector: paint.selector, value: paint.value };
  cascadeCache.set(key, result); return result;
}
function resolved(ancestors: string[][], property: string, theme: Theme, interaction = "rest", fallback?: string, form = themeForm): string {
  const paint = cascade(model(ancestors, theme, interaction, form), 0, property);
  if (paint) return paint.value;
  if (fallback !== undefined) return fallback;
  throw new Error(`Missing production ${property}: ${ancestors[0].join(".")}, ${theme}/${interaction}`);
}
function paintedAncestor(ancestors: string[][], theme: Theme, interaction = "rest", form = themeForm): Paint {
  const nodes = model(ancestors, theme, interaction, form);
  for (let i = 0; i < nodes.length; i++) {
    const paint = cascade(nodes, i, "background");
    if (paint && !["none", "transparent"].includes(paint.value)) return paint;
  }
  throw new Error(`No production ancestor paints below opacity group: ${theme}`);
}
const keyBackdrop = (theme: Theme, interaction = "rest") => paintedAncestor(keyAncestors, theme, interaction);
const deleteBackdrop = (theme: Theme, interaction = "rest") => paintedAncestor(deleteAncestors, theme, interaction);
const opacity = (selector: string) => Number(declaration(selector, "opacity"));
const ringOpacity = Number(mapSource.match(/opacity: outline \? ([\d.]+)/)?.[1]);
if (!Number.isFinite(ringOpacity)) throw new Error("Missing production ring opacity");
function contexts(): Context[] {
  const result: Context[] = [];
  const pigment = (surface: Surface, state: string, p: Palette, before: boolean, theme: Theme, interaction = "rest", part = "fill", requiredness = "required", sidebar = false) => {
    let path: string[][], property = "color", fallback: string | undefined;
    if (surface === "memory") { path = [["mem-fill", ...(state === "over" ? ["over"] : [])], ...memoryAncestors]; property = "background"; }
    else if (surface === "delete") path = [["lm-trash", ...(state === "armed" ? ["armed"] : [])], ["lm-action"], ["lm-quant", "ready"], ...deleteAncestors];
    else if (surface === "key") path = [["key-status", ...(state === "present" || state === "verified" ? [state] : [])], ["key-row", ...(state === "required-missing" ? ["missing"] : state === "optional-absent" || requiredness === "optional" ? ["optional"] : [])], ...keyAncestors];
    else {
      path = [[part === "ring" && state !== "rest" ? "map-state-ring" : "map-state-fill", `proof-shape-${state === "selected" ? "rect" : state === "hovered" ? "polygon" : "circle"}`], ["map-state-glyph"], ...(sidebar ? [["map-place-dot"], ...sidebarAncestors] : [["map-pin"], ...pinAncestors])];
      property = part === "ring" && state !== "rest" ? "stroke" : "fill"; fallback = `var(${MAPPINGS.map[state]})`;
    }
    const value = resolved(path, property, theme, interaction, fallback);
    if (!/^var\(--state-[a-z-]+\)$/.test(value)) throw new Error(`Unmodeled state-surface color expression: ${theme} ${surface}/${state} ${value}`);
    const root = rootOf(value);
    if (root !== MAPPINGS[surface][state]) throw new Error(`State mapping override: ${theme} ${surface}/${state} ${value}`);
    return p[before ? BASE_ROOTS[root] : root];
  };
  result.push({ surface: "memory", name: "fill", render: (s, p, b, theme) => pigment("memory", s, p, b, theme) });
  for (const row of ["ready", "ready-exceeds"])
    for (const interaction of ["rest", "hover", "focus"]) {
      // No hover/focus rule changes .lm-trash foreground/background. Resolve
      // the ready row first, then its group opacity against provider parent.
      result.push({ surface: "delete", name: `${row}/${interaction}`, render: (s, p, b, theme) => {
        const rowBg = background(resolved([["lm-quant", "ready", ...(row === "ready-exceeds" ? ["exceeds"] : [])], ...deleteAncestors], "background", theme, interaction), p);
        const glyph = composite(pigment("delete", s, p, b, theme, interaction), rowBg, 1);
        return composite(glyph, background(deleteBackdrop(theme, interaction).value, p), row === "ready-exceeds" ? opacity(".lm-quant.exceeds") : 1);
      } });
    }
  // Include required and optional presence/verification rows at rest and
  // hover/focus-within; required-missing cannot be an optional row.
  for (const requiredness of ["required", "optional"])
    for (const interaction of ["rest", "hover", "focus"]) {
      result.push({ surface: "key", name: `${requiredness}/${interaction}`, render: (s, p, b, theme) => {
        const optional = s === "optional-absent" || (requiredness === "optional" && s !== "required-missing");
        const alpha = optional ? opacity(interaction === "rest" ? ".key-row.optional" : `.key-row.optional:${interaction === "hover" ? "hover" : "focus-within"}`) : 1;
        return composite(pigment("key", s, p, b, theme, interaction, "fill", requiredness), background(keyBackdrop(theme, interaction).value, p), alpha);
      } });
    }
  for (const terrain of ["sea", "land"])
    for (const part of ["fill", "ring"]) {
      result.push({ surface: "map", name: `canvas-${terrain}/${part}`, render: (s, p, b, theme) => {
        const bg = background(resolved(canvasAncestors, `--map-${terrain}`, theme), p);
        return composite(pigment("map", s, p, b, theme, "rest", part), bg, part === "ring" && s !== "rest" ? ringOpacity : 1);
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
        result.push({ surface: "map", name: `sidebar-wash-${washAlpha}/${interaction}/${part}`, render: (s, p, b, theme) => {
          const themedContent = resolved(mapOuter, "background", theme);
          if (themedContent !== content) throw new Error(`Unmodeled sidebar gradient: ${theme} ${themedContent}`);
          const parent = composite(rgb(wash[1]), p[rootOf(themedContent)], washAlpha);
          const on = s === "selected" || (interaction === "selected-current" && s === "current");
          const bg = background(resolved([["map-place-row", ...(on ? ["on"] : [])], ...sidebarAncestors.slice(1)], "background", theme, interaction), p, parent);
          return composite(pigment("map", s, p, b, theme, interaction, part, "required", true), bg, !b && part === "ring" && s !== "rest" ? ringOpacity : 1);
        } });
      }
  return result;
}
const CONTEXTS = contexts();
function palette(css: string, theme: Theme): Palette {
  return Object.fromEntries(Object.entries(tokens(css, theme))
    .filter(([, value]) => value === "#b83d7a" || /^(?:hsl\()?([\d.]+)\s+([\d.]+)%\s+([\d.]+)%/.test(value))
    .map(([root, value]) => [root, rgb(value)]));
}
function baselineValue(theme: Theme, root: string): string {
  return theme === "Veil" && BASE_ROOTS[root] === "--brass"
    ? `hsl(${ANCHOR_HSL})` : tokens(baseCss, theme)[BASE_ROOTS[root]];
}
function candidates(theme: Theme, root: string): { value: string; rgb: Triple; changed: number }[] {
  const base = baselineValue(theme, root);
  const old = rgb(base);
  let [h, s, l] = hsl(base);
  if (theme === "Veil" && ["--brass", "--brass-bright"].includes(BASE_ROOTS[root])) h = ANCHOR_HUE;
  const destructive = root === "--state-delete-armed";
  const sats = [...new Set(destructive ? [80, 90, 100] : [s, Math.min(100, s + 10), Math.min(100, s + 20)])];
  const lights = [...new Set(destructive ? [50, 55, 60, 65] : [l, 30, 40, 50, 60, 70])];
  return sats.flatMap(s => lights.map(l => {
    const next = hslRgb([h, s, l]);
    return { value: `hsl(${h} ${s}% ${l}%)`, rgb: next, changed: next.every((v, i) => Math.abs(v - old[i]) < 1e-12) ? 0 : 1 };
  }));
}
function measures(theme: Theme, p: Palette, before: boolean) {
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
// Explicit one-theme exception manifests; exact context inventory is generated
// from CSS, while shortfall IDs are committed and checked below.
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
      const values = measures(theme, palette(shippedCss, theme), false);
      expect(values).toHaveLength(139);
      for (const ctx of CONTEXTS) expect(values.filter(v => v.context === ctx.name && v.surface === ctx.surface)).toHaveLength(STATE_PAIRS[ctx.surface].length);
    }
  });
  it("opacity_backdrops_follow_the_production_painting_ancestors", () => {
    for (const theme of THEMES) expect(keyBackdrop(theme)).toEqual({ selector: ".set-card-frame", value: declaration(".set-card-frame", "background") });
    for (const theme of THEMES) expect(deleteBackdrop(theme)).toEqual({ selector: ".model-provider", value: declaration(".model-provider", "background") });
    expect(jsxAncestors(settingsSource, "key-row")).toEqual([["key-list"], ["set-card-body"], ["set-card-frame"], ["set-card"]]);
    // Assert every opacity context against an independently assembled production
    // layer path. A context addition must extend this inventory, not pick a color.
    for (const theme of THEMES) {
      const p = palette(shippedCss, theme);
      const content = declaration(".nexus-content", "background");
      const wash = content.match(/hsl\(([^/]+) \/ ([\d.]+)\)/)!;
      for (const ctx of CONTEXTS) for (const state of Object.keys(MAPPINGS[ctx.surface])) {
        const pigment = p[MAPPINGS[ctx.surface][state]];
        let expected: Triple;
        if (ctx.surface === "memory") expected = pigment;
        else if (ctx.surface === "key") {
          const [need, interaction] = ctx.name.split("/");
          const optional = state === "optional-absent" || (need === "optional" && state !== "required-missing");
          const alpha = optional ? opacity(interaction === "rest" ? ".key-row.optional" : `.key-row.optional:${interaction === "hover" ? "hover" : "focus-within"}`) : 1;
          expected = composite(pigment, background(paintedAncestor(keyAncestors, theme).value, p), alpha);
        } else if (ctx.surface === "delete") {
          const row = composite(pigment, background(declaration(".lm-quant.ready", "background"), p), 1);
          expected = composite(row, background(paintedAncestor(deleteAncestors, theme).value, p), ctx.name.startsWith("ready-exceeds/") ? opacity(".lm-quant.exceeds") : 1);
        } else {
          const alpha = ctx.name.endsWith("/ring") && state !== "rest" ? ringOpacity : 1;
          if (ctx.name.startsWith("canvas-")) {
            // SVG terrain is painted beneath the glyph, not an HTML background.
            expect(mapSource).toContain('fill="var(--map-sea)"');
            expect(mapSource).toContain('fill="var(--map-land)"');
            const terrain = ctx.name.split("/")[0].slice("canvas-".length);
            expected = composite(pigment, background(declaration(".mappane-canvas", `--map-${terrain}`), p), alpha);
          } else {
            expect(jsxAncestors(mapSource, "map-place-dot")[0]).toContain("map-place-row");
            const [, washAlpha, interaction] = ctx.name.match(/^sidebar-wash-([\d.]+)\/(.*?)\//)!;
            const parent = composite(rgb(wash[1].trim()), p[rootOf(content)], Number(washAlpha));
            const on = state === "selected" || (interaction === "selected-current" && state === "current");
            expected = composite(pigment, background(declaration(on ? ".map-place-row.on" : interaction === "hover" ? ".map-place-row:hover" : ".map-place-row", "background"), p, parent), alpha);
          }
        }
        expect(ctx.render(state, p, false, theme), `${theme}/${ctx.surface}/${ctx.name}/${state}`).toEqual(expected);
      }
    }
  });
  it("theme_ancestry_and_every_relevant_rule_are_modeled", () => {
    try {
      for (const theme of THEMES) {
        themeForm = "compound";
        const compound = measures(theme, palette(shippedCss, theme), false);
        themeForm = "descendant";
        expect(measures(theme, palette(shippedCss, theme), false), `${theme}: compound and descendant theme contexts`).toEqual(compound);
      }
      for (const theme of THEMES) for (const form of ["compound", "descendant"]) {
        model([["mem-over-glyph"], ...warningAncestors], theme, "rest", form);
        for (const state of Object.keys(MAPPINGS.key)) model([[`key-glyph-${state}`], ["key-status"], ["key-row"], ...keyAncestors], theme, "rest", form);
        model([["map-pin-leader"], ...leaderAncestors], theme, "rest", form);
      }
      const properties = new Set<string>([...ROOTS, ...measuredRoots, "--map-sea", "--map-land"]);
      for (const rule of cssRules) rule.walkDecls(decl => {
        if (/^(?:color|fill|stroke|background(?:$|-)|border(?:$|-.*color$)|outline(?:$|-color$)|box-shadow$|text-shadow$|filter$|opacity$)/.test(decl.prop)) properties.add(decl.prop);
      });
      for (const nodes of modeledPaths.values()) for (let i = 0; i < nodes.length; i++) {
        for (const property of properties) {
          const paint = cascade(nodes, i, property);
          if (property.startsWith("--") && paint && !["--map-sea", "--map-land", "--map-coast"].includes(property))
            throw new Error(`Unmodeled local custom-property cascade: ${paint.selector} { ${property}: ${paint.value} }`);
        }
      }
    } finally { themeForm = "compound"; }
  });
  it("reachable_deutan_pairs_meet_15_and_exceptions_keep_distinct_static_signatures", () => {
    expect(MAPPINGS).toEqual({
      memory: { normal: "--state-mem-normal", over: "--state-mem-over" },
      delete: { unarmed: "--state-delete-unarmed", armed: "--state-delete-armed" },
      map: { rest: "--state-map-rest", current: "--state-map-current", selected: "--state-map-selected", hovered: "--state-map-hovered" },
      key: { "optional-absent": "--state-key-absent", "required-missing": "--state-key-missing", present: "--state-key-present", verified: "--state-key-verified" },
    });
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
