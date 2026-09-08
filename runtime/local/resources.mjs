import {readFileSync} from 'node:fs';
export function readBundledCutAgentCliCommandCatalog(fallback = '') {
  try { return readFileSync(new URL('../../native/cutagent_cli/command_catalog_snapshot.json', import.meta.url), 'utf8'); }
  catch { return fallback; }
}
export function readBundledText(_name, fallback = '') { return fallback; }
