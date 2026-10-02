/** Install a packed adapter over its locked dependency graph, refusing graph drift. */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const [manifestInput, lockInput, tarballInput, destinationInput] = process.argv.slice(2);
if (!destinationInput) throw new Error('Expected manifest, lockfile, tarball and destination');
const [manifestPath, lockPath, tarball, destination] = [manifestInput, lockInput, tarballInput, destinationInput].map((path) => resolve(path));
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
const adapterPath = `node_modules/${manifest.name}`;
mkdirSync(destination, { recursive: true });
copyFileSync(manifestPath, join(destination, 'package.json'));
copyFileSync(lockPath, join(destination, 'package-lock.json'));
execFileSync('npm', ['ci', '--ignore-scripts', '--no-audit', '--no-fund'], { cwd: destination, stdio: 'inherit' });

// npm's installed-package lock describes platform-selected optional dependencies too.
function installedGraph() {
  const hiddenLock = join(destination, 'node_modules', '.package-lock.json');
  const packages = existsSync(hiddenLock) ? JSON.parse(readFileSync(hiddenLock, 'utf8')).packages : {};
  return Object.fromEntries(Object.entries(packages).map(([name, entry]) => [name, {
    version: entry.version, resolved: entry.resolved, integrity: entry.integrity, link: entry.link,
  }]));
}
const before = installedGraph();
// A consumer must resolve the tarball, not the copied manifest's package self-reference.
for (const key of ['name', 'exports', 'files', 'scripts', 'bin', 'main']) delete manifest[key];
writeFileSync(join(destination, 'package.json'), JSON.stringify(manifest, null, 2) + '\n');
// Preparation may fetch registry metadata; the installed-graph check below refuses drift.
execFileSync('npm', ['install', '--ignore-scripts', '--no-save', '--package-lock=true',
  '--no-audit', '--no-fund', tarball], { cwd: destination, stdio: 'inherit' });
const after = installedGraph();
for (const name of new Set([...Object.keys(before), ...Object.keys(after)])) {
  if (name !== adapterPath && JSON.stringify(before[name]) !== JSON.stringify(after[name])) {
    throw new Error(`Packed installation changed the locked dependency: ${name}`);
  }
}
if (!after[adapterPath]) throw new Error('The packed adapter was not installed');
const sha256 = (path) => createHash('sha256').update(readFileSync(path)).digest('hex');
writeFileSync(join(destination, 'locked-node-install.json'), JSON.stringify({
  lock_sha256: sha256(lockPath), tarball_sha256: sha256(tarball), adapter_path: adapterPath,
  locked_dependencies: before, installed_packages: after,
}, null, 2) + '\n');
