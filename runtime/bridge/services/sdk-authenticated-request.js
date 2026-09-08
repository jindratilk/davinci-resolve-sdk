export async function captureAuthenticatedSdkRequest(authority) {
  if (typeof authority?.capture !== "function") throw Object.assign(new Error("Local principal authority is unavailable."), {code:"AUTHENTICATION_REQUIRED"});
  return authority.capture();
}
export function assertAuthenticatedSdkRequestCurrent(authority, authenticated) {
  authority.assertCurrent(authenticated);
}
