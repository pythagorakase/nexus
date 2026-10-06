import postcss from 'postcss';
import { conditions } from './inputs.mjs';

const discrete = {
  'prefers-reduced-motion': ['reduce', 'no-preference'],
  'prefers-color-scheme': ['dark', 'light'],
  hover: ['hover', 'none'], 'any-hover': ['hover', 'none'],
  pointer: ['fine', 'coarse', 'none'], 'any-pointer': ['fine', 'coarse', 'none'],
};
const compare = (a, op, b) => ({ '<': a < b, '<=': a <= b, '>': a > b, '>=': a >= b, '=': a === b })[op];

/** Cross feature values, then retain one vector per satisfied-prelude set. */
export function mediaConditions(css) {
  const preludes = [], excluded = [], unsupported = [], queries = new Map();
  const ranges = { width: [], height: [] }, features = new Set();
  function parse(raw, prelude) {
    return raw.split(',').map(alternative => {
      let rest = alternative.trim(), negate = /^not\b/.test(rest);
      rest = rest.replace(/^(?:not|only)\s+/, '');
      const tests = [];
      const range = (axis, op, value) => {
        ranges[axis].push({ op, value: Number(value) });
        tests.push(v => compare(v.viewport[axis], op, Number(value)));
      };
      rest = rest.replace(/\(([^()]*)\)/g, (_, feature) => {
        let m = feature.match(/^(?:(min|max)-)?(width|height)\s*:\s*([\d.]+)px$/);
        if (m) { range(m[2], m[1] === 'min' ? '>=' : m[1] === 'max' ? '<=' : '=', m[3]); return ''; }
        m = feature.match(/^(width|height)\s*(<=|>=|<|>|=)\s*([\d.]+)px$/);
        if (m) { range(m[1], m[2], m[3]); return ''; }
        m = feature.match(/^([\d.]+)px\s*(<=|>=|<|>|=)\s*(width|height)(?:\s*(<=|>=|<|>|=)\s*([\d.]+)px)?$/);
        if (m) {
          range(m[3], { '<': '>', '<=': '>=', '>': '<', '>=': '<=', '=': '=' }[m[2]], m[1]);
          if (m[4]) range(m[3], m[4], m[5]); return '';
        }
        m = feature.match(/^([a-z-]+)\s*:\s*([a-z-]+)$/);
        if (m && discrete[m[1]]?.includes(m[2])) {
          features.add(m[1]); tests.push(v => v.features[m[1]] === m[2]); return '';
        }
        unsupported.push(prelude); return '';
      });
      if (rest.replace(/\b(?:screen|all|and)\b|\s/g, '')) unsupported.push(prelude);
      return v => negate !== tests.every(test => test(v));
    });
  }
  postcss.parse(css).walkAtRules(rule => {
    if (!['media', 'container'].includes(rule.name)) return;
    const prelude = `${rule.name} ${rule.params}`;
    if (!preludes.includes(prelude)) preludes.push(prelude);
    if (rule.name === 'container') { unsupported.push(prelude); return; }
    // Nested Tailwind media variants are conjunctions too.
    const chain = [rule.params];
    for (let parent = rule.parent; parent; parent = parent.parent)
      if (parent.type === 'atrule' && parent.name === 'media') chain.unshift(parent.params);
    if (chain.some(p => /\bprint\b|forced-colors/.test(p))) {
      if (!excluded.some(e => e.prelude === prelude)) excluded.push({ prelude,
        reason: 'not a screen color environment the deutan objective governs; forced colors replace every pigment' });
      return;
    }
    const alternatives = chain.map(p => parse(p, prelude));
    const test = v => alternatives.every(list => list.some(t => t(v)));
    // A repeated prelude under different ancestors is an alternative chain.
    const previous = queries.get(prelude);
    queries.set(prelude, previous ? v => previous(v) || test(v) : test);
  });
  function bands(axis) {
    if (!ranges[axis].length) return [{ name: '', value: conditions.viewport[axis] }];
    // Playwright viewports use integer CSS pixels. Preserve inclusive/exclusive
    // cuts and singleton bands where min and max share a breakpoint.
    const cuts = new Set([1]);
    for (const { op, value } of ranges[axis]) {
      if (op === '>=' || op === '=') cuts.add(Math.ceil(value));
      if (op === '>' || op === '=') cuts.add(Math.floor(value) + 1);
      if (op === '<=') cuts.add(Math.floor(value) + 1);
      if (op === '<') cuts.add(Math.ceil(value));
    }
    const boundaries = [...cuts].filter(v => v >= 1).sort((a, b) => a - b);
    return boundaries.map((low, i) => {
      const high = boundaries[i + 1] === undefined ? Infinity : boundaries[i + 1] - 1;
      const preferred = conditions.viewport[axis];
      const value = preferred >= low && preferred <= high ? preferred :
        preferred < low ? low : high;
      return { name: `${axis[0]}${low}${low === high ? '' : high === Infinity ? '+' : `-${high}`}`, value };
    });
  }
  let vectors = bands('width').flatMap(w => bands('height').map(h => ({
    ...conditions, viewport: { width: w.value, height: h.value },
    band: [w.name, h.name].filter(Boolean).join('/'), features: {},
  })));
  for (const feature of features) vectors = vectors.flatMap(v => discrete[feature].map(value => ({
    ...v, features: { ...v.features, [feature]: value },
  })));
  const isDefault = v => v.viewport.width === 1200 && v.viewport.height === 900 &&
    Object.entries(v.features).every(([f, value]) => value === discrete[f][0]);
  vectors.sort((a, b) => Number(isDefault(b)) - Number(isDefault(a)));
  const kept = new Map();
  for (const v of vectors) {
    const satisfied = [...queries].filter(([, test]) => test(v)).map(([p]) => p);
    const key = JSON.stringify(satisfied);
    if (!kept.has(key)) kept.set(key, { ...v, satisfied });
  }
  const representatives = [...kept.values()];
  if (!unsupported.length) for (const prelude of queries.keys())
    if (!representatives.some(v => v.satisfied.includes(prelude))) throw new Error(`Unsatisfied media prelude: ${prelude}`);
  const variants = representatives.flatMap(v => {
    const reducedMotion = v.features['prefers-reduced-motion'] ?? conditions.reducedMotion;
    const colorScheme = v.features['prefers-color-scheme'] ?? conditions.colorScheme;
    const hasTouch = Object.entries(v.features).some(([f, value]) => /hover|pointer/.test(f) && value !== 'hover' && value !== 'fine');
    const other = Object.entries(v.features).filter(([f]) => f !== 'prefers-reduced-motion').map(([f, value]) => `${f}=${value}`);
    const prefix = [v.band, ...other].filter(Boolean).join('/') || 'default';
    const common = { ...v, reducedMotion, colorScheme, hasTouch, isMobile: hasTouch };
    return reducedMotion === 'reduce' ? [{ ...common, id: `${prefix}/reduce` }] :
      [0, .5].map(animationPhase => ({ ...common, animationPhase, id: `${prefix}/motion/${animationPhase ? 'trough' : 'start'}` }));
  });
  return { preludes, excluded, unsupported: [...new Set(unsupported)], representatives, variants };
}
