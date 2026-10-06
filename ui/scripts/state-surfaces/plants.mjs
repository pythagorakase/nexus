/** Default-only adversarial protocol; all mutations stay in the scratch copy. */
import { spawn, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
const root = resolve(import.meta.dirname, '../../..'), ui = resolve(root, 'ui');
const scratch = process.env.STATE_SURFACES_SCRATCH;
if (!scratch || !resolve(scratch).startsWith(resolve(root, 'scratchpad/777-S2') + '/'))
  throw new Error('STATE_SURFACES_SCRATCH must be beneath the order scratch directory');
const copy = resolve(scratch, 'plant-copy'), copiedUi = resolve(copy, 'ui');
const layout = 'ui/client/src/components/nexus/nexus-layout.css';
const theme = 'ui/client/src/contexts/ThemeContext.tsx';
const plants = [
  { name: 'opaque-gradient-stop', path: layout, replace: ['radial-gradient(1200px 600px at 50% -10%, hsl(320 55% 40% / .07), transparent 60%)', 'radial-gradient(1200px 600px at 50% -10%, hsl(320 55% 40% / .07), #ffffff 60%)'] },
  { name: 'theme-provider-opacity', path: theme, replace: ['{children}', '<div style={{opacity: 0.35}}>{children}</div>'] },
  { name: 'media-root-override', path: layout, append: '\n@media (prefers-color-scheme: dark) { html.dark.theme-vector { --state-key-verified: var(--state-key-present); } }\n' },
  { name: 'optional-row-opacity', path: layout, append: '\n.key-row.optional { opacity: .15; }\n' },
  { name: 'theme-backdrop', path: layout, append: '\n.dark.theme-vector .key-row { background: #ffffff; }\n' },
  { name: 'important-state-surface', path: layout, append: '\n.lm-trash.armed { color: var(--state-delete-unarmed) !important; }\n' },
  { name: 'has-state-surface', path: layout, append: '\n.key-row:has(.key-status.verified) .key-status { color: var(--state-key-present); }\n' },
  { name: 'map-blend', path: layout, append: '\n.map-pin { mix-blend-mode: difference; }\n' },
  { name: 'key-overpainting-shadow', path: layout, append: '\n.key-status svg { background: var(--state-key-present); box-shadow: inset 0 0 0 12px var(--state-key-present); }\n' },  { name: 'gradient-state-surface', path: layout, append: '\n.topbar .mem-fill.over { background-color: transparent; background-image: linear-gradient(var(--state-mem-over), var(--state-mem-over)); }\n' },
  { name: 'element-state-redeclaration', path: layout, append: '\n.dark:not(.theme-gilded):not(.theme-vector) .lm-trash.armed { --state-delete-armed: inherit; }\n' },
];
const arg = name => { const i = process.argv.indexOf(name); return i < 0 ? undefined : process.argv[i + 1]; };
const stage = arg('--stage'), plant = plants.find(p => p.name === arg('--plant'));
if (!stage || (stage !== 'control' && !plant)) throw new Error('Specify --stage control, or --plant NAME --stage stale|capture|fresh|restore');
mkdirSync(scratch, { recursive: true });
const ledger = resolve(scratch, 'plants-proof.json'), snapshotPath = resolve(scratch, 'before-plants.json');
const report = stage === 'control' ? [] : JSON.parse(readFileSync(ledger, 'utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const git = args => execFileSync('git', args, { cwd: root, maxBuffer: 10 * 1024 * 1024 });
const headHash = path => {
  const bytes = git(['show', `HEAD:${path}`]), pointer = bytes.toString().match(/^oid sha256:([a-f0-9]{64})$/m);
  return pointer && bytes.toString().startsWith('version https://git-lfs.github.com/spec/v1') ? pointer[1] : hash(bytes);
};
const paths = [...new Set([...plants.map(p => p.path), 'ui/client/src/state-surfaces.resolved.json'])];
let snapshot, copyReady = false;
function restorationProof() {
  const files = paths.map(path => ({ path, before: snapshot.files[path],
    worktree: hash(readFileSync(resolve(root, path))), head: headHash(path),
    scratch: hash(readFileSync(resolve(copy, path))) }));
  const passed = files.every(f => f.before === f.worktree && f.before === f.head && f.before === f.scratch);
  if (!passed) throw new Error(`Restoration mismatch: ${JSON.stringify(files)}`);
  return { passed, files, prePlantCommit: snapshot.head };
}
function restoreScratch() {
  for (const [i, path] of paths.entries()) writeFileSync(resolve(copy, path), readFileSync(resolve(scratch, 'originals', String(i))));
}
async function run(name, args, env = {}) {
  const started = performance.now(), child = spawn(args[0], args.slice(1), { cwd: root, detached: true,
    env: { ...process.env, GIT_DIR: git(['rev-parse', '--absolute-git-dir']).toString().trim(), ...env } });
  let output = '';
  for (const stream of [child.stdout, child.stderr]) stream.on('data', b => { output += b; });
  const timer = setTimeout(() => process.kill(-child.pid, 'SIGTERM'), 589000);
  const progress = setInterval(() => console.log(`${name}: still running\n${output.slice(-400)}`), 45000);
  const code = await new Promise(r => child.on('exit', r)); clearTimeout(timer); clearInterval(progress);
  const tail = output.split('\n').slice(-40).join('\n');
  writeFileSync(resolve(scratch, `${name}.log`), output);
  const result = { name, args, code, wallSeconds: (performance.now() - started) / 1000, tail };
  report.push(result); console.log(`${name}: exit ${code}\n${tail}`); return result;
}
const receiptPath = resolve(copiedUi, 'client/src/state-surfaces.resolved.json');
const shipping = JSON.parse(readFileSync(resolve(ui, 'client/src/state-surfaces.resolved.json'), 'utf8'));
const defaultId = shipping.media.variants.find(v => v.viewport.width === 1200 && v.viewport.height === 900 && v.reducedMotion === 'reduce' && v.colorScheme === 'dark').id;
function diagnostic(path, sourceId) {
  const src = resolve(copiedUi, 'client/src');
  let test = readFileSync(resolve(src, 'state-shades.test.ts'), 'utf8')
    .replaceAll('import.meta.dirname', JSON.stringify(src))
    .replaceAll('from "../../scripts/state-surfaces/', 'from "../scripts/state-surfaces/')
    .replace('"./state-shades-measurement"', '"./src/state-shades-measurement"');
  test = test.replace('const receiptPath = resolve(' + JSON.stringify(src) + ', "state-surfaces.resolved.json");', `const receiptPath = ${JSON.stringify(path)};`);
  const guard = 'if (receipt.proof.acceptanceComplete !== true)\n  throw new Error("Incomplete painted state surfaces: filtered/probe captures are not acceptance receipts.");';
  if (!test.includes(guard)) throw new Error('Default diagnostic: acceptance guard changed');
  // Preserve acceptanceComplete=false. Normalize only the default comparison ID:
  // a media plant may add a feature to the ID while retaining 1200×900/dark/reduce.
  test = test.replace(guard, `receipt.conditions = { [${JSON.stringify(defaultId)}]: receipt.conditions[${JSON.stringify(sourceId)}] };\nreceipt.media.variants = [{id: ${JSON.stringify(defaultId)}}];`);
  test = test.replace('toEqual(evidence.measurements)', `toEqual(evidence.measurements.filter((m: {condition: string}) => m.condition === ${JSON.stringify(defaultId)}))`)
    .replace('toEqual(evidence.before)', `toEqual(evidence.before.filter((m: {condition: string}) => m.condition === ${JSON.stringify(defaultId)}))`);
  writeFileSync(resolve(copiedUi, 'client/plant-default-r5.test.ts'), test);
}
const diagnosticTests = 'browser_measurements_match_recorded_tables|same_value_has_exactly_the_same_settled_mask_mean|painted_mask_means_are_linear_and_interactions_are_real_and_settled|global_tokens_are_unchanged|state_surfaces_read_only_state_tokens';
try {
  if (stage === 'control') {
    mkdirSync(resolve(scratch, 'originals'), { recursive: true });
    snapshot = { head: git(['rev-parse', 'HEAD']).toString().trim(), files: {} };
    for (const [i, path] of paths.entries()) {
      const bytes = readFileSync(resolve(root, path)); snapshot.files[path] = hash(bytes);
      if (snapshot.files[path] !== headHash(path)) throw new Error(`Commit before planting: ${path} differs from HEAD`);
      writeFileSync(resolve(scratch, 'originals', String(i)), bytes);
    }
    writeFileSync(snapshotPath, JSON.stringify(snapshot, null, 2) + '\n');
    cpSync(ui, copiedUi, { recursive: true, verbatimSymlinks: true, filter: p => p !== resolve(ui, 'dist') && !p.startsWith(resolve(ui, 'dist') + '/') });
    cpSync(resolve(root, 'docs/qa/777-glyph-first-states'), resolve(copy, 'docs/qa/777-glyph-first-states'), { recursive: true });
    copyReady = true;
    const control = await run('control', ['npm', '--prefix', copiedUi, 'test', '--', 'state-shades']);
    if (control.code !== 0) throw new Error('Unplanted control must pass before any plant is evidence');
    report.push({ name: 'pre-plant-restore-proof', ...restorationProof() });
  } else {
    snapshot = JSON.parse(readFileSync(snapshotPath, 'utf8')); copyReady = true;
    if (!report.some(r => r.name === 'control' && r.code === 0)) throw new Error('Missing passing unplanted control');
    // Read both live trees and HEAD BEFORE any restoration write.
    const proof = restorationProof();
    if (stage === 'restore') report.push({ name: `${plant.name}-restored`, ...proof });
    else {
      const original = readFileSync(resolve(scratch, 'originals', String(paths.indexOf(plant.path))), 'utf8');
      if (plant.replace && !original.includes(plant.replace[0])) throw new Error(`Missing exact source for ${plant.name}`);
      writeFileSync(resolve(copy, plant.path), plant.replace ? original.replace(...plant.replace) : original + plant.append);
      if (stage === 'stale') {
        const stale = await run(`${plant.name}-stale`, ['npm', '--prefix', copiedUi, 'test', '--', 'state-shades']);
        if (stale.code === 0 || !stale.tail.includes('Stale browser-resolved state surfaces')) throw new Error('Expected named stale rejection');
      } else if (stage === 'capture') {
        const capture = resolve(scratch, `${plant.name}-capture`); mkdirSync(capture, { recursive: true });
        const regenerated = await run(`${plant.name}-regenerate-default`, ['npm', '--prefix', copiedUi, 'run', 'resolve-state-surfaces'],
          { STATE_SURFACES_SCRATCH: capture, STATE_SURFACES_CONDITION: 'default', STATE_SURFACES_OUTPUT: resolve(capture, 'default.json') });
        if (regenerated.code !== 0 && !/Measurement failure|Calibration (?:non-vacuity )?failure|Unemulatable/.test(regenerated.tail)) throw new Error('Unrelated regeneration failure');
        if (plant.name === 'gradient-state-surface' && regenerated.code !== 0) throw new Error('Gradient must be measured successfully');
      } else if (stage === 'fresh') {
        const capture = report.findLast(r => r.name === `${plant.name}-regenerate-default`);
        if (!capture) throw new Error('Missing default regeneration');
        if (capture.code !== 0) report.push({ name: `${plant.name}-measurement-rejected`, reason: capture.tail });
        else {
          const path = resolve(scratch, `${plant.name}-capture/default.json`), partial = JSON.parse(readFileSync(path, 'utf8'));
          const [sourceId] = Object.keys(partial.conditions), condition = partial.media.variants.find(v => v.id === sourceId);
          if (partial.proof.acceptanceComplete !== false || Object.keys(partial.conditions).length !== 1 || condition.viewport.width !== 1200 || condition.viewport.height !== 900 || condition.reducedMotion !== 'reduce' || condition.colorScheme !== 'dark') throw new Error('Diagnostic scope escaped default');
          diagnostic(path, sourceId);
          const fresh = await run(`${plant.name}-fresh-default`, ['npm', '--prefix', copiedUi, 'test', '--', 'plant-default-r5', '-t', diagnosticTests]);
          if (fresh.code === 0) throw new Error('Regenerated default plant unexpectedly accepted');
          report.push({ name: `${plant.name}-scope`, sourceId, comparisonId: defaultId, acceptanceComplete: false, renderCount: partial.proof.renderCount, mutatedPath: plant.path, mutation: plant.replace ?? plant.append });
        }
      } else throw new Error(`Unknown stage ${stage}`);
    }
  }
} finally {
  if (copyReady) restoreScratch();
  writeFileSync(ledger, JSON.stringify(report, null, 2) + '\n');
}

// Codex, GPT-6.
