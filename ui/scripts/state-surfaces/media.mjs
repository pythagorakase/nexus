import postcss from 'postcss';
import { conditions } from './inputs.mjs';
/** Cover every shipped media prelude and its complement; unknown features fail loudly. */
export function mediaConditions(css) {
  const preludes = [], unsupported = [];
  postcss.parse(css).walkAtRules(rule => {
    if (['media', 'container'].includes(rule.name)) {
      const key = `${rule.name} ${rule.params}`;
      if (!preludes.includes(key)) preludes.push(key);
    }
  });
  const variants = [{ id: 'default', ...conditions }], widths = new Set(), heights = new Set();
  const add = (id, overrides) => { if (!variants.some(c => c.id === id)) variants.push({ ...conditions, id, ...overrides }); };
  for (const prelude of preludes) {
    if (prelude.startsWith('container ')) { unsupported.push(prelude); continue; }
    let rest = prelude.slice(6).trim();
    rest = rest.replace(/\((min|max)-(width|height):\s*([\d.]+)px\)/g, (_, bound, dimension, value) => {
      const set = dimension === 'width' ? widths : heights;
      set.add(Number(value)); set.add(Number(value) + (bound === 'max' ? 1 : -1)); return '';
    });
    rest = rest.replace(/\(prefers-color-scheme:\s*(dark|light)\)/g, (_, v) => { add('color-light', { colorScheme: 'light' }); add('color-dark', { colorScheme: 'dark' }); return ''; });
    rest = rest.replace(/\(prefers-reduced-motion:\s*(reduce|no-preference)\)/g, () => { add('motion-start', { reducedMotion: 'no-preference', animationPhase: 0 }); add('motion-trough', { reducedMotion: 'no-preference', animationPhase: .5 }); return ''; });
    rest = rest.replace(/\(forced-colors:\s*(active|none)\)/g, () => { add('forced-colors', { forcedColors: 'active' }); return ''; });
    rest = rest.replace(/\((?:any-)?(?:hover|pointer):\s*(hover|none|fine|coarse)\)/g, () => { add('touch', { hasTouch: true, isMobile: true }); return ''; });
    if (/\bprint\b/.test(rest)) add('print', { media: 'print' });
    rest = rest.replace(/\b(?:screen|print|all|and|or|not|only)\b|[\s,]/g, '');
    if (rest) unsupported.push(prelude);
  }
  for (const width of [...widths].sort((a, b) => a - b)) add(`width-${width}`, { viewport: { ...conditions.viewport, width } });
  for (const height of [...heights].sort((a, b) => a - b)) add(`height-${height}`, { viewport: { ...conditions.viewport, height } });
  return { preludes, unsupported, variants };
}
