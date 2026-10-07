/** Write the evidence index last, then re-read every indexed artifact. */
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { relative, resolve } from 'node:path';

const root = resolve(import.meta.dirname, '../../../../../..');
const final = resolve(import.meta.dirname, '..');
const index = resolve(final, 'artifact-hashes.json');
// The check's output is produced after indexing; it cannot index itself.
const checkLog = resolve(import.meta.dirname, 'artifact-index-check.log');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
if (process.argv.includes('--write')) {
  const paths = new Set(JSON.parse(readFileSync(index, 'utf8')).map(entry => entry.path));
  function inventory(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = resolve(dir, entry.name);
      if (entry.isDirectory()) inventory(path);
      else if (path !== index && path !== checkLog) paths.add(relative(root, path));
    }
  }
  inventory(final);
  paths.delete(relative(root, checkLog));
  const entries = [...paths].sort().map(path => {
    const bytes = readFileSync(resolve(root, path));
    return { path, sha256: digest(bytes), bytes: bytes.length };
  });
  writeFileSync(index, JSON.stringify(entries, null, 2) + '\n');
}
const entries = JSON.parse(readFileSync(index, 'utf8'));
for (const entry of entries) {
  const bytes = readFileSync(resolve(root, entry.path));
  if (digest(bytes) !== entry.sha256 || bytes.length !== entry.bytes)
    throw new Error(`Artifact index mismatch: ${entry.path}`);
}
console.log(`Artifact index self-check: ${entries.length} indexed files re-read; 0 mismatches; PASS`);

// Codex, GPT-6.
