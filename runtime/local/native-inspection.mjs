import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {SdkLiveInspectionError} from '../bridge/services/sdk-live-inspection-service.js';
const nativeRoot = resolve(import.meta.dirname, '../../native');
const maximumBytes = 16 * 1024 * 1024;

export function createNativeInspectionOwner({python = 'python3', transport} = {}) {
  if (!['studio_external', 'embedded_free'].includes(transport)) throw new TypeError('Select the exact native transport.');
  function identity() {
    const inventory = JSON.parse(readFileSync(join(nativeRoot, 'SOURCE_INVENTORY.json'), 'utf8'));
    const hash = createHash('sha256');
    for (const relative of ['sdk_inspection_host.py', 'cutagent', 'framed_prepared_host', 'cutagent_cli/local_prepared_authority.py', 'cutagent_cli/authz.py', 'cutagent_cli/local_admission.py', ...inventory.files.map(x => x.destination.replace(/^native\//, ''))].sort()) {
      hash.update(relative).update('\0').update(readFileSync(join(nativeRoot, relative)));
    }
    return {version:'3.0.0', executableDigest:hash.digest('hex')};
  }
  return Object.freeze({
    nativeIdentityProbe: identity,
    nativeIdentityCurrent: observed => observed?.executableDigest === identity().executableDigest,
    resolveService: Object.freeze({
      async readSdkLiveInspection(operation, {deadlineAtMs, signal, readRequest = {}} = {}) {
        if (!['project.current', 'mediaPool.page'].includes(operation)) {
          throw new SdkLiveInspectionError('CAPABILITY_UNAVAILABLE', 'This native SDK owner has not been composed yet.');
        }
        const remaining = deadlineAtMs - Date.now();
        if (!Number.isSafeInteger(deadlineAtMs) || remaining <= 0 || remaining > 180_000) throw new DOMException('SDK inspection deadline expired.', 'TimeoutError');
        if (signal?.aborted) throw signal.reason;
        const env = Object.fromEntries(['PATH','HOME','USERPROFILE','APPDATA','LOCALAPPDATA','SYSTEMROOT','WINDIR','TMPDIR','TEMP','LANG','RESOLVE_SCRIPT_API','RESOLVE_SCRIPT_LIB','DYLD_LIBRARY_PATH','CUTAGENT_RESOLVE_UUID','CUTAGENT_RESOLVE_HOST','CUTAGENT_RESOLVE_PID','DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_PATH','DAVINCI_RESOLVE_SDK_EMBEDDED_PORT'].filter(key => process.env[key] !== undefined).map(key => [key,process.env[key]]));
        env.PYTHONPATH = nativeRoot;
        env.CUTAGENT_RESOLVE_TRANSPORT = transport;
        const input = {operation, deadlineAtMs, ...(operation === 'mediaPool.page' ? {offset:readRequest.offset ?? 0, pageSize:readRequest.pageSize ?? 100, search:readRequest.search ?? null} : {})};
        return await new Promise((resolveResult, reject) => {
          const child = spawn(python, [join(nativeRoot, 'sdk_inspection_host.py')], {env, stdio:['pipe','pipe','pipe'], windowsHide:true});
          const chunks = []; let bytes = 0; let failure = null;
          const terminate = error => { failure ??= error; child.kill('SIGKILL'); };
          const abort = () => terminate(signal.reason ?? new DOMException('SDK inspection cancelled.', 'AbortError'));
          const timer = setTimeout(() => terminate(new DOMException('SDK native inspection timed out.', 'TimeoutError')), remaining);
          signal?.addEventListener('abort', abort, {once:true});
          child.stdout.on('data', data => { bytes += data.length; if (bytes > maximumBytes) terminate(new Error('Native inspection response exceeded its byte limit.')); else chunks.push(data); });
          child.stderr.resume();
          child.stdin.on('error', error => terminate(error));
          child.on('error', error => { failure ??= error; });
          child.on('close', code => {
            clearTimeout(timer); signal?.removeEventListener('abort', abort);
            if (failure) return reject(failure);
            if (code !== 0) return reject(new SdkLiveInspectionError('RUNTIME_UNAVAILABLE','The native SDK inspection host could not start.'));
            try {
              const payload = JSON.parse(Buffer.concat(chunks).toString('utf8'));
              if (payload?.ok !== true) throw new SdkLiveInspectionError('RUNTIME_UNAVAILABLE','DaVinci Resolve native inspection is unavailable.');
              resolveResult(payload.data);
            } catch (error) { reject(error); }
          });
          child.stdin.end(JSON.stringify(input)+'\n');
          if (signal?.aborted) abort();
        });
      },
    }),
  });
}
