import {createHash} from 'node:crypto';
import {resolve, join} from 'node:path';
export {CutAgentCliIdentityError, probeCutAgentCliIdentity, isCutAgentCliIdentityCurrent} from './native-identity.mjs';
const root = resolve(import.meta.dirname, '../..');
let transport = null;
export function configureLocalCliRuntime(options) {
  if (!['studio_external', 'embedded_free'].includes(options.transport)) throw new TypeError('An exact local native transport is required.');
  transport = options.transport;
}
export function resolveCutAgentCliCommand() { return join(root, 'native/cutagent'); }
export function buildCutAgentCliEnv({args, sessionEnv = {}, extraEnv = {}} = {}) {
  if (!transport) throw new Error('The standalone native runtime transport is not configured.');
  const keys = ['PATH','HOME','USERPROFILE','APPDATA','LOCALAPPDATA','SYSTEMROOT','WINDIR','TMPDIR','TEMP','LANG','RESOLVE_SCRIPT_API','RESOLVE_SCRIPT_LIB','DYLD_LIBRARY_PATH','DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_PATH','DAVINCI_RESOLVE_SDK_EMBEDDED_PORT'];
  const env = Object.fromEntries(keys.filter(key => process.env[key] !== undefined).map(key => [key, process.env[key]]));
  for (const [key,value] of Object.entries({...sessionEnv, ...extraEnv})) {
    if (/^CUTAGENT_.*AUTH/.test(key) || key === 'CUTAGENT_MUTATION_POLICY_SCOPE_VALID') continue;
    env[key] = value;
  }
  env.PATH = `${join(root, '.venv/bin')}:${env.PATH ?? ''}`;
  env.PYTHONPATH = join(root, 'native');
  env.CUTAGENT_RESOLVE_TRANSPORT = transport;
  if (Array.isArray(args)) {
    const digest = createHash('sha256').update(JSON.stringify(args)).digest('hex');
    env.DAVINCI_RESOLVE_SDK_COMMAND_SHA256 = digest;
    env.DAVINCI_RESOLVE_SDK_PARENT_PID = String(process.pid);
    if (extraEnv.CUTAGENT_MUTATION_POLICY_ARGS_SHA256 === digest) env.CUTAGENT_MUTATION_POLICY_SCOPE_VALID = '1';
  }
  return env;
}
