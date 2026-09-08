import {createHash, randomBytes} from 'node:crypto';

/** Local process ownership, never a synthetic commercial account or subscription. */
export function createLocalPrincipalAuthority({installationAuthority} = {}) {
  const owner = process.getuid?.() ?? null;
  if (installationAuthority !== undefined && !/^sdk_installation_[A-Za-z0-9._~-]+$/.test(installationAuthority)) {
    throw new TypeError('Invalid local installation authority.');
  }
  const instance = installationAuthority ?? randomBytes(32).toString('hex');
  let generation = 0;
  let closed = false;
  const issued = new WeakSet();
  const fingerprint = () => createHash('sha256').update(`local:${owner}:${instance}`).digest('hex');
  function fail() { throw Object.assign(new Error('The local SDK principal is no longer current.'), {code: 'AUTH_SESSION_CHANGED'}); }
  return Object.freeze({
    capture() {
      if (closed || (process.getuid?.() ?? null) !== owner) fail();
      // accountFingerprint is the inherited private routing slot. Its value is
      // exclusively local ownership; no account object or credential is created.
      const value = Object.freeze({identity: Object.freeze({generation}), accountFingerprint: fingerprint()});
      issued.add(value);
      return value;
    },
    assertCurrent(value) {
      if (closed || !issued.has(value) || value.identity.generation !== generation
          || value.accountFingerprint !== fingerprint() || (process.getuid?.() ?? null) !== owner) fail();
    },
    rotate() { if (closed) fail(); generation += 1; },
    close() { closed = true; generation += 1; },
  });
}
