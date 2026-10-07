import postcss from 'postcss';
import { conditions } from './inputs.mjs';

const ignoredAtRules = new Set([
  'supports', 'layer', 'font-face', 'keyframes', 'property', 'scope', 'page',
  'starting-style', 'charset', 'namespace', 'font-feature-values',
  'counter-style', 'view-transition',
]);
/** Normalize the undecoded media grammar before matching any term. */
const stripComments = raw => raw.replace(/\/\*[\s\S]*?\*\//g, '');
const normalize = raw => stripComments(raw).toLowerCase()
  .replace(/\s+/g, ' ').replace(/\s*([():,])\s*/g, '$1').trim();
// Keep the receipt's established human-readable feature spelling.
const display = term => term.replaceAll(':', ': ').replace(/^not\(/, 'not (');

const discrete = {
  'prefers-reduced-motion': ['reduce', 'no-preference'],
  'prefers-color-scheme': ['dark', 'light'],
  hover: ['hover', 'none'], 'any-hover': ['hover', 'none'],
  pointer: ['fine', 'coarse', 'none'], 'any-pointer': ['fine', 'coarse', 'none'],
};
/** Split only media-list commas; commas inside nested features stay intact. */
function mediaAlternatives(raw) {
  const alternatives = [];
  let depth = 0, start = 0;
  for (let i = 0; i < raw.length; i++) {
    if (raw[i] === '(') depth++;
    else if (raw[i] === ')') depth--;
    else if (raw[i] === ',' && depth === 0) {
      alternatives.push(raw.slice(start, i).trim()); start = i + 1;
    }
  }
  alternatives.push(raw.slice(start).trim());
  return alternatives;
}
const compare = (a, op, b) => ({ '<': a < b, '<=': a <= b, '>': a > b, '>=': a >= b, '=': a === b })[op];

/** Cross feature values, then retain one vector per satisfied-prelude set. */
export function mediaConditions(css) {
  const preludes = [], excluded = [], stripped = [], unsupported = [], queries = new Map();
  const ranges = { width: [], height: [] }, features = new Set();
  const remember = prelude => { if (!preludes.includes(prelude)) preludes.push(prelude); };
  // Evaluate only this allowlist in screen / forced-colors:none. Parse the
  // entire alternative before exclusion so an unknown term never disappears.
  function evaluate(raw, parentList) {
    const prelude = `media ${raw}`, normalized = normalize(raw);
    const terms = normalized.split(/\s*\band\b\s*/);
    remember(prelude);
    const tests = [], kept = [], always = [];
    let reason;
    const refuse = () => { unsupported.push(prelude); return undefined; };
    if (/\bor\b/.test(normalized)) return refuse();
    if (/^not\b/.test(terms[0])) {
      if (terms.length !== 1) return refuse();
      const term = terms[0];
      if (term === 'not print' || /^not\(forced-colors:active\)$/.test(term))
        always.push(display(term));
      else if (term === 'not screen' || term === 'not all')
        reason = `${term} is false in the screen environment`;
      else if (/^not\(forced-colors:none\)$/.test(term))
        reason = 'not (forced-colors: none) is false with forced-colors: none';
      else return refuse();
    } else {
      for (const [i, term] of terms.entries()) {
        if (i === 0 && /^(?:only\s+)?(?:screen|all|print)$/.test(term)) {
          if (term.replace(/^only\s+/, '') === 'print')
            reason = 'print media type is false in the screen environment';
          else always.push(display(term));
          continue;
        }
        const feature = term.match(/^\(\s*([^()]*)\s*\)$/)?.[1].trim();
        if (!feature) return refuse();
        let m = feature.match(/^(?:(min|max)-)?(width|height):(\d+)px$/);
        if (m) {
          if (!Number.isSafeInteger(Number(m[3]))) return refuse();
          const axis = m[2], op = m[1] === 'min' ? '>=' : m[1] === 'max' ? '<=' : '=';
          tests.push({ axis, op, value: Number(m[3]) }); kept.push(display(term)); continue;
        }
        m = feature.match(/^([a-z-]+)\s*:\s*([a-z-]+)$/);
        if (m?.[1] === 'forced-colors' && ['active', 'none'].includes(m[2])) {
          if (m[2] === 'active') reason = 'forced-colors: active is false with forced-colors: none';
          else always.push(display(term));
        } else if (m && discrete[m[1]]?.includes(m[2])) {
          tests.push({ feature: m[1], value: m[2] }); kept.push(display(term));
        } else return refuse();
      }
    }
    for (const term of always) {
      if (!stripped.some(e => e.prelude === prelude && e.parentList === parentList && e.term === term))
        stripped.push({ prelude, parentList, term, reason: 'always true in screen / forced-colors: none' });
    }
    if (reason) {
      let entry = excluded.find(e => e.prelude === prelude && e.parentList === parentList);
      if (!entry) { entry = { prelude, parentList, reason }; excluded.push(entry); }
      return { excluded: entry };
    }
    // Only kept alternatives contribute dimensions to the measured inventory.
    for (const test of tests) {
      if (test.axis) ranges[test.axis].push(test);
      else features.add(test.feature);
    }
    return { terms: kept, test: v => tests.every(t => t.axis ?
      compare(v.viewport[t.axis], t.op, t.value) : v.features[t.feature] === t.value) };
  }
  let root;
  try { root = postcss.parse(css); }
  catch (error) {
    // PostCSS cannot tokenize an at-keyword beginning with a CSS escape.
    // Refuse that exact header by name; unrelated syntax errors still surface.
    const source = error.source?.split('\n').slice(error.line - 1).join('\n')
      .slice(error.column - 1);
    if (error.reason !== 'At-rule without name' || !source?.startsWith('@\\')) throw error;
    const prelude = source.slice(1).split(/[{};]/, 1)[0].trim();
    remember(prelude); unsupported.push(prelude); root = postcss.root();
  }
  // Audit every at-rule, including children of excluded media parents. They
  // cannot silently bypass the evaluator through an unrecognised wrapper.
  const refused = new Set();
  root.walkAtRules(rule => {
    const name = rule.name.toLowerCase();
    const params = rule.raws.params?.raw ?? rule.params;
    const afterName = rule.raws.afterName ?? '';
    if (rule.name.includes('\\') || afterName.includes('\\') || params.includes('\\') ||
        (!ignoredAtRules.has(name) && name !== 'media')) {
      const prelude = `${name} ${afterName.includes('\\') ? afterName.trim() + ' ' : ''}${params}`.trim();
      remember(prelude); unsupported.push(prelude); refused.add(rule);
    }
  });
  function visit(node, parents = [{ terms: [], test: () => true }]) {
    for (const rule of node.nodes ?? []) {
      if (refused.has(rule)) continue;
      if (rule.type !== 'atrule' || rule.name.toLowerCase() !== 'media') {
        visit(rule, parents); continue;
      }
      const own = mediaAlternatives(stripComments(rule.params)).map(raw => evaluate(raw, `media ${rule.params}`));
      // Refused parents fail before their children are inspected.
      if (own.some(alternative => !alternative)) continue;
      for (const alternative of own.filter(a => a.excluded)) {
        const skipped = [];
        rule.walkAtRules(child => {
          if (['media', 'container'].includes(child.name.toLowerCase()))
            skipped.push(`${child.name.toLowerCase()} ${child.params}`);
        });
        if (skipped.length) alternative.excluded.skipped = [...new Set(skipped)];
      }
      const effective = parents.flatMap(parent => own.filter(a => !a.excluded).map(child => ({
        terms: [...parent.terms, ...child.terms], test: v => parent.test(v) && child.test(v),
      })));
      for (const alternative of effective) {
        const prelude = `media ${alternative.terms.join(' and ') || 'all'}`;
        remember(prelude);
        const previous = queries.get(prelude);
        queries.set(prelude, previous ? v => previous(v) || alternative.test(v) : alternative.test);
      }
      if (effective.length) visit(rule, effective);
    }
  }
  visit(root);
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
  return { preludes, excluded, stripped, unsupported: [...new Set(unsupported)], representatives, variants };
}
