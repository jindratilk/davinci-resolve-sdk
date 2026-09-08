/** Native implementation ownership is supplied by the standalone composition. */
export class CutAgentCliIdentityError extends Error {
  constructor(message = 'The standalone native host has not been configured.') {
    super(message); this.code = 'CUTAGENT_CLI_UNAVAILABLE';
  }
}
export function probeCutAgentCliIdentity() { throw new CutAgentCliIdentityError(); }
export function isCutAgentCliIdentityCurrent() { return false; }
