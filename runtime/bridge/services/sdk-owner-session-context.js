import { AsyncLocalStorage } from "node:async_hooks";

const ownerSessionStorage = new AsyncLocalStorage();

export function runWithSdkOwnerSession(session, operation) {
  if (!session?.id || typeof operation !== "function") {
    throw new TypeError("SDK owner-session context requires a product session and operation.");
  }
  return ownerSessionStorage.run(session, operation);
}

export function getSdkOwnerSession() {
  return ownerSessionStorage.getStore() ?? null;
}
