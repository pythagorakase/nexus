import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

export const conditions = {
  viewport: { width: 1200, height: 900 },
  colorScheme: 'dark', reducedMotion: 'reduce', origin: 'file://', network: 'aborted',
};
export const sourcePaths = [
  'client/src/index.css', 'client/src/components/nexus/nexus-layout.css',
  ...['TopBar', 'LocalModelRows', 'MapPane', 'SettingsPane'].map(n => `client/src/components/nexus/${n}.tsx`),
  'scripts/state-surfaces/fixture.tsx', 'scripts/state-surfaces/styles.css',
  'scripts/state-surfaces/inputs.mjs', 'scripts/resolve-state-surfaces.mjs',
  'package.json', 'package-lock.json', 'postcss.config.js', 'tailwind.config.ts',
];
/** Hash path-delimited bytes, so changing any measurement input invalidates the receipt. */
export function inputs(uiRoot) {
  const hash = createHash('sha256');
  const files = {};
  for (const path of sourcePaths) {
    const bytes = readFileSync(resolve(uiRoot, path));
    files[path] = createHash('sha256').update(bytes).digest('hex');
    hash.update(path).update('\0').update(bytes).update('\0');
  }
  const chromium = JSON.parse(readFileSync(resolve(uiRoot, 'node_modules/playwright-core/browsers.json'), 'utf8')).browsers.find(b => b.name === 'chromium');
  hash.update(JSON.stringify({ conditions, chromium }));
  return { chromium: chromium.browserVersion, chromiumRevision: chromium.revision, sha256: hash.digest('hex'), files, conditions,
    playwright: JSON.parse(readFileSync(resolve(uiRoot, 'node_modules/playwright/package.json'), 'utf8')).version };
}
