import {readFile, readdir, lstat} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {resolve, relative, join} from 'node:path';
const root = resolve(import.meta.dirname, '..');
const sdkInventory = JSON.parse(await readFile(join(root, 'EXTRACTION_INVENTORY.json'), 'utf8'));
const nativeInventory = JSON.parse(await readFile(join(root, 'native/SOURCE_INVENTORY.json'), 'utf8'));
const inventory = {files:[...sdkInventory.files,...nativeInventory.files]};
const allowed = new Set();
for (const entry of inventory.files) {
  const path = resolve(root, entry.destination);
  if (!relative(root, path) || relative(root, path).startsWith('..') || allowed.has(entry.destination)) throw new Error('Unsafe or duplicate source inventory path');
  allowed.add(entry.destination);
  if (!(await lstat(path)).isFile() || (await lstat(path)).isSymbolicLink()) throw new Error(`Source is not a regular file: ${entry.destination}`);
  const bytes = await readFile(path);
  if (createHash('sha256').update(bytes).digest('hex') !== entry.sha256) throw new Error(`Extracted source drift: ${entry.destination}`);
  // Source code legitimately contains defensive rejection expressions. Check
  // actual credential material and explicit forbidden source families instead.
  if (/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/.test(bytes.toString())) throw new Error(`Private key in ${entry.destination}`);
  if (/^(?:cloud|frontend|landing|cutagent-cli-agent-reference|cutagent-cli-command-metadata)\//.test(entry.source)) throw new Error(`Unselected product source: ${entry.source}`);
}
async function walk(directory) {
  for (const entry of await readdir(join(root, directory), {withFileTypes: true})) {
    const path = `${directory}/${entry.name}`;
    if (entry.isDirectory()) await walk(path);
    else if (!allowed.has(path)) throw new Error(`Unexpected extracted source: ${path}`);
  }
}
await walk('sdk/src'); await walk('runtime/bridge');
console.log(`Verified ${inventory.files.length} extracted source hashes and exact SDK/runtime source inventories.`);
