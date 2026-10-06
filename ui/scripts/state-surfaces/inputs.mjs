import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';

export const conditions = {
  viewport: { width: 1200, height: 900 }, deviceScaleFactor: 4,
  colorScheme: 'dark', reducedMotion: 'reduce', forcedColors: 'none',
  hasTouch: false, isMobile: false, origin: 'file://', network: 'aborted',
};
/** Bundle the fixture itself; the metafile is the source of rendering inputs. */
export async function fixtureBuild(uiRoot) {
  const require = createRequire(resolve(uiRoot, 'package.json'));
  const { build } = createRequire(require.resolve('vite'))('esbuild');
  return build({ absWorkingDir: uiRoot, entryPoints: ['scripts/state-surfaces/fixture.tsx'],
    bundle: true, write: false, metafile: true, platform: 'browser', format: 'iife', jsx: 'automatic',
    alias: { '@': resolve(uiRoot, 'client/src'), '@shared': resolve(uiRoot, 'shared') },
    loader: { '.css': 'empty' },
  });
}
/** Path-delimited hashes of all transitive modules, styles/imports and tooling. */
export async function inputs(uiRoot, bundle = undefined) {
  bundle ??= await fixtureBuild(uiRoot);
  const paths = new Set(Object.keys(bundle.metafile.inputs));
  const styles = path => {
    if (paths.has(path) && path.endsWith('.css')) return;
    paths.add(path);
    for (const match of readFileSync(resolve(uiRoot, path), 'utf8').matchAll(/@import\s+['"]([^'"]+)['"]/g))
      styles(relative(uiRoot, resolve(uiRoot, dirname(path), match[1])));
  };
  // Empty CSS loaders do not enumerate imports, so recurse separately.
  paths.delete('client/src/index.css'); paths.delete('client/src/components/nexus/nexus-layout.css');
  styles('client/src/index.css'); styles('client/src/components/nexus/nexus-layout.css');
  for (const name of readdirSync(resolve(uiRoot, 'scripts/state-surfaces')))
    if (/\.(?:mjs|tsx|css)$/.test(name)) paths.add(`scripts/state-surfaces/${name}`);
  for (const path of ['scripts/resolve-state-surfaces.mjs', 'package.json', 'package-lock.json',
    'tailwind.config.ts', 'postcss.config.js', 'vite.config.ts', 'client/index.html', 'client/src/main.tsx']) paths.add(path);
  // Tailwind's content scan affects shipped CSS even for modules outside the fixture graph.
  const content = dir => { for (const entry of readdirSync(resolve(uiRoot, dir), { withFileTypes: true })) {
    const path = `${dir}/${entry.name}`;
    if (entry.isDirectory()) content(path);
    else if (/\.(?:[jt]sx?|css)$/.test(path)) paths.add(path);
  } };
  content('client/src');
  const assets = dir => { for (const entry of readdirSync(resolve(uiRoot, dir), { withFileTypes: true })) {
    const path = `${dir}/${entry.name}`;
    if (entry.isDirectory()) assets(path); else paths.add(path);
  } };
  assets('client/public/fonts');
  const hash = createHash('sha256'), files = {};
  for (const path of [...paths].sort()) {
    const bytes = readFileSync(resolve(uiRoot, path));
    files[path] = createHash('sha256').update(bytes).digest('hex');
    hash.update(path).update('\0').update(bytes).update('\0');
  }
  const chromium = JSON.parse(readFileSync(resolve(uiRoot, 'node_modules/playwright-core/browsers.json'), 'utf8')).browsers.find(b => b.name === 'chromium');
  const playwright = JSON.parse(readFileSync(resolve(uiRoot, 'node_modules/playwright/package.json'), 'utf8')).version;
  hash.update(JSON.stringify({ conditions, chromium, playwright }));
  return { chromium: chromium.browserVersion, chromiumRevision: chromium.revision,
    playwright, sha256: hash.digest('hex'), files, conditions,
    moduleGraph: Object.keys(bundle.metafile.inputs).sort() };
}

// Vitest's jsdom Uint8Array is a different realm. The fingerprint CLI bundles
// in a clean Node process, without a browser, polyfills or environment changes.
if (process.argv[1] && resolve(process.argv[1]) === new URL(import.meta.url).pathname)
  console.log(JSON.stringify(await inputs(resolve(process.argv[2]))));
