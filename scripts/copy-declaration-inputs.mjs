import {readdir, cp, mkdir} from 'node:fs/promises';
import {resolve, join} from 'node:path';
const sdk = resolve(import.meta.dirname, '../sdk');
async function copy(directory = '') {
  for (const entry of await readdir(join(sdk, 'src', directory), {withFileTypes:true})) {
    const relative = join(directory, entry.name);
    if (entry.isDirectory()) await copy(relative);
    else if (entry.name.endsWith('.d.ts')) {
      await mkdir(join(sdk, '.types', directory), {recursive:true});
      await cp(join(sdk, 'src', relative), join(sdk, '.types', relative));
    }
  }
}
await copy();
