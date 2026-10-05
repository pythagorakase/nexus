/** Reproducible adversarial protocol. Mutations exist only in an order scratch copy. */
import { spawn, execFileSync } from 'node:child_process';
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { inputs } from './inputs.mjs';
const root = resolve(import.meta.dirname, '../../..'), ui = resolve(root, 'ui');
const scratch = process.env.STATE_SURFACES_SCRATCH;
if (!scratch || !scratch.includes('/scratchpad/777-S2/after-review-r4/'))
  throw new Error('STATE_SURFACES_SCRATCH must be beneath this fix order’s scratch directory');
const copy = resolve(scratch, 'plant-copy'), report = [];
mkdirSync(copy, { recursive: true });
cpSync(ui, resolve(copy, 'ui'), { recursive: true, filter: path => !path.includes('/dist/') });
cpSync(resolve(root, 'docs/qa/777-glyph-first-states'), resolve(copy, 'docs/qa/777-glyph-first-states'), { recursive: true });
const layout = 'ui/client/src/components/nexus/nexus-layout.css';
const theme = 'ui/client/src/contexts/ThemeContext.tsx';
const plants = [
  { name: 'opaque-gradient-stop', path: layout, replace: ['transparent 60%', '#ffffff 60%'] },
  { name: 'theme-provider-opacity', path: theme, replace: ['{children}', '<div style={{opacity: 0.35}}>{children}</div>'] },
  { name: 'media-root-override', path: layout, append: '\n@media (prefers-color-scheme: light) { .dark.theme-vector { --state-key-verified: var(--state-key-present); } }\n' },
  { name: 'optional-row-opacity', path: layout, append: '\n.key-row.optional { opacity: .15; }\n' },
  { name: 'theme-backdrop', path: layout, append: '\n.dark.theme-vector .key-row { background: #ffffff; }\n' },
  { name: 'important-state-surface', path: layout, append: '\n.lm-trash.armed { color: var(--state-delete-unarmed) !important; }\n' },
  { name: 'has-state-surface', path: layout, append: '\n.key-row:has(.key-status.verified) .key-status { color: var(--state-key-present); }\n' },
  { name: 'map-blend', path: layout, append: '\n.map-pin { mix-blend-mode: difference; }\n' },
  { name: 'key-overpainting-shadow', path: layout, append: '\n.key-status svg { background: var(--state-key-present); box-shadow: inset 0 0 0 12px var(--state-key-present); }\n' },
];
async function run(name, args, env = {}) {
  const started = performance.now();
  const child = spawn(args[0], args.slice(1), { cwd: root,
    env: { ...process.env, GIT_DIR: execFileSync('git', ['rev-parse', '--absolute-git-dir'], {cwd: root, encoding: 'utf8'}).trim(), ...env } });
  // The scratch copy reads baseline history through the linked worktree gitdir.
  let output = '';
  for (const stream of [child.stdout, child.stderr]) stream.on('data', b => { output += b; });
  const timer = setTimeout(() => child.kill('SIGTERM'), 589000);
  const progress = setInterval(() => console.log(`${name}: still running\n${output.slice(-400)}`), 45000);
  const code = await new Promise(r => child.on('exit', r));
  clearTimeout(timer); clearInterval(progress);
  const tail = output.split('\n').slice(-35).join('\n');
  writeFileSync(resolve(scratch, `${name}.log`), output);
  const result = { name, args, code, wallSeconds: (performance.now() - started) / 1000, tail };
  report.push(result); console.log(`\n${name}: exit ${code}\n${tail}`); return result;
}
const originalReceipt = readFileSync(resolve(copy, 'ui/client/src/state-surfaces.resolved.json'));
try {
  const control = await run('control', ['npm', '--prefix', resolve(copy, 'ui'), 'test', '--', 'state-shades']);
  if (control.code !== 0) throw new Error('Unplanted control must pass before any plant is evidence');
  for (const plant of plants) {
    const target = resolve(copy, plant.path), original = readFileSync(target, 'utf8');
    const before = await inputs(resolve(copy, 'ui'));
    try {
      let changed;
      if (plant.replace) {
        if (!original.includes(plant.replace[0])) throw new Error(`Plant ${plant.name}: missing exact source text`);
        changed = original.replace(plant.replace[0], plant.replace[1]);
      } else changed = original + plant.append;
      writeFileSync(target, changed);
      const after = await inputs(resolve(copy, 'ui'));
      if (before.sha256 === after.sha256) throw new Error(`${plant.name}: freshness hash failed to change`);
      const stale = await run(`${plant.name}-stale`, ['npm', '--prefix', resolve(copy, 'ui'), 'test', '--', 'state-shades']);
      if (stale.code === 0 || !stale.tail.includes('Stale browser-resolved state surfaces'))
        throw new Error(`${plant.name}: expected a named stale-receipt failure`);
      const regenerated = await run(`${plant.name}-regenerate`, ['npm', '--prefix', resolve(copy, 'ui'), 'run', 'resolve-state-surfaces'],
        { STATE_SURFACES_SCRATCH: resolve(scratch, `${plant.name}-capture`) });
      // Named measurement failure is a valid plant rejection, never a successful regeneration.
      if (regenerated.code !== 0 && !regenerated.tail.includes('Measurement failure') && !regenerated.tail.includes('Unemulatable'))
        throw new Error(`${plant.name}: regeneration failed for an unrelated reason`);
      if (regenerated.code === 0) {
        const fresh = await run(`${plant.name}-fresh`, ['npm', '--prefix', resolve(copy, 'ui'), 'test', '--', 'state-shades']);
        if (fresh.code === 0) throw new Error(`${plant.name}: regenerated plant unexpectedly accepted`);
      }
    } finally {
      writeFileSync(target, original);
      writeFileSync(resolve(copy, 'ui/client/src/state-surfaces.resolved.json'), originalReceipt);
    }
  }
} finally {
  writeFileSync(resolve(scratch, 'plants-proof.json'), JSON.stringify(report, null, 2) + '\n');
  rmSync(copy, { recursive: true, force: true });
}
