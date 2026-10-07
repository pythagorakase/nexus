import postcss from 'postcss';
export const START = '8ccd3008a48bdf8115232667399868e2bdf66f93';
export const roots = {
  memory: { normal: '--brass', over: '--bronze' }, delete: { unarmed: '--fg-muted', armed: '--destructive' },
  map: { rest: '--bronze', current: '--brass-bright', selected: '--brass', hovered: '--brass-bright' },
  key: { 'optional-absent': '--fg-dim', 'required-missing': '--bronze', present: '--fg-muted', verified: '--brass' },
};
export const token = (group, state) => `--state-${group === 'memory' ? 'mem' : group}-${state === 'optional-absent' ? 'absent' : state === 'required-missing' ? 'missing' : state}`;
export function themeTokens(css, theme) {
  const values = {};
  postcss.parse(css).walkRules(rule => {
    if (rule.parent?.type === 'root' && (rule.selector === ':root' || rule.selector === '.dark' ||
      (theme !== 'Veil' && rule.selector.includes(`.dark.theme-${theme.toLowerCase()}`))))
      rule.walkDecls(d => { values[d.prop] = d.value; });
  });
  return values;
}
export function domain(css, theme, group, state) {
  const root = roots[group][state], values = themeTokens(css, theme);
  let [h, s, l] = values[root].match(/([\d.]+)\s+([\d.]+)%\s+([\d.]+)%/).slice(1).map(Number);
  if (theme === 'Veil' && root === '--brass') [h, s, l] = [330.2439024390244, 50.20408163265306, 48.03921568627451];
  if (theme === 'Veil' && ['--brass', '--brass-bright'].includes(root)) h = 330.2439024390244;
  return [...new Set(root === '--destructive' ? [80, 90, 100] : [s, Math.min(100, s + 10), Math.min(100, s + 20)])]
    .flatMap(s => [...new Set(root === '--destructive' ? [50, 55, 60, 65] : [l, 30, 40, 50, 60, 70])].map(l => `hsl(${h} ${s}% ${l}%)`));
}
