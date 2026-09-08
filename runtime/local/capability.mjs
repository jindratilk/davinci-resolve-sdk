import {randomBytes, timingSafeEqual} from 'node:crypto';
const issued = new Set();
export function createLocalCapability() {
  const token = `cutagent-cap.v1.${randomBytes(24).toString('base64url')}.${randomBytes(32).toString('base64url')}`;
  issued.add(token);
  return Object.freeze({token, revoke() { issued.delete(token); }});
}
export function requireLocalCapability(req, res, next) {
  const received = req.headers['x-cutagent-bridge-capability'];
  const valid = req.method === 'POST' && req.path === '/internal/sdk/v1/connect'
    && typeof received === 'string' && received === req.app.locals.localCapability && [...issued].some(token => {
      const a = Buffer.from(token); const b = Buffer.from(received);
      return a.length === b.length && timingSafeEqual(a, b);
    });
  if (!valid) return res.status(401).json({ok: false, error: 'LOCAL_ACCESS_REQUIRED'});
  next();
}
