import crypto from "node:crypto";
import { canonicalPreparedActionBytes, preparedActionDigest } from "../sdk-prepared-action-digest.js";

function b64(value) { return Buffer.from(value).toString("base64url"); }

export function createPreparedActionPolicyAttestor({ now = () => Date.now() } = {}) {
  const { privateKey, publicKey } = crypto.generateKeyPairSync("ed25519");
  const publicJwk = publicKey.export({ format: "jwk" });
  const kid = `policy-${preparedActionDigest("policy-decision", publicJwk).slice(7, 23)}`;

  function issue(claims) {
    const nowSeconds = Math.floor(now() / 1000);
    const header = b64(canonicalPreparedActionBytes({ alg: "EdDSA", kid, typ: "JWT" }));
    const payload = b64(canonicalPreparedActionBytes({
      ...claims,
      iss: "cutagent-mutation-policy",
      aud: "cutagent-cli",
      token_type: "cutagent_sdk_policy_attestation",
      capability: "cutagent-sdk.mutation-policy",
      iat: nowSeconds,
      exp: nowSeconds + 30,
      jti: crypto.randomUUID(),
    }));
    const signingInput = `${header}.${payload}`;
    const signature = crypto.sign(null, Buffer.from(signingInput, "ascii"), privateKey);
    return `${signingInput}.${b64(signature)}`;
  }

  return Object.freeze({ issue, publicJwk: Object.freeze({ ...publicJwk, kid }) });
}
